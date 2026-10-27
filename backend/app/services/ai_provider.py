"""AI generation service with provider interface.

Supports:
- mock: Deterministic provider for tests and local demos (no external deps).
- local: Local Ollama/HuggingFace model.
- grok: Grok API.

The mock provider generates a realistic CRM configuration from keywords
in the prompt. It is NOT a real LLM and is clearly labeled as such.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from app.schemas.crm import CRMConfiguration, CRMField, CRMEntity


class AIProvider(ABC):
    """Abstract AI provider interface."""

    @abstractmethod
    def generate_crm_config(self, prompt: str) -> dict[str, Any]:
        """Generate a CRM configuration dict from a natural-language prompt."""
        ...

    @abstractmethod
    def generate_evolution_proposal(
        self, prompt: str, crm_config: dict[str, Any], analytics: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate an evolution proposal based on CRM state and analytics."""
        ...


class MockAIProvider(AIProvider):
    """Deterministic mock provider for tests and local demos.

    This is NOT a real LLM. It generates configurations from keyword matching
    in the prompt. Clearly labeled as mock-generated in all output.
    """

    def generate_crm_config(self, prompt: str) -> dict[str, Any]:
        """Generate a mock CRM configuration from prompt keywords."""
        lower = prompt.lower()

        # Detect industry from prompt
        industry = "general"
        for ind in ["real_estate", "real estate", "saas", "ecommerce", "e-commerce",
                     "healthcare", "education", "consulting", "restaurant", "fitness"]:
            if ind.replace("_", " ") in lower or ind in lower:
                industry = ind.replace(" ", "_").replace("-", "")
                break

        # Detect name hints
        name = f"{industry.replace('_', ' ').title()} CRM"

        # Build entities based on detected keywords
        entities = []

        # Always include a lead entity
        lead_fields = [
            {"name": "full_name", "label": "Full Name", "type": "text", "required": True},
            {"name": "email", "label": "Email", "type": "email", "required": False},
            {"name": "phone", "label": "Phone", "type": "phone", "required": False},
            {"name": "company", "label": "Company", "type": "text", "required": False},
            {
                "name": "lead_source",
                "label": "Lead Source",
                "type": "select",
                "required": True,
                "options": ["Website", "Referral", "Social Media", "Cold Call", "Other"],
            },
            {
                "name": "status",
                "label": "Status",
                "type": "select",
                "required": True,
                "options": ["New", "Contacted", "Qualified", "Proposal", "Won", "Lost"],
            },
        ]
        entities.append({"name": "lead", "label": "Lead", "fields": lead_fields})

        # Add contact if mentioned
        if "contact" in lower:
            entities.append({
                "name": "contact",
                "label": "Contact",
                "fields": [
                    {"name": "full_name", "label": "Full Name", "type": "text", "required": True},
                    {"name": "email", "label": "Email", "type": "email", "required": True},
                    {"name": "phone", "label": "Phone", "type": "phone", "required": False},
                    {"name": "organization", "label": "Organization", "type": "text", "required": False},
                ],
            })

        # Add deal/opportunity if mentioned
        if any(word in lower for word in ["deal", "opportunity", "sale"]):
            entities.append({
                "name": "deal",
                "label": "Deal",
                "fields": [
                    {"name": "title", "label": "Deal Title", "type": "text", "required": True},
                    {"name": "value", "label": "Value", "type": "number", "required": False},
                    {"name": "close_date", "label": "Close Date", "type": "date", "required": False},
                    {
                        "name": "stage",
                        "label": "Stage",
                        "type": "select",
                        "required": True,
                        "options": ["Prospecting", "Negotiation", "Closed Won", "Closed Lost"],
                    },
                ],
            })

        # Add task if mentioned
        if "task" in lower:
            entities.append({
                "name": "task",
                "label": "Task",
                "fields": [
                    {"name": "title", "label": "Title", "type": "text", "required": True},
                    {"name": "description", "label": "Description", "type": "textarea", "required": False},
                    {"name": "due_date", "label": "Due Date", "type": "date", "required": False},
                    {"name": "completed", "label": "Completed", "type": "boolean", "required": False},
                ],
            })

        # Build pipeline stages from lead status options
        stages = ["New", "Contacted", "Qualified", "Proposal", "Won", "Lost"]

        config = {
            "schema_version": "1.0",
            "name": name,
            "industry": industry,
            "entities": entities,
            "pipeline_stages": stages,
        }

        # Validate with Pydantic before returning
        CRMConfiguration(**config)

        return config

    def generate_evolution_proposal(
        self, prompt: str, crm_config: dict[str, Any], analytics: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate a deterministic mock evolution proposal.

        This mock provider generates proposals based on the objective keyword.
        All proposals are clearly labeled as mock-generated.
        """
        objective = prompt.lower()

        if "follow_up" in objective or "improve_follow_up" in objective:
            return {
                "summary": "[Mock] Reduce follow-up delay to improve response time.",
                "proposed_change": {
                    "type": "workflow.create",
                    "name": "Quick follow-up after new lead",
                    "trigger": {"type": "record.created", "entity": "lead"},
                    "actions": [{"type": "create_follow_up_task", "delay_hours": 4}],
                },
                "evidence": [
                    {"type": "mock_metric", "description": "Mock: Average follow-up time exceeds 24h."}
                ],
            }
        elif "conversion" in objective or "improve_conversion" in objective:
            return {
                "summary": "[Mock] Add notification on stage change to improve conversion tracking.",
                "proposed_change": {
                    "type": "workflow.create",
                    "name": "Notify on qualification",
                    "trigger": {"type": "record.stage_changed", "entity": "lead"},
                    "actions": [{"type": "notify_owner"}],
                },
                "evidence": [
                    {"type": "mock_metric", "description": "Mock: Conversion rate below target."}
                ],
            }
        else:  # reduce_manual_work or default
            return {
                "summary": "[Mock] Automate email on record update to reduce manual work.",
                "proposed_change": {
                    "type": "workflow.create",
                    "name": "Auto-email on update",
                    "trigger": {"type": "record.updated", "entity": "lead"},
                    "actions": [{"type": "send_email"}],
                },
                "evidence": [
                    {"type": "mock_metric", "description": "Mock: Manual email tasks detected."}
                ],
            }


def get_ai_provider(provider_name: str = "groq") -> AIProvider:
    """Factory function to get the configured AI provider."""
    normalized = (provider_name or "groq").lower().strip()
    if normalized == "mock":
        return MockAIProvider()
    if normalized == "groq":
        from app.services.groq_provider import GroqAIProvider
        return GroqAIProvider()
    if normalized in ("local", "ollama"):
        from app.config import get_settings
        from app.services.laya_runtime import LayaDecisionEngine
        from app.services.ollama_provider import OllamaAIProvider

        settings = get_settings()
        return OllamaAIProvider(
            base_url=settings.local_llm_base_url,
            model=settings.local_llm_model,
            decision_engine=LayaDecisionEngine(),
        )
    raise ValueError(f"Unsupported AI provider: {provider_name}. Use 'groq', 'local', or explicit test-only 'mock'.")
