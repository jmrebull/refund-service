"""
FastAPI application entry point.

Registers middleware (in order), routes, exception handlers,
and mounts the static developer docs.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.config import is_production, get_cors_origins
from app.middleware import (
    SecurityHeadersMiddleware,
    RequestSizeMiddleware,
    RateLimitMiddleware,
    RequestIDMiddleware,
    StructuredLoggingMiddleware,
)
from app.routes.refunds import router as refunds_router
from app.routes.transactions import router as transactions_router
from app.routes.audit import router as audit_router
from seed_data import load_seed_data


def create_app() -> FastAPI:
    docs_url = None if is_production() else "/docs"
    redoc_url = None if is_production() else "/redoc"

    application = FastAPI(
        title="Solara Retail — Refund Reconciliation Service",
        description="Intelligent refund processing for LatAm e-commerce.",
        version="1.0.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
    )

    # ── Middleware stack (order matters) ────────────────────────────────────
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(RequestSizeMiddleware, max_bytes=65536)
    application.add_middleware(RateLimitMiddleware)
    application.add_middleware(RequestIDMiddleware)
    application.add_middleware(StructuredLoggingMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key", "X-Request-ID", "Idempotency-Key"],
    )

    # ── Routes ──────────────────────────────────────────────────────────────
    application.include_router(refunds_router)
    application.include_router(transactions_router)
    application.include_router(audit_router)

    # ── Developer docs (static) ─────────────────────────────────────────────
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
    if os.path.isdir(docs_dir):
        application.mount("/developer", StaticFiles(directory=docs_dir, html=True), name="developer-docs")

    # ── Exception handlers ───────────────────────────────────────────────────
    @application.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        """OWASP A05: Never leak stack traces to clients."""
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"}},
        )

    # ── Startup ──────────────────────────────────────────────────────────────
    @application.on_event("startup")
    async def on_startup():
        load_seed_data()

    return application


app = create_app()
