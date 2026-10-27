"""Schema Binding Layer — Bridge between Laya (System 1) and Qwen (System 2).

This module provides utilities to:
1. Build Laya choice primitives with normalized custom columns and statuses
2. Inject normalized schema into Qwen system prompts
3. Enforce strict JSON output format that matches normalized keys
4. Eliminate repetitive intake logic and clarification loops
"""
from __future__ import annotations

from typing import Any
from app.services.laya_system1 import LayaSystem1, NormalizedSchema


class SchemaBinding:
    """Utilities for coordinating Laya routing with Qwen generation."""

    @staticmethod
    def build_laya_choice_primitive(
        question_key: str,
        instructions: str,
        normalized_schema: NormalizedSchema,
        choice_type: str = "column",  # "column" or "status"
    ) -> dict[str, Any]:
        """
        Build a Laya choice primitive with normalized machine keys and descriptions.

        Args:
            question_key: The key for this choice in Laya's questions dict
            instructions: Human-readable instructions for this choice
            normalized_schema: NormalizedSchema from LayaSystem1.normalize_custom_schema()
            choice_type: Either "column" or "status" to select which mapping to use

        Returns:
            A dict ready for Laya's predict() method:
            {
                "type": "choice",
                "instructions": "...",
                "criteria": {
                    "machine_key_1": "Human Label 1",
                    "machine_key_2": "Human Label 2",
                    ...
                }
            }

        Example:
            normalized = LayaSystem1.normalize_custom_schema(
                custom_columns=["Budget!", "Priority"],
            )
            choice = SchemaBinding.build_laya_choice_primitive(
                question_key="primary_field",
                instructions="Pick the most critical custom field for this CRM.",
                normalized_schema=normalized,
                choice_type="column",
            )
            # choice["criteria"] = {"budget": "Budget", "priority": "Priority"}
        """
        if choice_type == "status":
            criteria = normalized_schema.laya_status_criteria
        else:
            criteria = normalized_schema.laya_choice_criteria

        # Return empty if no custom items were provided
        if not criteria:
            return {
                "type": "choice",
                "instructions": instructions,
                "criteria": {"default": "Use default options"},
            }

        return {
            "type": "choice",
            "instructions": instructions,
            "criteria": criteria,
        }

    @staticmethod
    def build_qwen_system_prompt(
        normalized_schema: NormalizedSchema | None = None,
        base_prompt: str = "",
    ) -> str:
        """
        Build a system prompt for Qwen that enforces strict JSON output
        with keys matching the normalized schema.

        Args:
            normalized_schema: Optional NormalizedSchema to inject field constraints
            base_prompt: Optional base system prompt to prepend

        Returns:
            A complete system prompt that instructs Qwen to return structured JSON
            with exactly the normalized column and status keys.

        Example:
            normalized = LayaSystem1.normalize_custom_schema(
                custom_columns=["Budget", "Deal Size"],
                custom_statuses=["Active", "On Hold"],
            )
            system_prompt = SchemaBinding.build_qwen_system_prompt(
                normalized_schema=normalized,
                base_prompt="You are a CRM expert.",
            )
        """
        prompt = base_prompt or ""

        if normalized_schema:
            prompt += "\n\n## Normalized Schema Constraints\n"
            prompt += "You MUST return a JSON object whose keys strictly match these identifiers:\n\n"

            if normalized_schema.column_mapping:
                prompt += "**Custom Columns (use as JSON keys):**\n"
                for machine_key, ni in normalized_schema.column_mapping.items():
                    prompt += f"  - `{machine_key}` (originally: '{ni.original_raw}')\n"
                prompt += "\n"

            if normalized_schema.status_mapping:
                prompt += "**Custom Statuses (for `assigned_status` field):**\n"
                for machine_key, ni in normalized_schema.status_mapping.items():
                    prompt += f"  - `{machine_key}` (originally: '{ni.original_raw}')\n"
                prompt += "\n"

            prompt += (
                "Your JSON output MUST use these exact machine keys (lowercase, underscores) "
                "and include `assigned_status` and `draft_response` fields.\n"
                "Example:\n"
                "```json\n"
                "{\n"
                "  \"client_budget_size\": \"...\",\n"
                "  \"priority\": \"...\",\n"
                "  \"assigned_status\": \"active\",\n"
                "  \"draft_response\": \"...\"\n"
                "}\n"
                "```\n"
            )
        else:
            prompt += (
                "\n\nReturn a JSON object with the following structure:\n"
                "```json\n"
                "{\n"
                "  \"assigned_status\": \"status_value\",\n"
                "  \"draft_response\": \"human_readable_response\"\n"
                "}\n"
                "```\n"
            )

        return prompt

    @staticmethod
    def validate_qwen_output(
        raw_output: dict[str, Any],
        normalized_schema: NormalizedSchema | None = None,
    ) -> tuple[bool, dict[str, Any], list[str]]:
        """
        Validate Qwen's JSON output against the normalized schema.

        Args:
            raw_output: The parsed JSON dict from Qwen
            normalized_schema: Optional NormalizedSchema to validate against

        Returns:
            A tuple of (is_valid, cleaned_output, errors):
            - is_valid (bool): True if output matches schema requirements
            - cleaned_output (dict): Sanitized output with only valid keys
            - errors (list[str]): List of validation errors (empty if valid)

        Validation checks:
        1. If normalized_schema is provided, ensure all keys are either:
           - Normalized column keys
           - "assigned_status" (with value in normalized statuses)
           - "draft_response" (string)
        2. No extra keys beyond what the schema allows
        3. All required fields present
        """
        errors: list[str] = []
        cleaned: dict[str, Any] = {}

        if not isinstance(raw_output, dict):
            return False, {}, ["Qwen output is not a JSON object"]

        # Check for required fields
        if "draft_response" not in raw_output:
            errors.append("Missing required field: 'draft_response'")

        # Validate status field
        assigned_status = raw_output.get("assigned_status")
        if assigned_status and normalized_schema:
            valid_statuses = set(normalized_schema.status_mapping.keys())
            if assigned_status not in valid_statuses and valid_statuses:
                errors.append(
                    f"Invalid status '{assigned_status}'. "
                    f"Must be one of: {', '.join(sorted(valid_statuses))}"
                )
            else:
                cleaned["assigned_status"] = assigned_status
        elif assigned_status:
            cleaned["assigned_status"] = assigned_status

        # Copy draft_response
        if "draft_response" in raw_output:
            cleaned["draft_response"] = str(raw_output["draft_response"]).strip()

        # Validate and copy normalized schema keys
        if normalized_schema:
            valid_keys = set(normalized_schema.column_mapping.keys())
            for key, value in raw_output.items():
                if key in ("assigned_status", "draft_response"):
                    continue
                if key not in valid_keys:
                    errors.append(f"Unexpected key '{key}' not in normalized schema")
                    continue
                cleaned[key] = value

        # If there are no errors, validation passes
        is_valid = len(errors) == 0

        return is_valid, cleaned, errors

    @staticmethod
    def get_normalized_field_mapping(
        custom_columns: list[str] | None = None,
    ) -> dict[str, str]:
        """
        Quick utility to get the normalized field mapping for injection into Qwen context.

        Args:
            custom_columns: List of raw column names provided by the user

        Returns:
            Dict mapping machine_key -> human_label, e.g.:
            {
                "client_budget_size": "Client Budget Size",
                "priority": "Priority",
            }

        This is useful for including in Qwen's context window before generation.
        """
        if not custom_columns:
            return {}

        normalized = LayaSystem1.normalize_custom_schema(custom_columns=custom_columns)
        return {ni.machine_key: ni.human_label for ni in normalized.column_mapping.values()}

    @staticmethod
    def get_normalized_status_mapping(
        custom_statuses: list[str] | None = None,
    ) -> dict[str, str]:
        """
        Quick utility to get the normalized status mapping for injection into Qwen context.

        Args:
            custom_statuses: List of raw status names provided by the user

        Returns:
            Dict mapping machine_key -> human_label, e.g.:
            {
                "active": "Active",
                "on_hold": "On Hold",
            }
        """
        if not custom_statuses:
            return {}

        normalized = LayaSystem1.normalize_custom_schema(custom_statuses=custom_statuses)
        return {ni.machine_key: ni.human_label for ni in normalized.status_mapping.values()}
