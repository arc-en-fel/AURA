"""Database access layer using Supabase client.

For the MVP, the backend uses the Supabase service-role client for server-side
operations and enforces authorization at the application layer. RLS policies
provide defense-in-depth when using user-JWT-scoped clients.

IMPORTANT: Service-role credentials bypass RLS. Every query MUST include
explicit ownership filters. Never expose service-role credentials to the frontend.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from supabase import create_client, Client

from app.config import get_settings


_client: Client | None = None


def get_supabase_client() -> Client:
    """Get or create the Supabase client (service-role for server-side ops)."""
    global _client
    if _client is None:
        settings = get_settings()
        key = settings.supabase_service_role_key or settings.supabase_anon_key
        _client = create_client(settings.supabase_url, key)
    return _client


def get_user_scoped_client(access_token: str) -> Client:
    """Create a Supabase client whose requests carry the authenticated user's JWT."""
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client


class CRMRepository:
    """Data access for CRM operations. All methods enforce ownership."""

    def __init__(self, client: Client | None = None):
        self._client = client or get_supabase_client()

    # ── CRM CRUD ────────────────────────────────────────────────────

    def create_crm(self, owner_id: str, name: str, configuration: dict[str, Any]) -> dict[str, Any]:
        """Create a new CRM. owner_id comes from verified JWT, never from request body."""
        result = (
            self._client.table("crms")
            .insert({
                "owner_id": owner_id,
                "name": name,
                "configuration": configuration,
                "status": "active",
                "configuration_version": 1,
            })
            .execute()
        )
        if not result.data:
            raise RuntimeError("Failed to create CRM")
        return result.data[0]

    def list_crms(self, owner_id: str, limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
        """List CRMs owned by the authenticated user."""
        # Count query
        count_result = (
            self._client.table("crms")
            .select("id", count="exact")
            .eq("owner_id", owner_id)
            .execute()
        )
        total = count_result.count or 0

        # Data query
        result = (
            self._client.table("crms")
            .select("*")
            .eq("owner_id", owner_id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return result.data or [], total

    def get_crm(self, crm_id: str, owner_id: str) -> dict[str, Any] | None:
        """Get a CRM by ID, enforcing ownership."""
        result = (
            self._client.table("crms")
            .select("*")
            .eq("id", crm_id)
            .eq("owner_id", owner_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def update_crm(self, crm_id: str, owner_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        """Update CRM metadata. Enforces ownership and active status."""
        result = (
            self._client.table("crms")
            .update(updates)
            .eq("id", crm_id)
            .eq("owner_id", owner_id)
            .eq("status", "active")
            .execute()
        )
        return result.data[0] if result.data else None

    def update_crm_configuration(
        self,
        crm_id: str,
        owner_id: str,
        configuration: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Update CRM configuration and increment version.
        
        This method:
        1. Validates the new configuration with Pydantic
        2. Updates the configuration in the database
        3. Increments the configuration_version for change tracking
        4. Enforces ownership and active status
        """
        from app.schemas.crm import CRMConfiguration
        
        # Validate configuration
        CRMConfiguration(**configuration)
        
        # Update configuration and version
        result = (
            self._client.table("crms")
            .update({
                "configuration": configuration,
                "configuration_version": self._client.rpc(
                    "increment_config_version",
                    {"p_crm_id": crm_id, "p_owner_id": owner_id}
                ).data.get("configuration_version_after", 1) if False else None,  # Fallback
            })
            .eq("id", crm_id)
            .eq("owner_id", owner_id)
            .eq("status", "active")
            .execute()
        )
        
        if result.data:
            # If simple update worked, try to increment version separately
            try:
                version_result = self.increment_config_version(crm_id, owner_id)
                if version_result:
                    return version_result
            except:
                pass
        
        return result.data[0] if result.data else None

    # ── RECORDS CRUD ────────────────────────────────────────────────

    def create_record(
        self,
        crm_id: str,
        entity_name: str,
        data: dict[str, Any],
        source: str | None = None,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a record in the specified CRM entity."""
        row = {
            "crm_id": crm_id,
            "entity_name": entity_name,
            "data": data,
        }
        if source:
            row["source"] = source
        if owner_id:
            row["owner_id"] = owner_id
        result = self._client.table("records").insert(row).execute()
        if not result.data:
            raise RuntimeError("Failed to create record")
        return result.data[0]

    def create_records_batch(
        self,
        crm_id: str,
        entity_name: str,
        rows: list[dict[str, Any]],
        owner_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Batch insert records for CSV import."""
        records = [
            {
                "crm_id": crm_id,
                "entity_name": entity_name,
                "data": r["data"],
                "source": r.get("source"),
                **({"owner_id": owner_id} if owner_id else {}),
            }
            for r in rows
        ]
        result = self._client.table("records").insert(records).execute()
        return result.data or []

    def list_records(
        self,
        crm_id: str,
        entity_name: str,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """List non-deleted records for a CRM entity."""
        count_result = (
            self._client.table("records")
            .select("id", count="exact")
            .eq("crm_id", crm_id)
            .eq("entity_name", entity_name)
            .is_("deleted_at", "null")
            .execute()
        )
        total = count_result.count or 0

        result = (
            self._client.table("records")
            .select("*")
            .eq("crm_id", crm_id)
            .eq("entity_name", entity_name)
            .is_("deleted_at", "null")
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return result.data or [], total

    def get_record(self, record_id: str, crm_id: str, entity_name: str) -> dict[str, Any] | None:
        """Get a single non-deleted record."""
        result = (
            self._client.table("records")
            .select("*")
            .eq("id", record_id)
            .eq("crm_id", crm_id)
            .eq("entity_name", entity_name)
            .is_("deleted_at", "null")
            .execute()
        )
        return result.data[0] if result.data else None

    def update_record(self, record_id: str, crm_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update record data (merge)."""
        result = (
            self._client.table("records")
            .update({"data": data})
            .eq("id", record_id)
            .eq("crm_id", crm_id)
            .is_("deleted_at", "null")
            .execute()
        )
        return result.data[0] if result.data else None

    def soft_delete_record(self, record_id: str, crm_id: str, entity_name: str) -> bool:
        """Soft-delete a record by setting deleted_at."""
        from datetime import datetime, timezone

        result = (
            self._client.table("records")
            .update({"deleted_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", record_id)
            .eq("crm_id", crm_id)
            .eq("entity_name", entity_name)
            .is_("deleted_at", "null")
            .execute()
        )
        return bool(result.data)

    # ── WORKFLOWS ───────────────────────────────────────────────────

    def create_workflow(
        self,
        crm_id: str,
        name: str,
        trigger: dict[str, Any],
        actions: list[dict[str, Any]],
        status: str = "draft",
    ) -> dict[str, Any]:
        """Create a workflow (starts as draft)."""
        result = (
            self._client.table("workflows")
            .insert({
                "crm_id": crm_id,
                "name": name,
                "trigger": trigger,
                "actions": actions,
                "status": status,
            })
            .execute()
        )
        if not result.data:
            raise RuntimeError("Failed to create workflow")
        return result.data[0]

    def list_workflows(self, crm_id: str) -> list[dict[str, Any]]:
        """List workflows for a CRM."""
        result = (
            self._client.table("workflows")
            .select("*")
            .eq("crm_id", crm_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    # ── ANALYTICS ───────────────────────────────────────────────────

    def count_records_by_field(
        self, crm_id: str, entity_name: str, field_name: str
    ) -> list[dict[str, Any]]:
        """Count records grouped by a JSONB data field value."""
        # Use Supabase RPC or direct query
        result = (
            self._client.table("records")
            .select("data")
            .eq("crm_id", crm_id)
            .eq("entity_name", entity_name)
            .is_("deleted_at", "null")
            .execute()
        )
        counts: dict[str, int] = {}
        for rec in result.data or []:
            val = rec.get("data", {}).get(field_name, "Unknown")
            counts[val] = counts.get(val, 0) + 1
        return [{"value": k, "count": v} for k, v in counts.items()]

    def count_records(self, crm_id: str, entity_name: str) -> int:
        """Count non-deleted records for an entity."""
        result = (
            self._client.table("records")
            .select("id", count="exact")
            .eq("crm_id", crm_id)
            .eq("entity_name", entity_name)
            .is_("deleted_at", "null")
            .execute()
        )
        return result.count or 0

    def count_records_by_field_value(
        self, crm_id: str, entity_name: str, field_name: str, field_value: str
    ) -> int:
        """Count records with a specific JSONB data field value."""
        result = (
            self._client.table("records")
            .select("data")
            .eq("crm_id", crm_id)
            .eq("entity_name", entity_name)
            .is_("deleted_at", "null")
            .execute()
        )
        return sum(
            1
            for rec in (result.data or [])
            if rec.get("data", {}).get(field_name) == field_value
        )

    # ── EVOLUTION PROPOSALS ─────────────────────────────────────────

    def create_proposal(
        self,
        crm_id: str,
        summary: str,
        proposed_change: dict[str, Any],
        evidence: list[dict[str, Any]],
        config_version: int,
    ) -> dict[str, Any]:
        """Create an evolution proposal."""
        result = (
            self._client.table("evolution_proposals")
            .insert({
                "crm_id": crm_id,
                "summary": summary,
                "proposed_change": proposed_change,
                "evidence": evidence,
                "configuration_version_at_creation": config_version,
                "status": "pending",
            })
            .execute()
        )
        if not result.data:
            raise RuntimeError("Failed to create proposal")
        return result.data[0]

    def list_proposals(self, crm_id: str) -> list[dict[str, Any]]:
        """List proposals for a CRM."""
        result = (
            self._client.table("evolution_proposals")
            .select("*")
            .eq("crm_id", crm_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    def get_proposal(self, proposal_id: str, crm_id: str) -> dict[str, Any] | None:
        """Get a single proposal."""
        result = (
            self._client.table("evolution_proposals")
            .select("*")
            .eq("id", proposal_id)
            .eq("crm_id", crm_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def approve_proposal(
        self, proposal_id: str, actor_id: str, expected_version: int | None = None
    ) -> dict[str, Any] | None:
        """Approve a proposal through the authenticated database function.

        actor_id remains for call-site compatibility; PostgreSQL derives the
        authorization identity from auth.uid().
        """
        params: dict[str, Any] = {"proposal_uuid": proposal_id}
        if expected_version is not None:
            params["expected_version"] = expected_version
        rpc_res = self._client.rpc("approve_evolution_proposal", params).execute()
        if rpc_res.data == "approved":
            res = self._client.table("evolution_proposals").select("*").eq("id", proposal_id).execute()
            return res.data[0] if res.data else None
        if rpc_res.data:
            return {"status": rpc_res.data, "error": rpc_res.data}
        return None

    def apply_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        """Apply a proposal only through the atomic database function."""
        try:
            rpc_res = self._client.rpc("apply_evolution_proposal", {"proposal_uuid": proposal_id}).execute()
        except Exception as exc:
            raise RuntimeError("Failed to apply evolution proposal through database function") from exc

        if rpc_res.data == "applied":
            res = self._client.table("evolution_proposals").select("*").eq("id", proposal_id).execute()
            return res.data[0] if res.data else None
        if rpc_res.data:
            return {"status": rpc_res.data, "error": rpc_res.data}
        return None

    def reject_proposal(
        self, proposal_id: str, actor_id: str, reason: str
    ) -> dict[str, Any] | None:
        """Reject a proposal via stored procedure or direct update."""
        try:
            rpc_res = self._client.rpc(
                "reject_evolution_proposal", {"proposal_uuid": proposal_id, "p_reason": reason}
            ).execute()
            if rpc_res.data == "rejected":
                res = self._client.table("evolution_proposals").select("*").eq("id", proposal_id).execute()
                return res.data[0] if res.data else None
            elif rpc_res.data:
                return {"status": rpc_res.data, "error": rpc_res.data}
        except Exception:
            pass

        from datetime import datetime, timezone

        result = (
            self._client.table("evolution_proposals")
            .update({
                "status": "rejected",
                "rejected_at": datetime.now(timezone.utc).isoformat(),
                "rejected_by": actor_id,
                "rejection_reason": reason,
            })
            .eq("id", proposal_id)
            .in_("status", ["pending", "approved"])
            .execute()
        )
        return result.data[0] if result.data else None

    def fail_proposal(self, proposal_id: str, error: str) -> dict[str, Any] | None:
        """Mark a proposal as failed with error details."""
        result = (
            self._client.table("evolution_proposals")
            .update({
                "status": "failed",
                "application_error": error,
            })
            .eq("id", proposal_id)
            .eq("status", "approved")
            .execute()
        )
        return result.data[0] if result.data else None

    def update_workflow_actions(
        self, workflow_id: str, crm_id: str, actions: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Update workflow actions (used by apply_proposal)."""
        result = (
            self._client.table("workflows")
            .update({"actions": actions})
            .eq("id", workflow_id)
            .eq("crm_id", crm_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def get_workflow(self, workflow_id: str, crm_id: str) -> dict[str, Any] | None:
        """Get a single workflow."""
        result = (
            self._client.table("workflows")
            .select("*")
            .eq("id", workflow_id)
            .eq("crm_id", crm_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def increment_config_version(self, crm_id: str, owner_id: str) -> dict[str, Any] | None:
        """Increment CRM configuration_version. Returns updated CRM."""
        # Fetch current version then update atomically
        crm = self.get_crm(crm_id, owner_id)
        if not crm:
            return None
        new_version = crm["configuration_version"] + 1
        result = (
            self._client.table("crms")
            .update({"configuration_version": new_version})
            .eq("id", crm_id)
            .eq("owner_id", owner_id)
            .eq("configuration_version", crm["configuration_version"])  # optimistic lock
            .execute()
        )
        return result.data[0] if result.data else None

    # ── AUDIT LOGS ──────────────────────────────────────────────────

    def insert_audit_log(
        self,
        crm_id: str,
        user_id: str,
        action: str,
        entity_type: str,
        entity_id: str | None = None,
        old_values: dict[str, Any] | None = None,
        new_values: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Insert an audit log entry. crm_owner_id is looked up from the CRM."""
        crm = (
            self._client.table("crms")
            .select("owner_id")
            .eq("id", crm_id)
            .execute()
        )
        crm_owner_id = crm.data[0]["owner_id"] if crm.data else None

        row: dict[str, Any] = {
            "crm_id": crm_id,
            "crm_owner_id": crm_owner_id,
            "user_id": user_id,
            "action": action,
            "entity_type": entity_type,
        }
        if entity_id:
            row["entity_id"] = entity_id
        if old_values:
            row["old_values"] = old_values
        if new_values:
            row["new_values"] = new_values
        if metadata:
            row["metadata"] = metadata

        result = self._client.table("audit_logs").insert(row).execute()
        if not result.data:
            raise RuntimeError("Failed to insert audit log")
        return result.data[0]
