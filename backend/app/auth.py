"""Authentication dependency for FastAPI.

Verifies Supabase JWTs and extracts the authenticated user ID.
The user ID is ALWAYS derived from the verified token's `sub` claim —
never from a request body, query parameter, or header value.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt

from app.config import Settings, get_settings


def _extract_bearer_token(request: Request) -> str:
    """Extract Bearer token from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHENTICATED", "message": "Missing or invalid Authorization header."},
        )
    return auth_header[7:]


def _verify_jwt(token: str, settings: Settings) -> str:
    """Verify Supabase JWT and return user_id (sub claim).

    Uses configured JWT secret for HS256 verification if set,
    or falls back to Supabase Auth client verification (per docs/API_CONTRACTS.md).
    """
    # 1. Fast local verification if JWT secret is configured
    if settings.supabase_jwt_secret:
        try:
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
            user_id = payload.get("sub")
            if user_id:
                try:
                    uuid.UUID(user_id)
                    return user_id
                except ValueError:
                    pass
        except JWTError:
            pass

    # 2. Supported Supabase verification method via Supabase client (per docs/API_CONTRACTS.md)
    try:
        from app.database import get_supabase_client
        client = get_supabase_client()
        user_response = client.auth.get_user(token)
        if user_response and user_response.user and user_response.user.id:
            user_id = user_response.user.id
            uuid.UUID(user_id)
            return user_id
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHENTICATED", "message": "Invalid or expired token."},
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "UNAUTHENTICATED", "message": "Invalid or expired token."},
    )


async def get_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    """FastAPI dependency: returns the authenticated user's UUID string.

    Usage:
        @router.get("/protected")
        async def protected(user_id: str = Depends(get_current_user)):
            ...
    """
    token = _extract_bearer_token(request)
    from app.database import set_current_request_token
    set_current_request_token(token)
    return _verify_jwt(token, settings)


# Type alias for cleaner route signatures
CurrentUser = Annotated[str, Depends(get_current_user)]
