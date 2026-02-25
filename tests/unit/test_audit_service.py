"""Unit tests for app/services/audit_service.py."""
import pytest
from app.services.audit_service import (
    record_refund_requested,
    record_refund_rejected,
    get_audit_entries,
)
from app.repository.store import store


def test_audit_entry_is_appended():
    before = len(get_audit_entries())
    record_refund_requested("TXN-REG-001", "op1", "req-test")
    after = len(get_audit_entries())
    assert after == before + 1


def test_audit_log_is_immutable():
    """Audit entries cannot be deleted or overwritten through the public interface."""
    record_refund_requested("TXN-REG-001", "op1", "req-1")
    entries_before = get_audit_entries()
    count_before = len(entries_before)
    # There is no delete/update method on audit — verify the store has no such method
    assert not hasattr(store, "delete_audit")
    assert not hasattr(store, "update_audit")
    assert not hasattr(store, "clear_audit")
    # Appending another entry grows the log, never shrinks it
    record_refund_requested("TXN-REG-002", "op2", "req-2")
    assert len(get_audit_entries()) == count_before + 1


def test_audit_contains_operation_type():
    record_refund_requested("TXN-REG-001", "op1", "req-test")
    entries = get_audit_entries(transaction_id="TXN-REG-001")
    assert all(e.operation_type == "REFUND" for e in entries)


def test_reasoning_is_non_empty():
    record_refund_requested("TXN-REG-001", "op1", "req-test")
    record_refund_rejected("TXN-REG-001", "op1", "req-test", "SOME_ERROR", "Something went wrong")
    entries = get_audit_entries(transaction_id="TXN-REG-001")
    for entry in entries:
        assert entry.reasoning and len(entry.reasoning) > 10
