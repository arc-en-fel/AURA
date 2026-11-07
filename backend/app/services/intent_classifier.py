"""AURA Copilot Intent Classification Layer.

Classifies incoming user messages into 8 distinct operation categories:
1. GENERAL_QUESTION
2. SCHEMA_QUERY
3. ANALYTICS_QUERY
4. RECORD_QUERY
5. CREATE_RECORD
6. UPDATE_RECORD
7. DELETE_RECORD
8. CRM_CONFIGURATION_CHANGE

CRITICAL SAFETY RULE:
Read-only intents (GENERAL_QUESTION, SCHEMA_QUERY, ANALYTICS_QUERY, RECORD_QUERY)
must NEVER execute mutation tools (create_record, update_record, delete_record,
or schema mutation tools).
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any


class IntentCategory(str, Enum):
    GENERAL_QUESTION = "GENERAL_QUESTION"
    SCHEMA_QUERY = "SCHEMA_QUERY"
    ANALYTICS_QUERY = "ANALYTICS_QUERY"
    RECORD_QUERY = "RECORD_QUERY"
    CREATE_RECORD = "CREATE_RECORD"
    UPDATE_RECORD = "UPDATE_RECORD"
    DELETE_RECORD = "DELETE_RECORD"
    CRM_CONFIGURATION_CHANGE = "CRM_CONFIGURATION_CHANGE"


READ_ONLY_INTENTS = {
    IntentCategory.GENERAL_QUESTION,
    IntentCategory.SCHEMA_QUERY,
    IntentCategory.ANALYTICS_QUERY,
    IntentCategory.RECORD_QUERY,
}

MUTATION_TOOLS = {
    "create_record",
    "update_record",
    "delete_record",
    "add_crm_field",
    "update_crm_field",
    "delete_crm_field",
    "add_crm_stage",
    "delete_crm_stage",
    "reorder_crm_fields",
    "reorder_crm_stages",
}

READ_ONLY_TOOLS = {
    "get_crm_summary",
    "get_entity_schema",
    "get_status_distribution",
    "count_records",
    "query_records",
    "aggregate_records",
}


class IntentClassifier:
    """High-precision, schema-aware intent classifier for AURA Copilot."""

    @staticmethod
    def is_read_only(intent: IntentCategory | str) -> bool:
        """Check if an intent is strictly read-only."""
        val = intent.value if isinstance(intent, IntentCategory) else str(intent)
        return val in {i.value for i in READ_ONLY_INTENTS}

    @classmethod
    def classify(
        cls,
        message: str,
        conversation_history: list[dict[str, str]] | None = None,
        crm_context: dict[str, Any] | None = None,
    ) -> IntentCategory:
        """Classify a user message into one of the 8 intent categories.
        
        Evaluates context, pipeline stages, entities, and conversational history
        (e.g., follow-ups like 'what about High Value?').
        """
        raw = message.strip()
        q = raw.lower()

        config = crm_context.get("configuration", {}) if crm_context else {}
        pipeline_stages = [s.lower() for s in config.get("pipeline_stages", [])]
        entities = config.get("entities", [])
        entity_names = [e.get("name", "").lower() for e in entities]
        entity_labels = [e.get("label", "").lower() for e in entities]

        # ── 1. Check for CRM_CONFIGURATION_CHANGE ──────────────────────────
        # Adding/deleting columns, fields, stages, status options
        config_patterns = [
            r"\b(add|create|new)\s+(a\s+|new\s+)?(column|field)\b",
            r"\b(delete|remove|drop)\s+(the\s+)?(column|field)\b",
            r"\b(update|change|rename|modify)\s+(the\s+)?(column|field)\b",
            r"\b(add|create)\s+(a\s+|new\s+)?(pipeline\s+)?stage\b",
            r"\b(add|create)\s+['\"]?[\w\s]+['\"]?\s+(as|to)\s+(the\s+|a\s+)?(pipeline\s+)?stages?\b",
            r"\b(delete|remove|drop)\s+(the\s+)?(pipeline\s+)?stage\b",
            r"\b(reorder|order|sort)\s+(the\s+)?(stages?|fields?|columns?)\b",
            r"\b(add|create|new)\s+(a\s+|new\s+)?status\s+option\b",
        ]
        if any(re.search(pat, q) for pat in config_patterns):
            return IntentCategory.CRM_CONFIGURATION_CHANGE

        # ── 2. Check for Explicit Record Creation Commands ─────────────────
        # Imperative commands like "i need to add a new lead...", "create customer Bob..."
        # Checked before analytics queries so that queries with "total revenue 20000" are not mistaken for questions.
        create_start_pat = (
            r"^(please\s+)?(i\s+need\s+to\s+|i\s+want\s+to\s+|can\s+you\s+)?(add|create|insert|make)\s+"
            r"(a\s+|new\s+)?(record|customer|lead|candidate|patient|ticket|item|order|shipment|entry|\w+)\b"
        )
        if re.search(create_start_pat, q) and not any(re.search(rf"\b{w}\b", q) for w in ["how many", "count", "what is", "how much", "list", "show"]):
            return IntentCategory.CREATE_RECORD

        # ── 3. Check for ANALYTICS_QUERY (Quantitative / Metrics / Counts) ──
        # Crucial: "how many new lead are there" matches here!
        analytics_patterns = [
            r"\bhow\s+many\b",
            r"\bcount\b",
            r"\btotal\s+(number|count|amount|revenue|deal|value|records?|leads?|customers?|tickets?)\b",
            r"\bwhat\s+(is|are)\s+the\s+total\b",
            r"\b(average|avg|sum|min|max|median)\b",
            r"\b(distribution|breakdown|proportion|percentage|funnel|conversion|kpi|kpis|metrics?|stats?|statistics?|analytics?)\b",
            r"\bhow\s+much\b",
            r"\bnumber\s+of\b",
        ]
        if any(re.search(pat, q) for pat in analytics_patterns):
            return IntentCategory.ANALYTICS_QUERY

        # Conversational follow-up check for analytics:
        # e.g., "what about High Value?", "and for At Risk?", "how about New?"
        if cls._is_analytics_follow_up(q, conversation_history, pipeline_stages):
            return IntentCategory.ANALYTICS_QUERY

        # ── 4. Check for SCHEMA_QUERY (Informational about structure) ─────
        schema_patterns = [
            r"\b(what|which|list|show|view)\b.*\b(fields?|columns?)\b",
            r"\b(what|which|list|show|view)\b.*\b(entities|entity)\b",
            r"\b(what|which|list|show|view)\b.*\b(stages?|pipeline\s+stages?|pipeline)\b",
            r"\b(what|which|list|show)\b.*\b(status\s+options?|statuses)\b",
            r"\b(what\s+is|show\s+me\s+the|view\s+the)\s+(schema|structure|configuration)\b",
            r"\bfields?\s+does\b",
            r"\bwhat\s+can\s+i\s+track\b",
        ]
        if any(re.search(pat, q) for pat in schema_patterns):
            return IntentCategory.SCHEMA_QUERY

        # ── 5. Check for RECORD Mutations ─────────────────────────────────
        # Delete Record
        if (
            any(re.search(rf"\b{w}\b", q) for w in ["delete", "remove", "drop", "trash", "purge"])
            and any(re.search(rf"\b{w}\b", q) for w in ["record", "entry", "item", "lead", "customer", "ticket", "candidate", "shipment", "'s record"])
            and not any(re.search(rf"\b{w}\b", q) for w in ["column", "field", "stage", "status option"])
        ):
            return IntentCategory.DELETE_RECORD

        # Update Record
        if (
            any(re.search(rf"\b{w}\b", q) for w in ["update", "change", "modify", "set", "mark"])
            and not any(re.search(rf"\b{w}\b", q) for w in ["column", "field", "stage", "schema"])
            and (
                re.search(r"\bto\b", q)
                or any(stage in q for stage in pipeline_stages)
                or any(re.search(rf"\b{w}\b", q) for w in ["status", "priority", "value", "stage", "email", "phone"])
            )
        ):
            return IntentCategory.UPDATE_RECORD

        # Additional Create Record check
        if any(q.startswith(w) for w in ["create ", "add ", "insert ", "make "]):
            if not any(re.search(rf"\b{w}\b", q) for w in ["how", "what", "which", "show", "view", "list", "count", "where"]):
                return IntentCategory.CREATE_RECORD

        # ── 6. Check for RECORD_QUERY (Read-Only record viewing / searching)
        record_query_patterns = [
            r"\b(show|list|view|find|search|get|display|fetch)\b.*\b(records?|leads?|customers?|entries|items?|tickets?|candidates?)\b",
            r"\b(show|list|view|display)\s+(all|my|the|recent|latest)\b",
            r"\bfind\s+(the\s+|a\s+)?(record|lead|customer|candidate)\b",
            r"\bsearch\s+for\b",
        ]
        if any(re.search(pat, q) for pat in record_query_patterns):
            return IntentCategory.RECORD_QUERY

        # ── 7. Fallback: GENERAL_QUESTION ─────────────────────────────────
        return IntentCategory.GENERAL_QUESTION

    @staticmethod
    def _is_analytics_follow_up(
        q: str,
        history: list[dict[str, str]] | None,
        pipeline_stages: list[str],
    ) -> bool:
        """Check if message is a follow-up to a previous analytics question."""
        if not history:
            return False

        follow_up_starter = any(q.startswith(prefix) for prefix in [
            "what about",
            "how about",
            "and for",
            "and in",
            "what of",
            "how many in",
        ])

        mentions_stage = any(stage in q for stage in pipeline_stages if stage)

        if follow_up_starter or (len(q.split()) <= 4 and mentions_stage):
            last_user_msg = next(
                (m.get("content", "").lower() for m in reversed(history) if m.get("role") == "user"),
                "",
            )
            if any(w in last_user_msg for w in ["how many", "count", "total", "distribution", "breakdown", "analytics", "status"]):
                return True

        return False
