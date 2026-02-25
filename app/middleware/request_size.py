from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RequestSizeMiddleware(BaseHTTPMiddleware):
    """OWASP A03: Reject request bodies exceeding max_bytes (default 64KB)."""

    def __init__(self, app, max_bytes: int = 65536):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "REQUEST_TOO_LARGE",
                        "message": f"Request body exceeds the {self.max_bytes} byte limit",
                    }
                },
            )
        return await call_next(request)
