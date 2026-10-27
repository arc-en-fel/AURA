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
from pydantic import BaseModel, Field, ConfigDict

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
    data.setdefault("ai", {"provider": "ollama/qwen", "model": "qwen2.5:3b", "used": False, "fallback": False})
    data.setdefault("routing", {"route": "qwen_generation", "requires_llm": True, "laya_mode": "validation_only", "laya_model_loaded": False})
    return success_response({**data, "response_source": source})


def _chat_error_response(status_code: int, code: str, message: str, *, ai_used: bool = False):
    logger.warning("[AURA] CRM Builder error response code=%s", code)
    return error_response(status_code, code, message, response_source="error",
                          ai={"provider": "ollama/qwen", "model": "qwen2.5:3b", "used": ai_used, "fallback": False},
                          routing={"route": "qwen_generation", "requires_llm": True, "laya_mode": "validation_only", "laya_model_loaded": False})


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
    model_config = ConfigDict(extra="ignore")
    
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=8000)
    # Allow but ignore extra fields from frontend (response_source, isLoading, choices)
    response_source: str | None = None
    isLoading: bool | None = None
    choices: list[str] | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=40)
    generate_now: bool = False
    crm_type: str | None = Field(default=None, max_length=120)  # optional context from UI chip
    # NEW: Structured questionnaire answers from the CRM builder
    quest_answers: dict[str, str | None] = Field(default_factory=dict)


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
    """Call the Qwen AI provider for CRM Builder responses."""
    from app.services.ai_provider import get_ai_provider
    try:
        provider = get_ai_provider("local")
        logger.info("[_call_groq_builder] provider type=%s, has_chat=%s", 
                   type(provider).__name__, hasattr(provider, "chat"))
        if hasattr(provider, "chat"):
            logger.info("[_call_groq_builder] Calling provider.chat() for conversational response")
            response = provider.chat(messages, system_prompt=system, max_tokens=512)
            logger.info("[_call_groq_builder] chat() returned: %s", response)
            return str(response.get("content") or "").strip() or None
        else:
            logger.warning("[_call_groq_builder] Provider has no chat method, using fallback")
            # Fallback: use basic prompt-response
            response = provider.generate_crm_config(system + "\n" + str(messages[-1].get("content", "")))
            return str(response.get("content") or "").strip() or None
    except Exception as exc:
        logger.warning("Qwen provider request failed (%s): %s", type(exc).__name__, exc)
        return None


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
        
        # Check if user provided structured answers (custom CRM with explicit requirements)
        has_quest_answers = bool(body.quest_answers and any(body.quest_answers.values()))
        
        generation_prompt = ""
        if body.crm_type and body.crm_type != "custom":
            generation_prompt = f"Build a {body.crm_type} CRM."
        elif has_quest_answers:
            # For custom CRM with structured answers, create a prompt from answers
            parts = []
            if body.quest_answers.get("tracks"):
                parts.append(f"Track: {body.quest_answers['tracks']}")
            if body.quest_answers.get("pipeline_stages"):
                parts.append(f"Stages: {body.quest_answers['pipeline_stages']}")
            if body.quest_answers.get("key_fields"):
                parts.append(f"Fields: {body.quest_answers['key_fields']}")
            if body.quest_answers.get("team_size"):
                parts.append(f"Team: {body.quest_answers['team_size']}")
            generation_prompt = " ".join(parts)
        
        if generation_prompt:
            generation_prompt += "\n"
        generation_prompt += "Conversation (preserve the user's requested entities, fields, and stages):\n" + user_context
        
        provider = None
        config_dict: dict[str, Any] | None = None
        try:
            from app.services.ai_provider import get_ai_provider
            provider = get_ai_provider("local")
            if hasattr(provider, "generate_crm_config_async"):
                config_dict = await provider.generate_crm_config_async(generation_prompt)
            else:
                config_dict = await asyncio.to_thread(provider.generate_crm_config, generation_prompt)
            config_dict = CRMConfiguration(**config_dict).model_dump()
            warnings = []  # No warnings for successful generation
        except ValueError as exc:
            return _chat_error_response(502, "GENERATION_ERROR", str(exc), ai_used=True)
        except Exception as exc:
            logger.exception("CRM generation failed")
            return _chat_error_response(502, "GENERATION_ERROR", 
                                       "CRM generation failed. Please check your Ollama connection and try again.", 
                                       ai_used=True)

        return _chat_reply_response({
            "configuration": config_dict,
            "warnings": warnings,
            "ready_to_generate": False,
            "ai": {"provider": "ollama/qwen", "model": "qwen2.5:3b", "used": True, "fallback": False},
            "routing": {"route": "qwen_generation", "intent": "generate_crm", "requires_llm": True,
                        "laya_mode": "validation_only", "laya_model_loaded": False},
        }, "llm")

    # ── Branch: continue the conversation ───────────────────────────
    # Safety check on latest user message
    latest_user = next(
        (m.content for m in reversed(body.messages) if m.role == "user"), ""
    )
    try:
        LayaSystem1.validate_prompt_safety(latest_user)
    except ValueError as exc:
        return _chat_error_response(502, "GENERATION_ERROR", str(exc))

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

    try:
        raw_reply = _call_groq_builder(messages_dicts, system)
        if not raw_reply:
            return _chat_error_response(502, "GENERATION_ERROR", 
                                       "CRM interviewer is currently unavailable. Please try again.")
        
        # Parse JSON response from Qwen
        parsed = LayaSystem1.extract_json_payload(raw_reply)
        clean_reply = str(parsed.get("reply", "")).strip()
        ready = parsed.get("ready_to_generate", False) is True
        if not clean_reply or len(clean_reply) > 1200:
            raise ValueError("AI returned invalid reply format")
            
    except Exception as exc:
        logger.warning("CRM interviewer response parsing failed: %s", exc)
        return _chat_error_response(502, "GENERATION_ERROR", 
                                   "Could not parse AI response. Your conversation has been preserved. Please try again.")

    return _chat_reply_response({
        "reply": clean_reply,
        "ready_to_generate": ready,
        "ai": {"provider": "ollama/qwen", "model": "qwen2.5:3b", "used": True, "fallback": False},
        "routing": {"route": "qwen_generation", "intent": "crm_interview", "requires_llm": True,
                    "laya_mode": "validation_only", "laya_model_loaded": False},
    }, "llm")
