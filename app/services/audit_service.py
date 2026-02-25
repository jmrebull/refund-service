"""
Audit service — append-only audit log management.

Every refund operation (requested, approved, or rejected) is recorded here.
Entries are never modified or deleted.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from app.models.audit import AuditEntry
from app.models.refund import RefundResult, CalculationBreakdown
from app.repository.store import store


def record_refund_requested(
    transaction_id: str,
    operator_id: str,
    request_id: str,
    item_ids: Optional[list[str]] = None,
) -> AuditEntry:
    """
    Record that a refund was requested (before validation/calculation).

    Args:
        transaction_id: The transaction being refunded.
        operator_id: The operator initiating the refund.
        request_id: The X-Request-ID from the HTTP request.
        item_ids: Optional list of item IDs for partial refund.

    Returns:
        The created AuditEntry.
    """
    reasoning = f"Refund requested by operator '{operator_id}' for transaction {transaction_id}."
    if item_ids:
        reasoning += f" Partial refund for items: {item_ids}."

    entry = AuditEntry(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        refund_id=None,
        transaction_id=transaction_id,
        operator_id=operator_id,
        action="REFUND_REQUESTED",
        operation_type="REFUND",
        reasoning=reasoning,
        calculation_detail={"item_ids": item_ids} if item_ids else {},
        amount=None,
        currency=None,
        request_id=request_id,
    )
    store.append_audit(entry)
    return entry


def record_refund_approved(
    result: RefundResult,
    request_id: str,
) -> AuditEntry:
    """
    Record that a refund was successfully approved and processed.

    Args:
        result: The RefundResult containing all calculation details.
        request_id: The X-Request-ID from the HTTP request.

    Returns:
        The created AuditEntry.
    """
    reasoning = _build_approval_reasoning(result)
    calculation_detail = _serialize_breakdown(result.calculation_breakdown)

    entry = AuditEntry(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        refund_id=result.refund_id,
        transaction_id=result.transaction_id,
        operator_id=result.operator_id,
        action="REFUND_APPROVED",
        operation_type="REFUND",
        reasoning=reasoning,
        calculation_detail=calculation_detail,
        amount=result.total_refund_amount,
        currency=result.currency,
        request_id=request_id,
    )
    store.append_audit(entry)
    return entry


def record_refund_rejected(
    transaction_id: str,
    operator_id: str,
    request_id: str,
    error_code: str,
    error_message: str,
) -> AuditEntry:
    """
    Record that a refund was rejected due to a validation error.

    Args:
        transaction_id: The transaction for which the refund was attempted.
        operator_id: The operator who requested the refund.
        request_id: The X-Request-ID from the HTTP request.
        error_code: The validation error code (e.g. DUPLICATE_REFUND).
        error_message: Human-readable rejection reason.

    Returns:
        The created AuditEntry.
    """
    entry = AuditEntry(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        refund_id=None,
        transaction_id=transaction_id,
        operator_id=operator_id,
        action="REFUND_REJECTED",
        operation_type="REFUND",
        reasoning=f"Refund rejected. Code: {error_code}. Reason: {error_message}",
        calculation_detail={"error_code": error_code},
        amount=None,
        currency=None,
        request_id=request_id,
    )
    store.append_audit(entry)
    return entry


def get_audit_entries(
    transaction_id: Optional[str] = None,
    refund_id: Optional[str] = None,
) -> list[AuditEntry]:
    """
    Retrieve audit entries, optionally filtered by transaction or refund.

    Args:
        transaction_id: Filter by transaction ID.
        refund_id: Filter by refund ID.

    Returns:
        List of matching AuditEntry objects in chronological order.
    """
    return store.get_audit_log(transaction_id=transaction_id, refund_id=refund_id)


def _build_approval_reasoning(result: RefundResult) -> str:
    """Build a human-readable explanation of the approved refund."""
    bd = result.calculation_breakdown
    lines = []

    if bd.item_ratio is not None:
        # Extract item IDs from the payment breakdown scenario description is not available,
        # but items_subtotal and ratio are — give a precise numeric description instead.
        lines.append(
            f"Partial refund approved for items totalling {bd.items_subtotal} {result.currency}. "
            f"Item ratio: {bd.item_ratio:.4f} "
            f"({bd.items_subtotal} / subtotal)."
        )
        if bd.proportional_tax is not None:
            lines.append(f"Proportional tax: {bd.proportional_tax} ({result.currency}).")
        if bd.proportional_shipping is not None:
            lines.append(f"Proportional shipping: {bd.proportional_shipping} ({result.currency}).")
    elif bd.installments_total is not None:
        lines.append(
            f"Installment refund approved. "
            f"{bd.installments_charged} of {bd.installments_total} installments charged. "
            f"Installment value: {bd.installment_value} {result.currency}. "
            f"Charged amount: {bd.charged_amount} {result.currency}."
        )
    else:
        lines.append(f"Full refund approved for transaction {result.transaction_id}.")

    lines.append(f"Total refund: {result.total_refund_amount} {result.currency}.")

    # Payment distribution
    if bd.payment_breakdown:
        dist_parts = []
        for pr in bd.payment_breakdown:
            dist_parts.append(f"{pr.payment_type} {pr.refund_amount} {pr.currency}")
        lines.append(f"Distribution: {', '.join(dist_parts)}.")

    if bd.usd_equivalent is not None:
        lines.append(
            f"USD equivalent: {bd.usd_equivalent} USD "
            f"(exchange rate: {bd.exchange_rate_used})."
        )

    return " ".join(lines)


def _serialize_breakdown(bd: CalculationBreakdown) -> dict:
    """Serialize a CalculationBreakdown to a plain dict for the audit log."""
    return {
        "scenario": bd.scenario,
        "items_subtotal": str(bd.items_subtotal) if bd.items_subtotal is not None else None,
        "item_ratio": str(bd.item_ratio) if bd.item_ratio is not None else None,
        "proportional_tax": str(bd.proportional_tax) if bd.proportional_tax is not None else None,
        "proportional_shipping": str(bd.proportional_shipping) if bd.proportional_shipping is not None else None,
        "total_refund": str(bd.total_refund),
        "payment_breakdown": [
            {
                "payment_id": pr.payment_id,
                "payment_type": pr.payment_type,
                "original_amount": str(pr.original_amount),
                "refund_amount": str(pr.refund_amount),
                "currency": pr.currency,
            }
            for pr in bd.payment_breakdown
        ],
        "usd_equivalent": str(bd.usd_equivalent) if bd.usd_equivalent is not None else None,
        "exchange_rate_used": str(bd.exchange_rate_used) if bd.exchange_rate_used is not None else None,
        "installments_charged": bd.installments_charged,
        "installments_total": bd.installments_total,
        "installment_value": str(bd.installment_value) if bd.installment_value is not None else None,
        "charged_amount": str(bd.charged_amount) if bd.charged_amount is not None else None,
    }
