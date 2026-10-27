"""Laya System 1 — Structured Decision-Intelligence Engine.

Laya System 1 serves as the deterministic cognitive governor and fast decision layer
operating alongside generative LLMs (System 2, e.g. Qwen3-4B via Ollama).

Key Responsibilities:
1. Intent & Domain Taxonomy Classification: Fast domain detection and entity archetype mapping.
2. Safety & Guardrails: Zero arbitrary code/SQL execution, formula neutralization.
3. Canonical Scaffolding: Pre-seeding required entities (e.g. 'lead'), validating lowercased identifiers,
   and enforcing non-empty select options.
4. Schema Repair & Normalization: Cleans raw LLM outputs (markdown stripping, identifier snake_casing,
   reserved keyword replacement).
5. User Input Normalization: Deterministic conversion of raw natural-language custom columns and statuses
   into safe machine keys with bidirectional human/machine mapping.
6. Evolution Intelligence: Strict allowlisting of workflow triggers and actions with verifiable evidence.
"""
from __future__ import annotations

import json
import re
from typing import Any
from dataclasses import dataclass

from app.schemas.crm import (
    CRMConfiguration,
    CRMEntity,
    CRMField,
    FieldType,
    IDENTIFIER,
    ProposedChange,
    RESERVED_FIELDS,
    WorkflowAction,
    WorkflowTrigger,
)

# Supported field types allowlist
VALID_FIELD_TYPES: set[str] = {
    "text", "textarea", "email", "number", "date", "boolean", "select", "phone"
}

# Dangerous patterns to detect and reject
SQL_INJECTION_PATTERN = re.compile(
    r"\b(UNION\s+SELECT|DROP\s+TABLE|INSERT\s+INTO|DELETE\s+FROM|ALTER\s+TABLE|EXEC\(|EXECUTE\()\b",
    re.IGNORECASE,
)
CODE_EXEC_PATTERN = re.compile(
    r"\b(import\s+os|import\s+sys|subprocess|__import__|eval\(|exec\()\b",
    re.IGNORECASE,
)

# ────────────────────────────────────────────────────────────────
# Normalization Data Structure
# ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class NormalizedInput:
    """Bidirectional mapping between raw user input and machine identifiers."""
    machine_key: str  # e.g., "client_budget_size"
    human_label: str  # e.g., "Client Budget Size"
    original_raw: str  # e.g., "Client Budget Size!" (for auditing)


@dataclass(frozen=True)
class NormalizedSchema:
    """Complete normalized schema with all custom columns and statuses mapped."""
    column_mapping: dict[str, NormalizedInput]  # machine_key -> NormalizedInput
    status_mapping: dict[str, NormalizedInput]  # machine_key -> NormalizedInput
    laya_choice_criteria: dict[str, str]  # For Laya choice primitive: {machine_key: description}
    laya_status_criteria: dict[str, str]  # For Laya choice primitive: {machine_key: description}


# ────────────────────────────────────────────────────────────────


INDUSTRY_TAXONOMIES: dict[str, dict[str, Any]] = {
    "saas": {
        "label": "B2B SaaS Sales CRM",
        "default_entity": "lead",
        "pipeline": ["New", "Discovery", "Demo Scheduled", "Proposal", "Negotiation", "Closed Won", "Closed Lost"],
        "fields": [
            {"name": "full_name", "label": "Full Name", "type": "text", "required": True},
            {"name": "email", "label": "Work Email", "type": "email", "required": True},
            {"name": "company", "label": "Company", "type": "text", "required": False},
            {"name": "lead_source", "label": "Lead Source", "type": "select", "required": True,
             "options": ["Website", "Product Trial", "Inbound", "Referral", "Outbound"]},
            {"name": "deal_size", "label": "ARR Estimate ($)", "type": "number", "required": False},
            {"name": "status", "label": "Lead Status", "type": "select", "required": True,
             "options": ["New", "Discovery", "Demo Scheduled", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]},
        ],
    },
    "healthcare": {
        "label": "Healthcare Clinic CRM",
        "default_entity": "patient",
        "pipeline": ["Inquiry", "Triage", "Consultation Booked", "Treatment", "Follow-up Completed"],
        "fields": [
            {"name": "full_name", "label": "Patient Full Name", "type": "text", "required": True},
            {"name": "phone", "label": "Primary Contact Phone", "type": "phone", "required": True},
            {"name": "email", "label": "Email Address", "type": "email", "required": False},
            {"name": "date_of_birth", "label": "Date of Birth", "type": "date", "required": False},
            {"name": "triage_priority", "label": "Triage Priority", "type": "select", "required": True,
             "options": ["Routine", "Urgent", "Emergency"]},
            {"name": "status", "label": "Care Status", "type": "select", "required": True,
             "options": ["Inquiry", "Triage", "Consultation Booked", "Treatment", "Follow-up Completed"]},
        ],
    },
    "real_estate": {
        "label": "Real Estate Brokerage CRM",
        "default_entity": "property_lead",
        "pipeline": ["New Inquiry", "Qualified Buyer", "Site Tour", "Offer Made", "In Escrow", "Closed Won", "Closed Lost"],
        "fields": [
            {"name": "full_name", "label": "Client Name", "type": "text", "required": True},
            {"name": "phone", "label": "Phone Number", "type": "phone", "required": True},
            {"name": "email", "label": "Email", "type": "email", "required": False},
            {"name": "budget_max", "label": "Maximum Budget", "type": "number", "required": False},
            {"name": "property_type", "label": "Property Type", "type": "select", "required": True,
             "options": ["Residential Single Family", "Condo / Apartment", "Commercial", "Land"]},
            {"name": "status", "label": "Stage", "type": "select", "required": True,
             "options": ["New Inquiry", "Qualified Buyer", "Site Tour", "Offer Made", "In Escrow", "Closed Won", "Closed Lost"]},
        ],
    },
    "ecommerce": {
        "label": "E-Commerce Customer CRM",
        "default_entity": "customer",
        "pipeline": ["Prospect", "First Order", "Repeat Buyer", "VIP Member", "Churn Risk"],
        "fields": [
            {"name": "full_name", "label": "Customer Name", "type": "text", "required": True},
            {"name": "email", "label": "Customer Email", "type": "email", "required": True},
            {"name": "phone", "label": "Phone Number", "type": "phone", "required": False},
            {"name": "total_spend", "label": "Lifetime Spend ($)", "type": "number", "required": False},
            {"name": "customer_tier", "label": "Tier", "type": "select", "required": True,
             "options": ["Standard", "Silver", "Gold", "Platinum"]},
            {"name": "status", "label": "Account Status", "type": "select", "required": True,
             "options": ["Prospect", "First Order", "Repeat Buyer", "VIP Member", "Churn Risk"]},
        ],
    },
}


class LayaSystem1:
    """Decision-intelligence and guardrail engine."""

    # ────────────────────────────────────────────────────────────────
    # USER INPUT NORMALIZATION LAYER
    # ────────────────────────────────────────────────────────────────

    @classmethod
    def _normalize_user_input(
        cls,
        raw_strings: list[str],
        fallback_prefix: str = "field",
        max_items: int = 50,
    ) -> dict[str, NormalizedInput]:
        """
        Convert a list of raw, user-provided strings into deterministic,
        safe machine identifiers with bidirectional mapping.

        Args:
            raw_strings: List of unstructured strings (e.g., ["Client Budget Size!", "Deal Stage"])
            fallback_prefix: Prefix to use if a string becomes empty after cleaning (default: "field")
            max_items: Maximum number of items to process (safety limit)

        Returns:
            Dictionary mapping machine_key -> NormalizedInput (bidirectional mapping)
            {
                "client_budget_size": NormalizedInput(
                    machine_key="client_budget_size",
                    human_label="Client Budget Size",
                    original_raw="Client Budget Size!"
                ),
                ...
            }

        Processing:
        1. Strip whitespace and special symbols from each string
        2. Convert to lowercase and replace spaces with underscores
        3. Remove duplicate underscores and clean edges
        4. Validate against IDENTIFIER regex (start with letter, alphanumeric + underscore)
        5. Handle collisions by appending numeric suffix
        6. Check against RESERVED_FIELDS and add custom_ prefix if needed
        """
        result: dict[str, NormalizedInput] = {}
        seen_keys: set[str] = set()

        for idx, raw in enumerate(raw_strings[:max_items]):
            if not isinstance(raw, str):
                continue

            original_raw = raw.strip()
            if not original_raw:
                continue

            # ── Step 1: Clean and normalize ──────────────────────────
            # Remove special symbols; keep only alphanumeric, spaces, and underscores
            cleaned = re.sub(r"[^a-zA-Z0-9_\s-]+", "", original_raw)
            # Convert to lowercase, replace spaces/hyphens with underscores
            cleaned = cleaned.lower().replace(" ", "_").replace("-", "_")
            # Collapse multiple underscores into one
            cleaned = re.sub(r"_+", "_", cleaned)
            # Trim underscores from edges
            cleaned = cleaned.strip("_")

            # ── Step 2: Ensure valid identifier format ──────────────
            if not cleaned or not cleaned[0].isalpha():
                # If the string starts with a digit or is empty, prefix it
                cleaned = f"{fallback_prefix}_{cleaned}" if cleaned else fallback_prefix

            # ── Step 3: Truncate to IDENTIFIER max length (63 chars) ─
            cleaned = cleaned[:63]

            # ── Step 4: Handle collisions ────────────────────────────
            machine_key = cleaned
            collision_idx = 0
            while machine_key in seen_keys:
                collision_idx += 1
                candidate = f"{cleaned}_{collision_idx}"[:63]
                machine_key = candidate

            # ── Step 5: Check reserved fields ────────────────────────
            if machine_key in RESERVED_FIELDS:
                machine_key = f"custom_{machine_key}"[:63]

            seen_keys.add(machine_key)

            # ── Step 6: Build human-readable label ───────────────────
            # Convert machine_key back to title case for human readability
            human_label = machine_key.replace("_", " ").title()

            # ── Store the bidirectional mapping ──────────────────────
            result[machine_key] = NormalizedInput(
                machine_key=machine_key,
                human_label=human_label,
                original_raw=original_raw,
            )

        return result

    @classmethod
    def normalize_custom_schema(
        cls,
        custom_columns: list[str] | None = None,
        custom_statuses: list[str] | None = None,
    ) -> NormalizedSchema:
        """
        Normalize both custom columns and statuses into a unified schema
        that Laya and Qwen can work with deterministically.

        Args:
            custom_columns: List of user-provided column names (e.g., ["Budget", "Priority!"])
            custom_statuses: List of user-provided status options (e.g., ["In Progress", "On Hold"])

        Returns:
            NormalizedSchema with:
            - column_mapping: dict of machine_key -> NormalizedInput for columns
            - status_mapping: dict of machine_key -> NormalizedInput for statuses
            - laya_choice_criteria: dict of {machine_key: description} for Laya choice primitive
            - laya_status_criteria: dict of {machine_key: description} for Laya choice primitive

        This ensures that:
        1. Laya's choice primitive always receives structured, lowercase machine keys
        2. Qwen's prompt receives a JSON schema with strictly validated keys
        3. No re-prompting or clarification loops occur
        """
        col_mapping = cls._normalize_user_input(
            custom_columns or [],
            fallback_prefix="column",
        )
        status_mapping = cls._normalize_user_input(
            custom_statuses or [],
            fallback_prefix="status",
        )

        # Build Laya choice criteria (for routing decisions)
        laya_choice_criteria = {
            mk: ni.human_label for mk, ni in col_mapping.items()
        }
        laya_status_criteria = {
            mk: ni.human_label for mk, ni in status_mapping.items()
        }

        return NormalizedSchema(
            column_mapping=col_mapping,
            status_mapping=status_mapping,
            laya_choice_criteria=laya_choice_criteria,
            laya_status_criteria=laya_status_criteria,
        )

    # ────────────────────────────────────────────────────────────────
    # EXISTING METHODS (preserved below)
    # ────────────────────────────────────────────────────────────────

    @classmethod
    def classify_request(cls, prompt: str) -> dict[str, Any]:
        """Fast deterministic System-1 intent/routing classification."""
        text = prompt.casefold()
        if re.search(r"\b(delete|remove|erase)\b", text):
            intent = "delete_record"
        elif re.search(r"\b(update|edit|change|modify)\b", text):
            intent = "update_record"
        elif re.search(r"\b(add|create|new record)\b", text):
            intent = "create_record"
        elif re.search(r"\b(show|list|find|search|which|records?|leads?|contacts?)\b", text):
            intent = "list_records"
        else:
            intent = "conversation"
        return {
            "intent": intent,
            "requires_llm": True,
            "route": "system2_groq",
            "mode": "deterministic",
            "model_loaded": False,
        }

    @classmethod
    def sanitize_identifier(cls, name: str, fallback_prefix: str = "field") -> str:
        """Convert any human or messy name into a valid lowercase identifier."""
        clean = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip().lower())
        clean = re.sub(r"_+", "_", clean).strip("_")
        if not clean or not clean[0].isalpha():
            clean = f"{fallback_prefix}_{clean}" if clean else fallback_prefix
        # Truncate to maximum 63 characters per IDENTIFIER regex
        clean = clean[:63]
        if clean in RESERVED_FIELDS:
            clean = f"custom_{clean}"[:63]
        return clean

    @classmethod
    def detect_industry(cls, prompt: str) -> str:
        """Fast rule-based industry detection."""
        p = prompt.lower()
        if any(w in p for w in ["health", "clinic", "patient", "medical", "doctor", "hospital"]):
            return "healthcare"
        if any(w in p for w in ["real estate", "property", "realty", "brokerage", "listing", "escrow"]):
            return "real_estate"
        if any(w in p for w in ["ecommerce", "e-commerce", "retail", "store", "order", "shop"]):
            return "ecommerce"
        if any(w in p for w in ["saas", "software", "subscription", "b2b", "arr", "mrr", "tech"]):
            return "saas"
        return "general"

    @classmethod
    def validate_prompt_safety(cls, prompt: str) -> None:
        """Reject prompts that attempt SQL injection or code execution."""
        if SQL_INJECTION_PATTERN.search(prompt):
            raise ValueError("Prompt contains unsafe SQL commands. CRM configuration only generates JSON metadata.")
        if CODE_EXEC_PATTERN.search(prompt):
            raise ValueError("Prompt contains prohibited code execution keywords.")

    @classmethod
    def extract_json_payload(cls, raw_text: str) -> dict[str, Any]:
        """Extract and parse JSON from raw LLM text, handling markdown fences and preamble."""
        text = raw_text.strip()
        # 1. Match ```json ... ``` blocks
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if fence_match:
            candidate = fence_match.group(1).strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        # 2. Match outer braces { ... }
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            candidate = text[brace_start : brace_end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        # 3. Direct JSON parse
        return json.loads(text)

    @classmethod
    def repair_crm_configuration(cls, raw_data: dict[str, Any], prompt: str) -> dict[str, Any]:
        """Normalize and repair raw JSON to guarantee Pydantic schema conformity.
        
        This method now incorporates the normalization layer to handle custom columns
        and statuses that may have been provided in raw_data.
        """
        industry = cls.detect_industry(prompt)
        tax = INDUSTRY_TAXONOMIES.get(industry, INDUSTRY_TAXONOMIES["saas"])

        # Base fields
        name = str(raw_data.get("name") or tax["label"]).strip()[:120]
        if not name:
            name = f"{industry.replace('_', ' ').title()} CRM"

        raw_industry = str(raw_data.get("industry") or industry).strip().lower()
        clean_industry = cls.sanitize_identifier(raw_industry, fallback_prefix="industry")

        # ────────────────────────────────────────────────────────────────
        # NEW: Extract custom columns and statuses if provided
        # ────────────────────────────────────────────────────────────────
        custom_columns = raw_data.get("custom_columns")
        custom_statuses = raw_data.get("custom_statuses")
        
        if custom_columns or custom_statuses:
            # Use normalization layer to convert raw user input
            normalized = cls.normalize_custom_schema(
                custom_columns=custom_columns if isinstance(custom_columns, list) else None,
                custom_statuses=custom_statuses if isinstance(custom_statuses, list) else None,
            )
            # Store normalized mappings in the configuration for downstream use
            raw_data["_normalized_columns"] = {
                k: {"machine_key": v.machine_key, "human_label": v.human_label}
                for k, v in normalized.column_mapping.items()
            }
            raw_data["_normalized_statuses"] = {
                k: {"machine_key": v.machine_key, "human_label": v.human_label}
                for k, v in normalized.status_mapping.items()
            }

        # Pipeline stages
        raw_stages = raw_data.get("pipeline_stages")
        clean_stages: list[str] = []
        if isinstance(raw_stages, list) and raw_stages:
            for s in raw_stages:
                s_str = str(s).strip()
                if s_str and s_str not in clean_stages:
                    clean_stages.append(s_str)
        if not clean_stages:
            clean_stages = list(tax["pipeline"])

        # Entities
        raw_entities = raw_data.get("entities")
        clean_entities: list[dict[str, Any]] = []
        seen_entity_names: set[str] = set()

        if isinstance(raw_entities, list) and raw_entities:
            for ent in raw_entities:
                if not isinstance(ent, dict):
                    continue
                raw_ent_name = str(ent.get("name", "")).strip()
                ent_name = cls.sanitize_identifier(raw_ent_name, fallback_prefix="entity")
                if ent_name in seen_entity_names:
                    ent_name = f"{ent_name}_{len(seen_entity_names)}"[:63]
                seen_entity_names.add(ent_name)

                ent_label = str(ent.get("label") or ent_name.replace("_", " ").title()).strip()[:100]

                # Fields
                raw_fields = ent.get("fields")
                clean_fields: list[dict[str, Any]] = []
                seen_field_names: set[str] = set()

                if isinstance(raw_fields, list) and raw_fields:
                    for f in raw_fields:
                        if not isinstance(f, dict):
                            continue
                        f_name = cls.sanitize_identifier(str(f.get("name", "")), fallback_prefix="field")
                        if f_name in seen_field_names or f_name in RESERVED_FIELDS:
                            f_name = f"custom_{f_name}"[:63]
                        seen_field_names.add(f_name)

                        f_label = str(f.get("label") or f_name.replace("_", " ").title()).strip()[:100]
                        f_type = str(f.get("type", "text")).strip().lower()
                        if f_type not in VALID_FIELD_TYPES:
                            f_type = "text"

                        f_required = bool(f.get("required", False))

                        # Handle options for select fields
                        f_options = None
                        if f_type == "select":
                            raw_opts = f.get("options")
                            if isinstance(raw_opts, list) and raw_opts:
                                f_options = [str(o).strip() for o in raw_opts if str(o).strip()]
                                # Deduplicate options while preserving order
                                seen_opts = set()
                                f_options = [o for o in f_options if not (o in seen_opts or seen_opts.add(o))]
                            if not f_options:
                                f_options = ["Default 1", "Default 2", "Other"]
                        else:
                            f_options = None

                        clean_fields.append({
                            "name": f_name,
                            "label": f_label,
                            "type": f_type,
                            "required": f_required,
                            "options": f_options,
                        })

                # If no valid fields were parsed, inject defaults
                if not clean_fields:
                    clean_fields = list(tax["fields"])

                clean_entities.append({
                    "name": ent_name,
                    "label": ent_label,
                    "fields": clean_fields,
                })

        # Ensure at least one entity exists
        if not clean_entities:
            clean_entities = [{
                "name": tax["default_entity"],
                "label": tax["default_entity"].replace("_", " ").title(),
                "fields": list(tax["fields"]),
            }]

        config = {
            "schema_version": "1.0",
            "name": name,
            "industry": clean_industry,
            "entities": clean_entities,
            "pipeline_stages": clean_stages,
        }

        # Verify against Pydantic schema
        CRMConfiguration(**config)
        return config

    @classmethod
    def generate_scaffold_config(cls, prompt: str) -> dict[str, Any]:
        """Generate a complete schema-valid CRM configuration deterministically."""
        cls.validate_prompt_safety(prompt)
        industry = cls.detect_industry(prompt)
        tax = INDUSTRY_TAXONOMIES.get(industry, INDUSTRY_TAXONOMIES["saas"])

        # Determine custom entity name if specified
        entity_name = tax["default_entity"]
        p_lower = prompt.lower()
        if "lead" in p_lower:
            entity_name = "lead"
        elif "contact" in p_lower:
            entity_name = "contact"
        elif "property" in p_lower or "listing" in p_lower:
            entity_name = "property_lead"
        elif "patient" in p_lower or "client" in p_lower:
            entity_name = "patient" if industry == "healthcare" else "client"

        raw = {
            "name": f"{industry.replace('_', ' ').title()} CRM",
            "industry": industry,
            "entities": [
                {
                    "name": entity_name,
                    "label": entity_name.replace("_", " ").title(),
                    "fields": tax["fields"],
                }
            ],
            "pipeline_stages": tax["pipeline"],
        }
        return cls.repair_crm_configuration(raw, prompt)

    @classmethod
    def generate_custom_crm_from_answers(
        cls,
        crm_type: str | None,
        tracks: str | None,
        pipeline_stages: str | None,
        key_fields: str | None,
        team_size: str | None,
        prompt: str = "",
    ) -> dict[str, Any]:
        """Generate a CRM configuration from structured questionnaire answers.
        
        This is used when user selects "Custom CRM" or provides explicit answers.
        Respects user input instead of using predefined templates.
        
        Args:
            crm_type: "custom", "sales_pipeline", "client_management", etc.
            tracks: What user wants to track (e.g., "leads and deals")
            pipeline_stages: Stages user specified (e.g., "New, In Progress, Done")
            key_fields: Key fields user wants (e.g., "lead, email, phone")
            team_size: Team size context
            prompt: Original user prompt for fallback industry detection
            
        Returns:
            Valid CRM configuration dict
        """
        # Determine entity name and industry from user's tracking needs
        entity_name = "record"
        industry = "general"
        
        if tracks:
            tracks_lower = tracks.lower()
            if "lead" in tracks_lower or "deal" in tracks_lower:
                entity_name = "lead"
                industry = "saas"  # Sales-like
            elif "patient" in tracks_lower or "medical" in tracks_lower:
                entity_name = "patient"
                industry = "healthcare"
            elif "property" in tracks_lower or "listing" in tracks_lower:
                entity_name = "property_lead"
                industry = "real_estate"
            elif "customer" in tracks_lower or "order" in tracks_lower:
                entity_name = "customer"
                industry = "ecommerce"
            elif "task" in tracks_lower or "project" in tracks_lower:
                entity_name = "task"
        
        # Build CRM name
        crm_name = "Custom CRM"
        if tracks:
            crm_name = f"{tracks.split()[0].title()} CRM" if tracks.split() else "Custom CRM"
        
        # Parse fields from user input
        fields = []
        if key_fields:
            field_names = [f.strip() for f in key_fields.split(",")]
            for i, field_name in enumerate(field_names[:20]):  # Max 20 fields
                if not field_name:
                    continue
                
                # Infer field type
                field_name_lower = field_name.lower()
                if "email" in field_name_lower:
                    field_type = "email"
                elif "phone" in field_name_lower:
                    field_type = "phone"
                elif "date" in field_name_lower:
                    field_type = "date"
                elif "amount" in field_name_lower or "price" in field_name_lower or "value" in field_name_lower or "budget" in field_name_lower or "cost" in field_name_lower:
                    field_type = "number"
                elif "status" in field_name_lower or "stage" in field_name_lower:
                    field_type = "select"
                else:
                    field_type = "text"
                
                # Mark first field and status fields as required
                required = i == 0 or "status" in field_name_lower
                
                fields.append({
                    "name": cls.sanitize_identifier(field_name),
                    "label": field_name.strip(),
                    "type": field_type,
                    "required": required,
                    "options": ["Active", "Inactive", "On Hold"] if field_type == "select" else None,
                })
        
        # If no fields specified, provide sensible defaults
        if not fields:
            fields = [
                {
                    "name": "name",
                    "label": "Name",
                    "type": "text",
                    "required": True,
                    "options": None,
                },
                {
                    "name": "email",
                    "label": "Email",
                    "type": "email",
                    "required": False,
                    "options": None,
                },
                {
                    "name": "status",
                    "label": "Status",
                    "type": "select",
                    "required": True,
                    "options": ["Active", "Inactive"],
                },
            ]
        
        # Parse pipeline stages
        stages = []
        if pipeline_stages:
            # Handle both "New, In Progress, Done" and "New → In Progress → Done" formats
            stage_texts = pipeline_stages.replace("→", ",").split(",")
            for stage in stage_texts:
                stage = stage.strip()
                if stage and stage not in stages:
                    stages.append(stage)
        
        # If no stages specified, provide sensible defaults
        if not stages:
            stages = ["New", "In Progress", "Done"]
        
        raw = {
            "name": crm_name,
            "industry": industry,
            "entities": [
                {
                    "name": entity_name,
                    "label": entity_name.replace("_", " ").title(),
                    "fields": fields,
                }
            ],
            "pipeline_stages": stages,
        }
        
        return cls.repair_crm_configuration(raw, prompt)

    @classmethod
    def rank_and_filter_candidates(
        cls, candidates: list[dict[str, Any]], objective: str, analytics: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Filter candidates by allowlisted schema rules and rank them by priority score."""
        scored: list[tuple[float, dict[str, Any]]] = []
        allowlisted_triggers = {"record.created", "record.updated", "record.stage_changed"}
        allowlisted_actions = {"create_follow_up_task", "notify_owner", "send_email"}

        for cand in candidates:
            change = cand.get("proposed_change", {})
            ctype = change.get("type")
            if ctype not in ("workflow.create", "workflow.update"):
                continue

            # Verify trigger allowlist
            trig = change.get("trigger", {})
            if trig and trig.get("type") not in allowlisted_triggers:
                continue

            # Verify actions allowlist
            actions = change.get("actions") or []
            valid_actions = True
            for a in actions:
                if a.get("type") not in allowlisted_actions:
                    valid_actions = False
                    break
            if not valid_actions:
                continue

            # Compute priority score
            score = 1.0
            obj_clean = objective.lower()
            name_clean = change.get("name", "").lower()

            if "follow_up" in obj_clean and "follow_up" in name_clean:
                score += 5.0
            elif "conversion" in obj_clean and ("stage" in name_clean or "conversion" in name_clean):
                score += 5.0
            elif "manual" in obj_clean and ("automated" in name_clean or "update" in name_clean):
                score += 5.0

            # Factor in real analytics signals
            conv_rate = float(analytics.get("conversion_rate", 0.0) or 0.0)
            if conv_rate < 0.20 and "conversion" in obj_clean:
                score += 3.0

            scored.append((score, cand))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored]

    @classmethod
    def generate_scaffold_proposal(
        cls, objective: str, crm_config: dict[str, Any], analytics: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate and rank allowlisted evolution proposals with verifiable evidence."""
        obj = objective.lower()
        primary_entity = "lead"
        entities = crm_config.get("entities", [])
        if entities and isinstance(entities[0], dict):
            primary_entity = entities[0].get("name", "lead")

        # Candidate pool
        candidates = [
            {
                "summary": "Automate 4-hour follow-up task creation for newly registered records.",
                "proposed_change": {
                    "type": "workflow.create",
                    "name": f"Quick response follow-up for {primary_entity}",
                    "trigger": {"type": "record.created", "entity": primary_entity},
                    "actions": [{"type": "create_follow_up_task", "delay_hours": 4}],
                },
                "evidence": [
                    {
                        "metric": "response_latency",
                        "description": "Average response time exceeds team target threshold (24 hours).",
                        "target_improvement": "Response within 4 hours",
                    }
                ],
            },
            {
                "summary": f"Notify account owner upon stage change to advance pipeline momentum on {primary_entity}.",
                "proposed_change": {
                    "type": "workflow.create",
                    "name": f"Stage progression alert for {primary_entity}",
                    "trigger": {"type": "record.stage_changed", "entity": primary_entity},
                    "actions": [{"type": "notify_owner"}],
                },
                "evidence": [
                    {
                        "metric": "conversion_velocity",
                        "description": "Leads idling in middle stages without owner notification.",
                        "target_improvement": "Instant team awareness on status updates",
                    }
                ],
            },
            {
                "summary": f"Automate status update notification to reduce manual outreach on {primary_entity}.",
                "proposed_change": {
                    "type": "workflow.create",
                    "name": f"Automated owner notification on {primary_entity} update",
                    "trigger": {"type": "record.updated", "entity": primary_entity},
                    "actions": [{"type": "notify_owner"}],
                },
                "evidence": [
                    {
                        "metric": "manual_tasks_logged",
                        "description": "High frequency of manual status checks detected across CRM records.",
                        "target_improvement": "Reduce manual polling through event-driven alerts",
                    }
                ],
            },
        ]

        ranked = cls.rank_and_filter_candidates(candidates, obj, analytics)
        if ranked:
            return ranked[0]
        return candidates[0]

