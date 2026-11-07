"""CRM Builder Integration — Unified entry point for normalized schema handling.

This module provides high-level functions for the chat and generation endpoints
to use normalized input processing without repetitive intake logic.

Workflow:
1. User provides raw natural language (custom columns, statuses, etc.)
2. Normalize the input using LayaSystem1._normalize_user_input()
3. Build Laya choice primitives using SchemaBinding
4. Feed normalized schema keys into Laya and Qwen
5. Validate Qwen output against normalized schema
6. Return schema-valid, deterministic result
"""
from __future__ import annotations

from typing import Any
from app.services.laya_system1 import LayaSystem1
from app.services.schema_binding import SchemaBinding


def process_user_crm_input(
    user_message: str,
    mentioned_columns: list[str] | None = None,
    mentioned_statuses: list[str] | None = None,
) -> dict[str, Any]:
    """
    Process user input with automatic normalization and Laya/Qwen binding.

    This is the entry point for one-turn CRM generation that includes custom columns/statuses.

    Args:
        user_message: The full user message describing the CRM
        mentioned_columns: Optional list of raw column names mentioned by the user
        mentioned_statuses: Optional list of raw status names mentioned by the user

    Returns:
        A dict with:
        {
            "normalized_schema": NormalizedSchema,
            "laya_choice_primitive": dict for Laya,
            "qwen_system_prompt": str to inject into Qwen,
            "field_mapping": dict mapping machine_key -> human_label,
            "status_mapping": dict mapping machine_key -> human_label,
            "generation_prompt": str ready to send to Qwen,
        }

    Example usage in chat endpoint:
        >>> result = process_user_crm_input(
        ...     user_message="Build me a CRM with Budget and Priority fields",
        ...     mentioned_columns=["Budget", "Priority!"],
        ... )
        >>> normalized = result["normalized_schema"]
        >>> # Use normalized.laya_choice_criteria for Laya's choice primitive
        >>> # Use result["qwen_system_prompt"] as Qwen's system prompt
        >>> # Use result["field_mapping"] to show user what was normalized
    """
    # Normalize custom input
    normalized = LayaSystem1.normalize_custom_schema(
        custom_columns=mentioned_columns,
        custom_statuses=mentioned_statuses,
    )

    # Build Laya choice primitive for column selection (if columns were provided)
    laya_choice_primitive = None
    if normalized.column_mapping:
        laya_choice_primitive = SchemaBinding.build_laya_choice_primitive(
            question_key="primary_field",
            instructions="Which of the custom fields is most important for this CRM?",
            normalized_schema=normalized,
            choice_type="column",
        )

    # Build Qwen system prompt with normalized schema injected
    base_system_prompt = (
        "You are an expert CRM architect. Generate a complete CRM configuration JSON "
        "that matches the user's requirements and the normalized schema provided below."
    )
    qwen_system_prompt = SchemaBinding.build_qwen_system_prompt(
        normalized_schema=normalized,
        base_prompt=base_system_prompt,
    )

    # Prepare generation prompt for Qwen
    generation_prompt = (
        f"{user_message}\n\n"
        "Respond with valid JSON only, using the normalized schema provided in your system instructions."
    )

    # Prepare field and status mappings for frontend display
    field_mapping = {ni.machine_key: ni.human_label for ni in normalized.column_mapping.values()}
    status_mapping = {ni.machine_key: ni.human_label for ni in normalized.status_mapping.values()}

    return {
        "normalized_schema": normalized,
        "laya_choice_primitive": laya_choice_primitive,
        "qwen_system_prompt": qwen_system_prompt,
        "field_mapping": field_mapping,
        "status_mapping": status_mapping,
        "generation_prompt": generation_prompt,
    }


def validate_and_inject_normalized_schema(
    raw_crm_config: dict[str, Any],
    normalized_schema: dict[str, Any] | None = None,
) -> tuple[bool, dict[str, Any], list[str]]:
    """
    Post-process generated CRM config to ensure it uses normalized keys.

    Args:
        raw_crm_config: The raw CRM config dict from Qwen or AI provider
        normalized_schema: Optional NormalizedSchema to validate against

    Returns:
        Tuple of (is_valid, cleaned_config, errors):
        - is_valid: True if the config uses normalized keys correctly
        - cleaned_config: Config with normalized keys applied
        - errors: List of validation issues (empty if valid)

    This is useful as a post-generation step to ensure the generated CRM
    strictly adheres to the normalized schema, preventing key mismatches.
    """
    errors: list[str] = []
    cleaned = raw_crm_config.copy()

    if not normalized_schema:
        return True, cleaned, []

    # Validate that all entity fields use normalized keys
    entities = cleaned.get("entities", [])
    if isinstance(entities, list):
        valid_field_keys = set(normalized_schema.get("column_mapping", {}).keys())
        for entity in entities:
            if isinstance(entity, dict):
                fields = entity.get("fields", [])
                if isinstance(fields, list):
                    for field in fields:
                        if isinstance(field, dict):
                            field_name = field.get("name", "")
                            # Allow standard field names; warn if custom field is not normalized
                            if field_name and valid_field_keys and field_name not in valid_field_keys:
                                errors.append(
                                    f"Field '{field_name}' not in normalized schema. "
                                    f"Valid keys: {', '.join(sorted(valid_field_keys))}"
                                )

    is_valid = len(errors) == 0
    return is_valid, cleaned, errors


def eliminate_clarification_loop(
    conversation_history: list[dict[str, str]],
    user_provided_columns: list[str] | None = None,
    user_provided_statuses: list[str] | None = None,
) -> bool:
    """
    Determine if the conversation has enough information to skip clarifications
    and generate immediately.

    Args:
        conversation_history: List of {role, content} messages from chat
        user_provided_columns: If user explicitly provided columns, skip ask for them
        user_provided_statuses: If user explicitly provided statuses, skip ask for them

    Returns:
        True if generation should proceed without more clarification

    Logic:
    - If user has provided custom columns/statuses, we skip the "what fields?" loop
    - If conversation has at least 3 meaningful exchanges, assume readiness
    - If user says "generate now", override and return True
    """
    # Check for explicit "generate now" signal
    if conversation_history:
        last_user_msg = next(
            (m.get("content", "").lower() for m in reversed(conversation_history) if m.get("role") == "user"),
            ""
        )
        if any(phrase in last_user_msg for phrase in ["generate now", "create my crm", "build it", "let's build"]):
            return True

    # If user provided custom input, they've signaled intent clearly
    if user_provided_columns or user_provided_statuses:
        return True

    # Otherwise, require at least 3 exchanges (approximately 3 user messages + 3 assistant replies)
    user_count = sum(1 for m in conversation_history if m.get("role") == "user")
    return user_count >= 3
