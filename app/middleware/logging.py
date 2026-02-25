import time
import json
import logging
from datetime import datetime, timezone
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("access")


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """OWASP A09: Emit structured JSON access log on every request. Never logs API key value."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.monotonic()
        request_id = getattr(request.state, "request_id", "unknown")

        # Determine auth outcome without logging the key itself
        has_api_key = "X-API-Key" in request.headers
        auth_outcome = "present" if has_api_key else "missing"

        response = await call_next(request)

        duration_ms = round((time.monotonic() - start) * 1000)

        if response.status_code == 401:
            auth_outcome = "failed"
        elif has_api_key and response.status_code < 400:
            auth_outcome = "ok"

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "method": request.method,
            "path": str(request.url.path),
            "status_code": response.status_code,
            "ip": request.client.host if request.client else "unknown",
            "duration_ms": duration_ms,
            "auth": auth_outcome,
        }
        print(json.dumps(log_entry), flush=True)

        return response
