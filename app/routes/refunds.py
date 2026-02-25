"""Refund endpoints — POST /api/v1/refunds, GET /api/v1/refunds/{id}, GET /api/v1/refunds"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
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
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    _: str = Depends(require_api_key),
) -> Response:
    """Create a new refund for a captured or settled transaction.

    Send an Idempotency-Key header to safely retry without double-processing.
    Replayed responses include the Idempotent-Replayed: true header and return 200.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    try:
        result, was_replayed = process_refund(body, request_id, idempotency_key)
    except ValidationError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    response_body = _envelope(result.model_dump(mode="json"), request)
    status_code = status.HTTP_200_OK if was_replayed else status.HTTP_201_CREATED
    headers = {"Idempotent-Replayed": "true"} if was_replayed else {}
    return JSONResponse(content=response_body, status_code=status_code, headers=headers)


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
