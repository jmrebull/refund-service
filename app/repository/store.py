"""
In-memory data store with thread-safe operations.

No business logic — only data access primitives.
"""
import threading
from decimal import Decimal
from typing import Optional
from app.models.transaction import Transaction
from app.models.refund import RefundResult
from app.models.audit import AuditEntry


class InMemoryStore:
    """Thread-safe in-memory store for transactions, refunds, and audit entries."""

    def __init__(self):
        self._lock = threading.Lock()
        self._transactions: dict[str, Transaction] = {}
        self._refunds: dict[str, RefundResult] = {}
        # transaction_id -> list of refund_ids
        self._refunds_by_transaction: dict[str, list[str]] = {}
        # idempotency_key -> refund_id
        self._idempotency_keys: dict[str, str] = {}
        self._audit_log: list[AuditEntry] = []

    # ── Transactions ────────────────────────────────────────────────────────

    def get_transaction(self, transaction_id: str) -> Optional[Transaction]:
        with self._lock:
            return self._transactions.get(transaction_id)

    def list_transactions(self) -> list[Transaction]:
        with self._lock:
            return list(self._transactions.values())

    def save_transaction(self, transaction: Transaction) -> None:
        with self._lock:
            self._transactions[transaction.id] = transaction

    # ── Refunds ─────────────────────────────────────────────────────────────

    def get_refund(self, refund_id: str) -> Optional[RefundResult]:
        with self._lock:
            return self._refunds.get(refund_id)

    def get_refunds_by_transaction(self, transaction_id: str) -> list[RefundResult]:
        with self._lock:
            refund_ids = self._refunds_by_transaction.get(transaction_id, [])
            return [self._refunds[rid] for rid in refund_ids if rid in self._refunds]

    def list_refunds(self) -> list[RefundResult]:
        with self._lock:
            return list(self._refunds.values())

    def save_refund(self, refund: RefundResult) -> None:
        with self._lock:
            self._refunds[refund.refund_id] = refund
            if refund.transaction_id not in self._refunds_by_transaction:
                self._refunds_by_transaction[refund.transaction_id] = []
            self._refunds_by_transaction[refund.transaction_id].append(refund.refund_id)

    def get_total_refunded(self, transaction_id: str) -> Decimal:
        """Return total amount already approved and refunded for a transaction."""
        with self._lock:
            refund_ids = self._refunds_by_transaction.get(transaction_id, [])
            return sum(
                (self._refunds[rid].total_refund_amount for rid in refund_ids if rid in self._refunds),
                Decimal("0"),
            )

    def has_full_refund(self, transaction_id: str) -> Optional[str]:
        """Return the refund_id of a full refund if one exists, else None."""
        with self._lock:
            refund_ids = self._refunds_by_transaction.get(transaction_id, [])
            for rid in refund_ids:
                refund = self._refunds.get(rid)
                if refund and refund.calculation_breakdown.item_ratio is None and refund.calculation_breakdown.installments_total is None:
                    txn = self._transactions.get(transaction_id)
                    if txn and refund.total_refund_amount >= txn.total:
                        return rid
            return None

    # ── Idempotency ─────────────────────────────────────────────────────────

    def get_idempotency_key(self, key: str) -> Optional[str]:
        """Return the refund_id associated with an idempotency key, if any."""
        with self._lock:
            return self._idempotency_keys.get(key)

    def save_idempotency_key(self, key: str, refund_id: str) -> None:
        with self._lock:
            self._idempotency_keys[key] = refund_id

    # ── Audit ────────────────────────────────────────────────────────────────

    def append_audit(self, entry: AuditEntry) -> None:
        """Append-only audit log. No update or delete."""
        with self._lock:
            self._audit_log.append(entry)

    def get_audit_log(
        self,
        transaction_id: Optional[str] = None,
        refund_id: Optional[str] = None,
    ) -> list[AuditEntry]:
        with self._lock:
            entries = list(self._audit_log)

        if transaction_id:
            entries = [e for e in entries if e.transaction_id == transaction_id]
        if refund_id:
            entries = [e for e in entries if e.refund_id == refund_id]
        return entries


# Global singleton — initialized at startup and populated by seed_data
store = InMemoryStore()
