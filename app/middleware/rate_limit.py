import time
import threading
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


# Module-level reference to the active instance, used by tests to reset state.
_instance: "RateLimitMiddleware | None" = None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """OWASP A07: Per-IP rate limiting. After 5 failed auth attempts, block for 60 seconds."""

    WINDOW_SECONDS = 60
    MAX_FAILURES = 5

    def __init__(self, app):
        super().__init__(app)
        self._lock = threading.Lock()
        # ip -> {"count": int, "blocked_until": float}
        self._failures: dict = defaultdict(lambda: {"count": 0, "blocked_until": 0.0})
        global _instance
        _instance = self

    def reset(self) -> None:
        """Reset all tracked failures — intended for test isolation only."""
        with self._lock:
            self._failures.clear()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def record_auth_failure(self, ip: str) -> None:
        with self._lock:
            entry = self._failures[ip]
            entry["count"] += 1
            if entry["count"] >= self.MAX_FAILURES:
                entry["blocked_until"] = time.time() + self.WINDOW_SECONDS

    def is_blocked(self, ip: str) -> bool:
        with self._lock:
            entry = self._failures[ip]
            if entry["blocked_until"] > time.time():
                return True
            if entry["blocked_until"] > 0 and entry["blocked_until"] <= time.time():
                # Reset after block window expires
                entry["count"] = 0
                entry["blocked_until"] = 0.0
            return False

    def record_auth_success(self, ip: str) -> None:
        with self._lock:
            self._failures[ip] = {"count": 0, "blocked_until": 0.0}

    async def dispatch(self, request: Request, call_next):
        ip = self._get_client_ip(request)

        if self.is_blocked(ip):
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "Too many failed authentication attempts. Try again later.",
                    }
                },
            )

        response = await call_next(request)

        # Track auth failures for POST endpoints
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if response.status_code == 401:
                self.record_auth_failure(ip)
            elif response.status_code < 400:
                self.record_auth_success(ip)

        return response
