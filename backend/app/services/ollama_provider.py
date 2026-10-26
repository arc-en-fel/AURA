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
    """Local Ollama AI Provider utilizing Qwen3-4B / local LLM."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:3b",
        timeout: float = 120.0,
        enable_fallback: bool = True,
        decision_engine: LayaDecisionEngine | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model or "qwen2.5:3b"
        self.timeout = timeout
        self.enable_fallback = enable_fallback
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
            "Constraints:\n"
            "- Entity names and field names must be lowercase letters and underscores only.\n"
            "- Field types must be one of: text, textarea, email, number, date, boolean, select, phone.\n"
            "- Select fields must have a non-empty list of unique string options.\n"
            "- Output valid JSON only, no explanatory markdown."
            + decision_context
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
        """Generate a validated CRM configuration using Qwen3-4B and Laya System 1 (sync)."""
        LayaSystem1.validate_prompt_safety(prompt)
        decision = self.decision_engine.decide_generation(prompt) if self.decision_engine else None
        decision_prompt = f"{prompt}\nSystem 1 classified industry: {decision.industry}." if decision else prompt
        system_prompt = self._get_system_prompt(decision)
        raw_response = self._call_ollama_generate(system_prompt, decision_prompt)

        if raw_response:
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
                    logger.warning("Failed to parse or repair Ollama output: %s", exc)

        # Resilient fallback to Laya System 1 deterministic scaffolding
        if self.enable_fallback:
            self.last_warnings = [
                "AI provider fallback: Generated via AURA's deterministic scaffold after the System 1 decision; "
                "Ollama was unavailable or returned unusable output."
            ]
            return self._apply_generation_decision(
                LayaSystem1.generate_scaffold_config(decision_prompt), decision
            )

        raise ValueError("Ollama AI provider failed to generate a valid CRM configuration.")

    async def generate_crm_config_async(self, prompt: str) -> dict[str, Any]:
        """Generate a validated CRM configuration using Qwen3-4B and Laya System 1 (async)."""
        LayaSystem1.validate_prompt_safety(prompt)
        decision = await asyncio.to_thread(self.decision_engine.decide_generation, prompt) if self.decision_engine else None
        decision_prompt = f"{prompt}\nSystem 1 classified industry: {decision.industry}." if decision else prompt
        system_prompt = self._get_system_prompt(decision)
        raw_response = await self._call_ollama_generate_async(system_prompt, decision_prompt)

        if raw_response:
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
                    logger.warning("Failed to parse or repair Ollama output: %s", exc)

        # Resilient fallback to Laya System 1 deterministic scaffolding
        if self.enable_fallback:
            self.last_warnings = [
                "AI provider fallback: Generated via AURA's deterministic scaffold after the System 1 decision; "
                "Ollama was unavailable or returned unusable output."
            ]
            return self._apply_generation_decision(
                LayaSystem1.generate_scaffold_config(decision_prompt), decision
            )

        raise ValueError("Ollama AI provider failed to generate a valid CRM configuration.")

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
