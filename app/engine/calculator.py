from __future__ import annotations

"""
Refund calculation engine.

Pure functions with no side effects or I/O. All monetary math uses Decimal.
Rounding uses ROUND_HALF_UP to 2 decimal places, applied at final output only.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.transaction import Transaction, PaymentMethod
    from app.models.refund import CalculationBreakdown, PaymentRefund

CENTS = Decimal("0.01")


class CalculationError(Exception):
    """Raised when a financial guard condition is violated."""
    pass


def _quantize(value: Decimal) -> Decimal:
    """Round to 2 decimal places using ROUND_HALF_UP."""
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _build_payment_refunds(
    payments: list["PaymentMethod"],
    total_refund: Decimal,
    transaction_total: Decimal,
) -> list["PaymentRefund"]:
    """
    Distribute a refund amount across payment methods proportionally.

    Args:
        payments: List of payment methods on the transaction.
        total_refund: The total refund amount to distribute.
        transaction_total: The transaction total (used as the denominator for weights).

    Returns:
        List of PaymentRefund objects with distributed amounts.

    Raises:
        CalculationError: If transaction_total is zero.

    Example:
        total=100, CARD=60, WALLET=40, refund=38.40
        → CARD: 38.40 * (60/100) = 23.04
        → WALLET: 38.40 * (40/100) = 15.36
    """
    from app.models.refund import PaymentRefund

    if transaction_total == Decimal("0"):
        raise CalculationError("Cannot distribute refund: transaction total is zero")

    refunds = []
    for payment in payments:
        weight = payment.amount / transaction_total
        refund_amount = _quantize(total_refund * weight)
        refunds.append(
            PaymentRefund(
                payment_id=payment.id,
                payment_type=payment.type.value,
                original_amount=payment.amount,
                refund_amount=refund_amount,
                currency=payment.currency,
            )
        )
    return refunds


def calculate_full_refund(transaction: "Transaction") -> "CalculationBreakdown":
    """
    Scenario A/B: Full refund for a transaction (single or split payment).

    For single-method transactions, returns the exact amount paid.
    For split-payment transactions, refunds exactly what was paid per method.

    Args:
        transaction: The transaction to refund in full.

    Returns:
        CalculationBreakdown with total_refund == transaction.total.

    Raises:
        CalculationError: If transaction total is zero (guard against zero division).

    Example (Scenario A):
        transaction.total = 64.00, 1 CARD payment
        → total_refund = 64.00, CARD refund_amount = 64.00

    Example (Scenario B):
        transaction.total = 64.00, CARD=38.40 + WALLET=25.60
        → CARD refund_amount = 38.40, WALLET refund_amount = 25.60
    """
    from app.models.refund import CalculationBreakdown, PaymentRefund

    if transaction.total == Decimal("0"):
        raise CalculationError("Cannot distribute refund: transaction total is zero")

    if len(transaction.payments) == 1:
        scenario = "A: Full refund, single payment method"
        payment = transaction.payments[0]
        payment_breakdown = [
            PaymentRefund(
                payment_id=payment.id,
                payment_type=payment.type.value,
                original_amount=payment.amount,
                refund_amount=payment.amount,
                currency=payment.currency,
            )
        ]
    else:
        scenario = "B: Full refund, split payment"
        payment_breakdown = []
        for payment in transaction.payments:
            payment_breakdown.append(
                PaymentRefund(
                    payment_id=payment.id,
                    payment_type=payment.type.value,
                    original_amount=payment.amount,
                    refund_amount=payment.amount,
                    currency=payment.currency,
                )
            )

    breakdown = CalculationBreakdown(
        scenario=scenario,
        total_refund=transaction.total,
        payment_breakdown=payment_breakdown,
    )

    if transaction.is_cross_border and transaction.exchange_rate_to_usd:
        usd_equiv, rate = _calculate_usd_equivalent(transaction.total, transaction.exchange_rate_to_usd)
        breakdown.usd_equivalent = usd_equiv
        breakdown.exchange_rate_used = rate

    return breakdown


def calculate_partial_refund(
    transaction: "Transaction",
    item_ids: list[str],
    already_refunded: Decimal,
) -> "CalculationBreakdown":
    """
    Scenario C: Partial refund for a subset of items.

    Tax and shipping are refunded proportionally to the item ratio.
    The total is distributed across payment methods by their original weight.

    Args:
        transaction: The transaction containing the items.
        item_ids: IDs of the items to refund.
        already_refunded: Amount already refunded on this transaction.

    Returns:
        CalculationBreakdown with proportional tax, shipping, and payment breakdown.

    Raises:
        CalculationError: If subtotal or total is zero (division guards).

    Example (Scenario C):
        subtotal=50.00, tax=9.00, shipping=5.00, total=64.00
        item_ids=[ITEM-A] where ITEM-A.unit_price=30.00
        → ratio = 30.00 / 50.00 = 0.60
        → refund_tax = 9.00 * 0.60 = 5.40
        → refund_shipping = 5.00 * 0.60 = 3.00
        → total_refund = 30.00 + 5.40 + 3.00 = 38.40
    """
    if transaction.subtotal == Decimal("0"):
        raise CalculationError("Cannot calculate item ratio: transaction subtotal is zero")

    if transaction.total == Decimal("0"):
        raise CalculationError("Cannot distribute refund: transaction total is zero")

    requested_items = [item for item in transaction.items if item.id in item_ids]
    items_subtotal = sum(
        item.unit_price * item.quantity for item in requested_items
    )

    ratio = items_subtotal / transaction.subtotal
    refund_tax = _quantize(transaction.tax * ratio)
    refund_shipping = _quantize(transaction.shipping * ratio)
    total_refund = _quantize(items_subtotal + refund_tax + refund_shipping)

    payment_breakdown = _build_payment_refunds(
        transaction.payments, total_refund, transaction.total
    )

    breakdown_obj = __import__("app.models.refund", fromlist=["CalculationBreakdown"]).CalculationBreakdown(
        scenario="C: Partial refund, item subset",
        items_subtotal=_quantize(items_subtotal),
        item_ratio=_quantize(ratio),
        proportional_tax=refund_tax,
        proportional_shipping=refund_shipping,
        total_refund=total_refund,
        payment_breakdown=payment_breakdown,
    )

    if transaction.is_cross_border and transaction.exchange_rate_to_usd:
        usd_equiv, rate = _calculate_usd_equivalent(total_refund, transaction.exchange_rate_to_usd)
        breakdown_obj.usd_equivalent = usd_equiv
        breakdown_obj.exchange_rate_used = rate

    return breakdown_obj


def calculate_installment_refund(
    transaction: "Transaction",
    already_refunded: Decimal,
) -> "CalculationBreakdown":
    """
    Scenario D: Refund for an installment-based transaction.

    Only charged installments are refundable. Refund amount = installment_value * charged_count.

    Args:
        transaction: The installment transaction to refund.
        already_refunded: Amount already refunded on this transaction.

    Returns:
        CalculationBreakdown with installment details and payment breakdown.

    Raises:
        CalculationError: If installments_total is zero or total is zero.

    Example (Scenario D):
        payment.amount=64.00, installments_total=6, installments_charged=3
        → installment_value = 64.00 / 6 = 10.6667
        → charged_amount = 10.6667 * 3 = 32.00
        → total_refund = 32.00 - already_refunded
    """
    from app.models.refund import CalculationBreakdown

    # Find the installment payment method
    installment_payment = next(
        (p for p in transaction.payments if p.installments_total is not None),
        None,
    )
    if installment_payment is None:
        raise CalculationError("No installment payment method found on transaction")

    if installment_payment.installments_total == 0:
        raise CalculationError("Installment total count cannot be zero")

    if transaction.total == Decimal("0"):
        raise CalculationError("Cannot distribute refund: transaction total is zero")

    installment_value = installment_payment.amount / Decimal(str(installment_payment.installments_total))
    charged_count = installment_payment.installments_charged or 0
    charged_amount = _quantize(installment_value * charged_count)
    refundable = charged_amount - already_refunded
    total_refund = _quantize(max(refundable, Decimal("0")))

    payment_breakdown = _build_payment_refunds(
        transaction.payments, total_refund, transaction.total
    )

    return CalculationBreakdown(
        scenario="D: Installment refund",
        total_refund=total_refund,
        payment_breakdown=payment_breakdown,
        installments_charged=charged_count,
        installments_total=installment_payment.installments_total,
        installment_value=_quantize(installment_value),
        charged_amount=charged_amount,
    )


def _calculate_usd_equivalent(
    local_amount: Decimal,
    exchange_rate_to_usd: Decimal,
) -> tuple[Decimal, Decimal]:
    """
    Scenario E: Convert a local currency amount to USD using the stored exchange rate.

    Always uses the rate stored at purchase time, never a live rate.

    Args:
        local_amount: The refund amount in local currency.
        exchange_rate_to_usd: The exchange rate (local / USD) stored at purchase time.

    Returns:
        Tuple of (usd_equivalent, exchange_rate_used).

    Raises:
        CalculationError: If exchange_rate_to_usd is zero.

    Example (Scenario E):
        local_amount=64.00 BRL, exchange_rate_to_usd=5.20
        → usd_equivalent = 64.00 / 5.20 = 12.31 USD
    """
    if exchange_rate_to_usd == Decimal("0"):
        raise CalculationError("Cannot convert currency: exchange rate is zero")
    usd_equivalent = _quantize(local_amount / exchange_rate_to_usd)
    return usd_equivalent, exchange_rate_to_usd


def calculate_cross_border_refund(
    transaction: "Transaction",
    item_ids: list[str] | None,
    already_refunded: Decimal,
) -> "CalculationBreakdown":
    """
    Scenario E: Cross-border refund with currency conversion.

    Delegates to full or partial refund, then adds USD equivalent.
    Always uses the exchange rate stored at purchase time.

    Args:
        transaction: The cross-border transaction.
        item_ids: If provided, partial refund; otherwise full refund.
        already_refunded: Amount already refunded on this transaction.

    Returns:
        CalculationBreakdown with usd_equivalent and exchange_rate_used populated.

    Raises:
        CalculationError: If exchange_rate_to_usd is zero or any division guard triggers.

    Example (Scenario E):
        transaction.total=64.00 BRL, exchange_rate_to_usd=5.20, item_ids=None
        → delegates to calculate_full_refund → total_refund=64.00 BRL
        → usd_equivalent = 64.00 / 5.20 = 12.31 USD
    """
    if transaction.exchange_rate_to_usd is None:
        raise CalculationError("Cross-border transaction missing exchange_rate_to_usd")

    if transaction.exchange_rate_to_usd == Decimal("0"):
        raise CalculationError("Cannot convert currency: exchange rate is zero")

    if item_ids:
        breakdown = calculate_partial_refund(transaction, item_ids, already_refunded)
        breakdown.scenario = "E: Cross-border partial refund"
    else:
        breakdown = calculate_full_refund(transaction)
        breakdown.scenario = "E: Cross-border full refund"

    usd_equiv, rate = _calculate_usd_equivalent(
        breakdown.total_refund, transaction.exchange_rate_to_usd
    )
    breakdown.usd_equivalent = usd_equiv
    breakdown.exchange_rate_used = rate
    return breakdown
