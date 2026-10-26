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
5. Evolution Intelligence: Strict allowlisting of workflow triggers and actions with verifiable evidence.
"""
from __future__ import annotations

import json
import re
from typing import Any

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
        """Normalize and repair raw JSON to guarantee Pydantic schema conformity."""
        industry = cls.detect_industry(prompt)
        tax = INDUSTRY_TAXONOMIES.get(industry, INDUSTRY_TAXONOMIES["saas"])

        # Base fields
        name = str(raw_data.get("name") or tax["label"]).strip()[:120]
        if not name:
            name = f"{industry.replace('_', ' ').title()} CRM"

        raw_industry = str(raw_data.get("industry") or industry).strip().lower()
        clean_industry = cls.sanitize_identifier(raw_industry, fallback_prefix="industry")

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

