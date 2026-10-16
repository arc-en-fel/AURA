"""Adapter for the verified upstream Laya System 1 runtime.

This module intentionally does not substitute AURA's deterministic helper for
the upstream model. If the official runtime cannot load or returns an invalid
typed answer, callers receive ``LayaRuntimeError`` and can surface a controlled
provider error instead of silently claiming Laya-backed decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable


class LayaRuntimeError(RuntimeError):
    """Official Laya could not provide a valid structured decision."""


@dataclass(frozen=True)
class GenerationDecision:
    industry: str
    strategy: str
    model_id: str


@dataclass(frozen=True)
class EvolutionDecision:
    priority: str
    requires_human_review: bool
    model_id: str


class LayaDecisionEngine:
    """Lazy, process-local wrapper around ``laya.load(...).predict(...)``."""

    def __init__(
        self,
        model_id: str = "convaiinnovations/laya",
        loader: Callable[[str], Any] | None = None,
    ) -> None:
        self.model_id = model_id
        self._loader = loader
        self._agent: Any | None = None
        self._load_lock = Lock()

    def _get_agent(self) -> Any:
        if self._agent is not None:
            return self._agent
        with self._load_lock:
            if self._agent is not None:
                return self._agent
            try:
                if self._loader is None:
                    from laya import load

                    self._loader = load
                self._agent = self._loader(self.model_id)
                return self._agent
            except Exception as exc:
                raise LayaRuntimeError("Official Laya runtime could not be loaded.") from exc

    @staticmethod
    def _choice(result: dict[str, Any], question: str, allowed: set[str]) -> str:
        try:
            choice = result["answers"][question]["choice"]
        except (KeyError, TypeError) as exc:
            raise LayaRuntimeError(f"Laya did not return a choice for '{question}'.") from exc
        if not isinstance(choice, str) or choice not in allowed:
            raise LayaRuntimeError(f"Laya returned an unsupported choice for '{question}'.")
        return choice

    def decide_generation(self, prompt: str) -> GenerationDecision:
        questions = {
            "industry": {
                "type": "choice",
                "instructions": "Classify the requested CRM business domain.",
                "criteria": {
                    "saas": "software subscriptions, B2B products, demos, ARR",
                    "healthcare": "clinics, patients, doctors, appointments",
                    "real_estate": "property listings, buyers, viewings, sales",
                    "ecommerce": "stores, orders, customers, retail purchases",
                    "general": "a business not covered by the other categories",
                },
            },
            "strategy": {
                "type": "choice",
                "instructions": "Choose the safest CRM generation strategy.",
                "criteria": {
                    "sales_pipeline": "lead qualification and sales stages are central",
                    "case_management": "customer or patient cases and follow-up are central",
                    "transaction_tracking": "orders, listings, or transactions are central",
                },
            },
        }
        result = self._get_agent().predict({"business_description": prompt}, questions)
        if not isinstance(result, dict):
            raise LayaRuntimeError("Laya returned an invalid decision payload.")
        return GenerationDecision(
            industry=self._choice(result, "industry", {"saas", "healthcare", "real_estate", "ecommerce", "general"}),
            strategy=self._choice(result, "strategy", {"sales_pipeline", "case_management", "transaction_tracking"}),
            model_id=str(result.get("model") or self.model_id),
        )

    def decide_evolution(
        self, objective: str, crm_config: dict[str, Any], analytics: dict[str, Any]
    ) -> EvolutionDecision:
        questions = {
            "priority": {
                "type": "choice",
                "instructions": "Choose the safest workflow-improvement priority based on the objective and evidence.",
                "criteria": {
                    "improve_follow_up": "reduce response delays and create follow-up tasks",
                    "improve_conversion": "improve pipeline progression and owner alerts",
                    "reduce_manual_work": "reduce repetitive status updates and manual checks",
                },
            },
            "requires_human_review": {
                "type": "noul",
                "instructions": "Does this proposed CRM workflow change require human review before application?",
            },
        }
        state = {"objective": objective, "crm": crm_config, "analytics": analytics}
        result = self._get_agent().predict(state, questions)
        if not isinstance(result, dict):
            raise LayaRuntimeError("Laya returned an invalid evolution decision payload.")
        priority = self._choice(result, "priority", {"improve_follow_up", "improve_conversion", "reduce_manual_work"})
        try:
            review_answer = result["answers"]["requires_human_review"]
            review = review_answer.get("noul", review_answer.get("choice"))
        except (KeyError, TypeError) as exc:
            raise LayaRuntimeError("Laya did not return a review decision.") from exc
        # Upstream Laya represents a ``noul`` answer as P(true), not a Python
        # boolean. This flag is a review signal only; it never authorizes or
        # applies a proposal.
        if isinstance(review, bool):
            pass
        elif isinstance(review, (int, float)) and 0.0 <= float(review) <= 1.0:
            review = float(review) >= 0.5
        else:
            raise LayaRuntimeError("Laya returned an invalid review decision.")
        return EvolutionDecision(priority=priority, requires_human_review=review, model_id=str(result.get("model") or self.model_id))
