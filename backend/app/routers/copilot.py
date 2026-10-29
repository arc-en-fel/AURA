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
from app.services.ai_tools import CRMSchemaTools

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
    """Build system prompt with action detection and tool schemas."""
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
        
        "# TOOL CALLING FORMAT\n"
        "When you need to execute an action, generate a JSON tool call in this format:\n"
        "TOOL_CALL: {\"name\": \"tool_name\", \"arguments\": {arg1: value1, arg2: value2}}\n\n"
        "Examples:\n"
        "- Create record: TOOL_CALL: {\"name\": \"create_record\", \"arguments\": {\"entity_name\": \"lead\", \"data\": {\"name\": \"John\", \"email\": \"john@example.com\"}}}\n"
        "- Update record: TOOL_CALL: {\"name\": \"update_record\", \"arguments\": {\"entity_name\": \"lead\", \"record_id\": \"uuid-here\", \"data\": {\"status\": \"qualified\"}}}\n"
        "- Delete record: TOOL_CALL: {\"name\": \"delete_record\", \"arguments\": {\"entity_name\": \"lead\", \"record_id\": \"uuid-here\"}}\n"
        "- Add field: TOOL_CALL: {\"name\": \"add_crm_field\", \"arguments\": {\"field_name\": \"country\", \"label\": \"Country\", \"field_type\": \"text\"}}\n"
        "- Add stage: TOOL_CALL: {\"name\": \"add_crm_stage\", \"arguments\": {\"stage_name\": \"Negotiation\"}}\n\n"
        
        "# AVAILABLE TOOLS\n"
        "## Record Actions\n"
        "- create_record(entity_name, data, source?): Create a new record\n"
        "- update_record(entity_name, record_id, data): Update existing record\n"
        "- delete_record(entity_name, record_id): Delete a record (dangerous — requires user confirmation)\n\n"
        "## Field Actions\n"
        "- add_crm_field(field_name, label, field_type, required?, options?): Add field\n"
        "- update_crm_field(field_name, label?, field_type?, required?, options?): Update field\n"
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
        "- Never execute code or SQL.\n\n"
        f"Available AURA routes:\n{routes_text}\n"
    )

    if crm_context:
        config = crm_context.get("configuration", {})
        entities = config.get("entities", [])
        entity_summary = []
        for e in entities[:5]:  # cap at 5 to control prompt size
            field_names = [f["name"] for f in e.get("fields", [])[:8]]
            entity_summary.append(
                f"  - {e['label']} ({e['name']}): fields = {', '.join(field_names)}"
            )

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
            f"Entities:\n" + ("\n".join(entity_summary) if entity_summary else "  None") + "\n"
            f"Workflows ({len(workflows)} total):\n"
            + ("\n".join(wf_summary) if wf_summary else "  None defined") + "\n"
        )
        base += crm_block

    return base


# ── Universal Intent Resolver & Fallback ──────────────────────────

def _universal_action_reply(question: str, crm_context: dict[str, Any] | None) -> dict[str, Any]:
    """
    Intelligently analyzes user input and either generates an executable TOOL_CALL
    or returns schema-grounded information. Works for ANY CRM without hardcoding.
    """
    import json
    q = question.strip()
    q_lower = q.lower()
    
    config = crm_context.get("configuration", {}) if crm_context else {}
    crm_name = config.get("name", "your CRM")
    entities = config.get("entities", [])
    primary_entity = entities[0] if entities else None
    primary_entity_name = primary_entity["name"] if primary_entity else "record"
    primary_entity_label = primary_entity["label"] if primary_entity else "Record"
    pipeline_stages = config.get("pipeline_stages", [])

    # Find which entity the user might be referring to
    target_entity = primary_entity
    for ent in entities:
        if ent["name"].lower() in q_lower or ent["label"].lower() in q_lower:
            target_entity = ent
            break

    target_entity_name = target_entity["name"] if target_entity else primary_entity_name
    target_entity_label = target_entity["label"] if target_entity else primary_entity_label
    entity_fields = target_entity.get("fields", []) if target_entity else []

    # 1. ACTION: Delete Record
    # E.g. "Delete John's record", "Remove this ticket", "Delete customer Alice"
    if any(q_lower.startswith(w) or f" {w} " in f" {q_lower} " for w in ["delete", "remove", "drop"]) and any(
        w in q_lower for w in ["record", "ticket", "customer", "lead", "candidate", "shipment", "item", "'s record", "this"]
    ) and not any(w in q_lower for w in ["field", "column", "stage", "status"]):
        # Extract target identifier
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

    # 2. ACTION: Update Record
    # E.g. "Change John's status to Won", "Update ticket priority to High", "Change shipment destination to Chicago"
    if any(q_lower.startswith(w) or f" {w} " in f" {q_lower} " for w in ["update", "change", "set", "modify"]):
        # Look for field being changed
        matched_field = None
        new_val = None
        for f in entity_fields:
            f_norm = f["name"].replace("_", " ")
            if f["name"].lower() in q_lower or f["label"].lower() in q_lower or f_norm in q_lower:
                matched_field = f
                break

        # Check if updating a pipeline stage / status
        if not matched_field:
            for stage in pipeline_stages:
                if stage.lower() in q_lower:
                    new_val = stage
                    # Find status field
                    for f in entity_fields:
                        if f["type"] in ("select", "status") or "status" in f["name"] or "stage" in f["name"]:
                            matched_field = f
                            break
                    break

        # Extract record identifier
        rec_match = re.search(r"(?:update|change|set)\s+([A-Za-z0-9_\-\s]+?)(?:'s|\s+status|\s+field|\s+to|\s+priority)", q, re.IGNORECASE)
        record_id = rec_match.group(1).strip() if rec_match else "recent"

        # Extract new value if after 'to' or '='
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

    # 3. ACTION: Create Record
    # E.g. "Add a record", "Add John", "Create a new customer", "Add a new ticket", "Create a shipment", "Add customer Alice with email alice@corp.com"
    if any(q_lower.startswith(w) or f" {w} " in f" {q_lower} " for w in ["add", "create", "new", "insert", "make"]) and (
        any(w in q_lower for w in ["record", "customer", "lead", "ticket", "candidate", "shipment", "item", "order", "entry", "user"])
        or (len(q.split()) <= 4 and any(q_lower.startswith(w) for w in ["add ", "create ", "new "]))
    ) and not any(w in q_lower for w in ["field", "column", "stage", "status"]):
        record_data: dict[str, Any] = {}

        # Look for explicit key-value pairs (e.g. name: John, email: test@test.com)
        for f in entity_fields:
            fname = f["name"]
            flabel = f["label"]
            match = re.search(rf"(?:{fname}|{flabel})\s*[:=]\s*['\"]?([^,;\n]+)['\"]?", q, re.IGNORECASE)
            if match:
                val = match.group(1).strip()
                record_data[fname] = Number(val) if f["type"] in ("number", "currency") and val.replace(".", "").isdigit() else val

        # Extract email if present
        email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", q)
        if email_match:
            for f in entity_fields:
                if f["type"] == "email" or "email" in f["name"]:
                    record_data[f["name"]] = email_match.group(0)
                    break

        # Extract name if simple command like "Add John" or "Create customer Sarah Smith"
        name_match = re.search(r"(?:add|create)\s+(?:a\s+|new\s+)?(?:record\s+|customer\s+|lead\s+|ticket\s+|candidate\s+|shipment\s+)?([A-Za-z]+(?:\s+[A-Za-z]+)?)(?:\s+with|\s+and|\s*$)", q, re.IGNORECASE)
        if name_match:
            cand_name = name_match.group(1).strip()
            if cand_name.lower() not in ["a", "new", "record", "ticket", "customer", "lead", "candidate", "shipment"]:
                # Map to primary name/title/text field
                for f in entity_fields:
                    if f["type"] in ("text", "textarea") and any(k in f["name"].lower() for k in ["name", "title", "customer", "lead", "candidate", "specimen", "client"]):
                        record_data[f["name"]] = cand_name
                        break
                if not any(k in record_data for k in ["name", "full_name"]):
                    first_text = next((f["name"] for f in entity_fields if f["type"] == "text"), None)
                    if first_text and first_text not in record_data:
                        record_data[first_text] = cand_name

        # Set default status / stage if entity has a status field and none provided
        for f in entity_fields:
            if (f["type"] in ("select", "status") or "status" in f["name"]) and f["name"] not in record_data:
                if f.get("options") and len(f["options"]) > 0:
                    record_data[f["name"]] = f["options"][0]
                elif pipeline_stages:
                    record_data[f["name"]] = pipeline_stages[0]

        # If still completely empty, populate primary field with sample placeholder
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

    # 4. ACTION: Add Column / Field
    # E.g. "Add a new column Priority", "Add field Country as text"
    if any(q_lower.startswith(w) or f" {w} " in f" {q_lower} " for w in ["add", "create", "new"]) and any(
        w in q_lower for w in ["column", "field"]
    ):
        field_match = re.search(r"(?:add|create|new)\s+(?:a\s+|new\s+)?(?:column|field)\s+([A-Za-z0-9_\-\s]+)", q, re.IGNORECASE)
        raw_name = field_match.group(1).strip() if field_match else "new_field"
        clean_name = re.sub(r"\s+(as|type|with).*$", "", raw_name, flags=re.IGNORECASE).strip()
        machine_name = clean_name.lower().replace(" ", "_")
        label = clean_name.title()
        
        # Infer type
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

    # 5. ACTION: Delete Column / Field
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

    # 6. ACTION: Add Stage / Status
    # E.g. "Add Negotiation as a status", "Add In Review stage"
    if any(q_lower.startswith(w) or f" {w} " in f" {q_lower} " for w in ["add", "create", "new"]) and any(
        w in q_lower for w in ["stage", "status", "pipeline stage"]
    ):
        stage_match = re.search(r"(?:add|create|new)\s+['\"]?([A-Za-z0-9_\-\s]+?)['\"]?\s+(?:as\s+a\s+|as\s+)?(?:stage|status)", q, re.IGNORECASE)
        if not stage_match:
            stage_match = re.search(r"(?:stage|status)\s+['\"]?([A-Za-z0-9_\-\s]+)['\"]?", q, re.IGNORECASE)
        stage_name = stage_match.group(1).strip() if stage_match else "New Stage"
        
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

    # 7. ACTION: Delete Stage / Status
    # E.g. "Remove Waiting status", "Delete Closed stage"
    if any(q_lower.startswith(w) or f" {w} " in f" {q_lower} " for w in ["delete", "remove", "drop"]) and any(
        w in q_lower for w in ["stage", "status"]
    ):
        stage_match = re.search(r"(?:delete|remove|drop)\s+['\"]?([A-Za-z0-9_\-\s]+?)['\"]?\s+(?:stage|status)", q, re.IGNORECASE)
        if not stage_match:
            stage_match = re.search(r"(?:stage|status)\s+['\"]?([A-Za-z0-9_\-\s]+)['\"]?", q, re.IGNORECASE)
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

    # 8. INFORMATIONAL: Schema / Fields Question
    # E.g. "What fields does my CRM have?", "What entities exist?"
    if any(w in q_lower for w in ["what field", "which field", "list field", "fields does", "entities", "schema", "structure"]):
        if entities:
            summary_parts = []
            for ent in entities:
                f_list = ", ".join(f"{f['label']} ({f['type']})" for f in ent.get("fields", []))
                summary_parts.append(f"**{ent['label']}** ({ent['name']}): {f_list}")
            
            stages_text = " → ".join(pipeline_stages) if pipeline_stages else "None configured"
            reply_text = (
                f"**{crm_name}** configuration:\n\n"
                + "\n".join(summary_parts)
                + f"\n\n**Pipeline Stages:** {stages_text}"
            )
            return {
                "reply": reply_text,
                "nav_route": None,
                "nav_label": None,
                "fallback": False,
            }

    # 9. INFORMATIONAL: Stages / Status Flow Question
    if any(w in q_lower for w in ["what stage", "which stage", "status flow", "pipeline stages", "statuses"]):
        stages_text = " → ".join(pipeline_stages) if pipeline_stages else "No stages configured"
        return {
            "reply": f"The pipeline stages for **{crm_name}** are:\n\n{stages_text}",
            "nav_route": None,
            "nav_label": None,
            "fallback": False,
        }

    # 10. INFORMATIONAL: Analytics & Metrics
    if any(w in q_lower for w in ["analytics", "conversion", "metric", "pipeline", "funnel", "stat", "chart", "kpi"]):
        return {
            "reply": (
                f"You can view dynamic real-time analytics, status distributions, and categorical breakdowns for {crm_name} on the Analytics page."
            ),
            "nav_route": AURA_ROUTES["analytics"],
            "nav_label": "View Analytics",
            "fallback": False,
        }

    # 11. INFORMATIONAL: Records Navigation
    if any(w in q_lower for w in ["records", "view record", "open record", "table", "csv"]):
        return {
            "reply": (
                f"Records in {crm_name} are organized by entity with dynamic columns generated from your schema. You can add, edit, search, and import records on the Records page."
            ),
            "nav_route": AURA_ROUTES["records"],
            "nav_label": "Open Records",
            "fallback": False,
        }

    # Default friendly assistant reply
    return {
        "reply": (
            f"I'm AURA Copilot for **{crm_name}**. I can create records, update values, delete records, "
            f"add new fields/stages, or answer questions about your CRM. What would you like to do?"
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

    # Try configured LLM provider
    raw_reply = None
    if settings.llm_provider == "groq" and settings.groq_api_key:
        raw_reply = _call_groq_copilot(messages_dicts, system, settings)
    elif settings.llm_provider == "local":
        raw_reply = _call_ollama_copilot(messages_dicts, system)

    if raw_reply:
        clean_reply, nav_route, nav_label = _parse_nav(raw_reply)
        return success_response({
            "reply": clean_reply,
            "nav_route": nav_route,
            "nav_label": nav_label,
            "fallback": False,
        })

    # LLM unavailable or fallback — use universal action and intent resolver
    fallback = _universal_action_reply(latest, crm_context)
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
    }

    # Validate tool name
    tool_name = body.tool_name.strip().lower()
    if tool_name not in tool_handlers:
        return error_response(
            400,
            "INVALID_TOOL",
            f"Unknown tool '{body.tool_name}'. Available tools: {', '.join(tool_handlers.keys())}"
        )

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
