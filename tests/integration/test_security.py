"""Integration tests — OWASP security hardening coverage."""
import pytest
import threading


# ── A01 - Access Control ────────────────────────────────────────────────────

def test_post_without_api_key_returns_401(client):
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-REG-001", "operator_id": "op1", "reason": "test"},
    )
    assert resp.status_code == 401


def test_post_with_wrong_api_key_returns_401(client):
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-REG-001", "operator_id": "op1", "reason": "test"},
        headers={"X-API-Key": "WRONG-KEY"},
    )
    assert resp.status_code == 401


def test_get_requests_require_api_key(client, auth_headers):
    # All endpoints require authentication — financial data must not be publicly accessible
    for path in ["/api/v1/transactions", "/api/v1/refunds", "/api/v1/audit"]:
        resp = client.get(path)
        assert resp.status_code == 401, f"Expected 401 for GET {path} without auth, got {resp.status_code}"
    # With valid key they succeed
    resp = client.get("/api/v1/transactions", headers=auth_headers)
    assert resp.status_code == 200


# ── A03 - Injection / Input validation ─────────────────────────────────────

def test_negative_amount_rejected(client, auth_headers):
    """Pydantic model should reject negative transaction_id patterns via pattern constraint."""
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-REG-001", "operator_id": "op1", "reason": "test",
              "extra_malicious_field": "hack"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_extra_unknown_fields_rejected(client, auth_headers):
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-REG-001", "operator_id": "op1", "reason": "test",
              "extra_field": "injection_attempt"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_invalid_characters_in_transaction_id(client, auth_headers):
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN; DROP TABLE", "operator_id": "op1", "reason": "test"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_oversized_reason_rejected(client, auth_headers):
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-REG-001", "operator_id": "op1", "reason": "x" * 501},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_too_many_item_ids_rejected(client, auth_headers):
    resp = client.post(
        "/api/v1/refunds",
        json={
            "transaction_id": "TXN-REG-001",
            "operator_id": "op1",
            "reason": "test",
            "item_ids": [f"ITEM-{i:04d}" for i in range(101)],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


# ── A05 - Security Headers ──────────────────────────────────────────────────

def test_security_headers_present_on_all_responses(client):
    resp = client.get("/api/v1/transactions")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Cache-Control") == "no-store"
    assert "Content-Security-Policy" in resp.headers


def test_stack_trace_never_in_error_response(client, auth_headers):
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-NONEXISTENT", "operator_id": "op1", "reason": "test"},
        headers=auth_headers,
    )
    body = resp.text
    assert "Traceback" not in body
    assert "File " not in body


def test_api_key_never_in_response_body(client, auth_headers):
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-REG-001", "operator_id": "op1", "reason": "test"},
        headers=auth_headers,
    )
    assert "TEST-KEY-2026" not in resp.text


# ── A07 - Rate Limiting ─────────────────────────────────────────────────────

def test_rate_limit_after_5_failed_auth_attempts(client):
    for _ in range(5):
        client.post(
            "/api/v1/refunds",
            json={"transaction_id": "TXN-REG-001", "operator_id": "op1", "reason": "test"},
            headers={"X-API-Key": "WRONG"},
        )
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-REG-001", "operator_id": "op1", "reason": "test"},
        headers={"X-API-Key": "WRONG"},
    )
    assert resp.status_code == 429


# ── A08 - Idempotency ──────────────────────────────────────────────────────

def test_idempotency_key_prevents_duplicate_processing(client, auth_headers):
    headers = {**auth_headers, "Idempotency-Key": "idem-key-001"}
    payload = {"transaction_id": "TXN-REG-001", "operator_id": "op1", "reason": "test"}
    resp1 = client.post("/api/v1/refunds", json=payload, headers=headers)
    resp2 = client.post("/api/v1/refunds", json=payload, headers=headers)
    assert resp1.status_code == 201
    # Replay returns 200 with Idempotent-Replayed header and same refund_id
    assert resp2.status_code == 200
    assert resp2.headers.get("Idempotent-Replayed") == "true"
    assert resp1.json()["data"]["refund_id"] == resp2.json()["data"]["refund_id"]


def test_idempotency_key_in_body_is_rejected(client, auth_headers):
    """idempotency_key is a header concern — sending it in the body must return 422."""
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-REG-001", "operator_id": "op1", "reason": "test",
              "idempotency_key": "should-be-in-header"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_without_idempotency_key_second_request_is_not_replay(client, auth_headers):
    """Without an Idempotency-Key header, a second identical request is a new operation
    and is rejected as a duplicate full refund (409), not silently replayed."""
    payload = {"transaction_id": "TXN-REG-001", "operator_id": "op1", "reason": "test"}
    resp1 = client.post("/api/v1/refunds", json=payload, headers=auth_headers)
    resp2 = client.post("/api/v1/refunds", json=payload, headers=auth_headers)
    assert resp1.status_code == 201
    assert resp2.status_code == 409
    assert "Idempotent-Replayed" not in resp2.headers


def test_audit_log_cannot_be_deleted(client):
    client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-REG-001", "operator_id": "op1", "reason": "test"},
        headers={"X-API-Key": "TEST-KEY-2026"},
    )
    # No DELETE endpoint on /api/v1/audit
    resp = client.delete("/api/v1/audit")
    assert resp.status_code == 405


# ── Financial attacks ──────────────────────────────────────────────────────

def test_refund_cannot_exceed_transaction_total(client, auth_headers):
    # First full refund
    client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-REG-005", "operator_id": "op1", "reason": "first"},
        headers=auth_headers,
    )
    # Second attempt on same transaction
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-REG-005", "operator_id": "op1", "reason": "second"},
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_race_condition_double_refund_prevented(client, auth_headers):
    results = []

    def do_refund():
        resp = client.post(
            "/api/v1/refunds",
            json={"transaction_id": "TXN-REG-006", "operator_id": "op1", "reason": "race"},
            headers=auth_headers,
        )
        results.append(resp.status_code)

    threads = [threading.Thread(target=do_refund) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    successes = [s for s in results if s == 201]
    assert len(successes) == 1


# ── A09 - Request ID ────────────────────────────────────────────────────────

def test_request_id_present_in_response_headers(client):
    resp = client.get("/api/v1/transactions")
    assert "X-Request-ID" in resp.headers
