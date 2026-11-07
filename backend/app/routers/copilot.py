"""AI Co-pilot routes.

Endpoints:
- POST /api/v1/copilot/chat  — Ask the CRM-aware AI assistant a question

The co-pilot answers questions about the authenticated user's active CRM:
configuration, entities, pipeline stages, workflows, and analytics.
It can also guide users to AURA features using real routes.

Security:
- Every request is authenticated (JWT required).
- The CRM is fetched using the caller's user_id — never another tenant's data.
- No CRM data is returned if the caller does not own the CRM.
- Model output is treated as untrusted text — never executed.
- The co-pilot cannot approve evolution proposals or mutate any data.
"""
from __future__ import annotations

import logging
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth import CurrentUser
from app.config import get_settings, Settings
from app.database import CRMRepository
from app.routers.responses import success_response, error_response
from app.services.laya_system1 import LayaSystem1
from app.services.ai_tools import CRMSchemaTools, COPILOT_TOOLS
from app.services.intent_classifier import (
    IntentClassifier,
    IntentCategory,
    READ_ONLY_INTENTS,
    MUTATION_TOOLS,
    READ_ONLY_TOOLS,
)
from app.services.crm_rag import CRMRAGService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/copilot", tags=["AI Co-pilot"])

# ── Real application routes the co-pilot may reference ────────────
# Only routes that actually exist in App.tsx are listed here.

AURA_ROUTES = {
    "dashboard": "/dashboard",
    "crms": "/crms",
    "build_crm": "/chat-crm",
    "records": "/records",
    "workflows": "/workflows",
    "analytics": "/analytics",
    "evolution": "/evolution",
    "settings": "/settings",
}

# ── Request / Response schemas ─────────────────────────────────────

class CopilotMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=4000)


class CopilotRequest(BaseModel):
    messages: list[CopilotMessage] = Field(..., min_length=1, max_length=20)
    crm_id: str | None = Field(default=None, description="Active CRM ID for context")


# ── System prompt builder ──────────────────────────────────────────

def _build_system_prompt(crm_context: dict[str, Any] | None) -> str:
    """Build system prompt with action detection and tool schemas.
    
    CRITICAL FIX (RC-002, RC-003): Dynamically inject actual entity names from CRM configuration
    instead of using hardcoded examples like 'lead', 'customer', etc. This ensures the LLM
    generates tool calls with valid entity names that actually exist in the CRM.
    """
    routes_text = "\n".join(f"  - {k}: {v}" for k, v in AURA_ROUTES.items())

    base = (
        "You are AURA Copilot, an expert assistant for the AURA Self-Evolving CRM platform.\n\n"
        "# YOUR CAPABILITIES\n"
        "1. Answer questions about the user's CRM configuration, records, workflows, analytics.\n"
        "2. Guide users to AURA features using navigation markers.\n"
        "3. Execute CRM actions on behalf of the user using available tools.\n\n"
        
        "# DISTINGUISHING ACTION vs. INFORMATIONAL REQUESTS\n"
        "Recognize COMMANDS vs. QUESTIONS:\n\n"
        "COMMANDS (generate tool calls):\n"
        "- User says: 'Add a lead', 'Create a record', 'Delete John', 'Change field type', 'Add status'\n"
        "- User says: 'I want to...', 'I need to...', 'Please create...', 'Change to...'\n"
        "- Action: Generate TOOL_CALL (see TOOL CALLING FORMAT below)\n\n"
        "QUESTIONS (answer with information):\n"
        "- User says: 'What fields does my CRM have?', 'How do workflows work?', 'Tell me about leads'\n"
        "- User says: 'Show me...', 'Explain...', 'What is...', 'How do I...'\n"
        "- Action: Answer with schema info or explanation; do NOT generate tool call\n\n"
        
        "# ENTITY RESOLUTION (CRITICAL)\n"
        "When the user asks to create or modify a record, you MUST match their requested entity\n"
        "against the VALID ENTITY NAMES list below. Rules:\n"
        "1. If the user's request clearly matches ONE entity name, use it.\n"
        "2. If the user's request is ambiguous or matches MULTIPLE entities, ask which one.\n"
        "3. If the user's request matches NO entities, explain the mismatch and suggest available entities.\n"
        "4. NEVER use an entity name that is NOT in the VALID ENTITY NAMES list.\n"
        "5. NEVER invent or assume entity names (e.g., do not assume 'lead' exists unless listed).\n\n"
        
        "# TOOL CALLING FORMAT\n"
        "When you need to execute an action, generate a JSON tool call in this format:\n"
        "TOOL_CALL: {\"name\": \"tool_name\", \"arguments\": {arg1: value1, arg2: value2}}\n\n"
        "Important: The entity_name argument MUST be one of the VALID ENTITY NAMES below.\n\n"
        "Example format (do NOT copy entity names from here; use the actual valid ones):\n"
        "- TOOL_CALL: {\"name\": \"create_record\", \"arguments\": {\"entity_name\": \"<valid_entity_name>\", \"data\": {...}}}\n\n"
        
        "# AVAILABLE TOOLS\n"
        "## Record Actions\n"
        "- create_record(entity_name, data, source?): Create a new record. entity_name MUST be from VALID ENTITY NAMES.\n"
        "- update_record(entity_name, record_id, data): Update existing record. entity_name MUST be from VALID ENTITY NAMES.\n"
        "- delete_record(entity_name, record_id): Delete a record (dangerous — requires user confirmation). entity_name MUST be from VALID ENTITY NAMES.\n\n"
        "## Field Actions\n"
        "- add_crm_field(field_name, label, field_type, required?, options?): Add field to the CRM\n"
        "- update_crm_field(field_name, label?, field_type?, required?, options?): Update field properties\n"
        "- delete_crm_field(field_name): Delete field (dangerous)\n\n"
        "## Stage Actions\n"
        "- add_crm_stage(stage_name, position?): Add pipeline stage\n"
        "- delete_crm_stage(stage_name): Delete stage (dangerous)\n"
        "- reorder_crm_stages(stage_order): Reorder all stages\n"
        "- reorder_crm_fields(field_order): Reorder all fields\n\n"
        
        "# RULES\n"
        "- Keep replies under 120 words unless providing detailed context.\n"
        "- If mentioning navigation, use format: [NAV: route_key | Button Label]\n"
        "- Base answers on the CRM context. Do NOT invent fields, stages, or data.\n"
        "- For dangerous operations (delete, schema changes), always generate a tool call — the frontend will ask user for confirmation.\n"
        "- Never execute code or SQL.\n"
        "- NEVER use an entity_name that is not in the VALID ENTITY NAMES list below.\n"
        "- CRITICAL: Distinguish between record creation (create_record), adding a column/field (add_crm_field), adding a status option to a field (update_crm_field with options), and adding a pipeline stage (add_crm_stage). Never call add_crm_stage when the user intends to create or add a lead, customer, or record.\n\n"
        f"Available AURA routes:\n{routes_text}\n"
    )

    if crm_context:
        config = crm_context.get("configuration", {})
        entities = config.get("entities", [])
        
        # RC-003: Build explicit VALID ENTITY NAMES section for LLM clarity
        if entities:
            valid_entity_names = ", ".join(
                f"{e['name']} ({e['label']})" for e in entities
            )
            base += f"\nVALID ENTITY NAMES: {valid_entity_names}\n"
        else:
            base += "\nVALID ENTITY NAMES: (no entities defined)\n"
        
        # Build entity details with required fields highlighted
        entity_summary = []
        for e in entities[:10]:  # cap at 10 to control prompt size
            field_names = [f["name"] for f in e.get("fields", [])[:8]]
            required_fields = [f["name"] for f in e.get("fields", []) if f.get("required", False)]
            entity_summary.append(
                f"  - {e['label']} ({e['name']}): fields = {', '.join(field_names)}"
            )
            if required_fields:
                entity_summary.append(f"    (required: {', '.join(required_fields)})")

        stages = config.get("pipeline_stages", [])
        workflows = crm_context.get("workflows", [])
        wf_summary = [
            f"  - {w.get('name', 'Unnamed')} "
            f"(trigger: {w.get('trigger', {}).get('type', 'unknown')}, "
            f"status: {w.get('status', 'unknown')})"
            for w in workflows[:5]
        ]

        crm_block = (
            f"\nACTIVE CRM CONTEXT:\n"
            f"Name: {config.get('name', 'Unknown')}\n"
            f"Industry: {config.get('industry', 'Unknown')}\n"
            f"Configuration version: {crm_context.get('configuration_version', 1)}\n"
            f"Pipeline stages: {' → '.join(stages) if stages else 'None defined'}\n"
            f"Entity Details:\n" + ("\n".join(entity_summary) if entity_summary else "  None") + "\n"
            f"Workflows ({len(workflows)} total):\n"
            + ("\n".join(wf_summary) if wf_summary else "  None defined") + "\n"
        )
        base += crm_block

    return base


# ── Universal Intent Resolver & Fallback ──────────────────────────

def _universal_action_reply(
    question: str,
    crm_context: dict[str, Any] | None,
    user_id: str | None = None,
    crm_id: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Intelligently analyzes user input and either executes a live CRM operation / tool call
    or returns schema-grounded information. Works for ANY CRM without hardcoding.
    """
    import json
    q = question.strip()
    q_lower = q.lower()

    config = crm_context.get("configuration", {}) if crm_context else {}
    crm_name = config.get("name", "your CRM")
    entities = config.get("entities", [])
    pipeline_stages = config.get("pipeline_stages", [])

    # Classify user intent
    intent = IntentClassifier.classify(
        message=q,
        conversation_history=history,
        crm_context=crm_context,
    )

    # Disambiguate / match entity
    target_entity, is_ambiguous = CRMRAGService.resolve_entity(entities, q_lower)
    if is_ambiguous and len(entities) > 1 and intent in (IntentCategory.ANALYTICS_QUERY, IntentCategory.CREATE_RECORD, IntentCategory.RECORD_QUERY):
        avail = ", ".join(f"**{e.get('label', e.get('name'))}**" for e in entities)
        return {
            "reply": f"This CRM has multiple entities: {avail}. Which entity are you asking about?",
            "nav_route": None,
            "nav_label": None,
            "fallback": False,
        }

    primary_entity = entities[0] if entities else None
    if not target_entity:
        target_entity = primary_entity

    target_entity_name = target_entity["name"] if target_entity else "record"
    target_entity_label = target_entity.get("label", target_entity_name) if target_entity else "Record"
    entity_fields = target_entity.get("fields", []) if target_entity else []

    # ── 1. ANALYTICS_QUERY (Live Data Counts, Distributions, Aggregations) ──
    if intent == IntentCategory.ANALYTICS_QUERY:
        # Check if user query matches any pipeline stage
        matched_stage = None
        for stage in pipeline_stages:
            stage_l = stage.lower()
            if stage_l in q_lower or (stage_l == "new" and re.search(r"\bnew\b", q_lower)):
                matched_stage = stage
                break

        # Check status field options if no stage matched
        if not matched_stage:
            for f in entity_fields:
                if f.get("type") in ("select", "status") or "status" in f["name"].lower():
                    for opt in f.get("options", []):
                        if opt.lower() in q_lower or (opt.lower() == "new" and re.search(r"\bnew\b", q_lower)):
                            matched_stage = opt
                            break
                    if matched_stage:
                        break

        # A. Stage/Status Count Query (e.g. "how many new lead are there", "how many records are at risk")
        if matched_stage:
            count = 0
            if crm_id and user_id:
                try:
                    count_res = CRMSchemaTools.count_records(
                        crm_id=crm_id,
                        owner_id=user_id,
                        entity_name=target_entity_name,
                        stage=matched_stage,
                    )
                    count = count_res.get("count", 0)
                except Exception as e:
                    logger.warning("Error getting live count for stage '%s': %s", matched_stage, e)

            return {
                "reply": f"There are currently **{count}** records in the **{matched_stage}** stage in **{crm_name}** ({target_entity_label}).",
                "nav_route": AURA_ROUTES["records"],
                "nav_label": "Open Records",
                "fallback": False,
            }

        # B. Status Distribution / Breakdown
        if any(w in q_lower for w in ["distribution", "breakdown", "funnel", "stages", "pipeline"]):
            dist = {s: 0 for s in pipeline_stages}
            total = 0
            if crm_id and user_id:
                try:
                    dist_res = CRMSchemaTools.get_status_distribution(
                        crm_id=crm_id,
                        owner_id=user_id,
                        entity_name=target_entity_name,
                    )
                    dist = dist_res.get("distribution", dist)
                    total = dist_res.get("total_records", sum(dist.values()))
                except Exception as e:
                    logger.warning("Error getting status distribution: %s", e)

            breakdown_lines = [f"- **{k}**: {v}" for k, v in dist.items()]
            return {
                "reply": (
                    f"**Status distribution for {target_entity_label} in {crm_name}** (Total: {total}):\n\n"
                    + "\n".join(breakdown_lines)
                ),
                "nav_route": AURA_ROUTES["analytics"],
                "nav_label": "View Analytics",
                "fallback": False,
            }

        # C. Numeric Aggregation (Revenue, Value, Amount, Score)
        num_fields = [f for f in entity_fields if f.get("type") in ("number", "currency", "integer", "float")]
        matched_num_field = None
        for nf in num_fields:
            if nf["name"].lower() in q_lower or nf.get("label", "").lower() in q_lower:
                matched_num_field = nf
                break

        if matched_num_field and crm_id and user_id:
            agg_type = "avg" if any(w in q_lower for w in ["average", "avg", "mean"]) else "sum"
            try:
                agg_res = CRMSchemaTools.aggregate_records(
                    crm_id=crm_id,
                    owner_id=user_id,
                    field_name=matched_num_field["name"],
                    aggregation_type=agg_type,
                    entity_name=target_entity_name,
                )
                val = agg_res.get("value", 0.0)
                prefix = "$" if matched_num_field.get("type") == "currency" else ""
                label = matched_num_field.get("label", matched_num_field["name"])
                return {
                    "reply": f"The {agg_type.upper()} for **{label}** across all records in **{crm_name}** is **{prefix}{val:,.2f}**.",
                    "nav_route": AURA_ROUTES["analytics"],
                    "nav_label": "View Analytics",
                    "fallback": False,
                }
            except Exception as e:
                logger.warning("Error aggregating records: %s", e)

        # D. Generic Total Count ("how many records", "count leads", "total records")
        total_count = 0
        if crm_id and user_id:
            try:
                cnt_res = CRMSchemaTools.count_records(
                    crm_id=crm_id,
                    owner_id=user_id,
                    entity_name=target_entity_name,
                )
                total_count = cnt_res.get("count", 0)
            except Exception as e:
                logger.warning("Error counting records: %s", e)

        return {
            "reply": f"There are currently **{total_count}** total records in **{crm_name}** ({target_entity_label}).",
            "nav_route": AURA_ROUTES["records"],
            "nav_label": "Open Records",
            "fallback": False,
        }

    # ── 2. SCHEMA_QUERY (Fields, Columns, Entities, Stages Structure) ──────
    if intent == IntentCategory.SCHEMA_QUERY:
        if entities:
            summary_parts = []
            for ent in entities:
                f_list = ", ".join(f"{f['label']} ({f['type']}{', required' if f.get('required') else ''})" for f in ent.get("fields", []))
                summary_parts.append(f"**{ent.get('label', ent['name'])}** (`{ent['name']}`):\n{f_list}")

            stages_text = " → ".join(pipeline_stages) if pipeline_stages else "None configured"
            reply_text = (
                f"**{crm_name}** schema structure:\n\n"
                + "\n\n".join(summary_parts)
                + f"\n\n**Pipeline Stages:** {stages_text}"
            )
            return {
                "reply": reply_text,
                "nav_route": None,
                "nav_label": None,
                "fallback": False,
            }

    # ── 3. RECORD_QUERY (Read-Only Search / List Records) ─────────────────
    if intent == IntentCategory.RECORD_QUERY:
        return {
            "reply": f"Here are your records for **{crm_name}**.",
            "nav_route": AURA_ROUTES["records"],
            "nav_label": "Open Records",
            "fallback": False,
        }

    # ── 4. CRM_CONFIGURATION_CHANGE (Schema Modifications) ───────────────
    # A. Delete Column / Field
    if any(q_lower.startswith(w) or f" {w} " in f" {q_lower} " for w in ["delete", "remove", "drop"]) and any(
        w in q_lower for w in ["column", "field"]
    ):
        field_match = re.search(r"(?:delete|remove|drop)\s+(?:the\s+)?(?:column|field)\s+([A-Za-z0-9_\-\s]+)", q, re.IGNORECASE)
        raw_name = field_match.group(1).strip() if field_match else ""
        machine_name = raw_name.lower().replace(" ", "_")

        tool_call = {
            "name": "delete_crm_field",
            "arguments": {
                "entity_name": target_entity_name,
                "field_name": machine_name,
            }
        }
        return {
            "reply": f"I've prepared the deletion of field '{machine_name}' from {target_entity_label}. Please confirm in the dialog.\n\nTOOL_CALL: {json.dumps(tool_call)}",
            "nav_route": None,
            "nav_label": None,
            "fallback": False,
        }

    # B. Add Column / Field
    if (any(q_lower.startswith(w) or f" {w} " in f" {q_lower} " for w in ["add", "create", "new"]) and any(
        w in q_lower for w in ["column", "field"]
    )) and not any(w in q_lower for w in ["status option"]):
        field_match = re.search(r"(?:add|create|new)\s+(?:a\s+|new\s+)?(?:column|field)\s+([A-Za-z0-9_\-\s]+)", q, re.IGNORECASE)
        raw_name = field_match.group(1).strip() if field_match else "new_field"
        clean_name = re.sub(r"\s+(as|type|with).*$", "", raw_name, flags=re.IGNORECASE).strip()
        machine_name = clean_name.lower().replace(" ", "_")
        label = clean_name.title()

        field_type = "text"
        if any(w in q_lower for w in ["number", "count", "amount", "price", "score"]):
            field_type = "number"
        elif any(w in q_lower for w in ["currency", "revenue", "dollar", "cost"]):
            field_type = "currency"
        elif any(w in q_lower for w in ["date", "deadline", "time"]):
            field_type = "date"
        elif any(w in q_lower for w in ["select", "dropdown", "option"]):
            field_type = "select"
        elif any(w in q_lower for w in ["email"]):
            field_type = "email"
        elif any(w in q_lower for w in ["boolean", "toggle", "checkbox"]):
            field_type = "boolean"

        tool_call = {
            "name": "add_crm_field",
            "arguments": {
                "entity_name": target_entity_name,
                "field_name": machine_name,
                "label": label,
                "field_type": field_type,
            }
        }
        return {
            "reply": f"I've prepared the schema modification to add field '{label}' ({field_type}) to {target_entity_label}.\n\nTOOL_CALL: {json.dumps(tool_call)}",
            "nav_route": None,
            "nav_label": None,
            "fallback": False,
        }

    # C. Delete Stage
    if any(q_lower.startswith(w) or f" {w} " in f" {q_lower} " for w in ["delete", "remove", "drop"]) and any(
        w in q_lower for w in ["stage", "pipeline stage"]
    ):
        stage_match = re.search(r"(?:delete|remove|drop)\s+(?:the\s+)?(?:pipeline\s+)?stage\s+['\"]?([^'\"]+?)['\"]?$", q, re.IGNORECASE)
        if not stage_match:
            stage_match = re.search(r"(?:delete|remove|drop)\s+['\"]?([^'\"]+?)['\"]?\s+(?:from\s+(?:the\s+)?(?:pipeline|pipeline\s+stages|stages)|as\s+(?:a\s+)?(?:pipeline\s+)?stage)", q, re.IGNORECASE)
        stage_name = stage_match.group(1).strip() if stage_match else ""

        tool_call = {
            "name": "delete_crm_stage",
            "arguments": {
                "stage_name": stage_name,
            }
        }
        return {
            "reply": f"I've prepared the deletion of stage '{stage_name}'. Please confirm in the dialog to proceed.\n\nTOOL_CALL: {json.dumps(tool_call)}",
            "nav_route": None,
            "nav_label": None,
            "fallback": False,
        }

    # D. Add Stage
    stage_add_match = re.search(r"(?:add|create)\s+(?:a\s+|new\s+|a\s+new\s+)?(?:pipeline\s+)?stage\s+['\"]?([^'\"]+?)['\"]?$", q, re.IGNORECASE)
    if not stage_add_match:
        stage_add_match = re.search(r"(?:add|create)\s+['\"]?([^'\"]+?)['\"]?\s+(?:to\s+(?:the\s+)?(?:pipeline|pipeline\s+stages|stages)|as\s+(?:a\s+)?(?:pipeline\s+)?stage)", q, re.IGNORECASE)

    if stage_add_match:
        stage_name = stage_add_match.group(1).strip()
        tool_call = {
            "name": "add_crm_stage",
            "arguments": {
                "stage_name": stage_name,
            }
        }
        return {
            "reply": f"I've prepared the action to add '{stage_name}' to the pipeline stages.\n\nTOOL_CALL: {json.dumps(tool_call)}",
            "nav_route": None,
            "nav_label": None,
            "fallback": False,
        }

    # E. Add Status Option
    status_opt_match = re.search(r"(?:add|create)\s+(?:a\s+|new\s+|a\s+new\s+)?status\s+option\s+['\"]?([^'\"]+?)['\"]?$", q, re.IGNORECASE)
    if not status_opt_match:
        status_opt_match = re.search(r"(?:add|create)\s+['\"]?([^'\"]+?)['\"]?\s+(?:as\s+(?:a\s+)?status\s+option|to\s+(?:the\s+)?status\s+options)", q, re.IGNORECASE)

    if status_opt_match:
        opt_name = status_opt_match.group(1).strip()
        status_field = None
        for f in entity_fields:
            if f.get("type") in ("select", "status") or "status" in f["name"].lower():
                status_field = f
                break
        if not status_field and entity_fields:
            status_field = entity_fields[0]

        field_key = status_field["name"] if status_field else "status"
        current_opts = list(status_field.get("options", [])) if status_field else []
        updated_opts = current_opts + [opt_name] if opt_name not in current_opts else current_opts

        tool_call = {
            "name": "update_crm_field",
            "arguments": {
                "entity_name": target_entity_name,
                "field_name": field_key,
                "options": updated_opts,
            }
        }
        return {
            "reply": f"I've prepared the action to add status option '{opt_name}' to field '{field_key}'.\n\nTOOL_CALL: {json.dumps(tool_call)}",
            "nav_route": None,
            "nav_label": None,
            "fallback": False,
        }

    # ── 5. DELETE_RECORD ───────────────────────────────────────────────────
    if intent == IntentCategory.DELETE_RECORD:
        clean_target = re.sub(r"^(please\s+)?(delete|remove|drop)\s+(the\s+|this\s+)?", "", q, flags=re.IGNORECASE)
        clean_target = re.sub(r"('s\s+record|\s+record|\s+ticket|\s+entry).*$", "", clean_target, flags=re.IGNORECASE).strip()
        record_id = clean_target if clean_target else "target_record"

        tool_call = {
            "name": "delete_record",
            "arguments": {
                "entity_name": target_entity_name,
                "record_id": record_id,
            }
        }
        return {
            "reply": f"I have prepared the deletion action for {target_entity_label} record '{record_id}'. Please confirm in the dialog to proceed.\n\nTOOL_CALL: {json.dumps(tool_call)}",
            "nav_route": None,
            "nav_label": None,
            "fallback": False,
        }

    # ── 6. UPDATE_RECORD ───────────────────────────────────────────────────
    if intent == IntentCategory.UPDATE_RECORD:
        matched_field = None
        new_val = None
        for f in entity_fields:
            f_norm = f["name"].replace("_", " ")
            if f["name"].lower() in q_lower or f.get("label", "").lower() in q_lower or f_norm in q_lower:
                matched_field = f
                break

        if not matched_field:
            for stage in pipeline_stages:
                if stage.lower() in q_lower:
                    new_val = stage
                    for f in entity_fields:
                        if f.get("type") in ("select", "status") or "status" in f["name"].lower():
                            matched_field = f
                            break
                    break

        rec_match = re.search(r"(?:update|change|set)\s+([A-Za-z0-9_\-\s]+?)(?:'s|\s+status|\s+field|\s+to|\s+priority)", q, re.IGNORECASE)
        record_id = rec_match.group(1).strip() if rec_match else "recent"

        if not new_val:
            val_match = re.search(r"(?:to|=|is)\s+['\"]?([A-Za-z0-9_\-\s]+)['\"]?$", q, re.IGNORECASE)
            new_val = val_match.group(1).strip() if val_match else "Updated Value"

        field_key = matched_field["name"] if matched_field else "status"
        tool_call = {
            "name": "update_record",
            "arguments": {
                "entity_name": target_entity_name,
                "record_id": record_id,
                "data": {field_key: new_val},
            }
        }
        return {
            "reply": f"I've prepared the update for {target_entity_label} record '{record_id}' ({field_key} → {new_val}).\n\nTOOL_CALL: {json.dumps(tool_call)}",
            "nav_route": None,
            "nav_label": None,
            "fallback": False,
        }

    # ── 7. CREATE_RECORD (Explicit Record Creation Imperatives Only) ───────
    if intent == IntentCategory.CREATE_RECORD:
        record_data: dict[str, Any] = {}

        # Universal schema-driven field extraction across all fields in target_entity
        matches = []
        for f in entity_fields:
            fname = f["name"].lower()
            flabel = f.get("label", "").lower()
            patterns = [re.escape(fname), re.escape(fname.replace("_", " ")), re.escape(flabel)]
            if f.get("type") in ("select", "status") or "status" in fname:
                patterns.append(r"crm\s+status")
                patterns.append(r"status")
            for pat in patterns:
                for m in re.finditer(r"\b" + pat + r"\b", q_lower):
                    matches.append((m.start(), m.end(), f))

        matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))
        filtered_matches = []
        last_end = 0
        for start, end, f in matches:
            if start >= last_end:
                filtered_matches.append((start, end, f))
                last_end = end

        for i, (start, end, f) in enumerate(filtered_matches):
            val_start = end
            val_end = filtered_matches[i + 1][0] if i + 1 < len(filtered_matches) else len(q)
            raw_val = q[val_start:val_end].strip()
            clean_val = re.sub(r"^(?:is|to|=|:|\s|of\b|as\b|at\b|with\b)+", "", raw_val, flags=re.IGNORECASE)
            clean_val = re.sub(r"(?:\s+and|\s+with|[,\.;])+$", "", clean_val, flags=re.IGNORECASE).strip()

            ftype = f.get("type", "text")
            if ftype in ("number", "integer"):
                val = int(clean_val) if clean_val.isdigit() else (float(clean_val) if clean_val.replace(".", "", 1).isdigit() else clean_val)
            elif ftype in ("currency", "float"):
                v_clean = clean_val.replace("$", "").replace(",", "")
                val = int(v_clean) if v_clean.isdigit() else (float(v_clean) if v_clean.replace(".", "", 1).isdigit() else clean_val)
            elif ftype in ("select", "status"):
                opts = f.get("options") or pipeline_stages or []
                matched_opt = next((o for o in opts if o.lower() == clean_val.lower()), clean_val)
                val = matched_opt
            else:
                val = clean_val

            record_data[f["name"]] = val

        # Simple commands like "Add John" or "Create customer Sarah Smith"
        if not record_data:
            email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", q)
            if email_match:
                for f in entity_fields:
                    if f.get("type") == "email" or "email" in f["name"]:
                        record_data[f["name"]] = email_match.group(0)
                        break

            name_match = re.search(r"(?:add|create)\s+(?:a\s+|new\s+)?(?:record\s+|customer\s+|lead\s+|ticket\s+|candidate\s+|shipment\s+)?([A-Za-z]+(?:\s+[A-Za-z]+)?)(?:\s+with|\s+and|\s*$)", q, re.IGNORECASE)
            if name_match:
                cand_name = name_match.group(1).strip()
                if cand_name.lower() not in ["a", "new", "record", "ticket", "customer", "lead", "candidate", "shipment"]:
                    for f in entity_fields:
                        if f.get("type") in ("text", "textarea") and any(k in f["name"].lower() for k in ["name", "title", "customer", "lead", "candidate", "client"]):
                            record_data[f["name"]] = cand_name
                            break
                    if not any(k in record_data for k in ["name", "full_name"]):
                        first_text = next((f["name"] for f in entity_fields if f.get("type") == "text"), None)
                        if first_text and first_text not in record_data:
                            record_data[first_text] = cand_name

        # Populate required fields with default placeholders if not provided
        for f in entity_fields:
            if f.get("required", False) and f["name"] not in record_data:
                ftype = f.get("type", "text")
                if ftype in ("number", "integer"):
                    record_data[f["name"]] = 0
                elif ftype in ("currency", "float"):
                    record_data[f["name"]] = 0.0
                elif ftype in ("select", "status"):
                    opts = f.get("options") or pipeline_stages or ["New"]
                    record_data[f["name"]] = opts[0]
                else:
                    record_data[f["name"]] = f"New {target_entity_label}"

        # Set default status if defined in schema
        for f in entity_fields:
            if (f.get("type") in ("select", "status") or "status" in f["name"]) and f["name"] not in record_data:
                if f.get("options") and len(f["options"]) > 0:
                    record_data[f["name"]] = f["options"][0]
                elif pipeline_stages:
                    record_data[f["name"]] = pipeline_stages[0]

        if not record_data and entity_fields:
            first_f = entity_fields[0]
            record_data[first_f["name"]] = f"New {target_entity_label}"

        tool_call = {
            "name": "create_record",
            "arguments": {
                "entity_name": target_entity_name,
                "data": record_data,
            }
        }
        return {
            "reply": f"I've prepared a new {target_entity_label} record for creation.\n\nTOOL_CALL: {json.dumps(tool_call)}",
            "nav_route": None,
            "nav_label": None,
            "fallback": False,
        }

    # ── 8. GENERAL_QUESTION & Fallback ────────────────────────────────────
    return {
        "reply": (
            f"I'm AURA Copilot for **{crm_name}**. I can query records, show analytics counts and distributions, "
            f"modify schema fields, or assist with CRM operations. What would you like to know?"
        ),
        "nav_route": None,
        "nav_label": None,
        "fallback": False,
    }


def _call_groq_copilot(messages: list[dict], system: str, settings: Settings) -> str | None:
    """Call Groq provider for copilot chat if configured."""
    if not settings.groq_api_key:
        return None
    try:
        from app.services.groq_provider import GroqProvider
        provider = GroqProvider(settings)
        formatted_messages = [{"role": "system", "content": system}] + messages
        result = provider.chat(formatted_messages)
        content = result.get("content", "")
        tool_calls = result.get("tool_calls", [])
        if tool_calls:
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name")
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        pass
                content += f"\nTOOL_CALL: {json.dumps({'name': name, 'arguments': args})}"
        return content.strip() if content.strip() else None
    except Exception as exc:
        logger.info("Groq copilot call failed: %s", exc)
        return None


# ── Ollama call ────────────────────────────────────────────────────

def _call_ollama_copilot(
    messages: list[dict],
    system: str,
    timeout: float = 60.0,
) -> str | None:
    """Call Ollama for the co-pilot. Returns cleaned reply text or None."""
    import httpx

    prompt = f"<|im_start|>system\n{system}<|im_end|>\n"
    for m in messages:
        prompt += f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n"
    prompt += "<|im_start|>assistant\n"

    payload: dict[str, Any] = {
        "model": "qwen3:4b",
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {"temperature": 0.3, "top_p": 0.9},
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post("http://localhost:11434/api/generate", json=payload)
            if resp.status_code == 200:
                raw = resp.json().get("response", "").strip()
                if "</think>" in raw:
                    raw = raw.split("</think>")[-1].strip()
                raw = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.IGNORECASE).strip()
                return raw if raw else None
            logger.warning("Ollama copilot returned status %d", resp.status_code)
    except Exception as exc:
        logger.info("Ollama copilot call failed: %s", exc)

    return None


# ── Parse [NAV: ...] marker from Ollama reply ──────────────────────

def _parse_nav(reply: str) -> tuple[str, str | None, str | None]:
    """
    Extract [NAV: route_key | Label] from the reply.
    Returns (clean_reply, nav_route, nav_label).
    """
    match = re.search(r"\[NAV:\s*(\w+)\s*\|\s*([^\]]+)\]", reply)
    if match:
        key = match.group(1).strip()
        label = match.group(2).strip()
        clean = reply[:match.start()].strip()
        route = AURA_ROUTES.get(key)
        return clean, route, label if route else None
    return reply, None, None


# ── Route ──────────────────────────────────────────────────────────

@router.post("/chat")
async def copilot_chat(
    body: CopilotRequest,
    user_id: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
):
    """
    Answer a co-pilot question using real CRM context.

    - Fetches the active CRM (ownership enforced — cannot access another tenant's CRM).
    - Builds a context-aware system prompt with the CRM configuration and workflows.
    - Calls Qwen3-4B via Ollama for a grounded answer.
    - Falls back to deterministic navigation hints if Ollama is unavailable.
    - Returns the reply text, an optional navigation action, and a fallback flag.
    """
    # Safety check the user's latest message
    latest = next((m.content for m in reversed(body.messages) if m.role == "user"), "")
    try:
        LayaSystem1.validate_prompt_safety(latest)
    except ValueError as exc:
        return error_response(502, "AI_PROVIDER_ERROR", str(exc))

    # Fetch CRM context if a crm_id was provided
    crm_context: dict[str, Any] | None = None
    if body.crm_id:
        repo = CRMRepository()
        crm = repo.get_crm(body.crm_id, user_id)  # ownership enforced
        if crm:
            # Fetch workflows to enrich the context
            try:
                workflows = repo.list_workflows(body.crm_id)
            except Exception:
                workflows = []
            crm_context = {
                "configuration": crm.get("configuration", {}),
                "configuration_version": crm.get("configuration_version", 1),
                "workflows": [
                    {
                        "name": w.get("name"),
                        "status": w.get("status"),
                        "trigger": w.get("trigger"),
                    }
                    for w in workflows
                ],
            }

    # Build context-aware system prompt
    system = _build_system_prompt(crm_context)

    # Convert message objects to dicts for LLM
    messages_dicts = [{"role": m.role, "content": m.content} for m in body.messages]

    # Try configured LLM provider
    raw_reply = None
    if settings.llm_provider == "groq" and settings.groq_api_key:
        raw_reply = _call_groq_copilot(messages_dicts, system, settings)
    elif settings.llm_provider == "local":
        raw_reply = _call_ollama_copilot(messages_dicts, system)

    # Run intent classification
    intent = IntentClassifier.classify(latest, messages_dicts[:-1], crm_context)

    # Sanitize raw LLM reply: read-only queries must NEVER contain mutation tools
    if raw_reply and IntentClassifier.is_read_only(intent):
        for mut_tool in MUTATION_TOOLS:
            if f'"name": "{mut_tool}"' in raw_reply or f'"name":"{mut_tool}"' in raw_reply:
                logger.warning("[COPILOT-SAFETY] Blocked mutation tool '%s' from read-only intent '%s'", mut_tool, intent)
                raw_reply = None
                break

    if raw_reply:
        clean_reply, nav_route, nav_label = _parse_nav(raw_reply)
        return success_response({
            "reply": clean_reply,
            "nav_route": nav_route,
            "nav_label": nav_label,
            "fallback": False,
        })

    # Fallback to deterministic intent execution with live CRM context
    fallback = _universal_action_reply(
        latest,
        crm_context,
        user_id=str(user_id) if user_id else None,
        crm_id=body.crm_id,
        history=messages_dicts[:-1],
    )
    fallback["fallback"] = True
    return success_response(fallback)


# ── CRM Schema Tool Execution ──────────────────────────────────────

class ToolCallRequest(BaseModel):
    """Request to execute a CRM schema tool."""
    tool_name: str = Field(
        ...,
        description="Name of the tool to execute (e.g., 'add_crm_field')"
    )
    crm_id: str = Field(
        ...,
        description="The CRM ID to operate on"
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool arguments (field_name, label, field_type, etc.)"
    )


def _validate_entity_name(crm_id: str, owner_id: str, entity_name: str | None, tool_name: str) -> tuple[bool, str | dict]:
    """
    Validate that entity_name exists in the CRM configuration (RC-004).
    
    For record-related tools, verify the entity exists. If not, return error with available entities.
    
    Returns:
        (is_valid, error_or_entity_name)
        - If valid: (True, entity_name)
        - If invalid: (False, error_dict)
    """
    # These tools require entity validation
    record_tools = {"create_record", "update_record", "delete_record", "query_records"}
    
    if tool_name not in record_tools:
        # Non-record tools don't require entity validation
        return True, entity_name or ""
    
    if not entity_name:
        return False, {
            "error_code": "VALIDATION_ERROR",
            "error_message": "entity_name is required for record operations"
        }
    
    # Fetch CRM to validate entity exists
    repo = CRMRepository()
    crm = repo.get_crm(crm_id, owner_id)
    if not crm:
        return False, {
            "error_code": "NOT_FOUND",
            "error_message": f"CRM '{crm_id}' not found or unauthorized"
        }
    
    config = crm.get("configuration", {})
    entities = config.get("entities", [])
    
    if not entities:
        return False, {
            "error_code": "INVALID_ENTITY",
            "error_message": f"No entities defined in this CRM. Cannot create records."
        }
    
    # Try to find a matching entity (exact match on name or normalized match on label)
    norm = str(entity_name).lower().strip().replace(" ", "_").replace("-", "_")
    for e in entities:
        e_name = str(e.get("name", "")).lower().strip().replace(" ", "_").replace("-", "_")
        e_label = str(e.get("label", "")).lower().strip().replace(" ", "_").replace("-", "_")
        if e_name == norm or e_label == norm or e.get("name") == entity_name:
            # Found a match; return the canonical entity name
            return True, e.get("name", entity_name)
    
    # No match found; return error with available entities
    available = [f"{e.get('name')} ({e.get('label')})" for e in entities]
    return False, {
        "error_code": "INVALID_ENTITY",
        "error_message": (
            f"Entity '{entity_name}' not found in this CRM. "
            f"Available entities: {', '.join(available)}"
        )
    }


@router.post("/tool-call")
async def execute_tool_call(
    body: ToolCallRequest,
    user_id: CurrentUser,
):
    """
    Execute a CRM schema tool call from an AI assistant.

    This endpoint receives tool invocations from AURA Copilot or other AI systems
    and executes them with proper authorization checks. All tool calls are validated
    server-side before execution.
    
    RC-004 FIX: Entity names are validated before tool execution. Invalid entity names
    are rejected with a 400 error listing available entities.

    Args:
        body: ToolCallRequest with tool_name, crm_id, and arguments
        user_id: Authenticated user ID (enforces CRM ownership)

    Returns:
        - 200: Tool execution succeeded, returns updated CRM configuration
        - 403: User does not own the CRM
        - 404: CRM not found
        - 400/422: Invalid tool name or parameters
        - 500: Internal error during tool execution

    Tool responses include:
        - success: bool
        - crm_id: str (if successful)
        - configuration: dict (if successful)
        - configuration_version: int (if successful)
        - error_code: str (if failed)
        - error_message: str (if failed)
    """
    # Map tool names to their handler functions
    tool_handlers = {
        # Record actions
        "create_record": CRMSchemaTools.create_record,
        "update_record": CRMSchemaTools.update_record,
        "delete_record": CRMSchemaTools.delete_record,
        # Field actions
        "add_crm_field": CRMSchemaTools.add_crm_field,
        "update_crm_field": CRMSchemaTools.update_crm_field,
        "delete_crm_field": CRMSchemaTools.delete_crm_field,
        # Stage actions
        "add_crm_stage": CRMSchemaTools.add_crm_stage,
        "delete_crm_stage": CRMSchemaTools.delete_crm_stage,
        # Reorder actions
        "reorder_crm_fields": CRMSchemaTools.reorder_crm_fields,
        "reorder_crm_stages": CRMSchemaTools.reorder_crm_stages,
        # Read-only query & analytics tools
        "get_crm_summary": CRMSchemaTools.get_crm_summary,
        "get_entity_schema": CRMSchemaTools.get_entity_schema,
        "get_status_distribution": CRMSchemaTools.get_status_distribution,
        "count_records": CRMSchemaTools.count_records,
        "query_records": CRMSchemaTools.query_records,
        "aggregate_records": CRMSchemaTools.aggregate_records,
    }

    # Validate tool name
    tool_name = body.tool_name.strip().lower()
    if tool_name not in tool_handlers:
        return error_response(
            400,
            "INVALID_TOOL",
            f"Unknown tool '{body.tool_name}'. Available tools: {', '.join(tool_handlers.keys())}"
        )

    # RC-004: Validate entity_name if this is a record operation
    entity_name = body.arguments.get("entity_name")
    is_valid, result = _validate_entity_name(body.crm_id, str(user_id), entity_name, tool_name)
    if not is_valid:
        return error_response(400, result["error_code"], result["error_message"])
    
    # Update arguments with the canonical entity name if it was normalized
    if tool_name in {"create_record", "update_record", "delete_record"}:
        body.arguments["entity_name"] = result

    # Get the tool handler
    handler = tool_handlers[tool_name]

    # Execute the tool with owner_id for authorization
    try:
        # Pass owner_id to ensure authorization is checked by the tool
        result = handler(
            crm_id=body.crm_id,
            owner_id=str(user_id),
            **body.arguments
        )

        # Check if tool execution was successful
        if isinstance(result, dict) and result.get("success", False):
            logger.info(
                "[COPILOT-TOOL] Successfully executed tool '%s' on CRM %s",
                tool_name,
                body.crm_id
            )
            return success_response(result)
        elif isinstance(result, dict) and not result.get("success"):
            # Tool returned an error
            error_code = result.get("error_code", "TOOL_ERROR")
            error_msg = result.get("error_message", "Tool execution failed")

            # Map error codes to HTTP status codes
            status_code = 500  # default
            if error_code == "NOT_FOUND":
                status_code = 404
            elif error_code == "CONFLICT":
                status_code = 409
            elif error_code == "VALIDATION_ERROR":
                status_code = 422

            logger.warning(
                "[COPILOT-TOOL] Tool '%s' failed with code '%s': %s",
                tool_name,
                error_code,
                error_msg
            )
            return error_response(status_code, error_code, error_msg)
        else:
            # Unexpected result format
            logger.error("[COPILOT-TOOL] Unexpected result format from tool '%s'", tool_name)
            return error_response(500, "INTERNAL_ERROR", "Tool returned unexpected response format")

    except ValueError as exc:
        error_msg = str(exc)
        if "unauthorized" in error_msg.lower() or "not found" in error_msg.lower():
            return error_response(404, "NOT_FOUND", error_msg)
        return error_response(422, "VALIDATION_ERROR", error_msg)
    except Exception as exc:
        logger.exception("[COPILOT-TOOL] Unexpected error executing tool '%s'", tool_name)
        return error_response(500, "INTERNAL_ERROR", f"Tool execution failed: {str(exc)}")
