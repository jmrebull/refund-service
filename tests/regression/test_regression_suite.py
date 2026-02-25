"""
Regression tests — marked with @pytest.mark.regression.
These must never break.
"""
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


pytestmark = pytest.mark.regression


def _txn(**kwargs) -> Transaction:
    defaults = dict(
        id="TXN-REG-TEST",
        status=TransactionStatus.CAPTURED,
        currency="USD",
        subtotal=Decimal("50.00"),
        tax=Decimal("9.00"),
        shipping=Decimal("5.00"),
        total=Decimal("64.00"),
        items=[
            Item(id="ITEM-A", name="A", unit_price=Decimal("30.00"), quantity=1),
            Item(id="ITEM-B", name="B", unit_price=Decimal("20.00"), quantity=1),
        ],
        payments=[
            PaymentMethod(id="P1", type=PaymentMethodType.CARD, amount=Decimal("64.00"), currency="USD")
        ],
        merchant_id="M1",
    )
    defaults.update(kwargs)
    return Transaction(**defaults)


def test_all_five_mandatory_scenarios_produce_exact_amounts():
    """All five scenarios must produce exact Decimal outputs with known inputs."""
    # Scenario A: full single method
    txn_a = _txn()
    bd_a = calculate_full_refund(txn_a)
    assert bd_a.total_refund == Decimal("64.00")

    # Scenario B: full split payment
    txn_b = _txn(
        payments=[
            PaymentMethod(id="P1", type=PaymentMethodType.CARD, amount=Decimal("38.40"), currency="USD"),
            PaymentMethod(id="P2", type=PaymentMethodType.WALLET, amount=Decimal("25.60"), currency="USD"),
        ]
    )
    bd_b = calculate_full_refund(txn_b)
    assert bd_b.total_refund == Decimal("64.00")
    amounts_b = {p.payment_id: p.refund_amount for p in bd_b.payment_breakdown}
    assert amounts_b["P1"] == Decimal("38.40")
    assert amounts_b["P2"] == Decimal("25.60")

    # Scenario C: partial refund (Item A = 30/50 = 60%)
    txn_c = _txn()
    bd_c = calculate_partial_refund(txn_c, ["ITEM-A"], Decimal("0"))
    assert bd_c.item_ratio == Decimal("0.60")
    assert bd_c.total_refund == Decimal("38.40")

    # Scenario D: installment (3/6 charged, value=64/6)
    txn_d = _txn(
        payments=[
            PaymentMethod(
                id="P1", type=PaymentMethodType.CARD, amount=Decimal("64.00"),
                currency="USD", installments_total=6, installments_charged=3,
            )
        ]
    )
    bd_d = calculate_installment_refund(txn_d, Decimal("0"))
    assert bd_d.total_refund == Decimal("32.00")

    # Scenario E: cross-border (BRL, rate=5.20)
    txn_e = _txn(is_cross_border=True, exchange_rate_to_usd=Decimal("5.20"), currency="BRL")
    bd_e = calculate_cross_border_refund(txn_e, None, Decimal("0"))
    assert bd_e.usd_equivalent == Decimal("12.31")


def test_chargeback_always_rejected(client, auth_headers):
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-CB-001", "operator_id": "op1", "reason": "test"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"]["code"] == "INVALID_TRANSACTION_STATUS"


def test_voided_always_rejected(client, auth_headers):
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-VOID-001", "operator_id": "op1", "reason": "test"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"]["code"] == "INVALID_TRANSACTION_STATUS"


def test_duplicate_full_refund_always_rejected(client, auth_headers):
    client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-REG-007", "operator_id": "op1", "reason": "first"},
        headers=auth_headers,
    )
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-REG-007", "operator_id": "op1", "reason": "duplicate"},
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_idempotency_key_always_prevents_double_processing(client, auth_headers):
    """Idempotency key must always return the same refund_id and never re-process."""
    headers = {**auth_headers, "Idempotency-Key": "regression-idem-001"}
    payload = {"transaction_id": "TXN-REG-008", "operator_id": "op1", "reason": "test"}
    r1 = client.post("/api/v1/refunds", json=payload, headers=headers)
    r2 = client.post("/api/v1/refunds", json=payload, headers=headers)
    r3 = client.post("/api/v1/refunds", json=payload, headers=headers)
    assert r1.status_code == 201
    assert r2.status_code == 200 and r2.headers.get("Idempotent-Replayed") == "true"
    assert r3.status_code == 200 and r3.headers.get("Idempotent-Replayed") == "true"
    # All three calls return the exact same refund_id
    assert r1.json()["data"]["refund_id"] == r2.json()["data"]["refund_id"] == r3.json()["data"]["refund_id"]
    # Only one refund was actually created in the store
    from app.repository.store import store
    assert len(store.get_refunds_by_transaction("TXN-REG-008")) == 1


def test_zero_division_guards_never_raise_500(client, auth_headers):
    """All calculation guards must return 422, never 500."""
    # Attempt refund on transactions that would trigger calculation issues
    for txn_id in ["TXN-CB-001", "TXN-VOID-001", "TXN-AUTH-001"]:
        resp = client.post(
            "/api/v1/refunds",
            json={"transaction_id": txn_id, "operator_id": "op1", "reason": "test"},
            headers=auth_headers,
        )
        assert resp.status_code != 500, f"Got 500 for {txn_id}"
        assert resp.status_code == 422
