"""Regression tests for HTTP 422 and Custom CRM issues.

Tests the complete user flow:
1. User types first free-form message without CRM type selection
2. User later selects "Custom CRM"
3. User provides custom fields and stages
4. Generated CRM preserves exact user input
5. Fallback (AI failure) also preserves user config
"""
import pytest
from app.routers.chat import ChatRequest, ChatMessage
from app.services.laya_system1 import LayaSystem1


class TestRegressionHTTP422:
    """Verify that no 422 validation errors occur on initial chat message."""

    def test_initial_freeform_message_without_crm_type(self):
        """First message: user types without selecting CRM type chip."""
        request_data = {
            "messages": [
                {
                    "role": "user",
                    "content": "i would like to build a crm",
                }
            ],
            "generate_now": False,
            "crm_type": None,
            "quest_answers": {},
        }
        # Should not raise 422
        request = ChatRequest(**request_data)
        assert len(request.messages) == 1
        assert request.messages[0].content == "i would like to build a crm"
        assert request.crm_type is None

    def test_chat_request_with_extra_unknown_fields(self):
        """ChatRequest gracefully ignores unexpected extra fields."""
        request_data = {
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                }
            ],
            "generate_now": False,
            "crm_type": None,
            "quest_answers": {},
            "totally_unknown_field": "should be ignored",
            "another_unknown": 123,
        }
        # Should not raise 422 due to ConfigDict(extra="ignore")
        request = ChatRequest(**request_data)
        assert len(request.messages) == 1

    def test_messages_with_metadata_fields(self):
        """Messages can include metadata fields like response_source."""
        request_data = {
            "messages": [
                {
                    "role": "user",
                    "content": "I need a CRM",
                    "response_source": "user_input",
                    "isLoading": False,
                    "choices": None,
                },
                {
                    "role": "assistant",
                    "content": "What industry?",
                    "response_source": "llm",
                    "choices": ["SaaS", "Healthcare"],
                },
            ],
            "generate_now": False,
            "crm_type": None,
            "quest_answers": {},
        }
        request = ChatRequest(**request_data)
        assert len(request.messages) == 2
        assert request.messages[0].response_source == "user_input"
        assert request.messages[1].choices == ["SaaS", "Healthcare"]

    def test_freeform_then_custom_crm_selection(self):
        """Simulate: freeform message, then Custom CRM chip selected."""
        # First message (before chip)
        request_data_1 = {
            "messages": [
                {"role": "user", "content": "Let me build my own CRM from scratch"}
            ],
            "generate_now": False,
            "crm_type": None,
            "quest_answers": {},
        }
        request1 = ChatRequest(**request_data_1)
        assert request1.crm_type is None

        # Second: Custom CRM chip selected
        request_data_2 = {
            "messages": [
                {
                    "role": "user",
                    "content": "Let me build my own CRM from scratch",
                },
                {
                    "role": "assistant",
                    "content": "Got it. What do you need to track?",
                },
            ],
            "generate_now": False,
            "crm_type": "custom",
            "quest_answers": {},
        }
        request2 = ChatRequest(**request_data_2)
        assert request2.crm_type == "custom"


class TestRegressionCustomCRM:
    """Verify custom CRM answers are preserved through the flow."""

    def test_custom_crm_answers_in_request(self):
        """Custom CRM questionnaire answers are sent in the request."""
        request_data = {
            "messages": [
                {"role": "user", "content": "Leads and deals"}
            ],
            "generate_now": False,
            "crm_type": "custom",
            "quest_answers": {
                "tracks": "leads and deals",
                "pipeline_stages": "New → Contacted → Won",
                "key_fields": "lead,email,phone,product,status",
                "team_size": "Just me",
            },
        }
        request = ChatRequest(**request_data)
        assert request.crm_type == "custom"
        assert request.quest_answers["tracks"] == "leads and deals"
        assert request.quest_answers["pipeline_stages"] == "New → Contacted → Won"
        assert request.quest_answers["key_fields"] == "lead,email,phone,product,status"

    def test_custom_crm_generation_preserves_user_config(self):
        """Custom CRM generator preserves exact user input."""
        config = LayaSystem1.generate_custom_crm_from_answers(
            crm_type="custom",
            tracks="leads and deals",
            pipeline_stages="New → Contacted → Won",
            key_fields="lead,email,phone,product,status",
            team_size="Just me",
            prompt="Build a custom CRM"
        )
        
        # Verify it's NOT the default General/Sales CRM
        assert config["name"] != "General CRM"
        assert config["name"] != "AI Generated Sales CRM"
        
        # Verify stages match user input
        assert set(config["pipeline_stages"]) == {"New", "Contacted", "Won"}
        
        # Verify fields exist with correct types
        fields_by_name = {}
        for entity in config["entities"]:
            for field in entity["fields"]:
                fields_by_name[field["name"]] = field
        
        # Check that email/phone have correct inferred types
        assert fields_by_name.get("email", {}).get("type") == "email"
        assert fields_by_name.get("phone", {}).get("type") == "phone"
        assert fields_by_name.get("status", {}).get("type") == "select"

    def test_custom_crm_not_general_crm(self):
        """Custom CRM does not default to the General/Sales CRM template."""
        custom_config = LayaSystem1.generate_custom_crm_from_answers(
            crm_type="custom",
            tracks="tasks and projects",
            pipeline_stages="Backlog, In Progress, Done",
            key_fields="task_name,assigned_to,due_date,priority",
            team_size="Small (2-10)",
            prompt="Build a project management CRM"
        )
        
        # Not the Sales defaults
        assert "Lead Source" not in str(custom_config)
        assert "ARR Estimate" not in str(custom_config)
        assert "Discovery" not in custom_config["pipeline_stages"]
        assert "Negotiation" not in custom_config["pipeline_stages"]

    def test_fallback_with_custom_crm_answers(self):
        """When AI fails, fallback still respects custom CRM configuration."""
        # Simulate AI failure; system falls back to deterministic generation
        # with custom answers available
        custom_config = LayaSystem1.generate_custom_crm_from_answers(
            crm_type="custom",
            tracks="customer support tickets",
            pipeline_stages="Open → In Progress → Resolved → Closed",
            key_fields="ticket_id,customer,issue,assigned_to,status",
            team_size="Medium (10-50)",
            prompt="Fallback: support ticket CRM"
        )
        
        # Verify stages are exact
        stages = custom_config["pipeline_stages"]
        assert stages == ["Open", "In Progress", "Resolved", "Closed"]
        
        # Verify entity exists (probably named 'record' or 'ticket')
        assert len(custom_config["entities"]) > 0
        
        # Verify no hardcoded Sales CRM fields
        all_field_labels = []
        for entity in custom_config["entities"]:
            for field in entity["fields"]:
                all_field_labels.append(field["label"].lower())
        
        # Shouldn't have Sales-specific fields when not requested
        assert not any("deal" in label for label in all_field_labels)


class TestCustomCRMArrowFormat:
    """Test that custom CRM parsing supports arrow format stages."""

    def test_arrow_format_stages_parsing(self):
        """Stages in arrow format are correctly parsed."""
        config = LayaSystem1.generate_custom_crm_from_answers(
            crm_type="custom",
            tracks="workflow items",
            pipeline_stages="Start → Review → Approve → Deploy → Done",
            key_fields="name,owner,date",
            team_size="Small",
            prompt=""
        )
        
        expected_stages = ["Start", "Review", "Approve", "Deploy", "Done"]
        assert config["pipeline_stages"] == expected_stages

    def test_comma_separated_stages(self):
        """Stages in comma-separated format are also parsed."""
        config = LayaSystem1.generate_custom_crm_from_answers(
            crm_type="custom",
            tracks="workflow items",
            pipeline_stages="Start, Review, Approve, Deploy, Done",
            key_fields="name,owner,date",
            team_size="Small",
            prompt=""
        )
        
        expected_stages = ["Start", "Review", "Approve", "Deploy", "Done"]
        assert config["pipeline_stages"] == expected_stages


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
