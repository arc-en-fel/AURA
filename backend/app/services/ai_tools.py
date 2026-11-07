"""AI tools for CRM schema modifications.

Enables AURA Copilot to programmatically modify CRM schemas through controlled
tool calls that invoke backend operations.

Tools:
- add_crm_field: Add a new field to a CRM entity
- update_crm_field: Update field properties
- delete_crm_field: Delete a field from a CRM entity
- add_crm_stage: Add a pipeline stage
- delete_crm_stage: Delete a pipeline stage
- reorder_crm_fields: Reorder fields in an entity
- reorder_crm_stages: Reorder pipeline stages

All validation happens server-side. Tools return the updated CRMConfiguration
so the AI can see the result of its changes.
"""
from __future__ import annotations

from typing import Any
import logging
from uuid import UUID

from app.schemas.crm import CRMConfiguration, FieldType
from app.services.crm_editor import CRMSchemaEditor
from app.database import CRMRepository

logger = logging.getLogger(__name__)


class CRMSchemaTools:
    """Tool implementations for AI-driven CRM schema modifications and record operations.
    
    These are thin wrappers around backend operations that the AI can call.
    Each tool validates inputs and delegates to CRMSchemaEditor + database.
    """

    # ── Record CRUD Tools ──────────────────────────────────────────

    @staticmethod
    def _resolve_entity(config: dict[str, Any], entity_identifier: str | None) -> dict[str, Any] | None:
        """
        Resolve an entity from configuration by name, id, or label.
        
        RC-001 FIX: Returns None if no match found instead of silently falling back to entities[0].
        This ensures explicit entity selection rather than silent fallback to wrong entity.
        
        Args:
            config: CRM configuration dict
            entity_identifier: Entity name, ID, or label to resolve
            
        Returns:
            Resolved entity dict, or None if no match found or no entities available
        """
        entities = config.get("entities", [])
        if not entities:
            return None
        if not entity_identifier:
            return None
        
        norm = str(entity_identifier).lower().strip().replace(" ", "_").replace("-", "_")
        for e in entities:
            name = str(e.get("name", "")).lower().strip().replace(" ", "_").replace("-", "_")
            label = str(e.get("label", "")).lower().strip().replace(" ", "_").replace("-", "_")
            if name == norm or label == norm:
                return e
        
        # RC-001: Return None instead of falling back to entities[0]
        # Caller must handle None and ask user for clarification
        return None

    @staticmethod
    def _validate_and_normalize_record_data(
        entity: dict[str, Any],
        raw_data: dict[str, Any],
        config: dict[str, Any],
        partial: bool = False,
    ) -> tuple[bool, dict[str, Any] | str]:
        """
        Validate and normalize record data against the entity schema.
        Preserves all valid fields, coerces types, enforces allowed options,
        and returns an actionable error if any unknown or invalid field is passed.
        """
        entity_fields = entity.get("fields", [])
        field_map: dict[str, dict[str, Any]] = {}
        for f in entity_fields:
            name = f.get("name", "")
            label = f.get("label", "")
            field_map[name] = f
            field_map[name.lower()] = f
            field_map[name.lower().replace("_", " ")] = f
            field_map[label.lower()] = f
            field_map[label.lower().replace(" ", "_")] = f
            if f.get("type") in ("select", "status") or "status" in name.lower():
                field_map["status"] = f
                field_map["crm_status"] = f
                field_map["crm status"] = f

        normalized: dict[str, Any] = {}

        for raw_k, raw_v in raw_data.items():
            k_clean = str(raw_k).strip().lower()
            matched_field = field_map.get(k_clean) or field_map.get(k_clean.replace("_", " "))
            if not matched_field:
                available = [f"{f['name']} ({f.get('label', f['name'])})" for f in entity_fields]
                return False, f"Unknown field '{raw_k}'. Available fields for '{entity.get('name')}': {', '.join(available)}"

            canonical_key = matched_field["name"]
            ftype = matched_field.get("type", "text")

            if raw_v is None:
                if matched_field.get("required", False) and not partial:
                    return False, f"Required field '{canonical_key}' cannot be null."
                normalized[canonical_key] = None
                continue

            if ftype in ("number", "integer"):
                if isinstance(raw_v, (int, float)):
                    normalized[canonical_key] = raw_v
                else:
                    v_str = str(raw_v).strip().replace(",", "")
                    if v_str.isdigit():
                        normalized[canonical_key] = int(v_str)
                    else:
                        try:
                            normalized[canonical_key] = float(v_str)
                        except ValueError:
                            return False, f"Field '{canonical_key}' must be a number, got '{raw_v}'"
            elif ftype in ("currency", "float"):
                if isinstance(raw_v, (int, float)):
                    normalized[canonical_key] = raw_v
                else:
                    v_str = str(raw_v).strip().replace("$", "").replace(",", "")
                    if v_str.isdigit():
                        normalized[canonical_key] = int(v_str)
                    else:
                        try:
                            normalized[canonical_key] = float(v_str)
                        except ValueError:
                            return False, f"Field '{canonical_key}' must be a valid currency/number, got '{raw_v}'"
            elif ftype in ("select", "status"):
                v_str = str(raw_v).strip()
                allowed_options = matched_field.get("options") or config.get("pipeline_stages") or []
                if allowed_options:
                    matched_opt = next((opt for opt in allowed_options if opt.lower() == v_str.lower()), None)
                    if matched_opt:
                        normalized[canonical_key] = matched_opt
                    else:
                        return False, f"Field '{canonical_key}' value '{v_str}' is not in allowed options: {allowed_options}"
                else:
                    normalized[canonical_key] = v_str
            elif ftype == "boolean":
                if isinstance(raw_v, bool):
                    normalized[canonical_key] = raw_v
                else:
                    v_str = str(raw_v).strip().lower()
                    if v_str in ("true", "1", "yes"):
                        normalized[canonical_key] = True
                    elif v_str in ("false", "0", "no"):
                        normalized[canonical_key] = False
                    else:
                        return False, f"Field '{canonical_key}' must be a boolean, got '{raw_v}'"
            else:
                normalized[canonical_key] = str(raw_v).strip()

        if not partial:
            for f in entity_fields:
                if f.get("required", False) and f["name"] not in normalized:
                    return False, f"Required field '{f['name']}' ({f.get('label', f['name'])}) is missing."

        return True, normalized

    @staticmethod
    def create_record(
        crm_id: str,
        owner_id: str,
        entity_name: str | None = None,
        entity_id: str | None = None,
        data: dict[str, Any] | None = None,
        source: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Create a new record in the CRM dynamically without hardcoding entity or fields.
        """
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized",
            }

        config = crm.get("configuration", {})
        target_name = entity_name or entity_id or kwargs.get("entity")
        entity = CRMSchemaTools._resolve_entity(config, target_name)
        
        if not entity:
            entities = config.get("entities", [])
            if not entities:
                return {
                    "success": False,
                    "error_code": "INVALID_ENTITY",
                    "error_message": f"No entities defined in this CRM",
                }
            available = [f"{e.get('name')} ({e.get('label')})" for e in entities]
            return {
                "success": False,
                "error_code": "INVALID_ENTITY",
                "error_message": (
                    f"Entity '{target_name}' not found. "
                    f"Available entities: {', '.join(available)}"
                ),
            }

        resolved_name = entity["name"]
        raw_record_data = data if data is not None else kwargs.get("changes", {})
        if not isinstance(raw_record_data, dict):
            raw_record_data = {}

        # Merge kwargs that might be field names
        for k, v in kwargs.items():
            if k not in raw_record_data and k not in ("entity", "entity_id", "entity_name", "source", "crm_id", "owner_id"):
                raw_record_data[k] = v

        # Validate and normalize data against schema
        is_valid, validation_result = CRMSchemaTools._validate_and_normalize_record_data(
            entity=entity,
            raw_data=raw_record_data,
            config=config,
            partial=False,
        )
        if not is_valid:
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": str(validation_result),
            }

        record_data = validation_result

        # Duplicate prevention check (Requirement 13)
        try:
            recent_records, _ = repo.list_records(crm_id, resolved_name, limit=20)
            for rec in recent_records:
                if rec.get("data") == record_data:
                    logger.info("[AI-TOOLS] Found identical existing record %s, returning it to prevent duplicate", rec["id"])
                    return {
                        "success": True,
                        "crm_id": crm_id,
                        "entity_name": resolved_name,
                        "data": rec,
                    }
        except Exception:
            pass

        try:
            result = repo.create_record(
                crm_id=crm_id,
                entity_name=resolved_name,
                data=record_data,
                source=source or "AI Copilot",
                owner_id=owner_id,
            )
            logger.info(
                "[AI-TOOLS] Created record in entity '%s' for CRM %s via AI tool",
                resolved_name,
                crm_id,
            )
            return {
                "success": True,
                "crm_id": crm_id,
                "entity_name": resolved_name,
                "data": result,
            }
        except Exception as exc:
            logger.exception("Error creating record via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to create record: {str(exc)}",
            }

    @staticmethod
    def update_record(
        crm_id: str,
        owner_id: str,
        record_id: str | None = None,
        entity_name: str | None = None,
        entity_id: str | None = None,
        data: dict[str, Any] | None = None,
        changes: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Update an existing record dynamically.
        """
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized",
            }

        config = crm.get("configuration", {})
        target_name = entity_name or entity_id or kwargs.get("entity")
        entity = CRMSchemaTools._resolve_entity(config, target_name)
        
        if not entity:
            entities = config.get("entities", [])
            if not entities:
                return {
                    "success": False,
                    "error_code": "INVALID_ENTITY",
                    "error_message": f"No entities defined in this CRM",
                }
            available = [f"{e.get('name')} ({e.get('label')})" for e in entities]
            return {
                "success": False,
                "error_code": "INVALID_ENTITY",
                "error_message": (
                    f"Entity '{target_name}' not found. "
                    f"Available entities: {', '.join(available)}"
                ),
            }

        resolved_name = entity["name"]
        raw_update_payload = changes if changes is not None else (data if data is not None else {})
        if not isinstance(raw_update_payload, dict):
            raw_update_payload = {}

        for k, v in kwargs.items():
            if k not in raw_update_payload and k not in ("entity", "entity_id", "entity_name", "id", "record_id", "crm_id", "owner_id"):
                raw_update_payload[k] = v

        # Validate and normalize update fields
        is_valid, validation_result = CRMSchemaTools._validate_and_normalize_record_data(
            entity=entity,
            raw_data=raw_update_payload,
            config=config,
            partial=True,
        )
        if not is_valid:
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": str(validation_result),
            }

        update_payload = validation_result

        # Locate record by ID or by search
        target_record_id = record_id or kwargs.get("id")
        existing_record = None

        if target_record_id:
            try:
                UUID(str(target_record_id))
                existing_record = repo.get_record(str(target_record_id), crm_id, resolved_name)
            except (ValueError, TypeError):
                pass

        if not existing_record:
            items, _ = repo.list_records(crm_id, resolved_name, limit=50)
            search_term = str(target_record_id or "").lower().strip()
            for r in items:
                r_data = r.get("data", {})
                if not search_term or any(search_term in str(v).lower() for v in r_data.values()):
                    existing_record = r
                    target_record_id = r["id"]
                    break

        if not existing_record or not target_record_id:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": f"Record '{target_record_id}' not found in entity '{resolved_name}'",
            }

        try:
            merged_data = {**existing_record.get("data", {}), **update_payload}
            result = repo.update_record(str(target_record_id), crm_id, merged_data)
            logger.info(
                "[AI-TOOLS] Updated record %s in entity '%s' for CRM %s via AI tool",
                target_record_id,
                resolved_name,
                crm_id,
            )
            return {
                "success": True,
                "crm_id": crm_id,
                "entity_name": resolved_name,
                "data": result or merged_data,
            }
        except Exception as exc:
            logger.exception("Error updating record via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to update record: {str(exc)}",
            }

    @staticmethod
    def delete_record(
        crm_id: str,
        owner_id: str,
        record_id: str | None = None,
        entity_name: str | None = None,
        entity_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Soft delete a record dynamically.
        
        RC-001 FIX: Now properly handles None returned by _resolve_entity.
        """
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized",
            }

        config = crm.get("configuration", {})
        target_name = entity_name or entity_id or kwargs.get("entity")
        entity = CRMSchemaTools._resolve_entity(config, target_name)
        
        # RC-001: Explicitly check for None
        if not entity:
            entities = config.get("entities", [])
            if not entities:
                return {
                    "success": False,
                    "error_code": "INVALID_ENTITY",
                    "error_message": f"No entities defined in this CRM",
                }
            available = [f"{e.get('name')} ({e.get('label')})" for e in entities]
            return {
                "success": False,
                "error_code": "INVALID_ENTITY",
                "error_message": (
                    f"Entity '{target_name}' not found. "
                    f"Available entities: {', '.join(available)}"
                ),
            }

        resolved_name = entity["name"]
        target_record_id = record_id or kwargs.get("id")
        existing_record = None

        if target_record_id:
            try:
                UUID(str(target_record_id))
                existing_record = repo.get_record(str(target_record_id), crm_id, resolved_name)
            except (ValueError, TypeError):
                pass

        if not existing_record:
            items, _ = repo.list_records(crm_id, resolved_name, limit=50)
            search_term = str(target_record_id or "").lower().strip()
            for r in items:
                r_data = r.get("data", {})
                if search_term and any(search_term in str(v).lower() for v in r_data.values()):
                    existing_record = r
                    target_record_id = r["id"]
                    break

        if not existing_record or not target_record_id:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": f"Record '{target_record_id}' not found in entity '{resolved_name}'",
            }

        try:
            repo.soft_delete_record(str(target_record_id), crm_id, resolved_name)
            logger.info(
                "[AI-TOOLS] Deleted record %s from entity '%s' in CRM %s via AI tool",
                target_record_id,
                resolved_name,
                crm_id,
            )
            return {
                "success": True,
                "crm_id": crm_id,
                "entity_name": resolved_name,
                "data": {"deleted": True, "record_id": str(target_record_id)},
            }
        except Exception as exc:
            logger.exception("Error deleting record via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to delete record: {str(exc)}",
            }

    # ── Read-Only Query & Analytics Tools ──────────────────────────

    @staticmethod
    def get_crm_summary(crm_id: str, owner_id: str, **kwargs: Any) -> dict[str, Any]:
        """Get high-level summary of CRM schema and live record counts."""
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized",
            }
        config = crm.get("configuration", {})
        entities = config.get("entities", [])
        entity_summaries = []
        total_records = 0
        for e in entities:
            e_name = e.get("name", "")
            rec_count = repo.count_records(crm_id, e_name)
            total_records += rec_count
            entity_summaries.append({
                "name": e_name,
                "label": e.get("label", e_name),
                "field_count": len(e.get("fields", [])),
                "record_count": rec_count,
            })
        return {
            "success": True,
            "crm_id": crm_id,
            "name": config.get("name", crm.get("name", "Active CRM")),
            "industry": config.get("industry", "general"),
            "pipeline_stages": config.get("pipeline_stages", []),
            "entities": entity_summaries,
            "total_records": total_records,
        }

    @staticmethod
    def get_entity_schema(
        crm_id: str,
        owner_id: str,
        entity_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Get schema details (fields, types, required, options) for an entity."""
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized",
            }
        config = crm.get("configuration", {})
        entity = CRMSchemaTools._resolve_entity(config, entity_name)
        if not entity:
            entities = config.get("entities", [])
            entity = entities[0] if entities else None
        if not entity:
            return {
                "success": False,
                "error_code": "INVALID_ENTITY",
                "error_message": "No entities found in this CRM",
            }
        return {
            "success": True,
            "crm_id": crm_id,
            "entity_name": entity.get("name"),
            "label": entity.get("label"),
            "fields": [
                {
                    "name": f.get("name"),
                    "label": f.get("label"),
                    "type": f.get("type"),
                    "required": f.get("required", False),
                    "options": f.get("options", []),
                }
                for f in entity.get("fields", [])
            ],
            "pipeline_stages": config.get("pipeline_stages", []),
        }

    @staticmethod
    def get_status_distribution(
        crm_id: str,
        owner_id: str,
        entity_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Get live count of records grouped by status/pipeline stage."""
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized",
            }
        config = crm.get("configuration", {})
        entity = CRMSchemaTools._resolve_entity(config, entity_name)
        if not entity:
            entities = config.get("entities", [])
            entity = entities[0] if entities else None
        if not entity:
            return {
                "success": False,
                "error_code": "INVALID_ENTITY",
                "error_message": "No entities found in this CRM",
            }
        resolved_name = entity.get("name")
        pipeline_stages = config.get("pipeline_stages", [])

        # Find status field
        status_field = None
        for f in entity.get("fields", []):
            if f.get("type") in ("select", "status") or "status" in f.get("name", "").lower():
                status_field = f
                break

        records = repo.get_all_records(crm_id, resolved_name)
        status_key = status_field.get("name", "crm_status") if status_field else "crm_status"
        
        allowed_stages = list(pipeline_stages)
        if status_field and status_field.get("options"):
            for opt in status_field.get("options"):
                if opt not in allowed_stages:
                    allowed_stages.append(opt)

        distribution = {stage: 0 for stage in allowed_stages}
        for r in records:
            r_data = r.get("data", {})
            val = r_data.get(status_key)
            if not val:
                for alt_k in ["status", "crm_status", "stage", "lead_status"]:
                    if r_data.get(alt_k):
                        val = r_data.get(alt_k)
                        break
            val_str = str(val).strip() if val else "Unassigned"
            matched_stage = next((s for s in allowed_stages if s.lower() == val_str.lower()), val_str)
            distribution[matched_stage] = distribution.get(matched_stage, 0) + 1

        return {
            "success": True,
            "crm_id": crm_id,
            "entity_name": resolved_name,
            "distribution": distribution,
            "total_records": len(records),
        }

    @staticmethod
    def count_records(
        crm_id: str,
        owner_id: str,
        entity_name: str | None = None,
        filters: dict[str, Any] | None = None,
        stage: str | None = None,
        status: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Count records matching optional filters (e.g., status or stage)."""
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized",
            }
        config = crm.get("configuration", {})
        entity = CRMSchemaTools._resolve_entity(config, entity_name)
        if not entity:
            entities = config.get("entities", [])
            entity = entities[0] if entities else None
        if not entity:
            return {
                "success": False,
                "error_code": "INVALID_ENTITY",
                "error_message": "No entities found in this CRM",
            }
        resolved_name = entity.get("name")
        all_filters = dict(filters or {})
        if stage:
            all_filters["status"] = stage
        if status:
            all_filters["status"] = status
        for k, v in kwargs.items():
            if k in ("crm_status", "lead_status"):
                all_filters["status"] = v

        if not all_filters:
            count = repo.count_records(crm_id, resolved_name)
            return {
                "success": True,
                "crm_id": crm_id,
                "entity_name": resolved_name,
                "count": count,
                "filters_applied": {},
            }

        # Filter live records
        records = repo.get_all_records(crm_id, resolved_name)
        status_field = next(
            (f["name"] for f in entity.get("fields", []) if f.get("type") in ("select", "status") or "status" in f["name"].lower()),
            "crm_status",
        )

        matching_count = 0
        for r in records:
            r_data = r.get("data", {})
            matches = True
            for f_key, f_val in all_filters.items():
                target_val = str(f_val).lower().strip()
                if f_key in ("status", "stage", "crm_status"):
                    actual = r_data.get(status_field) or r_data.get("crm_status") or r_data.get("status") or r_data.get("stage")
                else:
                    actual = r_data.get(f_key)
                if not actual or str(actual).lower().strip() != target_val:
                    matches = False
                    break
            if matches:
                matching_count += 1

        return {
            "success": True,
            "crm_id": crm_id,
            "entity_name": resolved_name,
            "count": matching_count,
            "filters_applied": all_filters,
        }

    @staticmethod
    def query_records(
        crm_id: str,
        owner_id: str,
        entity_name: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Query non-deleted records with optional filtering."""
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized",
            }
        config = crm.get("configuration", {})
        entity = CRMSchemaTools._resolve_entity(config, entity_name)
        if not entity:
            entities = config.get("entities", [])
            entity = entities[0] if entities else None
        if not entity:
            return {
                "success": False,
                "error_code": "INVALID_ENTITY",
                "error_message": "No entities found in this CRM",
            }
        resolved_name = entity.get("name")
        records = repo.get_all_records(crm_id, resolved_name, limit=max(limit, 50))
        
        filtered = []
        for r in records:
            r_data = r.get("data", {})
            if filters:
                matches = True
                for k, v in filters.items():
                    if str(r_data.get(k, "")).lower() != str(v).lower():
                        matches = False
                        break
                if not matches:
                    continue
            filtered.append({
                "id": r.get("id"),
                "entity_name": resolved_name,
                "created_at": r.get("created_at"),
                "data": r_data,
            })
            if len(filtered) >= limit:
                break

        return {
            "success": True,
            "crm_id": crm_id,
            "entity_name": resolved_name,
            "total_returned": len(filtered),
            "records": filtered,
        }

    @staticmethod
    def aggregate_records(
        crm_id: str,
        owner_id: str,
        field_name: str,
        aggregation_type: str = "sum",
        entity_name: str | None = None,
        filters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Compute numeric aggregations (sum, avg, min, max, count) on a field."""
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized",
            }
        config = crm.get("configuration", {})
        entity = CRMSchemaTools._resolve_entity(config, entity_name)
        if not entity:
            entities = config.get("entities", [])
            entity = entities[0] if entities else None
        if not entity:
            return {
                "success": False,
                "error_code": "INVALID_ENTITY",
                "error_message": "No entities found in this CRM",
            }
        resolved_name = entity.get("name")
        records = repo.get_all_records(crm_id, resolved_name)

        values: list[float] = []
        for r in records:
            r_data = r.get("data", {})
            v = r_data.get(field_name)
            if v is not None:
                try:
                    clean_v = float(str(v).replace("$", "").replace(",", "").strip())
                    values.append(clean_v)
                except ValueError:
                    pass

        agg = aggregation_type.lower()
        if not values:
            result_val = 0.0
        elif agg in ("sum", "total"):
            result_val = sum(values)
        elif agg in ("avg", "average", "mean"):
            result_val = sum(values) / len(values)
        elif agg == "min":
            result_val = min(values)
        elif agg == "max":
            result_val = max(values)
        elif agg == "count":
            result_val = float(len(values))
        else:
            result_val = sum(values)

        return {
            "success": True,
            "crm_id": crm_id,
            "entity_name": resolved_name,
            "field_name": field_name,
            "aggregation": agg,
            "value": round(result_val, 2),
            "record_count": len(values),
        }

    # ── Schema Modification Tools ──────────────────────────────────

    @staticmethod
    def add_crm_field(
        crm_id: str,
        owner_id: str,
        field_name: str | None = None,
        entity_name: str | None = None,
        field_type: FieldType = "text",
        label: str | None = None,
        required: bool = False,
        options: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Add a new field to a CRM entity."""
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized",
            }

        actual_field_name = field_name or kwargs.get("field_name") or kwargs.get("name")
        if not actual_field_name:
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": "field_name is required",
            }

        actual_label = label or kwargs.get("field_label") or str(actual_field_name).replace("_", " ").title()

        try:
            target_entity = CRMSchemaTools._resolve_entity(
                crm["configuration"], entity_name or kwargs.get("entity") or kwargs.get("entity_id")
            )
            resolved_entity_name = target_entity["name"] if target_entity else crm["configuration"]["entities"][0]["name"]

            updated_config = CRMSchemaEditor.add_field(
                crm["configuration"],
                entity_name=resolved_entity_name,
                field_name=actual_field_name,
                field_label=actual_label,
                field_type=field_type,
                required=required,
                options=options,
            )

            CRMConfiguration(**updated_config)

            updated_crm = repo.update_crm_configuration(
                crm_id=crm_id,
                owner_id=owner_id,
                configuration=updated_config,
            )

            if not updated_crm:
                return {
                    "success": False,
                    "error_code": "INTERNAL_ERROR",
                    "error_message": "Failed to save CRM configuration",
                }

            logger.info(
                "[AI-TOOLS] Added field '%s' (type: %s) to CRM %s via AI tool",
                actual_field_name,
                field_type,
                crm_id,
            )

            return {
                "success": True,
                "crm_id": str(updated_crm["id"]),
                "configuration": updated_crm["configuration"],
                "configuration_version": updated_crm["configuration_version"],
            }
        except ValueError as exc:
            error_msg = str(exc)
            if "already exists" in error_msg:
                return {
                    "success": False,
                    "error_code": "CONFLICT",
                    "error_message": error_msg,
                }
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": error_msg,
            }
        except Exception as exc:
            logger.exception("Error adding CRM field via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to add field: {str(exc)}",
            }

    @staticmethod
    def update_crm_field(
        crm_id: str,
        owner_id: str,
        field_name: str | None = None,
        label: str | None = None,
        field_type: FieldType | None = None,
        required: bool | None = None,
        options: list[str] | None = None,
        entity_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Update properties of an existing field."""
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized",
            }

        actual_field_name = field_name or kwargs.get("field_name") or kwargs.get("name")
        if not actual_field_name:
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": "field_name is required",
            }

        try:
            target_entity = CRMSchemaTools._resolve_entity(
                crm["configuration"], entity_name or kwargs.get("entity") or kwargs.get("entity_id")
            )
            resolved_entity_name = target_entity["name"] if target_entity else crm["configuration"]["entities"][0]["name"]

            updated_config = CRMSchemaEditor.update_field(
                crm["configuration"],
                entity_name=resolved_entity_name,
                field_name=actual_field_name,
                label=label,
                field_type=field_type,
                required=required,
                options=options,
            )

            CRMConfiguration(**updated_config)

            updated_crm = repo.update_crm_configuration(
                crm_id=crm_id,
                owner_id=owner_id,
                configuration=updated_config,
            )

            if not updated_crm:
                return {
                    "success": False,
                    "error_code": "INTERNAL_ERROR",
                    "error_message": "Failed to save CRM configuration",
                }

            logger.info(
                "[AI-TOOLS] Updated field '%s' in CRM %s via AI tool",
                actual_field_name,
                crm_id,
            )

            return {
                "success": True,
                "crm_id": str(updated_crm["id"]),
                "configuration": updated_crm["configuration"],
                "configuration_version": updated_crm["configuration_version"],
            }
        except ValueError as exc:
            error_msg = str(exc)
            if "not found" in error_msg:
                return {
                    "success": False,
                    "error_code": "NOT_FOUND",
                    "error_message": error_msg,
                }
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": error_msg,
            }
        except Exception as exc:
            logger.exception("Error updating CRM field via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to update field: {str(exc)}",
            }

    @staticmethod
    def delete_crm_field(
        crm_id: str,
        owner_id: str,
        field_name: str | None = None,
        entity_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Delete a field from a CRM entity."""
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized",
            }

        actual_field_name = field_name or kwargs.get("field_name") or kwargs.get("name")
        if not actual_field_name:
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": "field_name is required",
            }

        try:
            target_entity = CRMSchemaTools._resolve_entity(
                crm["configuration"], entity_name or kwargs.get("entity") or kwargs.get("entity_id")
            )
            resolved_entity_name = target_entity["name"] if target_entity else crm["configuration"]["entities"][0]["name"]

            updated_config = CRMSchemaEditor.delete_field(
                crm["configuration"],
                entity_name=resolved_entity_name,
                field_name=actual_field_name,
            )

            CRMConfiguration(**updated_config)

            updated_crm = repo.update_crm_configuration(
                crm_id=crm_id,
                owner_id=owner_id,
                configuration=updated_config,
            )

            if not updated_crm:
                return {
                    "success": False,
                    "error_code": "INTERNAL_ERROR",
                    "error_message": "Failed to save CRM configuration",
                }

            logger.info(
                "[AI-TOOLS] Deleted field '%s' from CRM %s via AI tool",
                actual_field_name,
                crm_id,
            )

            return {
                "success": True,
                "crm_id": str(updated_crm["id"]),
                "configuration": updated_crm["configuration"],
                "configuration_version": updated_crm["configuration_version"],
            }
        except ValueError as exc:
            error_msg = str(exc)
            if "not found" in error_msg:
                return {
                    "success": False,
                    "error_code": "NOT_FOUND",
                    "error_message": error_msg,
                }
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": error_msg,
            }
        except Exception as exc:
            logger.exception("Error deleting CRM field via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to delete field: {str(exc)}",
            }

    @staticmethod
    def add_crm_stage(
        crm_id: str,
        owner_id: str,
        stage_name: str | None = None,
        position: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Add a new pipeline stage to a CRM."""
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized",
            }

        actual_stage_name = stage_name or kwargs.get("stage_name") or kwargs.get("name")
        if not actual_stage_name:
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": "stage_name is required",
            }

        try:
            updated_config = CRMSchemaEditor.add_pipeline_stage(
                crm["configuration"],
                stage_name=actual_stage_name,
                position=position,
            )

            CRMConfiguration(**updated_config)

            updated_crm = repo.update_crm_configuration(
                crm_id=crm_id,
                owner_id=owner_id,
                configuration=updated_config,
            )

            if not updated_crm:
                return {
                    "success": False,
                    "error_code": "INTERNAL_ERROR",
                    "error_message": "Failed to save CRM configuration",
                }

            logger.info(
                "[AI-TOOLS] Added stage '%s' to CRM %s via AI tool",
                actual_stage_name,
                crm_id,
            )

            return {
                "success": True,
                "crm_id": str(updated_crm["id"]),
                "configuration": updated_crm["configuration"],
                "configuration_version": updated_crm["configuration_version"],
            }
        except ValueError as exc:
            error_msg = str(exc)
            if "already exists" in error_msg:
                return {
                    "success": False,
                    "error_code": "CONFLICT",
                    "error_message": error_msg,
                }
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": error_msg,
            }
        except Exception as exc:
            logger.exception("Error adding CRM stage via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to add stage: {str(exc)}",
            }

    @staticmethod
    def delete_crm_stage(
        crm_id: str,
        owner_id: str,
        stage_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Delete a pipeline stage from a CRM."""
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized",
            }

        actual_stage_name = stage_name or kwargs.get("stage_name") or kwargs.get("name")
        if not actual_stage_name:
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": "stage_name is required",
            }

        try:
            updated_config = CRMSchemaEditor.delete_pipeline_stage(
                crm["configuration"],
                stage_name=actual_stage_name,
            )

            CRMConfiguration(**updated_config)

            updated_crm = repo.update_crm_configuration(
                crm_id=crm_id,
                owner_id=owner_id,
                configuration=updated_config,
            )

            if not updated_crm:
                return {
                    "success": False,
                    "error_code": "INTERNAL_ERROR",
                    "error_message": "Failed to save CRM configuration",
                }

            logger.info(
                "[AI-TOOLS] Deleted stage '%s' from CRM %s via AI tool",
                actual_stage_name,
                crm_id,
            )

            return {
                "success": True,
                "crm_id": str(updated_crm["id"]),
                "configuration": updated_crm["configuration"],
                "configuration_version": updated_crm["configuration_version"],
            }
        except ValueError as exc:
            error_msg = str(exc)
            if "not found" in error_msg:
                return {
                    "success": False,
                    "error_code": "NOT_FOUND",
                    "error_message": error_msg,
                }
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": error_msg,
            }
        except Exception as exc:
            logger.exception("Error deleting CRM stage via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to delete stage: {str(exc)}",
            }

    @staticmethod
    def reorder_crm_fields(
        crm_id: str,
        owner_id: str,
        field_order: list[str],
        entity_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Reorder fields in a CRM entity."""
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized",
            }

        try:
            target_entity = CRMSchemaTools._resolve_entity(
                crm["configuration"], entity_name or kwargs.get("entity") or kwargs.get("entity_id")
            )
            resolved_entity_name = target_entity["name"] if target_entity else crm["configuration"]["entities"][0]["name"]

            updated_config = CRMSchemaEditor.reorder_fields(
                crm["configuration"],
                entity_name=resolved_entity_name,
                field_order=field_order,
            )

            CRMConfiguration(**updated_config)

            updated_crm = repo.update_crm_configuration(
                crm_id=crm_id,
                owner_id=owner_id,
                configuration=updated_config,
            )

            if not updated_crm:
                return {
                    "success": False,
                    "error_code": "INTERNAL_ERROR",
                    "error_message": "Failed to save CRM configuration",
                }

            logger.info(
                "[AI-TOOLS] Reordered %d fields in CRM %s via AI tool",
                len(field_order),
                crm_id,
            )

            return {
                "success": True,
                "crm_id": str(updated_crm["id"]),
                "configuration": updated_crm["configuration"],
                "configuration_version": updated_crm["configuration_version"],
            }
        except ValueError as exc:
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": str(exc),
            }
        except Exception as exc:
            logger.exception("Error reordering CRM fields via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to reorder fields: {str(exc)}",
            }

    @staticmethod
    def reorder_crm_stages(
        crm_id: str,
        owner_id: str,
        stage_order: list[str],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Reorder pipeline stages in a CRM."""
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized",
            }

        try:
            updated_config = CRMSchemaEditor.reorder_pipeline_stages(
                crm["configuration"],
                stage_order=stage_order,
            )

            CRMConfiguration(**updated_config)

            updated_crm = repo.update_crm_configuration(
                crm_id=crm_id,
                owner_id=owner_id,
                configuration=updated_config,
            )

            if not updated_crm:
                return {
                    "success": False,
                    "error_code": "INTERNAL_ERROR",
                    "error_message": "Failed to save CRM configuration",
                }

            logger.info(
                "[AI-TOOLS] Reordered %d stages in CRM %s via AI tool",
                len(stage_order),
                crm_id,
            )

            return {
                "success": True,
                "crm_id": str(updated_crm["id"]),
                "configuration": updated_crm["configuration"],
                "configuration_version": updated_crm["configuration_version"],
            }
        except ValueError as exc:
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": str(exc),
            }
        except Exception as exc:
            logger.exception("Error reordering CRM stages via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to reorder stages: {str(exc)}",
            }
        """Reorder pipeline stages in a CRM.
        
        Args:
            crm_id: The CRM ID
            owner_id: The owner user ID (for authorization)
            stage_order: List of stage names in desired order
            
        Returns:
            Updated CRMConfiguration as dict
            
        Raises:
            ValueError: If CRM not found or stage order is invalid
        """
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            raise ValueError("CRM not found or unauthorized")
        
        try:
            updated_config = CRMSchemaEditor.reorder_pipeline_stages(
                crm["configuration"],
                stage_order=stage_order,
            )
            
            CRMConfiguration(**updated_config)
            
            updated_crm = repo.update_crm_configuration(
                crm_id=crm_id,
                owner_id=owner_id,
                configuration=updated_config,
            )
            
            if not updated_crm:
                raise ValueError("Failed to save CRM configuration")
            
            logger.info(
                "[AI-TOOLS] Reordered %d stages in CRM %s via AI tool",
                len(stage_order),
                crm_id
            )
            
            return {
                "success": True,
                "crm_id": str(updated_crm["id"]),
                "configuration": updated_crm["configuration"],
                "configuration_version": updated_crm["configuration_version"],
            }
        except ValueError as exc:
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": str(exc),
            }
        except Exception as exc:
            logger.exception("Error reordering CRM stages via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to reorder stages: {str(exc)}",
            }


# OpenAI/Groq-format tool definitions for function calling
COPILOT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_record",
            "description": "Create a new record in the active CRM. Use this when the user asks to add a lead, contact, or other entity record.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Name of the entity to create a record for (e.g., 'lead', 'contact')",
                    },
                    "data": {
                        "type": "object",
                        "description": "Record field values as key-value pairs",
                    },
                    "source": {
                        "type": "string",
                        "description": "Optional source tag (e.g., 'Website', 'Email', 'Manual')",
                    },
                },
                "required": ["entity_name", "data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_record",
            "description": "Update an existing record in the active CRM. Use this when the user wants to change a record's fields.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Name of the entity",
                    },
                    "record_id": {
                        "type": "string",
                        "description": "ID of the record to update",
                    },
                    "data": {
                        "type": "object",
                        "description": "Fields to update (partial update OK)",
                    },
                },
                "required": ["entity_name", "record_id", "data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_record",
            "description": "Delete a record from the active CRM. Requires explicit user confirmation before execution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Name of the entity",
                    },
                    "record_id": {
                        "type": "string",
                        "description": "ID of the record to delete",
                    },
                },
                "required": ["entity_name", "record_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_crm_field",
            "description": "Add a new field to the CRM's main entity. Use this when the user asks to add a field to their CRM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_name": {
                        "type": "string",
                        "description": "Machine-readable field name (lowercase, underscores only, e.g., 'assigned_agent')",
                        "pattern": "^[a-z][a-z0-9_]{0,62}$",
                    },
                    "label": {
                        "type": "string",
                        "description": "Human-readable field label (e.g., 'Assigned Agent')",
                    },
                    "field_type": {
                        "type": "string",
                        "enum": ["text", "textarea", "email", "number", "date", "boolean", "select", "phone"],
                        "description": "The type of field",
                    },
                    "required": {
                        "type": "boolean",
                        "description": "Whether this field is required",
                        "default": False,
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "For select fields, list of available options (e.g., ['High', 'Medium', 'Low'])",
                    },
                },
                "required": ["field_name", "label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_crm_field",
            "description": "Update properties of an existing field in the CRM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_name": {
                        "type": "string",
                        "description": "The name of the field to update",
                    },
                    "label": {
                        "type": "string",
                        "description": "New human-readable label",
                    },
                    "field_type": {
                        "type": "string",
                        "enum": ["text", "textarea", "email", "number", "date", "boolean", "select", "phone"],
                        "description": "New field type",
                    },
                    "required": {
                        "type": "boolean",
                        "description": "New required state",
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New options for select fields",
                    },
                },
                "required": ["field_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_crm_field",
            "description": "Delete a field from the CRM's main entity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_name": {
                        "type": "string",
                        "description": "The name of the field to delete",
                    },
                },
                "required": ["field_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_crm_stage",
            "description": "Add a new pipeline stage to the CRM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stage_name": {
                        "type": "string",
                        "description": "Name of the new stage (e.g., 'Negotiation')",
                    },
                    "position": {
                        "type": "integer",
                        "description": "Optional position in the pipeline (0-indexed)",
                        "minimum": 0,
                    },
                },
                "required": ["stage_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_crm_stage",
            "description": "Delete a pipeline stage from the CRM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stage_name": {
                        "type": "string",
                        "description": "Name of the stage to delete",
                    },
                },
                "required": ["stage_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reorder_crm_fields",
            "description": "Reorder fields in the CRM's main entity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_order": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of field names in desired order (must include all existing fields)",
                    },
                },
                "required": ["field_order"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reorder_crm_stages",
            "description": "Reorder pipeline stages in the CRM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stage_order": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of stage names in desired order (must include all existing stages)",
                    },
                },
                "required": ["stage_order"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_crm_summary",
            "description": "Get high-level summary of CRM schema, total records, and pipeline stages.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_entity_schema",
            "description": "Get detailed schema (fields, types, required, options) for a specific entity in the CRM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Name of the entity to inspect",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_status_distribution",
            "description": "Get real-time distribution and count of records across pipeline stages or status options.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Name of the entity to analyze",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "count_records",
            "description": "Count records matching optional status or stage filters. Use this when the user asks 'how many leads/records are in X status'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Name of the entity to count records for",
                    },
                    "stage": {
                        "type": "string",
                        "description": "Optional pipeline stage or status name to filter by (e.g., 'New', 'Analyzing', 'High Value', 'At Risk')",
                    },
                    "filters": {
                        "type": "object",
                        "description": "Key-value map of field filters",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_records",
            "description": "Query records with optional filters. Use when the user asks to find, list, or show specific records.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Entity name to query",
                    },
                    "filters": {
                        "type": "object",
                        "description": "Optional filters to match",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max records to return (default 10)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "aggregate_records",
            "description": "Compute numeric aggregations (sum, avg, min, max, count) on a numeric field.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_name": {
                        "type": "string",
                        "description": "Name of the numeric field to aggregate",
                    },
                    "aggregation_type": {
                        "type": "string",
                        "enum": ["sum", "avg", "min", "max", "count"],
                        "description": "Type of aggregation",
                    },
                    "entity_name": {
                        "type": "string",
                        "description": "Entity name containing the field",
                    },
                },
                "required": ["field_name"],
            },
        },
    },
]
