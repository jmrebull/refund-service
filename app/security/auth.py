import hmac
from typing import Optional
from fastapi import Header, HTTPException, status
from app.config import API_KEY

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid or missing API key"}},
)


async def require_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> str:
    """Verify API key using constant-time comparison to prevent timing attacks."""
    if not x_api_key:
        raise _UNAUTHORIZED
    if not hmac.compare_digest(x_api_key.encode(), API_KEY.encode()):
        raise _UNAUTHORIZED
    return x_api_key
