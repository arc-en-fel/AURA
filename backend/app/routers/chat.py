"""Interactive CRM Chat routes.

Endpoints:
- POST /api/v1/crm/chat          — Send a message, receive AI question or CRM draft
- POST /api/v1/crm/chat/generate — Convert a completed conversation into a CRM draft

The chat endpoint drives a multi-turn conversation where the AI asks targeted
questions about the user's business before generating a CRM configuration.
The generated CRM is a draft — it is NOT saved until the user explicitly saves it.
"""
from __future__ import annotations

import json
import logging
import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth import CurrentUser
from app.config import get_settings, Settings
from app.routers.responses import success_response, error_response
from app.schemas.crm import CRMConfiguration
from app.services.laya_system1 import LayaSystem1

logger = logging.getLogger(__name__)


def _chat_reply_response(data: dict[str, Any], source: str):
    """Attach safe response provenance to a CRM Builder reply."""
    logger.info("[AURA] CRM Builder reply response_source=%s ready_to_generate=%s",
                source, data.get("ready_to_generate"))
    data.setdefault("ai", {"provider": "groq", "model": get_settings().groq_model, "used": False, "fallback": source == "fallback"})
    data.setdefault("routing", {"route": "system2_groq", "requires_llm": True, "laya_mode": "deterministic", "laya_model_loaded": False})
    return success_response({**data, "response_source": source})


def _chat_error_response(status_code: int, code: str, message: str, *, ai_used: bool = False):
    logger.warning("[AURA] CRM Builder error response code=%s", code)
    settings = get_settings()
    return error_response(status_code, code, message, response_source="error",
                          ai={"provider": "groq", "model": settings.groq_model, "used": ai_used, "fallback": True},
                          routing={"route": "system2_groq", "requires_llm": True, "laya_mode": "deterministic", "laya_model_loaded": False})


router = APIRouter(prefix="/crm/chat", tags=["CRM Chat"])


@router.get("/runtime-status")
async def runtime_status(user_id: CurrentUser, settings: Annotated[Settings, Depends(get_settings)]):
    """Report provider readiness without exposing credentials."""
    from app.services.groq_provider import groq_status
    groq = groq_status(settings)
    return success_response({
        "system1_laya": {"laya_available": True, "laya_mode": "deterministic", "model_loaded": False},
        "system2_groq": {**groq, "groq_available": groq["available"]},
    })


# ── Request / Response schemas ──────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=40)
    generate_now: bool = False
    crm_type: str | None = Field(default=None, max_length=120)  # optional context from UI chip


class ChatResponse(BaseModel):
    reply: str
    generate_now: bool = False
    ready_to_generate: bool = False


class ChatGenerateRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=40)


# ── Prompts ─────────────────────────────────────────────────────────

_GENERATOR_SYSTEM = """\
You are an expert CRM architect. Based on the conversation below, generate a complete CRM \
configuration JSON that exactly matches this schema:

{
  "schema_version": "1.0",
  "name": "Human-readable CRM Name",
  "industry": "industry_slug",
  "entities": [
    {
      "name": "machine_identifier",
      "label": "Human Label",
      "fields": [
        {"name": "field_name", "label": "Label", "type": "text", "required": true},
        {"name": "status", "label": "Status", "type": "select", "required": true, "options": ["A", "B"]}
      ]
    }
  ],
  "pipeline_stages": ["Stage1", "Stage2", "Stage3"]
}

Constraints:
- Entity names and field names must be lowercase letters and underscores only.
- Field types must be one of: text, textarea, email, number, date, boolean, select, phone.
- Select fields must have a non-empty list of unique string options.
- Build the CRM specifically around what the user described in the conversation.
- Output valid JSON only. No explanation, no markdown.
"""


# ── Groq helpers ────────────────────────────────────────────────

def _call_groq_builder(messages: list[dict], system: str, timeout: float = 120.0) -> str | None:
    """Compatibility-named adapter; CRM Builder inference is served by Groq."""
    from app.services.groq_provider import GroqProvider
    try:
        response = GroqProvider().chat([{"role": "system", "content": system}, *messages], max_tokens=512)
        return str(response.get("content") or "").strip() or None
    except Exception as exc:
        logger.warning("[AURA] Groq Builder request failed (%s)", type(exc).__name__)
        return None


def _fallback_reply(messages: list[ChatMessage]) -> tuple[str, bool]:
    """Deterministic fallback when Groq is unavailable during conversation."""
    count = sum(1 for m in messages if m.role == "user")
    questions = [
        "What kind of business is this CRM for — real estate, healthcare, sales, or something else?",
        "What are the main things you need to track? For example: leads, clients, deals, appointments?",
        "How many stages does your typical process have? For example: New → Contacted → Qualified → Won.",
        "What's the most important field you need on each record — like budget, phone number, or priority?",
    ]
    if count <= len(questions):
        reply = questions[count - 1]
        ready = count >= len(questions)
        if ready:
            reply += "\n\n[READY_TO_GENERATE]"
        return reply, ready
    return "I have everything I need! Click 'Generate My CRM' to create your custom CRM.", True


def _fallback_generate(messages: list[ChatMessage]) -> dict[str, Any]:
    """Build a scaffold CRM from the conversation when Groq is unavailable."""
    # Extract user messages to build a combined prompt for the scaffold
    user_text = " ".join(m.content for m in messages if m.role == "user")
    return LayaSystem1.generate_scaffold_config(user_text)


# ── Routes ──────────────────────────────────────────────────────────

@router.post("")
async def chat(
    body: ChatRequest,
    user_id: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
):
    """Send a message to the CRM consultant AI and receive the next question or CRM draft.

    - While gathering info: returns {reply, ready_to_generate: false}
    - When enough info gathered: returns {reply, ready_to_generate: true}
    - When generate_now=true: returns {configuration, warnings} as a CRM draft
    """
    logger.info("[AURA] CRM Builder request received generate_now=%s history_items=%d",
                body.generate_now, len(body.messages))
    messages_dicts = [{"role": m.role, "content": m.content} for m in body.messages]

    # ── Branch: generate the CRM from the full conversation ─────────
    if body.generate_now:
        warnings: list[str] = []

        user_context = "\n".join(
            f"{m.role.title()}: {m.content.strip()}"
            for m in body.messages
            if m.content.strip()
        )
        if not any(m.role == "user" and m.content.strip() for m in body.messages):
            return _chat_error_response(422, "VALIDATION_ERROR", "Describe your business or what you want the CRM to manage.")
        
        generation_prompt = (
            f"Build a {body.crm_type} CRM. " if body.crm_type else ""
        ) + "\nConversation (preserve the user's requested entities, fields, and stages):\n" + user_context
        
        provider = None
        config_dict: dict[str, Any] | None = None
        try:
            from app.services.ai_provider import get_ai_provider
            provider = get_ai_provider("groq")
            if hasattr(provider, "generate_crm_config_async"):
                config_dict = await provider.generate_crm_config_async(generation_prompt)
            else:
                config_dict = await asyncio.to_thread(provider.generate_crm_config, generation_prompt)
            config_dict = CRMConfiguration(**config_dict).model_dump()
            warnings = list(getattr(provider, "last_warnings", []))
        except ValueError as exc:
            return _chat_error_response(502, "AI_PROVIDER_ERROR", str(exc), ai_used=bool(getattr(provider, "last_used", False)))
        except Exception:
            logger.exception("Configured provider failed during chat CRM generation")
            # Fall back to deterministic scaffold
            warnings = [
                "AI provider fallback: CRM generated via AURA's deterministic scaffold "
                "after the AI provider was unavailable or returned unusable output."
            ]
            config_dict = _fallback_generate(body.messages)

        return _chat_reply_response({
            "configuration": config_dict,
            "warnings": warnings,
            "ready_to_generate": False,
            "ai": {"provider": "groq", "model": settings.groq_model,
                   "used": bool(getattr(provider, "last_used", False) if provider else False),
                   "fallback": bool(warnings)},
            "routing": {"route": "system2_groq", "intent": "generate_crm", "requires_llm": True,
                        "laya_mode": "deterministic", "laya_model_loaded": False},
        }, "fallback" if warnings else "llm")

    # ── Branch: continue the conversation ───────────────────────────
    # Safety check on latest user message
    latest_user = next(
        (m.content for m in reversed(body.messages) if m.role == "user"), ""
    )
    try:
        LayaSystem1.validate_prompt_safety(latest_user)
    except ValueError as exc:
        return _chat_error_response(502, "AI_PROVIDER_ERROR", str(exc))

    # Enrich the system prompt with the CRM type chip selection when provided
    system = (
        "You are AURA's CRM design interviewer. Use the complete conversation and the collected details "
        "already present in it. Respond naturally to the latest user message, ask at most one useful "
        "follow-up question, and never ask again for a detail already answered. Ask only about details "
        "that materially help define entities, fields, or lifecycle stages. If the user has provided "
        "enough to design a useful draft, say so and set ready_to_generate true. Return one JSON object "
        'with exactly "reply" (string) and "ready_to_generate" (boolean). No canned sequence.'
    )
    if body.crm_type:
        system = (
            f"The user has already indicated they want to build a '{body.crm_type}' CRM. "
            f"Use this as confirmed context — do not ask about CRM type again.\n\n"
            + system
        )

    raw_reply = _call_groq_builder(messages_dicts, system)
    fallback_used = raw_reply is None

    if fallback_used:
        reply, _ = _fallback_reply(body.messages)
        ready = "[READY_TO_GENERATE]" in (reply or "")
        clean_reply = (reply or "").replace("[READY_TO_GENERATE]", "").strip()
        if ready and not clean_reply:
            clean_reply = (
                "I have all the information I need to build your CRM! "
                "Click 'Generate My CRM' whenever you're ready."
            )
    else:
        # Try to parse JSON response from Groq
        try:
            parsed = LayaSystem1.extract_json_payload(raw_reply or "")
            clean_reply = str(parsed.get("reply", "")).strip()
            ready = parsed.get("ready_to_generate", False) is True
            if not clean_reply or len(clean_reply) > 1200:
                raise ValueError("invalid reply")
        except (ValueError, KeyError, TypeError):
            clean_reply = "The AI interviewer returned an unusable response. Please retry; your conversation has been preserved."
            ready = False
            fallback_used = True

    return _chat_reply_response({
        "reply": clean_reply,
        "ready_to_generate": ready,
        "fallback_used": fallback_used,
        "ai": {"provider": "groq", "model": settings.groq_model, "used": raw_reply is not None, "fallback": fallback_used},
        "routing": {"route": "system2_groq", "intent": "crm_interview", "requires_llm": True,
                    "laya_mode": "deterministic", "laya_model_loaded": False},
    }, "fallback" if fallback_used else "llm")
