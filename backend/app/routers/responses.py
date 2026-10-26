"""Response helpers for consistent API envelopes."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi.responses import JSONResponse


def success_response(data: Any, status_code: int = 200) -> JSONResponse:
    """Build a SuccessEnvelope response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "data": data,
            "meta": {"request_id": f"req_{uuid.uuid4().hex[:12]}"},
        },
    )


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    response_source: str | None = None,
    ai: dict[str, Any] | None = None,
    routing: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build an ErrorEnvelope response."""
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "details": details or [],
        "request_id": f"req_{uuid.uuid4().hex[:12]}",
    }
    if response_source:
        error["response_source"] = response_source
    if ai is not None:
        error["ai"] = ai
    if routing is not None:
        error["routing"] = routing
    return JSONResponse(
        status_code=status_code,
        content={"error": error, **({"meta": meta} if meta else {})},
    )
