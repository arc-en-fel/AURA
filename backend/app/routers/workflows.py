"""Workflow and Analytics routes.

Endpoints:
- POST /api/v1/crm/{crm_id}/workflows     — Create workflow
- GET  /api/v1/crm/{crm_id}/workflows     — List workflows
- GET  /api/v1/crm/{crm_id}/analytics     — Get CRM analytics
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter

from app.auth import CurrentUser
from app.database import CRMRepository
from app.routers.responses import success_response, error_response
from app.schemas.crm import (
    CRMConfiguration,
    CreateWorkflowRequest,
)
from app.services.validation import find_entity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crm/{crm_id}", tags=["Workflows & Analytics"])


def _get_repo() -> CRMRepository:
    return CRMRepository()


@router.post("/workflows")
async def create_workflow(
    crm_id: UUID,
    body: CreateWorkflowRequest,
    user_id: CurrentUser,
):
    """Create a workflow. AI-generated workflows start as draft."""
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")
    if crm["status"] != "active":
        return error_response(403, "FORBIDDEN", "CRM is archived.")

    # Validate trigger entity exists in CRM
    config = CRMConfiguration(**crm["configuration"])
    entity = find_entity(config, body.trigger.entity)
    if not entity:
        return error_response(422, "VALIDATION_ERROR", f"Trigger entity '{body.trigger.entity}' not in CRM.")

    try:
        wf = repo.create_workflow(
            crm_id=str(crm_id),
            name=body.name,
            trigger=body.trigger.model_dump(),
            actions=[a.model_dump() for a in body.actions],
            status="draft" if not body.enabled else "active",
        )
        return success_response(
            {
                "workflow_id": wf["id"],
                "status": wf["status"],
                "name": wf["name"],
                "trigger": wf["trigger"],
                "actions": wf["actions"],
            },
            status_code=201,
        )
    except Exception:
        return error_response(500, "INTERNAL_ERROR", "Failed to create workflow.")


@router.get("/workflows")
async def list_workflows(crm_id: UUID, user_id: CurrentUser):
    """List workflows for a CRM."""
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")

    try:
        workflows = repo.list_workflows(str(crm_id))
        return success_response({
            "items": [
                {
                    "workflow_id": w["id"],
                    "status": w["status"],
                    "name": w["name"],
                    "trigger": w["trigger"],
                    "actions": w["actions"],
                }
                for w in workflows
            ],
        })
    except Exception:
        return error_response(500, "INTERNAL_ERROR", "Failed to list workflows.")


@router.get("/analytics")
async def get_analytics(crm_id: UUID, user_id: CurrentUser):
    """
    Get CRM analytics dynamically derived from the active CRM's configuration.
    
    Handles edge cases:
    - Empty pipeline_stages: return empty by_stage array
    - No stage field: return empty by_stage array
    - Orphaned stage values: include in counts
    - No source field: return empty by_source array
    - Zero records: return 0 counts with 0% percentages
    
    Returns:
    {
        "total_records": int,
        "by_stage": [{"value": str, "count": int, "percentage": float}, ...],
        "by_source": [{"value": str, "count": int, "percentage": float}, ...],
        "schema_info": {
            "primary_entity_name": str,
            "pipeline_stages": [str, ...],
            "stage_field_name": str | None,
            "source_field_name": str | None
        }
    }
    """
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")

    config = CRMConfiguration(**crm["configuration"])

    # Get primary entity (first entity in configuration)
    if not config.entities:
        return success_response({
            "total_records": 0,
            "by_stage": [],
            "by_source": [],
            "schema_info": {
                "primary_entity_name": None,
                "pipeline_stages": [],
                "stage_field_name": None,
                "source_field_name": None,
            }
        })

    primary_entity = config.entities[0]
    entity_name = primary_entity.name

    # Get pipeline stages from configuration (user-defined)
    pipeline_stages = config.pipeline_stages if config.pipeline_stages else []

    # Find stage field (typically "status" or "stage" with type "select")
    stage_field_name = None
    for field in primary_entity.fields:
        if field.type == "select" and field.name in ("status", "stage"):
            stage_field_name = field.name
            break

    # Find source field (typically "source" with type "select")
    source_field_name = None
    for field in primary_entity.fields:
        if field.name == "source":
            source_field_name = field.name
            break

    try:
        # Query: Total records
        total_records = repo.count_records(str(crm_id), entity_name)

        # Query: Records by stage
        by_stage: list[dict[str, Any]] = []
        if stage_field_name:
            stage_counts = repo.count_records_by_field(str(crm_id), entity_name, stage_field_name)
            # Add percentage for each stage
            for entry in stage_counts:
                count = entry.get("count", 0)
                percentage = (count / total_records * 100) if total_records > 0 else 0.0
                by_stage.append({
                    "value": entry.get("value", "Unassigned"),
                    "count": count,
                    "percentage": round(percentage, 1),
                })

        # Query: Records by source
        by_source: list[dict[str, Any]] = []
        if source_field_name:
            source_counts = repo.count_records_by_field(str(crm_id), entity_name, source_field_name)
            for entry in source_counts:
                count = entry.get("count", 0)
                percentage = (count / total_records * 100) if total_records > 0 else 0.0
                by_source.append({
                    "value": entry.get("value", "Direct"),
                    "count": count,
                    "percentage": round(percentage, 1),
                })

        return success_response({
            "total_records": total_records,
            "by_stage": by_stage,
            "by_source": by_source,
            "schema_info": {
                "primary_entity_name": entity_name,
                "pipeline_stages": pipeline_stages,
                "stage_field_name": stage_field_name,
                "source_field_name": source_field_name,
            }
        })
    except Exception as exc:
        logger.exception("Error computing analytics")
        return error_response(500, "INTERNAL_ERROR", "Failed to compute analytics.")
