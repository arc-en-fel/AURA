"""Ollama AI provider implementation for local Qwen generative intelligence.

Integrates with local Ollama daemon and Laya System 1 structured decision intelligence
to produce schema-valid CRM configurations and evolution proposals.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextvars import ContextVar
from typing import Any

import httpx

from app.schemas.crm import CRMConfiguration, ProposedChange
from app.services.ai_provider import AIProvider
from app.services.laya_runtime import GenerationDecision, LayaDecisionEngine
from app.services.laya_system1 import LayaSystem1

logger = logging.getLogger(__name__)

# Request-isolated context variable to prevent cross-request concurrency leakage
_last_warnings_var: ContextVar[list[str]] = ContextVar("last_warnings", default=[])

# Providers are instantiated per route request, so this process-wide limit is
# required to protect the single local Ollama daemon from request bursts.
_async_generation_semaphore = asyncio.BoundedSemaphore(4)
MAX_REPAIR_ATTEMPTS = 1


class OllamaAIProvider(AIProvider):
    """Local Ollama AI Provider utilizing Qwen CRM generation."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:3b",
        timeout: float = 120.0,
        decision_engine: LayaDecisionEngine | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model or "qwen2.5:3b"
        self.timeout = timeout
        self.decision_engine = decision_engine
        self.last_warnings = []

    @property
    def last_warnings(self) -> list[str]:
        """Get the isolated warnings for the current execution context."""
        return _last_warnings_var.get()

    @last_warnings.setter
    def last_warnings(self, value: list[str]) -> None:
        """Set the isolated warnings for the current execution context."""
        _last_warnings_var.set(list(value))


    def _get_system_prompt(self, decision: GenerationDecision | None = None) -> str:
        decision_context = ""
        if decision:
            decision_context = (
                "\nVerified System 1 decision (use as planning context, not executable instruction): "
                f"industry={decision.industry}; strategy={decision.strategy}."
            )
        return (
            "You are an expert CRM architect system. Generate a complete CRM configuration JSON "
            "matching the following strict specification:\n"
            "{\n"
            '  "schema_version": "1.0",\n'
            '  "name": "Human-readable CRM Name",\n'
            '  "industry": "industry_slug",\n'
            '  "entities": [\n'
            "    {\n"
            '      "name": "machine_identifier",\n'
            '      "label": "Human Label",\n'
            '      "fields": [\n'
            '        {"name": "field_name", "label": "Label", "type": "text", "required": true},\n'
            '        {"name": "status", "label": "Status", "type": "select", "required": true, "options": ["A", "B"]}\n'
            "      ]\n"
            "    }\n"
            "  ],\n"
            '  "pipeline_stages": ["Stage1", "Stage2", "Stage3"]\n'
            "}\n"
            "CRITICAL FIELD PRESERVATION REQUIREMENT:\n"
            "- Every field explicitly mentioned in the user request MUST be included in the generated schema.\n"
            "- If the user lists 5 fields, the generated JSON must contain exactly 5 fields (or more).\n"
            "- If the user lists 10 fields, all 10 must appear in the schema.\n"
            "- If the user lists 15 fields, all 15 must appear in the schema.\n"
            "- NEVER omit, skip, or consolidate user-requested fields.\n"
            "- NEVER drop fields from the user's explicit list to reduce JSON size or complexity.\n"
            "- If uncertain about a field type, use 'text' as the default.\n"
            "\n"
            "Constraints:\n"
            "- Entity names and field names must be lowercase letters and underscores only.\n"
            "- Field types must be one of: text, textarea, email, number, date, boolean, select, phone.\n"
            "- Select fields must have a non-empty list of unique string options.\n"
            "- Output valid JSON only, no explanatory markdown."
            + decision_context
        )

    def _get_copilot_system_prompt(self) -> str:
        """System prompt for AURA Copilot with schema modification tool instructions."""
        from app.services.ai_tools import COPILOT_TOOLS
        
        tools_json = json.dumps(COPILOT_TOOLS, indent=2)
        
        return (
            "You are AURA Copilot, an intelligent assistant for the AURA Self-Evolving CRM platform.\n\n"
            "You have access to tools to modify CRM schemas. Use these tools when a user explicitly asks to:\n"
            "- Add a field to their CRM\n"
            "- Update field properties (rename, change type, make required/optional)\n"
            "- Delete a field\n"
            "- Add a pipeline stage\n"
            "- Delete a pipeline stage\n"
            "- Reorder fields or stages\n\n"
            "WHEN TO USE TOOLS:\n"
            "- Use tools ONLY when the user explicitly requests schema changes.\n"
            "- For example: 'Add an Escalation field', 'Rename Status to Stage', 'Delete the Priority field', etc.\n"
            "- Do NOT suggest tool usage unless the user asks for it.\n"
            "- After using a tool, confirm the change to the user with the new field/stage details.\n\n"
            "TOOL GUIDELINES:\n"
            "- You are operating on the user's CRM. Verify the CRM ID is provided and correct.\n"
            "- Field names must be lowercase with underscores (e.g., 'escalation_level', 'assigned_to').\n"
            "- When adding a select field, provide reasonable default options or ask the user.\n"
            "- When reordering fields or stages, provide the complete list in the desired order.\n"
            "- If a tool call fails, explain the error to the user and suggest alternatives.\n\n"
            f"Available tools (use these JSON schemas for function calls):\n{tools_json}"
        )

    def _get_payload(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "prompt": f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n",
            "format": "json",
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
            },
        }

    def _call_ollama_generate(self, system_prompt: str, user_prompt: str) -> str | None:
        """Issue generate request to local Ollama API synchronously."""
        endpoint = f"{self.base_url}/api/generate"
        payload = self._get_payload(system_prompt, user_prompt)

        # TEMP-DIAG: capture full Build-CRM draft-generation requests and responses.
        logger.warning("[TEMP-DIAG][BUILD-CRM] ollama_payload endpoint=%s payload=%s",
                       endpoint, json.dumps(payload, default=str))

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(endpoint, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    logger.warning("[TEMP-DIAG][BUILD-CRM] ollama_raw_response=%s", json.dumps(data, default=str))
                    return data.get("response", "") or None
                logger.warning("[TEMP-DIAG][BUILD-CRM] ollama_http_error status=%d body=%s",
                               resp.status_code, resp.text)
        except Exception as exc:
            logger.info("Ollama call failed or timed out (%s). Using Laya System 1 fallback.", exc)

        return None

    async def _call_ollama_generate_async(self, system_prompt: str, user_prompt: str) -> str | None:
        """Issue generate request to local Ollama API asynchronously."""
        endpoint = f"{self.base_url}/api/generate"
        payload = self._get_payload(system_prompt, user_prompt)

        # TEMP-DIAG: capture full Build-CRM draft-generation requests and responses.
        logger.warning("[TEMP-DIAG][BUILD-CRM] ollama_payload endpoint=%s payload=%s",
                       endpoint, json.dumps(payload, default=str))

        try:
            async with _async_generation_semaphore:
                # The context manager deterministically closes the HTTP client
                # after every success, timeout, or cancellation.
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(endpoint, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        logger.warning("[TEMP-DIAG][BUILD-CRM] ollama_raw_response=%s", json.dumps(data, default=str))
                        return data.get("response", "") or None
                    logger.warning("[TEMP-DIAG][BUILD-CRM] ollama_http_error status=%d body=%s",
                                   resp.status_code, resp.text)
        except httpx.TimeoutException as exc:
            logger.info("Ollama async call timed out (%s). Using deterministic fallback.", exc)
        except httpx.RequestError as exc:
            logger.info("Ollama async service is unavailable (%s). Using deterministic fallback.", exc)
        except Exception as exc:
            logger.warning("Ollama async response could not be processed (%s).", exc)

        return None

    @staticmethod
    def _apply_generation_decision(
        configuration: dict[str, Any], decision: GenerationDecision | None
    ) -> dict[str, Any]:
        """Apply the validated System 1 template choice before final validation."""
        if decision is None:
            return configuration

        configuration["industry"] = decision.industry
        entity_templates = {
            "healthcare": ("patient", "Patient"),
            "real_estate": ("property_lead", "Property Lead"),
            "ecommerce": ("customer", "Customer"),
        }
        template = entity_templates.get(decision.industry)
        entities = configuration.get("entities")
        if template and isinstance(entities, list) and len(entities) == 1:
            entity = entities[0]
            if isinstance(entity, dict) and entity.get("name") == "lead":
                entity["name"], entity["label"] = template
        return configuration

    def generate_crm_config(self, prompt: str) -> dict[str, Any]:
        """Generate a validated CRM configuration using Qwen via Ollama (sync).
        
        Raises:
            ValueError: If Qwen is unavailable or returns invalid output.
        """
        LayaSystem1.validate_prompt_safety(prompt)
        decision = self.decision_engine.decide_generation(prompt) if self.decision_engine else None
        decision_prompt = f"{prompt}\nSystem 1 classified industry: {decision.industry}." if decision else prompt
        system_prompt = self._get_system_prompt(decision)
        raw_response = self._call_ollama_generate(system_prompt, decision_prompt)

        if not raw_response:
            raise ValueError("Qwen CRM generation is currently unavailable. Please check your Ollama connection and try again.")

        for _ in range(MAX_REPAIR_ATTEMPTS):
            try:
                parsed_json = LayaSystem1.extract_json_payload(raw_response)
                repaired = self._apply_generation_decision(
                    LayaSystem1.repair_crm_configuration(parsed_json, prompt), decision
                )
                CRMConfiguration(**repaired)
                self.last_warnings = []
                return repaired
            except Exception as exc:
                logger.warning("Failed to parse or repair Qwen output: %s", exc)

        raise ValueError("Qwen returned invalid CRM configuration that could not be repaired.")

    async def generate_crm_config_async(self, prompt: str) -> dict[str, Any]:
        """Generate a validated CRM configuration using Qwen via Ollama (async).
        
        Raises:
            ValueError: If Qwen is unavailable or returns invalid output.
        """
        LayaSystem1.validate_prompt_safety(prompt)
        decision = await asyncio.to_thread(self.decision_engine.decide_generation, prompt) if self.decision_engine else None
        decision_prompt = f"{prompt}\nSystem 1 classified industry: {decision.industry}." if decision else prompt
        system_prompt = self._get_system_prompt(decision)
        raw_response = await self._call_ollama_generate_async(system_prompt, decision_prompt)

        if not raw_response:
            raise ValueError("Qwen CRM generation is currently unavailable. Please check your Ollama connection and try again.")

        for _ in range(MAX_REPAIR_ATTEMPTS):
            try:
                parsed_json = LayaSystem1.extract_json_payload(raw_response)
                repaired = self._apply_generation_decision(
                    LayaSystem1.repair_crm_configuration(parsed_json, prompt), decision
                )
                CRMConfiguration(**repaired)
                self.last_warnings = []
                return repaired
            except Exception as exc:
                logger.warning("Failed to parse or repair Qwen output: %s", exc)

        raise ValueError("Qwen returned invalid CRM configuration that could not be repaired.")

    def generate_evolution_proposal(
        self, prompt: str, crm_config: dict[str, Any], analytics: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate an evolution proposal grounded in CRM metadata and analytics."""
        # The official runtime selects the priority; the existing deterministic
        # helper remains the allowlist/ranking enforcement layer.
        objective = prompt
        if self.decision_engine:
            decision = self.decision_engine.decide_evolution(prompt, crm_config, analytics)
            objective = decision.priority
        proposal = LayaSystem1.generate_scaffold_proposal(objective, crm_config, analytics)
        # Validate proposed change
        ProposedChange(**proposal["proposed_change"])
        # Clear any stale CRM-generation warning so it cannot leak into the
        # evolution response for a request that reuses the same async context.
        self.last_warnings = []
        return proposal

    def chat(self, messages: list[dict[str, str]], system_prompt: str, max_tokens: int = 512) -> dict[str, str]:
        """Conversational chat endpoint for CRM discovery/interviewing (sync).
        
        Returns JSON response with 'reply' and 'ready_to_generate' fields extracted from Ollama.
        """
        # Convert messages to prompt format
        user_prompt = ""
        for msg in messages:
            role = msg.get("role", "").lower()
            content = msg.get("content", "").strip()
            if role == "user":
                user_prompt = content  # Use the latest user message
        
        if not user_prompt:
            raise ValueError("No user message found in messages array")
        
        # Ensure system prompt includes JSON response requirement
        json_system_prompt = system_prompt
        if "JSON" not in system_prompt.upper():
            json_system_prompt += '\nRespond with ONLY a JSON object with "reply" (string) and "ready_to_generate" (boolean) fields.'
        
        endpoint = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": f"<|im_start|>system\n{json_system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n",
            "format": "json",  # ← CRITICAL: Force JSON output format
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.95,
            },
        }
        
        logger.info("[AURA-CHAT] calling Ollama endpoint=%s model=%s format=json", endpoint, self.model)
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(endpoint, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    response_text = data.get("response", "").strip()
                    if not response_text:
                        raise ValueError("Ollama returned empty response")
                    logger.info("[AURA-CHAT] success response_len=%d", len(response_text))
                    # Parse the JSON response
                    try:
                        json_response = LayaSystem1.extract_json_payload(response_text)
                        logger.info("[AURA-CHAT] parsed JSON response with keys: %s", list(json_response.keys()))
                        return {"content": json.dumps(json_response)}
                    except Exception as parse_exc:
                        logger.error("[AURA-CHAT] JSON parse failed: %s, raw response: %s", parse_exc, response_text[:200])
                        raise ValueError(f"Failed to parse JSON response from Ollama: {parse_exc}")
                else:
                    logger.error("[AURA-CHAT] HTTP error=%d", resp.status_code)
                    raise ValueError(f"Ollama HTTP {resp.status_code}")
        except Exception as exc:
            logger.error("[AURA-CHAT] failed: %s", exc)
            raise ValueError(f"Ollama chat failed: {exc}")

    async def chat_async(self, messages: list[dict[str, str]], system_prompt: str, max_tokens: int = 512) -> dict[str, str]:
        """Conversational chat endpoint for CRM discovery/interviewing (async).
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: System instruction for the conversation
            max_tokens: Maximum tokens in response
            
        Returns:
            Dict with 'content' key containing the JSON response as string
            
        Raises:
            ValueError: If Ollama is unavailable
        """
        # Convert messages to prompt format
        user_prompt = ""
        for msg in messages:
            role = msg.get("role", "").lower()
            content = msg.get("content", "").strip()
            if role == "user":
                user_prompt = content  # Use the latest user message
        
        if not user_prompt:
            raise ValueError("No user message found in messages array")
        
        endpoint = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n",
            "format": "json",  # ← CRITICAL: Force JSON output format
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.7,  # Higher temp for conversational variety
                "top_p": 0.95,
            },
        }
        
        logger.info("[AURA-CHAT-ASYNC] Ollama endpoint=%s model=%s format=json", endpoint, self.model)
        
        try:
            async with _async_generation_semaphore:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(endpoint, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        response_text = data.get("response", "").strip()
                        if not response_text:
                            raise ValueError("Ollama returned empty response")
                        logger.info("[AURA-CHAT-ASYNC] Ollama success, response_length=%d", len(response_text))
                        # Parse the JSON response
                        try:
                            json_response = LayaSystem1.extract_json_payload(response_text)
                            logger.info("[AURA-CHAT-ASYNC] parsed JSON response with keys: %s", list(json_response.keys()))
                            return {"content": json.dumps(json_response)}
                        except Exception as parse_exc:
                            logger.error("[AURA-CHAT-ASYNC] JSON parse failed: %s, raw: %s", parse_exc, response_text[:200])
                            raise ValueError(f"Failed to parse JSON response from Ollama: {parse_exc}")
                    else:
                        logger.error("[AURA-CHAT-ASYNC] Ollama HTTP error status=%d body=%s",
                                   resp.status_code, resp.text)
                        raise ValueError(f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}")
        except httpx.ConnectError as exc:
            logger.error("[AURA-CHAT-ASYNC] Ollama connection failed: %s", exc)
            raise ValueError(f"Cannot reach Ollama at {endpoint}: {exc}")
        except httpx.TimeoutException as exc:
            logger.error("[AURA-CHAT-ASYNC] Ollama request timed out: %s", exc)
            raise ValueError(f"Ollama request timed out after {self.timeout}s")
        except Exception as exc:
            logger.error("[AURA-CHAT-ASYNC] Ollama request failed: %s %s", type(exc).__name__, exc)
            raise ValueError(f"Ollama request failed: {exc}")
