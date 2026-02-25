"""
Refund service — orchestrates validation, calculation, persistence, and audit.

Flow: validate → calculate → persist → audit
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from app.models.refund import RefundRequest, RefundResult
from app.models.transaction import Transaction, TransactionStatus
from app.validators.refund_validator import validate_refund_request, ValidationError
from app.engine.calculator import (
    calculate_full_refund,
    calculate_partial_refund,
    calculate_installment_refund,
    calculate_cross_border_refund,
    CalculationError,
)
from app.services.audit_service import (
    record_refund_requested,
    record_refund_approved,
    record_refund_rejected,
)
from app.repository.store import store


def process_refund(request: RefundRequest, request_id: str) -> RefundResult:
    """
    Process a refund request end-to-end.

    Steps:
      1. Check idempotency key — return existing result if duplicate.
      2. Record REFUND_REQUESTED in audit log.
      3. Validate business rules (raises ValidationError on failure).
      4. Select and run the correct calculation scenario.
      5. Verify calculated amount does not exceed remaining balance.
      6. Persist the RefundResult.
      7. Save idempotency key if provided.
      8. Record REFUND_APPROVED in audit log.

    Args:
        request: The parsed RefundRequest from the API layer.
        request_id: The X-Request-ID header for tracing.

    Returns:
        The persisted RefundResult.

    Raises:
        ValidationError: If any business rule check fails.
        CalculationError: If a financial guard condition triggers.
    """
    # Step 1: Idempotency — return cached result immediately
    if request.idempotency_key:
        existing_id = store.get_idempotency_key(request.idempotency_key)
        if existing_id:
            existing = store.get_refund(existing_id)
            if existing:
                return existing

    # Step 2: Audit — record request before validation
    record_refund_requested(
        transaction_id=request.transaction_id,
        operator_id=request.operator_id,
        request_id=request_id,
        item_ids=request.item_ids,
    )

    # Step 3: Validate
    try:
        transaction = validate_refund_request(request)
    except ValidationError as exc:
        record_refund_rejected(
            transaction_id=request.transaction_id,
            operator_id=request.operator_id,
            request_id=request_id,
            error_code=exc.code,
            error_message=exc.message,
        )
        raise

    # Step 4: Calculate
    already_refunded = store.get_total_refunded(transaction.id)
    try:
        breakdown = _select_calculation(request, transaction, already_refunded)
    except CalculationError as exc:
        record_refund_rejected(
            transaction_id=request.transaction_id,
            operator_id=request.operator_id,
            request_id=request_id,
            error_code="CALCULATION_ERROR",
            error_message=str(exc),
        )
        raise ValidationError(
            code="CALCULATION_ERROR",
            message=str(exc),
            http_status=422,
        ) from exc

    # Step 5: Final balance guard after calculation
    remaining = transaction.total - already_refunded
    if breakdown.total_refund > remaining:
        exc = ValidationError(
            code="REFUND_AMOUNT_EXCEEDED",
            message=(
                f"Calculated refund {breakdown.total_refund} {transaction.currency} "
                f"exceeds remaining refundable balance {remaining} {transaction.currency}"
            ),
            details={
                "calculated_refund": str(breakdown.total_refund),
                "remaining_balance": str(remaining),
            },
        )
        record_refund_rejected(
            transaction_id=request.transaction_id,
            operator_id=request.operator_id,
            request_id=request_id,
            error_code=exc.code,
            error_message=exc.message,
        )
        raise exc

    # Step 6: Persist
    result = RefundResult(
        refund_id=f"RF-{str(uuid.uuid4())[:8].upper()}",
        operation_type="REFUND",
        transaction_id=transaction.id,
        status="APPROVED",
        total_refund_amount=breakdown.total_refund,
        currency=transaction.currency,
        operator_id=request.operator_id,
        reason=request.reason,
        calculation_breakdown=breakdown,
        created_at=datetime.now(timezone.utc),
        idempotency_key=request.idempotency_key,
    )
    store.save_refund(result)

    # Step 7: Save idempotency key
    if request.idempotency_key:
        store.save_idempotency_key(request.idempotency_key, result.refund_id)

    # Step 8: Audit — record approval
    record_refund_approved(result=result, request_id=request_id)

    return result


def get_refund(refund_id: str) -> Optional[RefundResult]:
    """Retrieve a single refund by ID."""
    return store.get_refund(refund_id)


def list_refunds(transaction_id: Optional[str] = None) -> list[RefundResult]:
    """List all refunds, optionally filtered by transaction ID."""
    if transaction_id:
        return store.get_refunds_by_transaction(transaction_id)
    return store.list_refunds()


def _select_calculation(
    request: RefundRequest,
    transaction: Transaction,
    already_refunded: Decimal,
):
    """
    Select the correct calculation scenario based on transaction and request properties.

    Priority:
      1. Cross-border → Scenario E (adds USD conversion on top of full/partial)
      2. Installment (no item_ids) → Scenario D
      3. Partial (item_ids provided) → Scenario C
      4. Full → Scenario A or B (single vs split handled inside calculator)
    """
    has_installments = any(p.installments_total is not None for p in transaction.payments)

    if transaction.is_cross_border:
        return calculate_cross_border_refund(transaction, request.item_ids, already_refunded)

    if has_installments and request.item_ids is None:
        return calculate_installment_refund(transaction, already_refunded)

    if request.item_ids is not None:
        return calculate_partial_refund(transaction, request.item_ids, already_refunded)

    return calculate_full_refund(transaction)
