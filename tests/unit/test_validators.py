"""Unit tests for app/validators/refund_validator.py — 100% coverage required."""
import pytest
from app.models.refund import RefundRequest
from app.validators.refund_validator import validate_refund_request, ValidationError
from app.repository.store import store


def _req(**kwargs) -> RefundRequest:
    defaults = dict(transaction_id="TXN-REG-001", operator_id="op1", reason="test")
    defaults.update(kwargs)
    return RefundRequest(**defaults)


def test_transaction_not_found():
    with pytest.raises(ValidationError) as exc_info:
        validate_refund_request(_req(transaction_id="TXN-NONEXISTENT"))
    assert exc_info.value.code == "TRANSACTION_NOT_FOUND"
    assert exc_info.value.http_status == 404


def test_refund_blocked_on_chargebacked():
    with pytest.raises(ValidationError) as exc_info:
        validate_refund_request(_req(transaction_id="TXN-CB-001"))
    assert exc_info.value.code == "INVALID_TRANSACTION_STATUS"
    assert "CHARGEBACKED" in exc_info.value.message
    assert "disputes" in exc_info.value.message


def test_refund_blocked_on_voided():
    with pytest.raises(ValidationError) as exc_info:
        validate_refund_request(_req(transaction_id="TXN-VOID-001"))
    assert exc_info.value.code == "INVALID_TRANSACTION_STATUS"
    assert "VOIDED" in exc_info.value.message


def test_refund_blocked_on_authorized():
    with pytest.raises(ValidationError) as exc_info:
        validate_refund_request(_req(transaction_id="TXN-AUTH-001"))
    assert exc_info.value.code == "INVALID_TRANSACTION_STATUS"
    assert "authorized" in exc_info.value.message.lower()


def test_duplicate_full_refund_rejected():
    from app.services.refund_service import process_refund
    req = _req(transaction_id="TXN-REG-001")
    process_refund(req, "req-1")
    with pytest.raises(ValidationError) as exc_info:
        validate_refund_request(_req(transaction_id="TXN-REG-001"))
    assert exc_info.value.code == "DUPLICATE_REFUND"
    assert exc_info.value.http_status == 409


def test_unknown_item_ids_rejected():
    with pytest.raises(ValidationError) as exc_info:
        validate_refund_request(_req(transaction_id="TXN-REG-001", item_ids=["ITEM-FAKE-999"]))
    assert exc_info.value.code == "INVALID_ITEM_IDS"
    assert "ITEM-FAKE-999" in str(exc_info.value.details)


def test_amount_exceeds_refundable_balance():
    from app.services.refund_service import process_refund
    # First full refund
    process_refund(_req(transaction_id="TXN-REG-001"), "req-1")
    # Second attempt should fail
    with pytest.raises(ValidationError) as exc_info:
        validate_refund_request(_req(transaction_id="TXN-REG-001"))
    assert exc_info.value.code == "DUPLICATE_REFUND"


def test_installment_exceeds_charged():
    """Transactions with 0 installments charged should be rejected."""
    from app.models.transaction import Transaction, TransactionStatus, PaymentMethod, PaymentMethodType, Item
    from decimal import Decimal
    txn = Transaction(
        id="TXN-INST-ZERO",
        status=TransactionStatus.CAPTURED,
        currency="USD",
        subtotal=Decimal("100.00"),
        tax=Decimal("10.00"),
        shipping=Decimal("5.00"),
        total=Decimal("115.00"),
        items=[Item(id="ITEM-Z-001", name="Zero charged item", unit_price=Decimal("100.00"), quantity=1)],
        payments=[
            PaymentMethod(
                id="PAY-INST-ZERO",
                type=PaymentMethodType.CARD,
                amount=Decimal("115.00"),
                currency="USD",
                installments_total=6,
                installments_charged=0,
            )
        ],
        merchant_id="MERCHANT-1",
    )
    store.save_transaction(txn)
    with pytest.raises(ValidationError) as exc_info:
        validate_refund_request(_req(transaction_id="TXN-INST-ZERO"))
    assert exc_info.value.code == "INSTALLMENT_NOT_CHARGED"


def test_idempotency_key_duplicate_via_validator():
    # Save a refund with an idempotency key, then call validator directly — covers L111-113
    from app.services.refund_service import process_refund
    process_refund(_req(transaction_id="TXN-REG-001", idempotency_key="IDEM-KEY-DIRECT"), "req-1")
    # Call the validator directly (bypassing service-level idempotency check)
    with pytest.raises(ValidationError) as exc_info:
        validate_refund_request(_req(transaction_id="TXN-REG-002", idempotency_key="IDEM-KEY-DIRECT"))
    assert exc_info.value.code == "DUPLICATE_REFUND"
    assert exc_info.value.http_status == 409


def test_refundable_balance_exhausted_after_partial_refunds():
    # Two partial refunds drain the balance → third attempt hits L160 (remaining <= 0)
    from app.services.refund_service import process_refund
    txn = store.get_transaction("TXN-REG-001")
    item_a = txn.items[0].id
    item_b = txn.items[1].id
    # Refund item A then item B — together they exhaust the full balance
    process_refund(_req(transaction_id="TXN-REG-001", item_ids=[item_a]), "req-1")
    process_refund(_req(transaction_id="TXN-REG-001", item_ids=[item_b]), "req-2")
    # Full refund attempt: has_full_refund returns None (both refunds have item_ratio set)
    # but _validate_refundable_balance finds remaining = 0 and raises
    with pytest.raises(ValidationError) as exc_info:
        validate_refund_request(_req(transaction_id="TXN-REG-001"))
    assert exc_info.value.code == "REFUND_AMOUNT_EXCEEDED"


def test_partial_refund_estimate_exceeds_remaining_balance():
    """Covers L180: estimated partial refund > remaining refundable balance."""
    from app.services.refund_service import process_refund
    # TXN-REG-010 has items ITEM-REG-010-A and ITEM-REG-010-B
    txn = store.get_transaction("TXN-REG-010")
    item_a = next(i.id for i in txn.items if i.id.endswith("-A"))
    # First partial refund of item A succeeds, consuming most of the balance
    process_refund(_req(transaction_id="TXN-REG-010", item_ids=[item_a]), "req-1")
    # Second attempt to refund item A again: estimated > remaining → 422
    with pytest.raises(ValidationError) as exc_info:
        validate_refund_request(_req(transaction_id="TXN-REG-010", item_ids=[item_a]))
    assert exc_info.value.code == "REFUND_AMOUNT_EXCEEDED"
    assert "Estimated refund" in exc_info.value.message


def test_valid_partial_refund_passes():
    txn = store.get_transaction("TXN-REG-001")
    item_id = txn.items[0].id
    result = validate_refund_request(_req(transaction_id="TXN-REG-001", item_ids=[item_id]))
    assert result.id == "TXN-REG-001"


def test_valid_installment_refund_passes():
    result = validate_refund_request(_req(transaction_id="TXN-INSTALL-001"))
    assert result.id == "TXN-INSTALL-001"
