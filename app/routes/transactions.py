"""Transaction endpoints — GET /api/v1/transactions/{id}, GET /api/v1/transactions"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, status
from app.repository.store import store

router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])


def _envelope(data, request: Request) -> dict:
    return {
        "data": data,
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
    }


@router.get("/{transaction_id}")
async def get_transaction(transaction_id: str, request: Request) -> dict:
    """Retrieve a single transaction by its ID."""
    txn = store.get_transaction(transaction_id)
    if txn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "TRANSACTION_NOT_FOUND", "message": f"Transaction {transaction_id} not found"}},
        )
    return _envelope(txn.model_dump(mode="json"), request)


@router.get("")
async def list_transactions(request: Request) -> dict:
    """List all transactions."""
    txns = store.list_transactions()
    return _envelope([t.model_dump(mode="json") for t in txns], request)
