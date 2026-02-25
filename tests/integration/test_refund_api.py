"""Integration tests — full HTTP cycle per scenario."""
import pytest
from fastapi.testclient import TestClient


def test_scenario_a_full_single_method(client, auth_headers):
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-REG-001", "operator_id": "op1", "reason": "customer request"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["operation_type"] == "REFUND"
    assert data["status"] == "APPROVED"
    assert "calculation_breakdown" in data
    assert data["calculation_breakdown"]["payment_breakdown"] is not None


def test_scenario_b_full_split_payment(client, auth_headers):
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-SPLIT-001", "operator_id": "op1", "reason": "damaged item"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert len(data["calculation_breakdown"]["payment_breakdown"]) == 2
    total = sum(float(p["refund_amount"]) for p in data["calculation_breakdown"]["payment_breakdown"])
    assert abs(total - float(data["total_refund_amount"])) < 0.02


def test_scenario_c_partial_refund(client, auth_headers):
    from app.repository.store import store
    txn = store.get_transaction("TXN-REG-010")
    item_id = txn.items[0].id
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-REG-010", "item_ids": [item_id], "operator_id": "op2", "reason": "wrong size"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    bd = data["calculation_breakdown"]
    assert bd["item_ratio"] is not None
    assert bd["proportional_tax"] is not None
    assert float(data["total_refund_amount"]) < float(store.get_transaction("TXN-REG-010").total)


def test_scenario_d_installment_refund(client, auth_headers):
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-INSTALL-001", "operator_id": "op1", "reason": "cancel order"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    bd = data["calculation_breakdown"]
    assert bd["installments_charged"] is not None
    assert bd["installments_total"] is not None
    assert bd["installments_charged"] <= bd["installments_total"]


def test_scenario_e_cross_border(client, auth_headers):
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-CROSS-001", "operator_id": "op1", "reason": "item not received"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    bd = data["calculation_breakdown"]
    assert bd["usd_equivalent"] is not None
    assert bd["exchange_rate_used"] is not None


def test_get_refund_by_id(client, auth_headers):
    create_resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-REG-002", "operator_id": "op1", "reason": "test"},
        headers=auth_headers,
    )
    refund_id = create_resp.json()["data"]["refund_id"]
    get_resp = client.get(f"/api/v1/refunds/{refund_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["refund_id"] == refund_id


def test_get_refunds_by_transaction(client, auth_headers):
    client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-REG-003", "operator_id": "op1", "reason": "test"},
        headers=auth_headers,
    )
    resp = client.get("/api/v1/refunds?transaction_id=TXN-REG-003")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) >= 1


def test_refund_not_found(client):
    resp = client.get("/api/v1/refunds/RF-NONEXISTENT")
    assert resp.status_code == 404


def test_response_envelope_structure(client, auth_headers):
    resp = client.post(
        "/api/v1/refunds",
        json={"transaction_id": "TXN-REG-004", "operator_id": "op1", "reason": "test"},
        headers=auth_headers,
    )
    body = resp.json()
    assert "data" in body
    assert "meta" in body
    assert "timestamp" in body["meta"]
    assert "request_id" in body["meta"]
