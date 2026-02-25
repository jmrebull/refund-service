"""Refund endpoints — POST /api/v1/refunds, GET /api/v1/refunds/{id}, GET /api/v1/refunds"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from app.models.refund import RefundRequest, RefundResult
from app.security.auth import require_api_key
from app.services.refund_service import process_refund, get_refund, list_refunds
from app.validators.refund_validator import ValidationError

router = APIRouter(prefix="/api/v1/refunds", tags=["refunds"])


def _envelope(data, request: Request) -> dict:
    return {
        "data": data,
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
    }


def _validation_error_to_http(exc: ValidationError):
    raise HTTPException(
        status_code=exc.http_status,
        detail={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_refund(
    body: RefundRequest,
    request: Request,
    _: str = Depends(require_api_key),
) -> dict:
    """Create a new refund for a captured or settled transaction."""
    request_id = getattr(request.state, "request_id", "unknown")
    try:
        result = process_refund(body, request_id)
    except ValidationError as exc:
        _validation_error_to_http(exc)

    return _envelope(result.model_dump(mode="json"), request)


@router.get("/{refund_id}")
async def get_refund_by_id(
    refund_id: str,
    request: Request,
    _: str = Depends(require_api_key),
) -> dict:
    """Retrieve a single refund by its ID."""
    result = get_refund(refund_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "REFUND_NOT_FOUND", "message": f"Refund {refund_id} not found"}},
        )
    return _envelope(result.model_dump(mode="json"), request)


@router.get("")
async def list_refunds_endpoint(
    transaction_id: Optional[str] = None,
    request: Request = None,
    _: str = Depends(require_api_key),
) -> dict:
    """List all refunds, optionally filtered by transaction_id."""
    results = list_refunds(transaction_id=transaction_id)
    return _envelope([r.model_dump(mode="json") for r in results], request)
