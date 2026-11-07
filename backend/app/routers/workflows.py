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
    entity_label = primary_entity.label or entity_name.replace("_", " ").title()

    # Get pipeline stages from configuration (user-defined)
    pipeline_stages = config.pipeline_stages if config.pipeline_stages else []

    # Find stage/status field
    stage_field = None
    for field in primary_entity.fields:
        if field.type in ("status", "select") and any(k in field.name.lower() for k in ("status", "stage")):
            stage_field = field
            break
    if not stage_field and pipeline_stages:
        for field in primary_entity.fields:
            if field.type in ("status", "select"):
                stage_field = field
                break

    stage_field_name = stage_field.name if stage_field else None

    # Categorical and numeric fields identification
    select_fields = [f for f in primary_entity.fields if f.type in ("select", "status") and f.name != stage_field_name]
    numeric_fields = [f for f in primary_entity.fields if f.type in ("number", "currency")]

    try:
        # Fetch all records for this entity
        all_records = repo.get_all_records(str(crm_id), entity_name)
        total_records = len(all_records)

        # 1. Pipeline Stage Analytics: ALL stages in schema appear
        stage_counts_map: dict[str, int] = {s: 0 for s in pipeline_stages}
        if stage_field_name:
            for r in all_records:
                st = str(r.get("data", {}).get(stage_field_name, "")).strip()
                if st:
                    stage_counts_map[st] = stage_counts_map.get(st, 0) + 1

        by_stage: list[dict[str, Any]] = []
        for stage_val, count in stage_counts_map.items():
            pct = round((count / total_records * 100), 1) if total_records > 0 else 0.0
            by_stage.append({
                "value": stage_val,
                "name": stage_val,
                "count": count,
                "percentage": pct,
            })

        # 2. Categorical Metrics
        categorical_metrics: list[dict[str, Any]] = []
        for sf in select_fields:
            counts: dict[str, int] = {}
            for r in all_records:
                v = str(r.get("data", {}).get(sf.name, "")).strip()
                if v:
                    counts[v] = counts.get(v, 0) + 1
            dist: list[dict[str, Any]] = []
            for val, cnt in counts.items():
                p = round((cnt / total_records * 100), 1) if total_records > 0 else 0.0
                dist.append({"value": val, "name": val, "count": cnt, "percentage": p})
            dist.sort(key=lambda x: x["count"], reverse=True)
            categorical_metrics.append({
                "field_name": sf.name,
                "field_label": sf.label,
                "distribution": dist,
            })

        # By source backward compatibility
        by_source = []
        source_field_name = None
        for sf in primary_entity.fields:
            if "source" in sf.name.lower():
                source_field_name = sf.name
                break
        if source_field_name:
            counts = {}
            for r in all_records:
                src = str(r.get("data", {}).get(source_field_name, "")).strip()
                if src:
                    counts[src] = counts.get(src, 0) + 1
            for k, v in counts.items():
                p = round((v / total_records * 100), 1) if total_records > 0 else 0.0
                by_source.append({"value": k, "name": k, "count": v, "percentage": p})

        # 3. Numeric Aggregations (Total, Average, Min, Max)
        numeric_metrics: list[dict[str, Any]] = []
        for nf in numeric_fields:
            vals: list[float] = []
            for r in all_records:
                raw_v = r.get("data", {}).get(nf.name)
                if raw_v is not None and raw_v != "":
                    try:
                        vals.append(float(raw_v))
                    except (ValueError, TypeError):
                        pass
            if vals:
                total_val = round(sum(vals), 2)
                avg_val = round(total_val / len(vals), 2)
                min_val = round(min(vals), 2)
                max_val = round(max(vals), 2)
            else:
                total_val = 0.0
                avg_val = 0.0
                min_val = 0.0
                max_val = 0.0

            numeric_metrics.append({
                "field_name": nf.name,
                "field_label": nf.label,
                "type": nf.type,
                "total": total_val,
                "average": avg_val,
                "min": min_val,
                "max": max_val,
            })

        # 4. Dynamic KPI Cards
        kpi_cards: list[dict[str, Any]] = [
            {
                "id": "total_volume",
                "title": f"Total {entity_label}s",
                "value": total_records,
                "subtitle": "Total volume in CRM",
                "format": "number",
            }
        ]
        for nm in numeric_metrics[:3]:
            fmt = "currency" if nm["type"] == "currency" or "revenue" in nm["field_name"] or "value" in nm["field_name"] or "price" in nm["field_name"] else "number"
            kpi_cards.append({
                "id": f"total_{nm['field_name']}",
                "title": f"Total {nm['field_label']}",
                "value": nm["total"],
                "subtitle": f"Aggregated {nm['field_label']}",
                "format": fmt,
            })
            kpi_cards.append({
                "id": f"avg_{nm['field_name']}",
                "title": f"Average {nm['field_label']}",
                "value": nm["average"],
                "subtitle": f"Per {entity_label}",
                "format": fmt,
            })

        # If we have pipeline stages, add stage completion KPI
        if pipeline_stages and by_stage:
            last_stage = pipeline_stages[-1]
            last_stage_count = stage_counts_map.get(last_stage, 0)
            kpi_cards.append({
                "id": "stage_completed",
                "title": f"{last_stage} {entity_label}s",
                "value": last_stage_count,
                "subtitle": f"Reached final stage",
                "format": "number",
            })

        return success_response({
            "total_records": total_records,
            "entity_name": entity_name,
            "entity_label": entity_label,
            "by_stage": by_stage,
            "by_source": by_source,
            "numeric_metrics": numeric_metrics,
            "categorical_metrics": categorical_metrics,
            "kpi_cards": kpi_cards,
            "schema_info": {
                "primary_entity_name": entity_name,
                "pipeline_stages": pipeline_stages,
                "stage_field_name": stage_field_name,
                "source_field_name": source_field_name,
                "categorical_fields": [{"name": f.name, "label": f.label} for f in select_fields],
                "numeric_fields": [{"name": f.name, "label": f.label, "type": f.type} for f in numeric_fields],
            },
        })
    except Exception as exc:
        logger.exception("Error computing analytics")
        return error_response(500, "INTERNAL_ERROR", "Failed to compute analytics.")
