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
from pydantic import ValidationError, BaseModel, Field

from app.auth import CurrentUser
from app.config import get_settings, Settings
from app.database import CRMRepository
from app.routers.responses import success_response, error_response
from app.schemas.crm import (
    CRMConfiguration,
    GenerateCRMRequest,
    SaveCRMRequest,
    StrictModel,
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
    
    Process:
    1. AI generates initial schema
    2. Extract all user-requested fields from prompt
    3. Validate that all fields are preserved
    4. Repair missing fields if needed
    5. Return final configuration
    """
    from app.services.schema_preservation import SchemaPreservation
    from app.services.field_extractor import FieldExtractor
    
    try:
        provider = get_ai_provider(settings.llm_provider)
        config_dict = provider.generate_crm_config(body.prompt)
        
        # STEP 1: Preserve all user-requested fields
        config_dict = SchemaPreservation.validate_and_repair_schema(
            config_dict,
            body.prompt
        )
        
        # STEP 2: Analyze field coverage
        extracted_fields = FieldExtractor.extract_fields_from_prompt(body.prompt)
        coverage = SchemaPreservation.compare_field_counts(
            config_dict,
            len(extracted_fields)
        )
        
        # Validate with Pydantic
        config = CRMConfiguration(**config_dict)
        
        # Forward any provider warnings
        warnings = list(getattr(provider, "last_warnings", []))
        
        # Add field preservation info to warnings
        if not coverage["ok"]:
            warnings.append(
                f"Schema preservation: {coverage['reason']} "
                f"(generated {coverage['generated_count']}, user requested {coverage['extracted_count']})"
            )
        
        return success_response({
            "configuration": config.model_dump(),
            "warnings": warnings,
            "field_analysis": coverage,
        })
    except ValidationError as exc:
        return error_response(422, "VALIDATION_ERROR", "Generated configuration failed validation.", [
            {"field": str(e["loc"]), "issue": e["msg"]} for e in exc.errors()
        ])
    except ValueError as exc:
        return error_response(502, "AI_PROVIDER_ERROR", str(exc))
    except Exception as exc:
        import traceback
        traceback.print_exc()
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


# ─────────────────────────────────────────────────────────────────────────────
# POST-GENERATION CRM EDITING ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────
# These endpoints allow direct schema editing after CRM generation.
# They work for ANY CRM type — no hardcoded CRM-specific logic.


class EditFieldRequest(StrictModel):
    entity_name: str = Field(default="lead", min_length=1, max_length=64)
    field_name: str = Field(min_length=1, max_length=64)
    label: str | None = None
    field_type: str | None = None
    required: bool | None = None
    options: list[str] | None = None


class AddFieldRequest(StrictModel):
    entity_name: str = Field(default="lead", min_length=1, max_length=64)
    field_name: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=100)
    field_type: str = Field(default="text")
    required: bool = False
    options: list[str] | None = None


class EditPipelineStageRequest(StrictModel):
    old_stage_name: str = Field(min_length=1, max_length=100)
    new_stage_name: str = Field(min_length=1, max_length=100)


class AddPipelineStageRequest(StrictModel):
    stage_name: str = Field(min_length=1, max_length=100)
    position: int | None = None


@router.post("/{crm_id}/field/add")
async def add_field(
    crm_id: UUID,
    body: AddFieldRequest,
    user_id: CurrentUser,
):
    """Add a new field to a CRM entity.
    
    Works for any CRM type. Field is added to the specified entity.
    """
    from app.services.crm_editor import CRMSchemaEditor
    
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")
    
    try:
        updated_config = CRMSchemaEditor.add_field(
            crm["configuration"],
            entity_name=body.entity_name,
            field_name=body.field_name,
            field_label=body.label,
            field_type=body.field_type,  # type: ignore
            required=body.required,
            options=body.options,
        )
        
        # Save updated configuration
        crm = repo.update_crm_configuration(
            crm_id=str(crm_id),
            owner_id=user_id,
            configuration=updated_config,
        )
        
        return success_response({
            "crm_id": crm["id"],
            "configuration": crm["configuration"],
            "configuration_version": crm["configuration_version"],
        })
    except ValueError as exc:
        return error_response(400, "VALIDATION_ERROR", str(exc))
    except Exception as exc:
        return error_response(500, "INTERNAL_ERROR", f"Failed to add field: {exc}")


@router.patch("/{crm_id}/field/{field_name}")
async def update_field(
    crm_id: UUID,
    field_name: str,
    body: EditFieldRequest,
    user_id: CurrentUser,
):
    """Update a field in a CRM entity."""
    from app.services.crm_editor import CRMSchemaEditor
    
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")
    
    try:
        updated_config = CRMSchemaEditor.update_field(
            crm["configuration"],
            entity_name=body.entity_name,
            field_name=field_name,
            label=body.label,
            field_type=body.field_type,  # type: ignore
            required=body.required,
            options=body.options,
        )
        
        crm = repo.update_crm_configuration(
            crm_id=str(crm_id),
            owner_id=user_id,
            configuration=updated_config,
        )
        
        return success_response({
            "crm_id": crm["id"],
            "configuration": crm["configuration"],
            "configuration_version": crm["configuration_version"],
        })
    except ValueError as exc:
        return error_response(400, "VALIDATION_ERROR", str(exc))
    except Exception as exc:
        return error_response(500, "INTERNAL_ERROR", f"Failed to update field: {exc}")


@router.delete("/{crm_id}/field/{field_name}")
async def delete_field(
    crm_id: UUID,
    field_name: str,
    entity_name: str = "lead",
    user_id: CurrentUser = None,
):
    """Delete a field from a CRM entity."""
    from app.services.crm_editor import CRMSchemaEditor
    
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")
    
    try:
        updated_config = CRMSchemaEditor.delete_field(
            crm["configuration"],
            entity_name=entity_name,
            field_name=field_name,
        )
        
        crm = repo.update_crm_configuration(
            crm_id=str(crm_id),
            owner_id=user_id,
            configuration=updated_config,
        )
        
        return success_response({
            "crm_id": crm["id"],
            "configuration": crm["configuration"],
            "configuration_version": crm["configuration_version"],
        })
    except ValueError as exc:
        return error_response(400, "VALIDATION_ERROR", str(exc))
    except Exception as exc:
        return error_response(500, "INTERNAL_ERROR", f"Failed to delete field: {exc}")


@router.post("/{crm_id}/stage/add")
async def add_pipeline_stage(
    crm_id: UUID,
    body: AddPipelineStageRequest,
    user_id: CurrentUser,
):
    """Add a new pipeline stage to the CRM."""
    from app.services.crm_editor import CRMSchemaEditor
    
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")
    
    try:
        updated_config = CRMSchemaEditor.add_pipeline_stage(
            crm["configuration"],
            stage_name=body.stage_name,
            position=body.position,
        )
        
        crm = repo.update_crm_configuration(
            crm_id=str(crm_id),
            owner_id=user_id,
            configuration=updated_config,
        )
        
        return success_response({
            "crm_id": crm["id"],
            "configuration": crm["configuration"],
            "configuration_version": crm["configuration_version"],
        })
    except ValueError as exc:
        return error_response(400, "VALIDATION_ERROR", str(exc))
    except Exception as exc:
        return error_response(500, "INTERNAL_ERROR", f"Failed to add stage: {exc}")


@router.patch("/{crm_id}/stage/{old_stage_name}")
async def update_pipeline_stage(
    crm_id: UUID,
    old_stage_name: str,
    body: EditPipelineStageRequest,
    user_id: CurrentUser,
):
    """Update (rename) a pipeline stage."""
    from app.services.crm_editor import CRMSchemaEditor
    
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")
    
    try:
        updated_config = CRMSchemaEditor.update_pipeline_stage(
            crm["configuration"],
            old_stage_name=old_stage_name,
            new_stage_name=body.new_stage_name,
        )
        
        crm = repo.update_crm_configuration(
            crm_id=str(crm_id),
            owner_id=user_id,
            configuration=updated_config,
        )
        
        return success_response({
            "crm_id": crm["id"],
            "configuration": crm["configuration"],
            "configuration_version": crm["configuration_version"],
        })
    except ValueError as exc:
        return error_response(400, "VALIDATION_ERROR", str(exc))
    except Exception as exc:
        return error_response(500, "INTERNAL_ERROR", f"Failed to update stage: {exc}")


@router.delete("/{crm_id}/stage/{stage_name}")
async def delete_pipeline_stage(
    crm_id: UUID,
    stage_name: str,
    user_id: CurrentUser,
):
    """Delete a pipeline stage from the CRM."""
    from app.services.crm_editor import CRMSchemaEditor
    
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")
    
    try:
        updated_config = CRMSchemaEditor.delete_pipeline_stage(
            crm["configuration"],
            stage_name=stage_name,
        )
        
        crm = repo.update_crm_configuration(
            crm_id=str(crm_id),
            owner_id=user_id,
            configuration=updated_config,
        )
        
        return success_response({
            "crm_id": crm["id"],
            "configuration": crm["configuration"],
            "configuration_version": crm["configuration_version"],
        })
    except ValueError as exc:
        return error_response(400, "VALIDATION_ERROR", str(exc))
    except Exception as exc:
        return error_response(500, "INTERNAL_ERROR", f"Failed to delete stage: {exc}")
