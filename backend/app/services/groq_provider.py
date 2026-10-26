"""Groq System-2 provider. API credentials are read only from backend settings."""
from __future__ import annotations

import json
from typing import Any

from app.config import Settings, get_settings


class GroqUnavailable(RuntimeError):
    """Groq is not configured or could not complete a request."""


def groq_status(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    if not settings.groq_api_key:
        return {"available": False, "model": settings.groq_model, "status": "missing_api_key"}
    try:
        import groq  # noqa: F401
    except ImportError:
        return {"available": False, "model": settings.groq_model, "status": "error"}
    try:
        from groq import Groq
        Groq(api_key=settings.groq_api_key, max_retries=0, timeout=5.0).models.list()
    except Exception as exc:
        state = "unreachable" if type(exc).__name__ in {"APIConnectionError", "APITimeoutError", "TimeoutError"} else "error"
        return {"available": False, "model": settings.groq_model, "status": state}
    return {"available": True, "model": settings.groq_model, "status": "ready"}


class GroqProvider:
    """Small provider wrapper shared by Copilot and CRM Builder."""

    def __init__(self, settings: Settings | None = None, client: Any | None = None):
        self.settings = settings or get_settings()
        self.client = client
        self.last_used = False

    def _client(self):
        if self.client is None:
            if not self.settings.groq_api_key:
                raise GroqUnavailable("Groq API key is not configured.")
            try:
                from groq import Groq
            except ImportError as exc:
                raise GroqUnavailable("Groq SDK is not installed.") from exc
            self.client = Groq(api_key=self.settings.groq_api_key)
        return self.client

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 768,
    ) -> dict[str, Any]:
        """Return OpenAI-compatible assistant message plus provider metadata."""
        compatible_messages = []
        for original in messages:
            item = dict(original)
            item.pop("tool_name", None)
            compatible_messages.append(item)
        params: dict[str, Any] = {
            "model": self.settings.groq_model,
            "messages": compatible_messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"
        try:
            completion = self._client().chat.completions.create(**params)
            self.last_used = True
            choice = completion.choices[0]
            message = choice.message
            tool_calls = []
            for call in getattr(message, "tool_calls", None) or []:
                fn = call.function
                tool_calls.append({
                    "id": call.id,
                    "type": "function",
                    "function": {"name": fn.name, "arguments": fn.arguments},
                })
            return {
                "content": message.content or "",
                "tool_calls": tool_calls,
                "provider": "groq",
                "model": self.settings.groq_model,
                "used": True,
            }
        except GroqUnavailable:
            raise
        except Exception as exc:
            # Keep upstream error bodies and request data out of API responses/logs.
            raise GroqUnavailable(f"Groq request failed ({type(exc).__name__}).") from exc

    def generate_json(self, system: str, prompt: str, *, max_tokens: int = 4096) -> dict[str, Any]:
        result = self.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=max_tokens,
        )
        content = str(result["content"]).strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].removesuffix("```").strip()
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise GroqUnavailable("Groq returned invalid JSON.") from exc
        if not isinstance(parsed, dict):
            raise GroqUnavailable("Groq returned an invalid JSON object.")
        return parsed


class GroqAIProvider(GroqProvider):
    """CRM generation/evolution adapter for the existing provider interface."""

    def generate_crm_config(self, prompt: str) -> dict[str, Any]:
        from app.services.laya_system1 import LayaSystem1
        from app.schemas.crm import CRMConfiguration

        raw = self.generate_json(
            "Generate a valid CRM configuration JSON object only. Use schema_version, name, industry, entities with fields, and pipeline_stages. Never emit SQL or code.",
            prompt,
        )
        repaired = LayaSystem1.repair_crm_configuration(raw, prompt)
        return CRMConfiguration(**repaired).model_dump()

    async def generate_crm_config_async(self, prompt: str) -> dict[str, Any]:
        import asyncio
        return await asyncio.to_thread(self.generate_crm_config, prompt)

    def generate_evolution_proposal(
        self, prompt: str, crm_config: dict[str, Any], analytics: dict[str, Any]
    ) -> dict[str, Any]:
        return self.generate_json(
            "Return one JSON object with summary and proposed_change. Use only allowlisted workflow change types and cite evidence from supplied analytics. Do not invent metrics.",
            json.dumps({"objective": prompt, "crm": crm_config, "analytics": analytics}),
        )
