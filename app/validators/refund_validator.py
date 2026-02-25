from __future__ import annotations

"""
Business rule validation for refund requests.

All validations execute in order. Validators read from the repository
but never write to it — no side effects.
"""
from decimal import Decimal
from fastapi import HTTPException, status
from app.models.transaction import Transaction, TransactionStatus
from app.models.refund import RefundRequest
from app.repository.store import store


class ValidationError(Exception):
    """Raised when a business rule validation fails."""

    def __init__(self, code: str, message: str, details: dict | None = None, http_status: int = 422):
        self.code = code
        self.message = message
        self.details = details or {}
        self.http_status = http_status
        super().__init__(message)


def validate_refund_request(request: RefundRequest) -> Transaction:
    """
    Run all business rule validations in order.

    Args:
        request: The incoming refund request.

    Returns:
        The validated Transaction object.

    Raises:
        ValidationError: On the first failing rule, with code, message, and details.
    """
    transaction = _validate_transaction_exists(request.transaction_id)
    _validate_transaction_status(transaction)
    _validate_no_duplicate_full_refund(request, transaction)
    if request.item_ids is not None:
        _validate_item_ids(request.item_ids, transaction)
    _validate_refundable_balance(request, transaction)
    if request.item_ids is None:
        _validate_installment_constraints(transaction)
    return transaction


def _validate_transaction_exists(transaction_id: str) -> Transaction:
    """Rule 1: Transaction must exist."""
    transaction = store.get_transaction(transaction_id)
    if transaction is None:
        raise ValidationError(
            code="TRANSACTION_NOT_FOUND",
            message=f"Transaction {transaction_id} not found",
            http_status=404,
        )
    return transaction


def _validate_transaction_status(transaction: Transaction) -> None:
    """Rule 2: Transaction status must allow refunds (CAPTURED or SETTLED only)."""
    allowed = {TransactionStatus.CAPTURED, TransactionStatus.SETTLED}

    if transaction.status == TransactionStatus.CHARGEBACKED:
        raise ValidationError(
            code="INVALID_TRANSACTION_STATUS",
            message=(
                f"Transaction {transaction.id} cannot be refunded: status is CHARGEBACKED. "
                "Chargebacks are handled by the disputes process, not this service."
            ),
            details={"status": transaction.status.value},
        )

    if transaction.status == TransactionStatus.VOIDED:
        raise ValidationError(
            code="INVALID_TRANSACTION_STATUS",
            message=(
                f"Transaction {transaction.id} cannot be refunded: status is VOIDED. "
                "Use void/cancel operations for pre-capture reversals."
            ),
            details={"status": transaction.status.value},
        )

    if transaction.status == TransactionStatus.AUTHORIZED:
        raise ValidationError(
            code="INVALID_TRANSACTION_STATUS",
            message=(
                f"Transaction {transaction.id} is authorized but not yet captured. "
                "Use void/cancel instead."
            ),
            details={"status": transaction.status.value},
        )

    if transaction.status not in allowed:  # pragma: no cover — all enum values explicitly handled above
        raise ValidationError(
            code="INVALID_TRANSACTION_STATUS",
            message=f"Transaction {transaction.id} has status {transaction.status.value}, which does not allow refunds.",
            details={"status": transaction.status.value},
        )


def _validate_no_duplicate_full_refund(request: RefundRequest, transaction: Transaction) -> None:
    """Rule 3: A full refund cannot be issued twice (idempotency check)."""
    # Check idempotency key first
    if request.idempotency_key:
        existing_refund_id = store.get_idempotency_key(request.idempotency_key)
        if existing_refund_id:
            existing_refund = store.get_refund(existing_refund_id)
            if existing_refund:
                raise ValidationError(
                    code="DUPLICATE_REFUND",
                    message=f"A refund with this idempotency key already exists for transaction {transaction.id}",
                    details={
                        "existing_refund_id": existing_refund_id,
                        "refunded_at": existing_refund.created_at.isoformat(),
                    },
                    http_status=409,
                )

    # Check for existing full refund (no items specified = full refund attempt)
    if request.item_ids is None:
        existing_full_refund_id = store.has_full_refund(transaction.id)
        if existing_full_refund_id:
            existing_refund = store.get_refund(existing_full_refund_id)
            raise ValidationError(
                code="DUPLICATE_REFUND",
                message=f"A full refund already exists for transaction {transaction.id}",
                details={
                    "existing_refund_id": existing_full_refund_id,
                    "refunded_at": existing_refund.created_at.isoformat() if existing_refund else None,
                },
                http_status=409,
            )


def _validate_item_ids(item_ids: list[str], transaction: Transaction) -> None:
    """Rule 4: All requested item IDs must exist in the transaction."""
    transaction_item_ids = {item.id for item in transaction.items}
    unknown_ids = [iid for iid in item_ids if iid not in transaction_item_ids]
    if unknown_ids:
        raise ValidationError(
            code="INVALID_ITEM_IDS",
            message=f"The following item IDs were not found in transaction {transaction.id}: {unknown_ids}",
            details={
                "unknown_item_ids": unknown_ids,
                "valid_item_ids": list(transaction_item_ids),
            },
        )


def _validate_refundable_balance(request: RefundRequest, transaction: Transaction) -> None:
    """Rule 5: Refund must not exceed remaining refundable balance.

    For partial refunds, the estimated amount (items + proportional tax + shipping)
    is pre-calculated here to surface the error before reaching the engine.
    """
    already_refunded = store.get_total_refunded(transaction.id)
    remaining = transaction.total - already_refunded

    if remaining <= Decimal("0"):
        raise ValidationError(
            code="REFUND_AMOUNT_EXCEEDED",
            message=f"Transaction {transaction.id} has already been fully refunded",
            details={
                "transaction_total": str(transaction.total),
                "already_refunded": str(already_refunded),
                "remaining_refundable": "0.00",
            },
        )

    if request.item_ids and transaction.subtotal > Decimal("0"):
        requested_items = [item for item in transaction.items if item.id in request.item_ids]
        items_subtotal = sum(item.unit_price * item.quantity for item in requested_items)
        ratio = items_subtotal / transaction.subtotal
        estimated_refund = (items_subtotal + transaction.tax * ratio + transaction.shipping * ratio).quantize(Decimal("0.01"))
        if estimated_refund > remaining:
            raise ValidationError(
                code="REFUND_AMOUNT_EXCEEDED",
                message=(
                    f"Estimated refund of {estimated_refund} {transaction.currency} "
                    f"exceeds remaining refundable balance of {remaining} {transaction.currency}"
                ),
                details={
                    "estimated_refund": str(estimated_refund),
                    "remaining_refundable": str(remaining),
                    "transaction_total": str(transaction.total),
                    "already_refunded": str(already_refunded),
                },
            )


def _validate_installment_constraints(transaction: Transaction) -> None:
    """Rule 6: For installment transactions, only charged installments are refundable."""
    installment_payment = next(
        (p for p in transaction.payments if p.installments_total is not None),
        None,
    )
    if installment_payment is None:
        return  # Not an installment transaction

    charged = installment_payment.installments_charged or 0
    total = installment_payment.installments_total or 0

    if charged == 0:
        raise ValidationError(
            code="INSTALLMENT_NOT_CHARGED",
            message=(
                f"No installments have been charged yet for transaction {transaction.id}. "
                "Cannot refund uncharged installments."
            ),
            details={
                "installments_total": total,
                "installments_charged": charged,
            },
        )
