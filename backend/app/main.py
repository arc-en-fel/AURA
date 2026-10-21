"""FastAPI application entry point for the Self-Evolving CRM.

Start locally with: uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import crm, records, workflows, evolution, chat, copilot
from app.routers.responses import success_response, error_response

import uuid


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Self-Evolving CRM — AI-powered, multi-tenant CRM platform",
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routers under /api/v1
    api_prefix = "/api/v1"
    app.include_router(crm.router, prefix=api_prefix)
    app.include_router(records.router, prefix=api_prefix)
    app.include_router(workflows.router, prefix=api_prefix)
    app.include_router(evolution.router, prefix=api_prefix)
    app.include_router(chat.router, prefix=api_prefix)
    app.include_router(copilot.router, prefix=api_prefix)

    def _health_payload() -> dict[str, str]:
        return {
            "status": "ok",
            "app_name": settings.app_name,
            "version": "0.1.0",
            "environment": "development" if settings.debug else "production",
            "database": "configured" if settings.supabase_url and "localhost" not in settings.supabase_url else "unconfigured",
            "auth": "configured" if settings.supabase_jwt_secret or (settings.supabase_anon_key and settings.supabase_anon_key != "mock-anon-key") else "demo",
        }

    # Health checks
    @app.get("/health", tags=["Health"])
    async def root_health():
        return success_response(_health_payload())

    @app.get(f"{api_prefix}/health", tags=["Health"])
    async def health_check():
        return success_response(_health_payload())

    from fastapi import HTTPException

    # HTTP exception handler
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if isinstance(exc.detail, dict):
            code = exc.detail.get("code", "ERROR")
            message = exc.detail.get("message", "An error occurred.")
            details = exc.detail.get("details", [])
            return error_response(exc.status_code, code, message, details)
        return error_response(exc.status_code, "ERROR", str(exc.detail))

    # Global exception handler — never leak secrets or stack traces
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return error_response(500, "INTERNAL_ERROR", "An unexpected error occurred.")

    # Validation error handler
    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        details = []
        for err in exc.errors():
            loc = " -> ".join(str(l) for l in err.get("loc", []))
            details.append({"field": loc, "issue": err.get("msg", "")})
        return error_response(422, "VALIDATION_ERROR", "Request validation failed.", details)

    return app


app = create_app()
