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
import re
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
        """Generate a universal CRM configuration dynamically from prompt keywords, entities, and fields."""
        from app.services.field_extractor import FieldExtractor
        lower = prompt.lower()

        # Extract explicitly requested fields & stages
        extracted_fields = FieldExtractor.extract_fields_from_prompt(prompt)
        extracted_stages = FieldExtractor.extract_pipeline_stages(prompt)

        # Detect industry
        industry = "general"
        for ind in ["ecommerce", "e-commerce", "support", "customer_support", "recruitment", "hiring", "export",
                    "real_estate", "real estate", "saas", "healthcare", "education", "consulting", "logistics"]:
            if ind.replace("_", " ") in lower or ind in lower:
                industry = ind.replace(" ", "_").replace("-", "")
                break

        # Detect clean title
        title_match = re.search(r"(?:build|create)\s+(?:a\s+|an\s+)?([A-Za-z0-9_\-\s]+?)\s+(?:crm|with|to)", prompt, re.IGNORECASE)
        if title_match:
            raw_title = title_match.group(1).strip()
            name = f"{raw_title.title()} CRM" if not raw_title.lower().endswith("crm") else raw_title.title()
        else:
            name = f"{industry.replace('_', ' ').title()} CRM"

        # Detect primary entity name and label from prompt
        entity_name = "record"
        entity_label = "Record"
        known_entities = [
            ("customer", "Customer"),
            ("client", "Client"),
            ("candidate", "Candidate"),
            ("ticket", "Ticket"),
            ("issue", "Issue"),
            ("shipment", "Shipment"),
            ("order", "Order"),
            ("patient", "Patient"),
            ("property", "Property"),
            ("student", "Student"),
            ("employee", "Employee"),
            ("project", "Project"),
            ("vendor", "Vendor"),
            ("invoice", "Invoice"),
            ("booking", "Booking"),
            ("lead", "Lead"),
        ]
        for ent_key, ent_lbl in known_entities:
            if re.search(rf"\b{ent_key}s?\b", lower):
                entity_name = ent_key
                entity_label = ent_lbl
                break

        # Pipeline stages: use extracted stages, or appropriate defaults
        if extracted_stages:
            stages = extracted_stages
        elif "ecommerce" in industry or "ecommerce" in lower:
            stages = ["New", "Analyzing", "High Value", "At Risk", "Retained/Lost"]
        elif "support" in industry or "ticket" in lower:
            stages = ["Open", "Assigned", "In Progress", "Waiting", "Resolved", "Closed"]
        elif "recruitment" in industry or "candidate" in lower:
            stages = ["Applied", "Screening", "Interview", "Selected", "Hired", "Rejected"]
        elif "export" in industry or "shipment" in lower:
            stages = ["New Lead", "Contacted", "Quotation", "Order Confirmed", "Shipped", "Completed"]
        else:
            stages = ["New", "In Progress", "Completed"]

        # Build fields
        fields: list[dict[str, Any]] = []
        if extracted_fields:
            for ef in extracted_fields:
                ftype = ef.inferred_type
                fdict: dict[str, Any] = {
                    "name": ef.machine_key,
                    "label": ef.label,
                    "type": ftype,
                    "required": ef.required,
                }
                if ftype == "select":
                    if any(w in ef.machine_key for w in ["status", "stage"]):
                        fdict["options"] = list(stages)
                    elif "priority" in ef.machine_key:
                        fdict["options"] = ["Low", "Medium", "High", "Critical"]
                    elif "source" in ef.machine_key:
                        fdict["options"] = ["Website", "Referral", "Partner", "Direct"]
                    elif "segment" in ef.machine_key:
                        fdict["options"] = ["Standard", "Premium", "Enterprise"]
                    else:
                        fdict["options"] = ["Option 1", "Option 2", "Option 3"]
                fields.append(fdict)
        else:
            # Fallback fields based on entity
            fields = [
                {"name": f"{entity_name}_name", "label": f"{entity_label} Name", "type": "text", "required": True},
                {"name": "status", "label": f"{entity_label} Status", "type": "select", "required": True, "options": stages},
            ]

        # Ensure a status field exists and has the pipeline stages as options
        has_status = any(f.get("name") in ("status", "stage", f"{entity_name}_status", "shipping_status") or f.get("type") in ("status", "select") and "status" in f.get("name", "") for f in fields)
        if not has_status:
            fields.append({
                "name": "status",
                "label": "Status",
                "type": "select",
                "required": True,
                "options": stages,
            })

        entities = [
            {
                "name": entity_name,
                "label": entity_label,
                "fields": fields,
            }
        ]

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
