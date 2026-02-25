"""Shared fixtures for all test modules."""
import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_KEY", "TEST-KEY-2026")
os.environ.setdefault("APP_ENV", "development")

from app.main import app
from app.repository.store import store
from seed_data import load_seed_data


@pytest.fixture(autouse=True)
def reset_store():
    """Reset in-memory store before each test to ensure isolation."""
    from app.repository.store import InMemoryStore
    # Replace the store's internal state
    new_store = InMemoryStore()
    store._transactions = new_store._transactions
    store._refunds = new_store._refunds
    store._refunds_by_transaction = new_store._refunds_by_transaction
    store._idempotency_keys = new_store._idempotency_keys
    store._audit_log = new_store._audit_log
    load_seed_data()
    # Reset rate limiter so auth failure tests don't affect subsequent tests
    from app.middleware.rate_limit import _instance as rate_limiter
    if rate_limiter is not None:
        rate_limiter.reset()
    yield


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_headers():
    return {"X-API-Key": "TEST-KEY-2026"}
