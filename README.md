# Solara Retail — Refund Reconciliation Service

Intelligent refund processing API for LatAm e-commerce. Built with FastAPI + Python 3.12.

## Quick Start

### Option A: Local

```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload --port 9000
```

### Option B: Docker

```bash
docker compose up --build
```

API runs at `http://localhost:9000`. Developer docs at `http://localhost:8000` (run `cd fumadocs && npm run dev`).

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/refunds` | Required | Create a refund |
| GET | `/api/v1/refunds/{refund_id}` | Required | Get a refund by ID |
| GET | `/api/v1/refunds?transaction_id=` | Required | List refunds |
| GET | `/api/v1/transactions/{transaction_id}` | Required | Get a transaction |
| GET | `/api/v1/transactions` | Required | List transactions |
| GET | `/api/v1/audit?transaction_id=&refund_id=` | Required | Query audit log |

Authentication: `X-API-Key` header required on all endpoints.

---

## Refund Scenarios

### Scenario A — Full refund, single payment method
```bash
curl -X POST localhost:9000/api/v1/refunds \
  -H "X-API-Key: SOLARA-SECRET-2026" \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"TXN-REG-001","operator_id":"op1","reason":"customer request"}'
```

### Scenario B — Full refund, split payment
```bash
curl -X POST localhost:9000/api/v1/refunds \
  -H "X-API-Key: SOLARA-SECRET-2026" \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"TXN-SPLIT-001","operator_id":"op1","reason":"damaged item"}'
```

### Scenario C — Partial refund (item subset)
```bash
curl -X POST localhost:9000/api/v1/refunds \
  -H "X-API-Key: SOLARA-SECRET-2026" \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"TXN-REG-010","item_ids":["ITEM-REG-010-A"],"operator_id":"op2","reason":"wrong size"}'
```

### Scenario D — Installment refund
```bash
curl -X POST localhost:9000/api/v1/refunds \
  -H "X-API-Key: SOLARA-SECRET-2026" \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"TXN-INSTALL-001","operator_id":"op1","reason":"cancel order"}'
```

### Scenario E — Cross-border (currency conversion)
```bash
curl -X POST localhost:9000/api/v1/refunds \
  -H "X-API-Key: SOLARA-SECRET-2026" \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"TXN-CROSS-001","operator_id":"op1","reason":"item not received"}'
```

### Safe retry with idempotency
```bash
curl -X POST localhost:9000/api/v1/refunds \
  -H "X-API-Key: SOLARA-SECRET-2026" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: refund-req-20260225-001" \
  -d '{"transaction_id":"TXN-REG-001","operator_id":"op1","reason":"customer request"}'
# First call: 201 Created
# Retry with same key: 200 OK + Idempotent-Replayed: true
```

### Rejected: chargeback transaction
```bash
curl -X POST localhost:9000/api/v1/refunds \
  -H "X-API-Key: SOLARA-SECRET-2026" \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"TXN-CB-001","operator_id":"op1","reason":"refund attempt"}'
# Expected: 422 INVALID_TRANSACTION_STATUS
```

### Audit trail
```bash
curl localhost:9000/api/v1/audit?transaction_id=TXN-SPLIT-001 \
  -H "X-API-Key: SOLARA-SECRET-2026"
```

---

## Running Tests

```bash
# Full suite with coverage requirements
pytest --cov=app/engine --cov=app/validators --cov-fail-under=100 -v

# Regression suite only
pytest -m regression -v

# Security tests only
pytest tests/integration/test_security.py -v

# Dependency vulnerability scan
pip install pip-audit && pip-audit
```

---

## Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `TRANSACTION_NOT_FOUND` | 404 | Transaction does not exist |
| `INVALID_TRANSACTION_STATUS` | 422 | Status does not allow refund (VOIDED, CHARGEBACKED, AUTHORIZED) |
| `DUPLICATE_REFUND` | 409 | A full refund already exists for this transaction |
| `INVALID_ITEM_IDS` | 422 | One or more item IDs not found in transaction |
| `REFUND_AMOUNT_EXCEEDED` | 422 | Refund exceeds remaining refundable balance |
| `INSTALLMENT_NOT_CHARGED` | 422 | No installments charged yet |
| `UNAUTHORIZED` | 401 | Missing or invalid API key |
| `CALCULATION_ERROR` | 422 | Financial guard triggered (e.g., zero division) |
| `RATE_LIMITED` | 429 | Too many failed auth attempts |
| `REQUEST_TOO_LARGE` | 413 | Body exceeds 64KB limit |
| `INTERNAL_ERROR` | 500 | Unexpected server error (no details leaked) |

---

## Business Assumptions

1. **Refund only on CAPTURED or SETTLED**: `AUTHORIZED`, `VOIDED`, and `CHARGEBACKED` transactions are rejected with explicit reasons.
2. **Split payment distribution**: Refund is distributed proportionally to each payment method's original weight (`payment.amount / transaction.total`).
3. **Original exchange rate**: Cross-border refunds always use the exchange rate stored at purchase time, never a live rate.
4. **Installments**: Only charged installments are refundable. `installment_value = payment.amount / installments_total`.
5. **Partial refund**: Tax and shipping are refunded proportionally to the item ratio (`items_subtotal / transaction.subtotal`).
6. **All math uses `decimal.Decimal`**: Never `float`. Rounding is `ROUND_HALF_UP` to 2 decimal places at final output only.
7. **Audit log is append-only**: No entry can be modified or deleted.
8. **HTTPS required in production**: Deploy behind a TLS-terminating reverse proxy. The `Strict-Transport-Security` header is added automatically when `APP_ENV=production`.

---

## Operation Taxonomy

This service handles **refunds only**. Do not confuse with:

| Operation | Who initiates | Money direction | Handled here? |
|-----------|--------------|-----------------|---------------|
| Purchase / Authorization | Merchant | Customer → Merchant | No |
| Capture | Merchant | Completes authorization | No |
| **Refund** | Merchant | Merchant → Customer | **Yes** |
| Chargeback | Card network / bank | Forced reversal | No |
| Void / Cancel | Merchant (pre-capture) | Authorization reversal | No |

---

## Security

- OWASP Top 10 hardening applied (A01–A09; A10 N/A — no outbound HTTP calls)
- API key via `X-API-Key` header only (never in URL or logs)
- `hmac.compare_digest` prevents timing attacks
- Rate limiting: 5 failed auth attempts → 429 for 60 seconds
- 64KB request body limit
- `extra="forbid"` on all Pydantic models (mass-assignment protection)
- Idempotency via `Idempotency-Key` header — replays return `200` + `Idempotent-Replayed: true`
- Thread-safe in-memory store with `threading.Lock`
- Production mode disables `/docs`, `/redoc`, and stack traces
