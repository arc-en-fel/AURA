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
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth import CurrentUser
from app.config import get_settings, Settings
from app.routers.responses import success_response, error_response
from app.schemas.crm import CRMConfiguration
from app.services.laya_system1 import LayaSystem1

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crm/chat", tags=["CRM Chat"])


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

_CONSULTANT_SYSTEM = """\
You are AURA, an expert CRM architect. Your job is to gather information about a user's business \
through friendly, focused conversation before designing their CRM.

Rules:
- Ask ONE short question per turn. Never ask multiple questions at once.
- Keep your ENTIRE reply under 60 words. Output ONLY the question — no preamble, no explanation.
- Do NOT think out loud. Do NOT explain your reasoning. Just ask the next question.
- After 4-5 exchanges you have enough information. When you have enough context, \
end your reply with exactly: [READY_TO_GENERATE]
- Never generate JSON or a CRM config yourself. Only ask questions.
- Focus on: business type, what they track, team size, key pipeline stages, must-have fields.

Example good responses (output exactly like these):
- "What kind of business is this CRM for — real estate, healthcare, sales, or something else?"
- "What are the main things you need to track — leads, clients, deals, appointments?"
- "How many stages does your typical sales process have?"
- "What's the most important field you need on each record?"
"""

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


# ── Ollama helpers ──────────────────────────────────────────────────

def _call_ollama_chat(messages: list[dict], system: str, timeout: float = 120.0) -> str | None:
    """Call Ollama with a multi-turn conversation. Returns the assistant reply text."""
    import httpx
    import re

    # Build the prompt from message history in Qwen3 chat format
    prompt = f"<|im_start|>system\n{system}<|im_end|>\n"
    for m in messages:
        role = m["role"]
        content = m["content"]
        prompt += f"<|im_start|>{role}\n{content}<|im_end|>\n"
    prompt += "<|im_start|>assistant\n"

    payload: dict[str, Any] = {
        "model": "qwen3:4b",
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {"temperature": 0.4, "top_p": 0.9},
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post("http://localhost:11434/api/generate", json=payload)
            if resp.status_code == 200:
                raw = resp.json().get("response", "").strip()
                # Qwen3 sometimes emits thinking in the response field even with
                # think=False. Extract only the content AFTER </think> if present.
                if "</think>" in raw:
                    raw = raw.split("</think>")[-1].strip()
                # Strip any remaining full <think>...</think> blocks
                raw = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.IGNORECASE).strip()
                return raw if raw else None
            logger.warning("Ollama chat returned status %d", resp.status_code)
    except Exception as exc:
        logger.info("Ollama chat call failed: %s", exc)

    return None


def _call_ollama_generate(messages: list[dict], timeout: float = 120.0, crm_type: str | None = None) -> str | None:
    """Call Ollama to generate a CRM JSON from the conversation. Returns raw text."""
    import httpx

    # Summarise the conversation as context for the generator
    convo_text = "\n".join(
        f"{'User' if m['role'] == 'user' else 'AURA'}: {m['content']}"
        for m in messages
    )

    crm_type_hint = f"\nThe user has confirmed this is a '{crm_type}' CRM.\n" if crm_type else ""

    prompt = (
        f"<|im_start|>system\n{_GENERATOR_SYSTEM}<|im_end|>\n"
        f"<|im_start|>user\n"
        f"Based on this conversation, generate the CRM JSON:{crm_type_hint}\n\n{convo_text}"
        f"<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )

    payload: dict[str, Any] = {
        "model": "qwen3:4b",
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "think": False,
        "options": {"temperature": 0.2, "top_p": 0.9},
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post("http://localhost:11434/api/generate", json=payload)
            if resp.status_code == 200:
                return resp.json().get("response", "").strip()
            logger.warning("Ollama generate returned status %d", resp.status_code)
    except Exception as exc:
        logger.info("Ollama generate call failed: %s", exc)

    return None


def _fallback_reply(messages: list[ChatMessage]) -> tuple[str, bool]:
    """Deterministic fallback when Ollama is unavailable during conversation."""
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
    """Build a scaffold CRM from the conversation when Ollama is unavailable."""
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
    messages_dicts = [{"role": m.role, "content": m.content} for m in body.messages]

    # ── Branch: generate the CRM from the full conversation ─────────
    if body.generate_now:
        warnings: list[str] = []

        raw = _call_ollama_generate(messages_dicts, crm_type=body.crm_type)
        config_dict: dict[str, Any] | None = None

        if raw:
            try:
                parsed = LayaSystem1.extract_json_payload(raw)
                # Use the conversation as the repair prompt
                user_context = " ".join(m.content for m in body.messages if m.role == "user")
                repaired = LayaSystem1.repair_crm_configuration(parsed, user_context)
                CRMConfiguration(**repaired)  # validate
                config_dict = repaired
            except Exception as exc:
                logger.warning("Failed to parse chat-generated CRM: %s", exc)

        if not config_dict:
            warnings = [
                "AI provider fallback: CRM generated via AURA's deterministic scaffold "
                "after Ollama was unavailable or returned unusable output."
            ]
            config_dict = _fallback_generate(body.messages)

        return success_response({
            "configuration": config_dict,
            "warnings": warnings,
        })

    # ── Branch: continue the conversation ───────────────────────────
    # Safety check on latest user message
    latest_user = next(
        (m.content for m in reversed(body.messages) if m.role == "user"), ""
    )
    try:
        LayaSystem1.validate_prompt_safety(latest_user)
    except ValueError as exc:
        return error_response(502, "AI_PROVIDER_ERROR", str(exc))

    # Enrich the system prompt with the CRM type chip selection when provided
    system = _CONSULTANT_SYSTEM
    if body.crm_type:
        system = (
            f"The user has already indicated they want to build a '{body.crm_type}' CRM. "
            f"Use this as confirmed context — do not ask about CRM type again.\n\n"
            + _CONSULTANT_SYSTEM
        )

    reply = _call_ollama_chat(messages_dicts, system)
    fallback_used = reply is None

    if fallback_used:
        reply, _ = _fallback_reply(body.messages)

    ready = "[READY_TO_GENERATE]" in (reply or "")
    # Clean the marker from the visible reply
    clean_reply = (reply or "").replace("[READY_TO_GENERATE]", "").strip()
    if ready and not clean_reply:
        clean_reply = (
            "I have all the information I need to build your CRM! "
            "Click 'Generate My CRM' whenever you're ready."
        )

    return success_response({
        "reply": clean_reply,
        "ready_to_generate": ready,
        "fallback_used": fallback_used,
    })
