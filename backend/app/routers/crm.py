"""CRM CRUD routes.

Endpoints:
- POST /api/v1/crm/generate  — Generate a draft CRM configuration
- POST /api/v1/crm           — Save a validated CRM
- GET  /api/v1/crm           — List user's CRMs
- GET  /api/v1/crm/{crm_id}  — Get a single CRM
- PATCH /api/v1/crm/{crm_id}/configuration — Update CRM metadata

POST-GENERATION CRM EDITING ENDPOINTS (FEAT-002):
- POST   /api/v1/crm/{crm_id}/fields — Add a field
- PATCH  /api/v1/crm/{crm_id}/fields/{field_name} — Update field
- DELETE /api/v1/crm/{crm_id}/fields/{field_name} — Delete field
- PATCH  /api/v1/crm/{crm_id}/fields/reorder — Reorder fields
- POST   /api/v1/crm/{crm_id}/stages — Add stage
- PATCH  /api/v1/crm/{crm_id}/stages/{stage_name} — Update stage
- DELETE /api/v1/crm/{crm_id}/stages/{stage_name} — Delete stage
- PATCH  /api/v1/crm/{crm_id}/stages/reorder — Reorder stages
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Body
from pydantic import ValidationError

from app.auth import CurrentUser
from app.config import get_settings, Settings
from app.database import CRMRepository
from app.routers.responses import success_response, error_response
from app.schemas.crm import (
    CRMConfiguration,
    GenerateCRMRequest,
    SaveCRMRequest,
    AddFieldRequest,
    UpdateFieldRequest,
    ReorderFieldsRequest,
    AddStageRequest,
    UpdateStageRequest,
    ReorderStagesRequest,
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


# ─────────────────────────────────────────────────────────────────────────────
# POST-GENERATION CRM EDITING ENDPOINTS (FEAT-002)
# ─────────────────────────────────────────────────────────────────────────────
# Generic, CRM-type-agnostic field and stage editing.
# Every endpoint enforces authorization, validates inputs, and checks for 
# in-use fields/stages before deletion.


@router.post("/{crm_id}/fields")
async def add_field(
    crm_id: UUID,
    body: AddFieldRequest,
    user_id: CurrentUser,
):
    """Add a new field to the main entity in a CRM.
    
    Works for any CRM type. Assumes the main entity is at index 0.
    
    Returns:
    - 201: Field successfully added
    - 404: CRM not found or not authorized
    - 409: Field already exists (conflict)
    - 422: Validation error (invalid type, options format, etc.)
    """
    from app.services.crm_editor import CRMSchemaEditor
    
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")
    
    try:
        # Use first entity by default (main entity)
        entity_name = crm["configuration"]["entities"][0]["name"]
        
        updated_config = CRMSchemaEditor.add_field(
            crm["configuration"],
            entity_name=entity_name,
            field_name=body.field_name,
            field_label=body.label,
            field_type=body.field_type,  # type: ignore
            required=body.required,
            options=body.options,
        )
        
        # Validate the updated configuration
        CRMConfiguration(**updated_config)
        
        # Save updated configuration
        updated_crm = repo.update_crm_configuration(
            crm_id=str(crm_id),
            owner_id=user_id,
            configuration=updated_config,
        )
        
        if not updated_crm:
            return error_response(500, "INTERNAL_ERROR", "Failed to save CRM configuration.")
        
        return success_response({
            "crm_id": updated_crm["id"],
            "configuration": updated_crm["configuration"],
            "configuration_version": updated_crm["configuration_version"],
        }, status_code=201)
        
    except ValueError as exc:
        error_msg = str(exc)
        if "already exists" in error_msg:
            return error_response(409, "CONFLICT", error_msg)
        return error_response(422, "VALIDATION_ERROR", error_msg)
    except ValidationError as exc:
        return error_response(422, "VALIDATION_ERROR", "Configuration validation failed.", [
            {"field": str(e["loc"]), "issue": e["msg"]} for e in exc.errors()
        ])
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return error_response(500, "INTERNAL_ERROR", f"Failed to add field.")


@router.patch("/{crm_id}/fields/{field_name}")
async def update_field(
    crm_id: UUID,
    field_name: str,
    body: UpdateFieldRequest,
    user_id: CurrentUser,
):
    """Update field properties (label, required, type, options).
    
    Returns:
    - 200: Field successfully updated
    - 404: CRM not found or field not found
    - 409: Type conversion unsafe or conflict
    - 422: Validation error
    """
    from app.services.crm_editor import CRMSchemaEditor
    
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")
    
    try:
        entity_name = crm["configuration"]["entities"][0]["name"]
        
        updated_config = CRMSchemaEditor.update_field(
            crm["configuration"],
            entity_name=entity_name,
            field_name=field_name,
            label=body.label,
            field_type=body.field_type,  # type: ignore
            required=body.required,
            options=body.options,
        )
        
        CRMConfiguration(**updated_config)
        
        updated_crm = repo.update_crm_configuration(
            crm_id=str(crm_id),
            owner_id=user_id,
            configuration=updated_config,
        )
        
        if not updated_crm:
            return error_response(500, "INTERNAL_ERROR", "Failed to save CRM configuration.")
        
        return success_response({
            "crm_id": updated_crm["id"],
            "configuration": updated_crm["configuration"],
            "configuration_version": updated_crm["configuration_version"],
        })
        
    except ValueError as exc:
        error_msg = str(exc)
        if "not found" in error_msg:
            return error_response(404, "NOT_FOUND", error_msg)
        return error_response(422, "VALIDATION_ERROR", error_msg)
    except ValidationError as exc:
        return error_response(422, "VALIDATION_ERROR", "Configuration validation failed.", [
            {"field": str(e["loc"]), "issue": e["msg"]} for e in exc.errors()
        ])
    except Exception as exc:
        return error_response(500, "INTERNAL_ERROR", "Failed to update field.")


@router.delete("/{crm_id}/fields/{field_name}")
async def delete_field(
    crm_id: UUID,
    field_name: str,
    user_id: CurrentUser,
):
    """Delete a field from a CRM entity.
    
    Checks if field has values in existing records. If yes, returns 409 with warning.
    User must confirm deletion explicitly before the operation proceeds.
    
    Returns:
    - 204: Field successfully deleted
    - 404: CRM not found or field not found
    - 409: Field has records; user must confirm
    - 422: Validation error (last field, etc.)
    """
    from app.services.crm_editor import CRMSchemaEditor
    
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")
    
    try:
        entity_name = crm["configuration"]["entities"][0]["name"]
        
        # Check if field has records
        record_count = repo.count_records_by_field_value(
            crm_id=str(crm_id),
            entity_name=entity_name,
            field_name=field_name,
            field_value="*"  # Count any value
        )
        
        # Count records that have this field populated (not None/empty)
        all_records, total = repo.list_records(str(crm_id), entity_name, limit=10000, offset=0)
        records_with_field = sum(
            1 for rec in all_records 
            if field_name in rec.get("data", {}) and rec["data"][field_name] is not None
        )
        
        if records_with_field > 0:
            return error_response(
                409,
                "CONFLICT",
                f"Field '{field_name}' has {records_with_field} record(s) with values. "
                "Deletion would lose data. Confirm deletion with explicit confirmation.",
                details=[{"field": "confirm", "issue": f"{records_with_field} records use this field"}]
            )
        
        # Delete the field
        updated_config = CRMSchemaEditor.delete_field(
            crm["configuration"],
            entity_name=entity_name,
            field_name=field_name,
        )
        
        CRMConfiguration(**updated_config)
        
        updated_crm = repo.update_crm_configuration(
            crm_id=str(crm_id),
            owner_id=user_id,
            configuration=updated_config,
        )
        
        if not updated_crm:
            return error_response(500, "INTERNAL_ERROR", "Failed to save CRM configuration.")
        
        return success_response({
            "crm_id": updated_crm["id"],
            "configuration": updated_crm["configuration"],
            "configuration_version": updated_crm["configuration_version"],
        }, status_code=200)
        
    except ValueError as exc:
        error_msg = str(exc)
        if "not found" in error_msg:
            return error_response(404, "NOT_FOUND", error_msg)
        if "last field" in error_msg:
            return error_response(422, "VALIDATION_ERROR", error_msg)
        return error_response(422, "VALIDATION_ERROR", error_msg)
    except ValidationError as exc:
        return error_response(422, "VALIDATION_ERROR", "Configuration validation failed.", [
            {"field": str(e["loc"]), "issue": e["msg"]} for e in exc.errors()
        ])
    except Exception as exc:
        return error_response(500, "INTERNAL_ERROR", "Failed to delete field.")


@router.patch("/{crm_id}/fields/reorder")
async def reorder_fields(
    crm_id: UUID,
    body: ReorderFieldsRequest,
    user_id: CurrentUser,
):
    """Reorder fields in a CRM entity.
    
    The field_order array must contain exactly the current fields in a new order.
    
    Returns:
    - 200: Fields successfully reordered
    - 404: CRM not found
    - 422: Field order mismatch (missing/extra fields)
    """
    from app.services.crm_editor import CRMSchemaEditor
    
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")
    
    try:
        entity_name = crm["configuration"]["entities"][0]["name"]
        
        updated_config = CRMSchemaEditor.reorder_fields(
            crm["configuration"],
            entity_name=entity_name,
            field_order=body.field_order,
        )
        
        CRMConfiguration(**updated_config)
        
        updated_crm = repo.update_crm_configuration(
            crm_id=str(crm_id),
            owner_id=user_id,
            configuration=updated_config,
        )
        
        if not updated_crm:
            return error_response(500, "INTERNAL_ERROR", "Failed to save CRM configuration.")
        
        return success_response({
            "crm_id": updated_crm["id"],
            "configuration": updated_crm["configuration"],
            "configuration_version": updated_crm["configuration_version"],
        })
        
    except ValueError as exc:
        return error_response(422, "VALIDATION_ERROR", str(exc))
    except ValidationError as exc:
        return error_response(422, "VALIDATION_ERROR", "Configuration validation failed.", [
            {"field": str(e["loc"]), "issue": e["msg"]} for e in exc.errors()
        ])
    except Exception as exc:
        return error_response(500, "INTERNAL_ERROR", "Failed to reorder fields.")


@router.post("/{crm_id}/stages")
async def add_stage(
    crm_id: UUID,
    body: AddStageRequest,
    user_id: CurrentUser,
):
    """Add a new pipeline stage to a CRM.
    
    Returns:
    - 201: Stage successfully added
    - 404: CRM not found
    - 409: Stage already exists
    - 422: Validation error
    """
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
        
        CRMConfiguration(**updated_config)
        
        updated_crm = repo.update_crm_configuration(
            crm_id=str(crm_id),
            owner_id=user_id,
            configuration=updated_config,
        )
        
        if not updated_crm:
            return error_response(500, "INTERNAL_ERROR", "Failed to save CRM configuration.")
        
        return success_response({
            "crm_id": updated_crm["id"],
            "configuration": updated_crm["configuration"],
            "configuration_version": updated_crm["configuration_version"],
        }, status_code=201)
        
    except ValueError as exc:
        error_msg = str(exc)
        if "already exists" in error_msg:
            return error_response(409, "CONFLICT", error_msg)
        return error_response(422, "VALIDATION_ERROR", error_msg)
    except ValidationError as exc:
        return error_response(422, "VALIDATION_ERROR", "Configuration validation failed.", [
            {"field": str(e["loc"]), "issue": e["msg"]} for e in exc.errors()
        ])
    except Exception as exc:
        return error_response(500, "INTERNAL_ERROR", "Failed to add stage.")


@router.patch("/{crm_id}/stages/{stage_name}")
async def update_stage(
    crm_id: UUID,
    stage_name: str,
    body: UpdateStageRequest,
    user_id: CurrentUser,
):
    """Rename a pipeline stage.
    
    Returns:
    - 200: Stage successfully renamed
    - 404: CRM not found or stage not found
    - 409: New name already exists
    - 422: Validation error
    """
    from app.services.crm_editor import CRMSchemaEditor
    
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")
    
    try:
        updated_config = CRMSchemaEditor.update_pipeline_stage(
            crm["configuration"],
            old_stage_name=stage_name,
            new_stage_name=body.new_stage_name,
        )
        
        CRMConfiguration(**updated_config)
        
        updated_crm = repo.update_crm_configuration(
            crm_id=str(crm_id),
            owner_id=user_id,
            configuration=updated_config,
        )
        
        if not updated_crm:
            return error_response(500, "INTERNAL_ERROR", "Failed to save CRM configuration.")
        
        return success_response({
            "crm_id": updated_crm["id"],
            "configuration": updated_crm["configuration"],
            "configuration_version": updated_crm["configuration_version"],
        })
        
    except ValueError as exc:
        error_msg = str(exc)
        if "not found" in error_msg:
            return error_response(404, "NOT_FOUND", error_msg)
        if "already exists" in error_msg:
            return error_response(409, "CONFLICT", error_msg)
        return error_response(422, "VALIDATION_ERROR", error_msg)
    except ValidationError as exc:
        return error_response(422, "VALIDATION_ERROR", "Configuration validation failed.", [
            {"field": str(e["loc"]), "issue": e["msg"]} for e in exc.errors()
        ])
    except Exception as exc:
        return error_response(500, "INTERNAL_ERROR", "Failed to update stage.")


@router.delete("/{crm_id}/stages/{stage_name}")
async def delete_stage(
    crm_id: UUID,
    stage_name: str,
    user_id: CurrentUser,
):
    """Delete a pipeline stage from a CRM.
    
    Checks if stage has records with that stage value. Returns 409 if yes.
    
    Returns:
    - 200: Stage successfully deleted
    - 404: CRM not found or stage not found
    - 409: Stage has records; user must confirm
    - 422: Validation error (last stage, etc.)
    """
    from app.services.crm_editor import CRMSchemaEditor
    
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")
    
    try:
        entity_name = crm["configuration"]["entities"][0]["name"]
        
        # Check if stage has records
        records_with_stage = repo.count_records_by_field_value(
            crm_id=str(crm_id),
            entity_name=entity_name,
            field_name="status",  # Common stage field
            field_value=stage_name
        )
        
        if records_with_stage > 0:
            return error_response(
                409,
                "CONFLICT",
                f"Stage '{stage_name}' has {records_with_stage} record(s). "
                "Deletion would require manual data migration. Confirm deletion with explicit confirmation.",
                details=[{"field": "confirm", "issue": f"{records_with_stage} records have this stage"}]
            )
        
        # Delete the stage
        updated_config = CRMSchemaEditor.delete_pipeline_stage(
            crm["configuration"],
            stage_name=stage_name,
        )
        
        CRMConfiguration(**updated_config)
        
        updated_crm = repo.update_crm_configuration(
            crm_id=str(crm_id),
            owner_id=user_id,
            configuration=updated_config,
        )
        
        if not updated_crm:
            return error_response(500, "INTERNAL_ERROR", "Failed to save CRM configuration.")
        
        return success_response({
            "crm_id": updated_crm["id"],
            "configuration": updated_crm["configuration"],
            "configuration_version": updated_crm["configuration_version"],
        }, status_code=200)
        
    except ValueError as exc:
        error_msg = str(exc)
        if "not found" in error_msg:
            return error_response(404, "NOT_FOUND", error_msg)
        if "last" in error_msg:
            return error_response(422, "VALIDATION_ERROR", error_msg)
        return error_response(422, "VALIDATION_ERROR", error_msg)
    except ValidationError as exc:
        return error_response(422, "VALIDATION_ERROR", "Configuration validation failed.", [
            {"field": str(e["loc"]), "issue": e["msg"]} for e in exc.errors()
        ])
    except Exception as exc:
        return error_response(500, "INTERNAL_ERROR", "Failed to delete stage.")


@router.patch("/{crm_id}/stages/reorder")
async def reorder_stages(
    crm_id: UUID,
    body: ReorderStagesRequest,
    user_id: CurrentUser,
):
    """Reorder pipeline stages in a CRM.
    
    The stage_order array must contain exactly the current stages in a new order.
    
    Returns:
    - 200: Stages successfully reordered
    - 404: CRM not found
    - 422: Stage order mismatch (missing/extra stages)
    """
    from app.services.crm_editor import CRMSchemaEditor
    
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")
    
    try:
        updated_config = CRMSchemaEditor.reorder_pipeline_stages(
            crm["configuration"],
            stage_order=body.stage_order,
        )
        
        CRMConfiguration(**updated_config)
        
        updated_crm = repo.update_crm_configuration(
            crm_id=str(crm_id),
            owner_id=user_id,
            configuration=updated_config,
        )
        
        if not updated_crm:
            return error_response(500, "INTERNAL_ERROR", "Failed to save CRM configuration.")
        
        return success_response({
            "crm_id": updated_crm["id"],
            "configuration": updated_crm["configuration"],
            "configuration_version": updated_crm["configuration_version"],
        })
        
    except ValueError as exc:
        return error_response(422, "VALIDATION_ERROR", str(exc))
    except ValidationError as exc:
        return error_response(422, "VALIDATION_ERROR", "Configuration validation failed.", [
            {"field": str(e["loc"]), "issue": e["msg"]} for e in exc.errors()
        ])
    except Exception as exc:
        return error_response(500, "INTERNAL_ERROR", "Failed to reorder stages.")
