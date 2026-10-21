"""Evolution proposal routes.

Endpoints:
- POST /api/v1/crm/{crm_id}/evolution/proposals                              — Create proposal
- POST /api/v1/crm/{crm_id}/evolution/proposals/{proposal_id}/approve        — Approve
- POST /api/v1/crm/{crm_id}/evolution/proposals/{proposal_id}/apply          — Apply
- POST /api/v1/crm/{crm_id}/evolution/proposals/{proposal_id}/reject         — Reject

Two-stage approval: approve marks it ready, apply executes the change.
AI suggestions NEVER apply automatically.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.auth import CurrentUser
from app.config import get_settings, Settings
from app.database import CRMRepository, get_user_scoped_client
from app.routers.responses import success_response, error_response
from app.schemas.crm import (
    ApproveProposalRequest,
    CRMConfiguration,
    EvolutionObjectiveRequest,
    ProposedChange,
    RejectProposalRequest,
    WorkflowAction,
    WorkflowTrigger,
)
from app.services.ai_provider import get_ai_provider

router = APIRouter(prefix="/crm/{crm_id}/evolution", tags=["Evolution"])


def _get_repo(access_token: str | None = None) -> CRMRepository:
    if access_token:
        return CRMRepository(client=get_user_scoped_client(access_token))
    return CRMRepository()


def _proposal_to_dict(p: dict) -> dict:
    """Format a proposal DB row to API response."""
    return {
        "proposal_id": p["id"],
        "status": p["status"],
        "summary": p["summary"],
        "proposed_change": p["proposed_change"],
        "evidence": p.get("evidence", []),
        "approved_at": p.get("approved_at"),
        "approved_by": p.get("approved_by"),
        "applied_at": p.get("applied_at"),
        "applied_by": p.get("applied_by"),
        "rejected_at": p.get("rejected_at"),
        "rejected_by": p.get("rejected_by"),
        "rejection_reason": p.get("rejection_reason"),
    }


@router.post("/proposals")
async def create_proposal(
    crm_id: UUID,
    body: EvolutionObjectiveRequest,
    user_id: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
):
    """Generate an evolution proposal using AI (or mock provider)."""
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")
    if crm["status"] != "active":
        return error_response(403, "FORBIDDEN", "CRM is archived.")

    config = CRMConfiguration(**crm["configuration"])

    # Compute real analytics to give Laya accurate ranking signals.
    # Gracefully fall back to zeros if the DB call fails so proposal creation
    # is never blocked by an analytics read error.
    analytics_data: dict = {"total_leads": 0, "won_leads": 0, "conversion_rate": 0.0}
    try:
        primary_entity = config.entities[0].name if config.entities else "lead"
        total = repo.count_records(str(crm_id), primary_entity)
        analytics_data["total_leads"] = total

        # Derive won_leads from the stage/status select field options
        stage_field = next(
            (f for f in config.entities[0].fields if f.name in ("status", "stage") and f.type == "select"),
            None,
        ) if config.entities else None

        if stage_field and total > 0:
            won_stages = {"Won", "won", "Closed Won", "closed_won"}
            by_stage = repo.count_records_by_field(str(crm_id), primary_entity, stage_field.name)
            won = sum(entry.get("count", 0) for entry in by_stage if entry.get("value") in won_stages)
            analytics_data["won_leads"] = won
            analytics_data["conversion_rate"] = round(won / total, 4)
    except Exception:
        pass  # analytics failure must never block proposal generation

    try:
        provider = get_ai_provider(settings.llm_provider)
        suggestion = provider.generate_evolution_proposal(
            body.objective, crm["configuration"], analytics_data
        )
    except Exception:
        return error_response(502, "AI_PROVIDER_ERROR", "Failed to generate proposal.")

    # Validate the proposed change
    try:
        proposed = suggestion["proposed_change"]
        ProposedChange(**proposed)
    except Exception:
        return error_response(422, "VALIDATION_ERROR", "Generated proposal failed validation.")

    try:
        proposal = repo.create_proposal(
            crm_id=str(crm_id),
            summary=suggestion["summary"],
            proposed_change=proposed,
            evidence=suggestion.get("evidence", []),
            config_version=crm["configuration_version"],
        )
        return success_response(_proposal_to_dict(proposal), status_code=201)
    except Exception:
        return error_response(500, "INTERNAL_ERROR", "Failed to create proposal.")


@router.get("/proposals")
async def list_proposals(crm_id: UUID, user_id: CurrentUser):
    """List evolution proposals for a CRM."""
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")

    proposals = repo.list_proposals(str(crm_id))
    return success_response({
        "items": [_proposal_to_dict(p) for p in proposals],
    })


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(
    crm_id: UUID,
    proposal_id: UUID,
    request: Request,
    user_id: CurrentUser,
    body: ApproveProposalRequest | None = None,
):
    """Approve a pending proposal. Does NOT apply it."""
    authorization = request.headers.get("Authorization", "")
    access_token = authorization[7:] if authorization.startswith("Bearer ") else ""
    repo = _get_repo(access_token)
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")
    if crm["status"] != "active":
        return error_response(403, "FORBIDDEN", "CRM is archived.")

    proposal = repo.get_proposal(str(proposal_id), str(crm_id))
    if not proposal:
        return error_response(404, "NOT_FOUND", "Proposal not found.")
    if proposal["status"] != "pending":
        return error_response(422, "VALIDATION_ERROR", f"Proposal is '{proposal['status']}', not pending.")

    # Staleness check
    if proposal["configuration_version_at_creation"] != crm["configuration_version"]:
        return error_response(409, "CONFLICT", "CRM configuration has changed since proposal creation.")

    # Optional version check
    if body and body.expected_version is not None:
        if crm["configuration_version"] != body.expected_version:
            return error_response(409, "CONFLICT", "Configuration version mismatch.")

    # Validate change type
    change = proposal["proposed_change"]
    if change.get("type") not in ("workflow.update", "workflow.create"):
        return error_response(422, "VALIDATION_ERROR", "Proposed change type not allowlisted.")

    result = repo.approve_proposal(str(proposal_id), user_id)
    if not result:
        return error_response(422, "VALIDATION_ERROR", "Could not approve proposal.")
    if "error" in result:
        err = result["error"]
        if err in ("not_found", "not_owner"):
            return error_response(404, "NOT_FOUND", "Proposal not found.")
        elif err == "crm_archived":
            return error_response(403, "FORBIDDEN", "CRM is archived.")
        elif err in ("stale", "version_mismatch"):
            return error_response(409, "CONFLICT", "CRM configuration has changed since proposal creation.")
        elif err == "not_pending":
            return error_response(422, "VALIDATION_ERROR", "Proposal is not pending.")
        elif err == "invalid_change_type":
            return error_response(422, "VALIDATION_ERROR", "Proposed change type not allowlisted.")
        return error_response(422, "VALIDATION_ERROR", f"Could not approve proposal: {err}")

    return success_response(_proposal_to_dict(result))


@router.post("/proposals/{proposal_id}/apply")
async def apply_proposal(
    crm_id: UUID,
    proposal_id: UUID,
    request: Request,
    user_id: CurrentUser,
):
    """Apply an approved proposal atomically through the database function."""
    authorization = request.headers.get("Authorization", "")
    access_token = authorization[7:] if authorization.startswith("Bearer ") else ""
    repo = _get_repo(access_token)
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")
    if crm["status"] != "active":
        return error_response(403, "FORBIDDEN", "CRM is archived.")

    proposal = repo.get_proposal(str(proposal_id), str(crm_id))
    if not proposal:
        return error_response(404, "NOT_FOUND", "Proposal not found.")
    if proposal["status"] != "approved":
        return error_response(422, "VALIDATION_ERROR", f"Proposal is '{proposal['status']}', not approved.")

    # Staleness check
    if proposal.get("configuration_version_at_creation") != crm.get("configuration_version"):
        return error_response(409, "CONFLICT", "Configuration has changed since proposal creation.")

    # Validate change payload
    change = proposal.get("proposed_change", {})
    change_type = change.get("type")
    if change_type not in ("workflow.update", "workflow.create"):
        return error_response(422, "VALIDATION_ERROR", "Proposed change type not allowlisted.")
    if change_type == "workflow.update":
        if not change.get("workflow_id"):
            return error_response(422, "VALIDATION_ERROR", "workflow.update requires workflow_id.")
        if "delay_hours" not in change or change.get("delay_hours") is None:
            return error_response(422, "VALIDATION_ERROR", "workflow.update requires delay_hours.")
    elif change_type == "workflow.create":
        if not change.get("name"):
            return error_response(422, "VALIDATION_ERROR", "workflow.create requires non-empty name.")

    # The database function is authoritative for atomic execution in PostgreSQL.
    # The route checks access and translates its result.
    try:
        result = repo.apply_proposal(str(proposal_id))

        if not result:
            return error_response(500, "INTERNAL_ERROR", "Failed to apply proposal.")
        if "error" in result:
            err = result["error"]
            if err in ("not_found", "not_owner", "crm_not_found"):
                return error_response(404, "NOT_FOUND", "Proposal or CRM not found.")
            elif err == "crm_archived":
                return error_response(403, "FORBIDDEN", "CRM is archived.")
            elif err == "not_approved":
                return error_response(422, "VALIDATION_ERROR", "Proposal is not approved.")
            elif err == "stale":
                return error_response(409, "CONFLICT", "Configuration has changed since proposal creation.")
            elif err.startswith("invalid_change"):
                return error_response(422, "VALIDATION_ERROR", err)
            elif err == "apply_failed":
                return error_response(500, "INTERNAL_ERROR", "Proposal application failed.")
            return error_response(500, "INTERNAL_ERROR", "Failed to apply proposal.")

        return success_response(_proposal_to_dict(result))

    except Exception:
        # The database function owns failure status and rollback. Avoid a
        # second mutation here if the RPC outcome is uncertain.
        return error_response(500, "INTERNAL_ERROR", "Proposal application failed.")


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(
    crm_id: UUID,
    proposal_id: UUID,
    body: RejectProposalRequest,
    user_id: CurrentUser,
):
    """Reject a pending or approved proposal."""
    repo = _get_repo()
    crm = repo.get_crm(str(crm_id), user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found.")

    proposal = repo.get_proposal(str(proposal_id), str(crm_id))
    if not proposal:
        return error_response(404, "NOT_FOUND", "Proposal not found.")
    if proposal["status"] not in ("pending", "approved"):
        return error_response(422, "VALIDATION_ERROR", f"Cannot reject proposal in '{proposal['status']}' status.")

    result = repo.reject_proposal(str(proposal_id), user_id, body.reason)
    if not result:
        return error_response(422, "VALIDATION_ERROR", "Could not reject proposal.")

    return success_response(_proposal_to_dict(result))
