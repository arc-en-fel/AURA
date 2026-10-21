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
    routes_text = "\n".join(f"  - {k}: {v}" for k, v in AURA_ROUTES.items())

    base = (
        "You are AURA Copilot, an expert assistant for the AURA Self-Evolving CRM platform.\n\n"
        "Your capabilities:\n"
        "1. Answer questions about the user's CRM configuration (entities, fields, pipeline stages).\n"
        "2. Explain how workflows work in AURA.\n"
        "3. Guide users to the correct AURA screen using the real routes listed below.\n"
        "4. Suggest CRM improvements, but NEVER apply them — always tell the user to use the "
        "Evolution Center for changes.\n\n"
        "Rules:\n"
        "- Keep replies under 120 words. Be direct and helpful.\n"
        "- If you mention a navigation action, append it at the end as: "
        "[NAV: route_key | Button Label]\n"
        "  Example: [NAV: evolution | Go to Evolution Center]\n"
        "- Base answers on the CRM context below. Do NOT invent fields, stages, or metrics.\n"
        "- If information is unavailable, say so clearly.\n"
        "- NEVER approve, apply, or reject evolution proposals.\n"
        "- NEVER modify records, workflows, or CRM configuration.\n"
        "- NEVER execute code or SQL.\n\n"
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


# ── Deterministic navigation fallback ─────────────────────────────

def _deterministic_reply(question: str, crm_context: dict[str, Any] | None) -> dict[str, Any]:
    """
    Returns a helpful reply and optional navigation action without calling Ollama.
    Used when Ollama is unavailable.
    """
    q = question.lower()
    crm_name = crm_context.get("configuration", {}).get("name", "your CRM") if crm_context else "your CRM"

    if any(w in q for w in ["evolution", "proposal", "improve", "change crm", "update crm"]):
        return {
            "reply": (
                f"To suggest improvements to {crm_name}, go to the Evolution Center. "
                "AURA will generate an AI-powered proposal that you can review and approve "
                "before any change is applied."
            ),
            "nav_route": AURA_ROUTES["evolution"],
            "nav_label": "Go to Evolution Center",
            "fallback": True,
        }

    if any(w in q for w in ["workflow", "automation", "trigger", "follow-up", "follow up"]):
        return {
            "reply": (
                "Workflows in AURA fire automatically when a record event occurs "
                "(created, updated, or stage changed). Each workflow has one trigger "
                "and one or more allowlisted actions like creating a follow-up task or notifying the owner. "
                "You can view and manage workflows on the Workflows page."
            ),
            "nav_route": AURA_ROUTES["workflows"],
            "nav_label": "View Workflows",
            "fallback": True,
        }

    if any(w in q for w in ["record", "lead", "contact", "deal", "patient", "customer", "import"]):
        return {
            "reply": (
                f"Records in {crm_name} are stored dynamically — each record belongs to an entity "
                "you defined (like 'lead' or 'patient') and contains only the fields in your CRM schema. "
                "You can create, edit, filter, and import records via CSV on the Records page."
            ),
            "nav_route": AURA_ROUTES["records"],
            "nav_label": "Open Records",
            "fallback": True,
        }

    if any(w in q for w in ["analytics", "conversion", "metric", "pipeline", "funnel", "stat"]):
        return {
            "reply": (
                f"AURA tracks total leads, qualified leads, won leads, and conversion rate for {crm_name}. "
                "The Analytics page shows a pipeline stage breakdown and source distribution chart."
            ),
            "nav_route": AURA_ROUTES["analytics"],
            "nav_label": "View Analytics",
            "fallback": True,
        }

    if any(w in q for w in ["build", "create crm", "new crm", "generate crm"]):
        return {
            "reply": (
                "To build a new CRM, go to the Build a CRM page. "
                "AURA will guide you through a short questionnaire and then generate a custom CRM schema "
                "tailored to your business."
            ),
            "nav_route": AURA_ROUTES["build_crm"],
            "nav_label": "Build a CRM",
            "fallback": True,
        }

    if any(w in q for w in ["field", "entity", "schema", "structure", "config"]):
        if crm_context:
            entities = crm_context.get("configuration", {}).get("entities", [])
            entity_lines = [
                f"{e['label']}: {', '.join(f['name'] for f in e.get('fields', [])[:5])}"
                for e in entities[:3]
            ]
            return {
                "reply": (
                    f"{crm_name} has {len(entities)} entity type(s): "
                    + "; ".join(entity_lines) + ". "
                    "To change the schema, use the Evolution Center."
                ),
                "nav_route": None,
                "nav_label": None,
                "fallback": True,
            }

    return {
        "reply": (
            "I can help with questions about your CRM configuration, records, workflows, analytics, "
            "and evolution proposals. Try asking something like 'What fields does my lead entity have?' "
            "or 'How do I improve my conversion rate?'."
        ),
        "nav_route": None,
        "nav_label": None,
        "fallback": True,
    }


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

    # Call Ollama
    messages_dicts = [{"role": m.role, "content": m.content} for m in body.messages]
    raw_reply = _call_ollama_copilot(messages_dicts, system)

    if raw_reply:
        clean_reply, nav_route, nav_label = _parse_nav(raw_reply)
        return success_response({
            "reply": clean_reply,
            "nav_route": nav_route,
            "nav_label": nav_label,
            "fallback": False,
        })

    # Ollama unavailable — use deterministic fallback
    fallback = _deterministic_reply(latest, crm_context)
    return success_response(fallback)
