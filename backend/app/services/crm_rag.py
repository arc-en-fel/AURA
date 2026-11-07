"""Schema-Aware RAG (Retrieval-Augmented Generation) for AURA Copilot.

Provides schema retrieval, semantic grounding, and context assembly
from active CRM definitions.

Enforces:
1. Live database ground-truth for counts and metrics (never static or hallucinated).
2. Explicit entity matching and disambiguation.
3. Strict adherence to valid schema fields, types, and stage pipelines.
"""
from __future__ import annotations

import re
from typing import Any


class CRMRAGService:
    """Retrieves and formats CRM schema context for prompt grounding."""

    @classmethod
    def assemble_context(
        cls,
        crm_context: dict[str, Any] | None,
        user_query: str = "",
    ) -> dict[str, Any]:
        """Assemble structured schema context relevant to the user query."""
        if not crm_context:
            return {
                "crm_name": "No active CRM",
                "entities": [],
                "stages": [],
                "matched_entity": None,
                "is_ambiguous": False,
                "schema_prompt": "No CRM context available.",
            }

        config = crm_context.get("configuration", {})
        crm_name = config.get("name", "Active CRM")
        industry = config.get("industry", "general")
        entities = config.get("entities", [])
        stages = config.get("pipeline_stages", [])
        workflows = crm_context.get("workflows", [])

        # Match target entity from query
        q_lower = user_query.lower()
        matched_entity, is_ambiguous = cls.resolve_entity(entities, q_lower)

        # Build schema prompt text
        entity_blocks = []
        for ent in entities:
            fields = ent.get("fields", [])
            field_lines = []
            for f in fields:
                req = " (required)" if f.get("required") else ""
                opts = f", options: {f.get('options')}" if f.get("options") else ""
                field_lines.append(f"    - {f.get('name')} [{f.get('label', f.get('name'))}]: {f.get('type')}{req}{opts}")

            entity_blocks.append(
                f"Entity: {ent.get('name')} (Label: '{ent.get('label', ent.get('name'))}')\n"
                f"  Fields ({len(fields)}):\n" + "\n".join(field_lines)
            )

        stages_text = " → ".join(stages) if stages else "None"
        wf_text = ", ".join(w.get("name", "Workflow") for w in workflows) if workflows else "None"

        schema_prompt = (
            f"=== ACTIVE CRM SCHEMA: {crm_name} (Industry: {industry}) ===\n"
            f"Pipeline Stages: {stages_text}\n"
            f"Configured Workflows: {wf_text}\n\n"
            f"ENTITIES & FIELDS:\n" + "\n\n".join(entity_blocks) + "\n\n"
            f"GROUNDING RULES:\n"
            f"1. Valid Entities: {', '.join(e.get('name') for e in entities) if entities else 'None'}.\n"
            f"2. Only reference fields and entities that exist in this schema.\n"
            f"3. For questions asking 'how many', status counts, or metrics, NEVER hallucinate numbers.\n"
            f"   Always ground responses in live database tool results.\n"
        )

        return {
            "crm_name": crm_name,
            "industry": industry,
            "entities": entities,
            "stages": stages,
            "matched_entity": matched_entity,
            "is_ambiguous": is_ambiguous,
            "schema_prompt": schema_prompt,
        }

    @classmethod
    def resolve_entity(
        cls,
        entities: list[dict[str, Any]],
        query: str,
    ) -> tuple[dict[str, Any] | None, bool]:
        """Resolve query terms to a CRM entity, detecting ambiguity.
        
        Returns:
            (matched_entity, is_ambiguous)
        """
        if not entities:
            return None, False

        q = query.lower()

        # Exact matches on entity name or label
        exact_matches = []
        for ent in entities:
            ename = str(ent.get("name", "")).lower()
            elabel = str(ent.get("label", "")).lower()
            if re.search(rf"\b{re.escape(ename)}\b", q) or re.search(rf"\b{re.escape(elabel)}\b", q):
                exact_matches.append(ent)

        if len(exact_matches) == 1:
            return exact_matches[0], False
        if len(exact_matches) > 1:
            return exact_matches[0], True  # Ambiguous between multiple explicitly mentioned

        # Generic words like "lead", "record", "customer", "contact"
        # If CRM has exactly 1 entity, map to it without ambiguity
        if len(entities) == 1:
            return entities[0], False

        # If multiple entities exist, check if user said generic words like "lead" or "record"
        generic_terms = ["lead", "leads", "record", "records", "item", "items", "entry", "entries", "data", "row", "rows"]
        user_used_generic = any(re.search(rf"\b{w}\b", q) for w in generic_terms)
        if user_used_generic:
            # Check if any entity has that generic term in name/label
            for ent in entities:
                if any(w in ent.get("name", "").lower() or w in ent.get("label", "").lower() for w in generic_terms):
                    return ent, False
            # Truly ambiguous across multiple entities
            return entities[0], True

        # Fallback to primary entity
        return entities[0], False
