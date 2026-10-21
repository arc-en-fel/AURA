"""CRM CRUD routes.

Endpoints:
- POST /api/v1/crm/generate  — Generate a draft CRM configuration
- POST /api/v1/crm           — Save a validated CRM
- GET  /api/v1/crm           — List user's CRMs
- GET  /api/v1/crm/{crm_id}  — Get a single CRM
- PATCH /api/v1/crm/{crm_id}/configuration — Update CRM metadata
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError

from app.auth import CurrentUser
from app.config import get_settings, Settings
from app.database import CRMRepository
from app.routers.responses import success_response, error_response
from app.schemas.crm import (
    CRMConfiguration,
    GenerateCRMRequest,
    SaveCRMRequest,
)
from app.services.ai_provider import get_ai_provider

router = APIRouter(prefix="/crm", tags=["CRM"])


def _get_repo() -> CRMRepository:
    return CRMRepository()


@router.post("/generate")
async def generate_crm(
    body: GenerateCRMRequest,
    user_id: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
):
    """Generate a draft CRM configuration from a natural-language description.

    The configuration is NOT saved — the user must review and explicitly save it.
    """
    try:
        provider = get_ai_provider(settings.llm_provider)
        config_dict = provider.generate_crm_config(body.prompt)
        # Validate with Pydantic
        config = CRMConfiguration(**config_dict)
        # Forward any provider warnings (e.g. fallback indicator) to the caller
        warnings = list(getattr(provider, "last_warnings", []))
        return success_response({
            "configuration": config.model_dump(),
            "warnings": warnings,
        })
    except ValidationError as exc:
        return error_response(422, "VALIDATION_ERROR", "Generated configuration failed validation.", [
            {"field": str(e["loc"]), "issue": e["msg"]} for e in exc.errors()
        ])
    except ValueError as exc:
        return error_response(502, "AI_PROVIDER_ERROR", str(exc))
    except Exception:
        return error_response(502, "AI_PROVIDER_ERROR", "AI provider failed to generate configuration.")


@router.post("")
async def create_crm(body: SaveCRMRequest, user_id: CurrentUser):
    """Save a validated CRM configuration. Owner is derived from JWT."""
    repo = _get_repo()
    try:
        crm = repo.create_crm(
            owner_id=user_id,
            name=body.configuration.name,
            configuration=body.configuration.model_dump(),
        )
        return success_response(
            {
                "crm_id": crm["id"],
                "name": crm["name"],
                "status": crm["status"],
                "configuration_version": crm["configuration_version"],
                "configuration": crm["configuration"],
            },
            status_code=201,
        )
    except Exception:
        return error_response(500, "INTERNAL_ERROR", "Failed to create CRM.")


@router.get("")
async def list_crms(
    user_id: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List CRMs owned by the authenticated user."""
    repo = _get_repo()
    try:
        items, total = repo.list_crms(user_id, limit=limit, offset=offset)
        return success_response({
            "items": [
                {
                    "crm_id": c["id"],
                    "name": c["name"],
                    "status": c["status"],
                    "configuration_version": c["configuration_version"],
                    "configuration": c["configuration"],
                }
                for c in items
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        })
    except Exception:
        return error_response(500, "INTERNAL_ERROR", "Failed to list CRMs.")


@router.get("/{crm_id}")
async def get_crm(crm_id: UUID, user_id: CurrentUser):
    """Get a single CRM by ID. Returns 404 if missing or not owned by caller."""
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")
    return success_response({
        "crm_id": crm["id"],
        "name": crm["name"],
        "status": crm["status"],
        "configuration_version": crm["configuration_version"],
        "configuration": crm["configuration"],
    })


@router.patch("/{crm_id}/configuration")
async def update_crm_configuration(crm_id: UUID, user_id: CurrentUser):
    """Update CRM metadata. Schema/workflow changes must go through evolution proposals."""
    # For the MVP, this endpoint only allows safe metadata updates.
    # Full configuration changes require the evolution proposal flow.
    return error_response(
        403,
        "FORBIDDEN",
        "Configuration changes must go through the evolution proposal approval process.",
    )
