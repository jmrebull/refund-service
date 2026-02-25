"""Unit tests for app/engine/calculator.py — 100% coverage required."""
import pytest
from decimal import Decimal
from app.engine.calculator import (
    calculate_full_refund,
    calculate_partial_refund,
    calculate_installment_refund,
    calculate_cross_border_refund,
    CalculationError,
)
from app.models.transaction import Transaction, TransactionStatus, PaymentMethod, PaymentMethodType, Item


def _make_transaction(**kwargs) -> Transaction:
    defaults = dict(
        id="TXN-TEST",
        status=TransactionStatus.CAPTURED,
        currency="USD",
        subtotal=Decimal("50.00"),
        tax=Decimal("9.00"),
        shipping=Decimal("5.00"),
        total=Decimal("64.00"),
        items=[
            Item(id="ITEM-A", name="Item A", unit_price=Decimal("30.00"), quantity=1),
            Item(id="ITEM-B", name="Item B", unit_price=Decimal("20.00"), quantity=1),
        ],
        payments=[
            PaymentMethod(id="PAY-1", type=PaymentMethodType.CARD, amount=Decimal("64.00"), currency="USD")
        ],
        merchant_id="MERCHANT-1",
    )
    defaults.update(kwargs)
    return Transaction(**defaults)


def test_full_refund_single_method():
    txn = _make_transaction()
    bd = calculate_full_refund(txn)
    assert bd.total_refund == Decimal("64.00")
    assert len(bd.payment_breakdown) == 1
    assert bd.payment_breakdown[0].refund_amount == Decimal("64.00")
    assert "A" in bd.scenario


def test_full_refund_split_payment():
    txn = _make_transaction(
        payments=[
            PaymentMethod(id="PAY-CARD", type=PaymentMethodType.CARD, amount=Decimal("38.40"), currency="USD"),
            PaymentMethod(id="PAY-WALLET", type=PaymentMethodType.WALLET, amount=Decimal("25.60"), currency="USD"),
        ]
    )
    bd = calculate_full_refund(txn)
    assert bd.total_refund == Decimal("64.00")
    assert len(bd.payment_breakdown) == 2
    amounts = {p.payment_id: p.refund_amount for p in bd.payment_breakdown}
    assert amounts["PAY-CARD"] == Decimal("38.40")
    assert amounts["PAY-WALLET"] == Decimal("25.60")
    assert "B" in bd.scenario


def test_partial_refund_item_ratio():
    txn = _make_transaction()
    # Item A = $30, subtotal = $50, ratio = 0.60
    bd = calculate_partial_refund(txn, ["ITEM-A"], Decimal("0"))
    assert bd.item_ratio == Decimal("0.60")
    assert bd.proportional_tax == Decimal("5.40")   # 9.00 * 0.60
    assert bd.proportional_shipping == Decimal("3.00")  # 5.00 * 0.60
    assert bd.total_refund == Decimal("38.40")  # 30 + 5.40 + 3.00


def test_partial_refund_distributed_split():
    txn = _make_transaction(
        payments=[
            PaymentMethod(id="PAY-CARD", type=PaymentMethodType.CARD, amount=Decimal("38.40"), currency="USD"),
            PaymentMethod(id="PAY-WALLET", type=PaymentMethodType.WALLET, amount=Decimal("25.60"), currency="USD"),
        ]
    )
    bd = calculate_partial_refund(txn, ["ITEM-A"], Decimal("0"))
    total = sum(p.refund_amount for p in bd.payment_breakdown)
    # Sum should equal total_refund (may differ by at most 1 cent due to rounding)
    assert abs(total - bd.total_refund) <= Decimal("0.02")


def test_installment_refund_partial_charged():
    txn = _make_transaction(
        payments=[
            PaymentMethod(
                id="PAY-INST",
                type=PaymentMethodType.CARD,
                amount=Decimal("64.00"),
                currency="USD",
                installments_total=6,
                installments_charged=3,
            )
        ]
    )
    bd = calculate_installment_refund(txn, Decimal("0"))
    # installment_value = 64.00 / 6 = 10.6666...
    # charged_amount = 10.6666... * 3 = 32.00
    assert bd.installments_charged == 3
    assert bd.installments_total == 6
    assert bd.total_refund == Decimal("32.00")


def test_installment_refund_fully_charged():
    txn = _make_transaction(
        payments=[
            PaymentMethod(
                id="PAY-INST",
                type=PaymentMethodType.CARD,
                amount=Decimal("60.00"),
                currency="USD",
                installments_total=3,
                installments_charged=3,
            )
        ],
        total=Decimal("60.00"),
        subtotal=Decimal("50.00"),
        tax=Decimal("5.00"),
        shipping=Decimal("5.00"),
    )
    bd = calculate_installment_refund(txn, Decimal("0"))
    assert bd.total_refund == Decimal("60.00")


def test_cross_border_uses_original_rate():
    txn = _make_transaction(
        is_cross_border=True,
        exchange_rate_to_usd=Decimal("5.20"),
        currency="BRL",
    )
    bd = calculate_cross_border_refund(txn, None, Decimal("0"))
    assert bd.exchange_rate_used == Decimal("5.20")
    assert bd.usd_equivalent is not None
    # 64.00 BRL / 5.20 = ~12.31 USD
    assert bd.usd_equivalent == Decimal("12.31")


def test_rounding_half_up():
    # 0.005 should round to 0.01 (ROUND_HALF_UP), not 0.00 (ROUND_HALF_EVEN)
    txn = _make_transaction(
        subtotal=Decimal("10.00"),
        tax=Decimal("0.01"),
        shipping=Decimal("0.00"),
        total=Decimal("10.01"),
        items=[Item(id="ITEM-A", name="A", unit_price=Decimal("5.00"), quantity=1),
               Item(id="ITEM-B", name="B", unit_price=Decimal("5.00"), quantity=1)],
    )
    bd = calculate_partial_refund(txn, ["ITEM-A"], Decimal("0"))
    # ratio = 5/10 = 0.5, tax = 0.01 * 0.5 = 0.005 -> rounds to 0.01
    assert bd.proportional_tax == Decimal("0.01")


def test_guard_zero_subtotal():
    txn = _make_transaction(subtotal=Decimal("0"))
    with pytest.raises(CalculationError, match="subtotal is zero"):
        calculate_partial_refund(txn, ["ITEM-A"], Decimal("0"))


def test_guard_zero_total():
    with pytest.raises(CalculationError, match="transaction total is zero"):
        from app.engine.calculator import _build_payment_refunds
        from app.models.transaction import PaymentMethod, PaymentMethodType
        _build_payment_refunds(
            [PaymentMethod(id="P1", type=PaymentMethodType.CARD, amount=Decimal("10"), currency="USD")],
            Decimal("10"),
            Decimal("0"),
        )


def test_guard_zero_installments():
    # Use model_construct to bypass Pydantic validation and test the calculator guard directly
    bad_payment = PaymentMethod.model_construct(
        id="PAY-INST",
        type=PaymentMethodType.CARD,
        amount=Decimal("64.00"),
        currency="USD",
        installments_total=0,
        installments_charged=0,
        card_last4=None,
    )
    txn = _make_transaction()
    txn_bad = txn.model_copy(update={"payments": [bad_payment]})
    with pytest.raises(CalculationError, match="cannot be zero"):
        calculate_installment_refund(txn_bad, Decimal("0"))


def test_guard_zero_exchange_rate():
    # Use model_copy to bypass Pydantic's gt=0 constraint and test the calculator guard
    txn = _make_transaction()
    txn_bad = txn.model_copy(update={"is_cross_border": True, "exchange_rate_to_usd": Decimal("0"), "currency": "BRL"})
    with pytest.raises(CalculationError, match="exchange rate is zero"):
        calculate_cross_border_refund(txn_bad, None, Decimal("0"))


def test_guard_zero_total_in_full_refund():
    # model_construct bypasses Pydantic's gt=0 on total
    from app.models.transaction import Transaction
    txn = Transaction.model_construct(
        id="TXN-ZERO",
        status=TransactionStatus.CAPTURED,
        currency="USD",
        subtotal=Decimal("10.00"),
        tax=Decimal("0.00"),
        shipping=Decimal("0.00"),
        total=Decimal("0"),
        items=[Item(id="ITEM-A", name="A", unit_price=Decimal("10.00"), quantity=1)],
        payments=[PaymentMethod.model_construct(id="P1", type=PaymentMethodType.CARD, amount=Decimal("10"), currency="USD")],
        merchant_id="M1",
        is_cross_border=False,
        exchange_rate_to_usd=None,
    )
    with pytest.raises(CalculationError, match="transaction total is zero"):
        calculate_full_refund(txn)


def test_guard_zero_total_in_partial_refund():
    # subtotal > 0 but total = 0 to skip the subtotal guard and hit the total guard
    from app.models.transaction import Transaction
    txn = Transaction.model_construct(
        id="TXN-ZERO-TOTAL",
        status=TransactionStatus.CAPTURED,
        currency="USD",
        subtotal=Decimal("10.00"),
        tax=Decimal("0.00"),
        shipping=Decimal("0.00"),
        total=Decimal("0"),
        items=[Item(id="ITEM-A", name="A", unit_price=Decimal("10.00"), quantity=1)],
        payments=[PaymentMethod.model_construct(id="P1", type=PaymentMethodType.CARD, amount=Decimal("10"), currency="USD")],
        merchant_id="M1",
        is_cross_border=False,
        exchange_rate_to_usd=None,
    )
    with pytest.raises(CalculationError, match="transaction total is zero"):
        calculate_partial_refund(txn, ["ITEM-A"], Decimal("0"))


def test_partial_refund_cross_border_sets_usd():
    # Calls calculate_partial_refund directly on a cross-border txn — covers lines 183-185
    txn = _make_transaction(is_cross_border=True, exchange_rate_to_usd=Decimal("5.20"), currency="BRL")
    bd = calculate_partial_refund(txn, ["ITEM-A"], Decimal("0"))
    assert bd.usd_equivalent is not None
    assert bd.exchange_rate_used == Decimal("5.20")


def test_guard_no_installment_payment():
    # Transaction with no installments_total — covers L217 in calculate_installment_refund
    txn = _make_transaction()  # has plain CARD payment without installments
    with pytest.raises(CalculationError, match="No installment payment method found"):
        calculate_installment_refund(txn, Decimal("0"))


def test_guard_zero_total_in_installment_refund():
    # installments present but total=0 — covers L223
    bad_payment = PaymentMethod.model_construct(
        id="PAY-INST",
        type=PaymentMethodType.CARD,
        amount=Decimal("64.00"),
        currency="USD",
        installments_total=6,
        installments_charged=3,
        card_last4=None,
    )
    from app.models.transaction import Transaction
    txn = Transaction.model_construct(
        id="TXN-ZERO-INST",
        status=TransactionStatus.CAPTURED,
        currency="USD",
        subtotal=Decimal("50.00"),
        tax=Decimal("9.00"),
        shipping=Decimal("5.00"),
        total=Decimal("0"),
        items=[Item(id="ITEM-A", name="A", unit_price=Decimal("30.00"), quantity=1)],
        payments=[bad_payment],
        merchant_id="M1",
        is_cross_border=False,
        exchange_rate_to_usd=None,
    )
    with pytest.raises(CalculationError, match="transaction total is zero"):
        calculate_installment_refund(txn, Decimal("0"))


def test_calculate_usd_equivalent_direct_zero_rate():
    # Call _calculate_usd_equivalent directly to cover L266
    from app.engine.calculator import _calculate_usd_equivalent
    with pytest.raises(CalculationError, match="exchange rate is zero"):
        _calculate_usd_equivalent(Decimal("100.00"), Decimal("0"))


def test_guard_missing_exchange_rate_cross_border():
    # is_cross_border=True but exchange_rate_to_usd=None — covers L294
    txn = _make_transaction(is_cross_border=True, exchange_rate_to_usd=None)
    with pytest.raises(CalculationError, match="missing exchange_rate_to_usd"):
        calculate_cross_border_refund(txn, None, Decimal("0"))


def test_cross_border_partial_refund_with_items():
    # item_ids provided to cross-border refund — covers L300-301
    txn = _make_transaction(is_cross_border=True, exchange_rate_to_usd=Decimal("5.20"), currency="BRL")
    bd = calculate_cross_border_refund(txn, ["ITEM-A"], Decimal("0"))
    assert "E" in bd.scenario
    assert "partial" in bd.scenario.lower()
    assert bd.usd_equivalent is not None
