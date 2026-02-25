"""Audit endpoints — GET /api/v1/audit"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Request
from app.services.audit_service import get_audit_entries
from app.security.auth import require_api_key

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


def _envelope(data, request: Request) -> dict:
    return {
        "data": data,
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
    }


@router.get("")
async def get_audit(
    transaction_id: Optional[str] = None,
    refund_id: Optional[str] = None,
    request: Request = None,
    _: str = Depends(require_api_key),
) -> dict:
    """Retrieve audit log entries, optionally filtered by transaction_id or refund_id."""
    entries = get_audit_entries(transaction_id=transaction_id, refund_id=refund_id)
    return _envelope([e.model_dump(mode="json") for e in entries], request)
