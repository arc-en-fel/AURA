"""Tests for the normalization layer and schema binding.

This test suite verifies:
1. User input normalization (raw -> machine keys)
2. Bidirectional mapping (human <-> machine)
3. Collision handling (duplicate normalized keys)
4. Reserved field checking
5. Laya choice primitive building
6. Qwen system prompt generation
7. Output validation
8. Elimination of clarification loops
"""
import pytest
from app.services.laya_system1 import LayaSystem1, NormalizedInput
from app.services.schema_binding import SchemaBinding
from app.services.crm_builder_integration import (
    process_user_crm_input,
    eliminate_clarification_loop,
)


class TestNormalizationLayer:
    """Test LayaSystem1 user input normalization."""

    def test_normalize_user_input_basic(self):
        """Test basic normalization of raw strings."""
        raw_inputs = ["Client Budget Size", "Priority Level", "Contact Phone"]
        result = LayaSystem1._normalize_user_input(raw_inputs)

        assert len(result) == 3
        assert "client_budget_size" in result
        assert "priority_level" in result
        assert "contact_phone" in result

        # Verify bidirectional mapping
        assert result["client_budget_size"].machine_key == "client_budget_size"
        assert result["client_budget_size"].human_label == "Client Budget Size"
        assert result["client_budget_size"].original_raw == "Client Budget Size"

    def test_normalize_removes_special_characters(self):
        """Test that special characters are removed."""
        raw_inputs = ["Client Budget Size!", "Priority (Level) & Status", "Deal @Amount"]
        result = LayaSystem1._normalize_user_input(raw_inputs)

        assert "client_budget_size" in result
        assert "priority_level_status" in result
        assert "deal_amount" in result

    def test_normalize_handles_spaces_and_hyphens(self):
        """Test that spaces and hyphens become underscores."""
        raw_inputs = ["Contact Phone", "Sales-Stage", "Lead Status"]
        result = LayaSystem1._normalize_user_input(raw_inputs)

        assert "contact_phone" in result
        assert "sales_stage" in result
        assert "lead_status" in result

    def test_normalize_handles_duplicate_collisions(self):
        """Test that duplicate normalized keys get numeric suffixes."""
        raw_inputs = ["Budget", "budget", "BUDGET"]  # All normalize to "budget"
        result = LayaSystem1._normalize_user_input(raw_inputs)

        keys = list(result.keys())
        # Should have "budget", "budget_1", "budget_2"
        assert "budget" in keys
        assert len(keys) == 3

    def test_normalize_enforces_max_items(self):
        """Test that max_items limit is enforced."""
        raw_inputs = [f"field_{i}" for i in range(100)]
        result = LayaSystem1._normalize_user_input(raw_inputs, max_items=10)

        assert len(result) <= 10

    def test_normalize_schema_complete(self):
        """Test the complete schema normalization."""
        custom_columns = ["Client Budget", "Deal Priority!"]
        custom_statuses = ["Active", "On-Hold", "Completed"]

        normalized = LayaSystem1.normalize_custom_schema(
            custom_columns=custom_columns,
            custom_statuses=custom_statuses,
        )

        # Verify column mapping
        assert len(normalized.column_mapping) == 2
        assert "client_budget" in normalized.column_mapping
        assert "deal_priority" in normalized.column_mapping

        # Verify status mapping
        assert len(normalized.status_mapping) == 3
        assert "active" in normalized.status_mapping
        assert "on_hold" in normalized.status_mapping
        assert "completed" in normalized.status_mapping

        # Verify Laya choice criteria
        assert "client_budget" in normalized.laya_choice_criteria
        assert normalized.laya_choice_criteria["client_budget"] == "Client Budget"

        assert "active" in normalized.laya_status_criteria
        assert normalized.laya_status_criteria["active"] == "Active"

    def test_normalize_handles_empty_inputs(self):
        """Test that empty inputs are handled gracefully."""
        normalized = LayaSystem1.normalize_custom_schema(
            custom_columns=None,
            custom_statuses=[],
        )

        assert len(normalized.column_mapping) == 0
        assert len(normalized.status_mapping) == 0


class TestSchemaBinding:
    """Test SchemaBinding utilities for Laya and Qwen integration."""

    def test_build_laya_choice_primitive_columns(self):
        """Test building Laya choice primitive for columns."""
        normalized = LayaSystem1.normalize_custom_schema(
            custom_columns=["Budget", "Priority"],
        )

        choice = SchemaBinding.build_laya_choice_primitive(
            question_key="primary_field",
            instructions="Pick the most critical field.",
            normalized_schema=normalized,
            choice_type="column",
        )

        assert choice["type"] == "choice"
        assert "budget" in choice["criteria"]
        assert "priority" in choice["criteria"]
        assert choice["criteria"]["budget"] == "Budget"

    def test_build_laya_choice_primitive_statuses(self):
        """Test building Laya choice primitive for statuses."""
        normalized = LayaSystem1.normalize_custom_schema(
            custom_statuses=["Active", "On Hold"],
        )

        choice = SchemaBinding.build_laya_choice_primitive(
            question_key="lifecycle",
            instructions="Choose a status option.",
            normalized_schema=normalized,
            choice_type="status",
        )

        assert "active" in choice["criteria"]
        assert "on_hold" in choice["criteria"]

    def test_build_qwen_system_prompt_with_schema(self):
        """Test building Qwen system prompt with schema injection."""
        normalized = LayaSystem1.normalize_custom_schema(
            custom_columns=["Budget", "Priority"],
            custom_statuses=["Active", "On Hold"],
        )

        prompt = SchemaBinding.build_qwen_system_prompt(
            normalized_schema=normalized,
            base_prompt="You are a CRM expert.",
        )

        # Verify schema constraints are in the prompt
        assert "budget" in prompt.lower()
        assert "priority" in prompt.lower()
        assert "active" in prompt.lower()
        assert "on_hold" in prompt.lower()
        assert "assigned_status" in prompt.lower()
        assert "draft_response" in prompt.lower()

    def test_validate_qwen_output_valid(self):
        """Test validation of valid Qwen output."""
        normalized = LayaSystem1.normalize_custom_schema(
            custom_columns=["Budget"],
            custom_statuses=["Active"],
        )

        valid_output = {
            "budget": 50000,
            "assigned_status": "active",
            "draft_response": "Generated draft CRM.",
        }

        is_valid, cleaned, errors = SchemaBinding.validate_qwen_output(
            valid_output, normalized_schema=normalized
        )

        assert is_valid is True
        assert len(errors) == 0
        assert "budget" in cleaned
        assert cleaned["assigned_status"] == "active"
        assert cleaned["draft_response"] == "Generated draft CRM."

    def test_validate_qwen_output_invalid_status(self):
        """Test validation rejects invalid status."""
        normalized = LayaSystem1.normalize_custom_schema(
            custom_statuses=["Active", "On Hold"],
        )

        invalid_output = {
            "assigned_status": "invalid_status",
            "draft_response": "Test",
        }

        is_valid, cleaned, errors = SchemaBinding.validate_qwen_output(
            invalid_output, normalized_schema=normalized
        )

        assert is_valid is False
        assert len(errors) > 0
        assert any("Invalid status" in e for e in errors)

    def test_validate_qwen_output_missing_response(self):
        """Test validation requires draft_response."""
        invalid_output = {"assigned_status": "active"}

        is_valid, cleaned, errors = SchemaBinding.validate_qwen_output(invalid_output)

        assert is_valid is False
        assert any("draft_response" in e for e in errors)


class TestCRMBuilderIntegration:
    """Test high-level CRM builder integration."""

    def test_process_user_crm_input_basic(self):
        """Test end-to-end input processing."""
        result = process_user_crm_input(
            user_message="Build a sales CRM with Budget and Priority fields",
            mentioned_columns=["Budget", "Priority!"],
        )

        # Verify all required outputs are present
        assert "normalized_schema" in result
        assert "laya_choice_primitive" in result
        assert "qwen_system_prompt" in result
        assert "field_mapping" in result
        assert "generation_prompt" in result

        # Verify field mapping
        assert result["field_mapping"]["budget"] == "Budget"
        assert result["field_mapping"]["priority"] == "Priority"

        # Verify generation prompt includes normalized schema instruction
        assert "normalized" in result["generation_prompt"].lower()

    def test_eliminate_clarification_loop_with_custom_input(self):
        """Test that custom input signals readiness to generate."""
        history = [
            {"role": "user", "content": "I need a CRM."},
            {"role": "assistant", "content": "What kind?"},
        ]

        # With custom columns, should skip clarifications
        ready = eliminate_clarification_loop(
            history,
            user_provided_columns=["Budget", "Priority"],
        )
        assert ready is True

    def test_eliminate_clarification_loop_with_generate_signal(self):
        """Test that explicit generate signal triggers generation."""
        history = [
            {"role": "user", "content": "Build a CRM for sales."},
            {"role": "assistant", "content": "What fields?"},
            {"role": "user", "content": "Generate now!"},
        ]

        ready = eliminate_clarification_loop(history)
        assert ready is True

    def test_eliminate_clarification_loop_with_conversation_depth(self):
        """Test that deep conversation signals readiness."""
        history = [
            {"role": "user", "content": "I need a sales CRM."},
            {"role": "assistant", "content": "What entities?"},
            {"role": "user", "content": "Leads and deals."},
            {"role": "assistant", "content": "What stages?"},
            {"role": "user", "content": "New, negotiating, won."},
            {"role": "assistant", "content": "Any custom fields?"},
        ]

        ready = eliminate_clarification_loop(history)
        assert ready is True


class TestEndToEndIntegration:
    """Test real-world integration scenarios."""

    def test_raw_user_input_flows_through_normalization(self):
        """Test complete flow: raw input -> normalized -> Laya/Qwen binding."""
        raw_columns = ["Client Budget Size!", "Deal @Priority", "Contact-Phone"]
        raw_statuses = ["In Progress", "On-Hold", "Completed!"]

        # Step 1: Normalize
        normalized = LayaSystem1.normalize_custom_schema(
            custom_columns=raw_columns,
            custom_statuses=raw_statuses,
        )

        # Verify normalization removed special characters
        assert "client_budget_size" in normalized.column_mapping
        assert "deal_priority" in normalized.column_mapping
        assert "contact_phone" in normalized.column_mapping
        assert "in_progress" in normalized.status_mapping
        assert "on_hold" in normalized.status_mapping

        # Step 2: Build Laya choice primitive
        choice = SchemaBinding.build_laya_choice_primitive(
            "field",
            "Pick the primary field.",
            normalized,
            "column",
        )
        assert len(choice["criteria"]) == 3

        # Step 3: Build Qwen system prompt
        prompt = SchemaBinding.build_qwen_system_prompt(
            normalized_schema=normalized
        )
        assert "client_budget_size" in prompt
        assert "in_progress" in prompt

        # Verify no ambiguity in the process
        assert set(normalized.laya_choice_criteria.keys()) == set(normalized.column_mapping.keys())
        assert set(normalized.laya_status_criteria.keys()) == set(normalized.status_mapping.keys())

    def test_no_re_prompting_with_custom_input(self):
        """Test that custom input prevents clarification loops."""
        # User provides custom columns -> system should skip "what fields?" question
        result = process_user_crm_input(
            user_message="Build a CRM",
            mentioned_columns=["Budget", "Priority"],
        )

        # Laya choice primitive should be built (no need to ask again)
        assert result["laya_choice_primitive"] is not None

        # Qwen prompt should include schema constraints (no ambiguity)
        assert "Normalized" in result["qwen_system_prompt"]

        # No repetitive intake logic needed
        history = [{"role": "user", "content": "Build a CRM with Budget and Priority"}]
        ready = eliminate_clarification_loop(
            history,
            user_provided_columns=["Budget", "Priority"],
        )
        assert ready is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
