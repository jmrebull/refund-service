"""
Seed data generator for Solara Retail refund-service.

Generates 50+ test transactions covering all refund scenarios.
Run via: python seed_data.py (standalone) or imported by app startup.
"""
from decimal import Decimal
from app.models.transaction import Transaction, TransactionStatus, PaymentMethod, PaymentMethodType, Item
from app.repository.store import store


def load_seed_data() -> None:
    """Populate the in-memory store with test transactions."""
    transactions = _build_transactions()
    for txn in transactions:
        store.save_transaction(txn)


def _build_transactions() -> list[Transaction]:
    txns = []

    # ── Regular single-method transactions (TXN-REG-001..040) ──────────────

    currencies = ["BRL", "MXN", "COP", "USD"]
    statuses = [TransactionStatus.CAPTURED, TransactionStatus.SETTLED]

    for i in range(1, 41):
        currency = currencies[(i - 1) % 4]
        status = statuses[(i - 1) % 2]
        base = Decimal(str(10 + i * 2))
        tax = (base * Decimal("0.15")).quantize(Decimal("0.01"))
        shipping = Decimal("5.00")
        total = base + tax + shipping

        items = [
            Item(id=f"ITEM-REG-{i:03d}-A", name=f"Product A-{i}", unit_price=base * Decimal("0.6"), quantity=1),
            Item(id=f"ITEM-REG-{i:03d}-B", name=f"Product B-{i}", unit_price=base * Decimal("0.4"), quantity=1),
        ]

        txns.append(Transaction(
            id=f"TXN-REG-{i:03d}",
            status=status,
            currency=currency,
            subtotal=base,
            tax=tax,
            shipping=shipping,
            total=total,
            items=items,
            payments=[
                PaymentMethod(
                    id=f"PAY-REG-{i:03d}",
                    type=PaymentMethodType.CARD,
                    amount=total,
                    currency=currency,
                    card_last4="4242",
                )
            ],
            merchant_id="MERCHANT-SOLARA",
        ))

    # ── Split payment transactions (TXN-SPLIT-001..005) ────────────────────

    for i in range(1, 6):
        subtotal = Decimal(str(50 + i * 10))
        tax = (subtotal * Decimal("0.10")).quantize(Decimal("0.01"))
        shipping = Decimal("8.00")
        total = subtotal + tax + shipping
        card_amount = (total * Decimal("0.6")).quantize(Decimal("0.01"))
        wallet_amount = total - card_amount

        txns.append(Transaction(
            id=f"TXN-SPLIT-{i:03d}",
            status=TransactionStatus.CAPTURED,
            currency="BRL",
            subtotal=subtotal,
            tax=tax,
            shipping=shipping,
            total=total,
            items=[
                Item(id=f"ITEM-SPLIT-{i:03d}-A", name=f"Split Item A-{i}", unit_price=subtotal * Decimal("0.5"), quantity=1),
                Item(id=f"ITEM-SPLIT-{i:03d}-B", name=f"Split Item B-{i}", unit_price=subtotal * Decimal("0.3"), quantity=1),
                Item(id=f"ITEM-SPLIT-{i:03d}-C", name=f"Split Item C-{i}", unit_price=subtotal * Decimal("0.2"), quantity=1),
            ],
            payments=[
                PaymentMethod(
                    id=f"PAY-SPLIT-{i:03d}-CARD",
                    type=PaymentMethodType.CARD,
                    amount=card_amount,
                    currency="BRL",
                    card_last4="1111",
                ),
                PaymentMethod(
                    id=f"PAY-SPLIT-{i:03d}-WALLET",
                    type=PaymentMethodType.WALLET,
                    amount=wallet_amount,
                    currency="BRL",
                ),
            ],
            merchant_id="MERCHANT-SOLARA",
        ))

    # ── Installment transactions (TXN-INSTALL-001..005) ────────────────────

    installment_configs = [
        (3, 2),   # 3 total, 2 charged
        (6, 3),   # 6 total, 3 charged
        (6, 6),   # 6 total, 6 charged (fully charged)
        (12, 5),  # 12 total, 5 charged
        (12, 12), # 12 total, 12 charged
    ]

    for i, (total_inst, charged_inst) in enumerate(installment_configs, start=1):
        subtotal = Decimal(str(120 + i * 20))
        tax = (subtotal * Decimal("0.12")).quantize(Decimal("0.01"))
        shipping = Decimal("10.00")
        total = subtotal + tax + shipping

        txns.append(Transaction(
            id=f"TXN-INSTALL-{i:03d}",
            status=TransactionStatus.CAPTURED,
            currency="MXN",
            subtotal=subtotal,
            tax=tax,
            shipping=shipping,
            total=total,
            items=[
                Item(id=f"ITEM-INSTALL-{i:03d}-A", name=f"Installment Product A-{i}", unit_price=subtotal, quantity=1),
            ],
            payments=[
                PaymentMethod(
                    id=f"PAY-INSTALL-{i:03d}",
                    type=PaymentMethodType.CARD,
                    amount=total,
                    currency="MXN",
                    installments_total=total_inst,
                    installments_charged=charged_inst,
                    card_last4="5678",
                )
            ],
            merchant_id="MERCHANT-SOLARA",
        ))

    # ── Cross-border transactions (TXN-CROSS-001..005) ─────────────────────

    cross_configs = [
        ("BRL", Decimal("5.20")),   # BRL -> USD
        ("MXN", Decimal("17.15")),  # MXN -> USD
        ("COP", Decimal("4100.00")), # COP -> USD
        ("ARS", Decimal("900.00")),  # ARS -> USD
        ("CLP", Decimal("950.00")),  # CLP -> USD
    ]

    for i, (currency, rate) in enumerate(cross_configs, start=1):
        subtotal = Decimal(str(200 + i * 50))
        tax = (subtotal * Decimal("0.18")).quantize(Decimal("0.01"))
        shipping = Decimal("15.00")
        total = subtotal + tax + shipping

        txns.append(Transaction(
            id=f"TXN-CROSS-{i:03d}",
            status=TransactionStatus.SETTLED,
            currency=currency,
            subtotal=subtotal,
            tax=tax,
            shipping=shipping,
            total=total,
            items=[
                Item(id=f"ITEM-CROSS-{i:03d}-A", name=f"Cross-border Item A-{i}", unit_price=subtotal * Decimal("0.6"), quantity=1),
                Item(id=f"ITEM-CROSS-{i:03d}-B", name=f"Cross-border Item B-{i}", unit_price=subtotal * Decimal("0.4"), quantity=1),
            ],
            payments=[
                PaymentMethod(
                    id=f"PAY-CROSS-{i:03d}",
                    type=PaymentMethodType.CARD,
                    amount=total,
                    currency=currency,
                    card_last4="9999",
                )
            ],
            exchange_rate_to_usd=rate,
            is_cross_border=True,
            merchant_id="MERCHANT-SOLARA",
        ))

    # ── High-value transactions (TXN-HIGH-001..003) ────────────────────────

    for i in range(1, 4):
        subtotal = Decimal(str(500 + i * 100))
        tax = (subtotal * Decimal("0.20")).quantize(Decimal("0.01"))
        shipping = Decimal("25.00")
        total = subtotal + tax + shipping

        txns.append(Transaction(
            id=f"TXN-HIGH-{i:03d}",
            status=TransactionStatus.SETTLED,
            currency="USD",
            subtotal=subtotal,
            tax=tax,
            shipping=shipping,
            total=total,
            items=[
                Item(id=f"ITEM-HIGH-{i:03d}-A", name=f"High-value Item A-{i}", unit_price=subtotal * Decimal("0.7"), quantity=1),
                Item(id=f"ITEM-HIGH-{i:03d}-B", name=f"High-value Item B-{i}", unit_price=subtotal * Decimal("0.3"), quantity=1),
            ],
            payments=[
                PaymentMethod(
                    id=f"PAY-HIGH-{i:03d}",
                    type=PaymentMethodType.CARD,
                    amount=total,
                    currency="USD",
                    card_last4="0000",
                )
            ],
            merchant_id="MERCHANT-SOLARA",
        ))

    # ── Voided transactions (for rejection path testing) ───────────────────

    for i in range(1, 4):
        subtotal = Decimal("50.00")
        tax = Decimal("7.50")
        shipping = Decimal("5.00")
        total = subtotal + tax + shipping

        txns.append(Transaction(
            id=f"TXN-VOID-{i:03d}",
            status=TransactionStatus.VOIDED,
            currency="USD",
            subtotal=subtotal,
            tax=tax,
            shipping=shipping,
            total=total,
            items=[Item(id=f"ITEM-VOID-{i:03d}-A", name=f"Voided Item {i}", unit_price=subtotal, quantity=1)],
            payments=[
                PaymentMethod(id=f"PAY-VOID-{i:03d}", type=PaymentMethodType.CARD, amount=total, currency="USD", card_last4="1234")
            ],
            merchant_id="MERCHANT-SOLARA",
        ))

    # ── Chargebacked transactions (for rejection path testing) ─────────────

    for i in range(1, 4):
        subtotal = Decimal("75.00")
        tax = Decimal("11.25")
        shipping = Decimal("5.00")
        total = subtotal + tax + shipping

        txns.append(Transaction(
            id=f"TXN-CB-{i:03d}",
            status=TransactionStatus.CHARGEBACKED,
            currency="USD",
            subtotal=subtotal,
            tax=tax,
            shipping=shipping,
            total=total,
            items=[Item(id=f"ITEM-CB-{i:03d}-A", name=f"Chargebacked Item {i}", unit_price=subtotal, quantity=1)],
            payments=[
                PaymentMethod(id=f"PAY-CB-{i:03d}", type=PaymentMethodType.CARD, amount=total, currency="USD", card_last4="5678")
            ],
            merchant_id="MERCHANT-SOLARA",
        ))

    # ── Authorized (not yet captured) transactions ─────────────────────────

    for i in range(1, 3):
        subtotal = Decimal("30.00")
        tax = Decimal("4.50")
        shipping = Decimal("5.00")
        total = subtotal + tax + shipping

        txns.append(Transaction(
            id=f"TXN-AUTH-{i:03d}",
            status=TransactionStatus.AUTHORIZED,
            currency="USD",
            subtotal=subtotal,
            tax=tax,
            shipping=shipping,
            total=total,
            items=[Item(id=f"ITEM-AUTH-{i:03d}-A", name=f"Authorized Item {i}", unit_price=subtotal, quantity=1)],
            payments=[
                PaymentMethod(id=f"PAY-AUTH-{i:03d}", type=PaymentMethodType.CARD, amount=total, currency="USD", card_last4="9012")
            ],
            merchant_id="MERCHANT-SOLARA",
        ))

    return txns


if __name__ == "__main__":
    load_seed_data()
    all_txns = store.list_transactions()
    print(f"Loaded {len(all_txns)} transactions:")
    for txn in sorted(all_txns, key=lambda t: t.id):
        print(f"  {txn.id}: {txn.status.value} | {txn.currency} {txn.total}")
