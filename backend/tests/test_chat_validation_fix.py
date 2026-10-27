"""Test: 422 Validation Error Fix for /api/v1/crm/chat

Verifies that the backend ChatMessage model accepts extra fields
from the frontend without throwing a 422 Unprocessable Entity error.
"""
import pytest
from app.routers.chat import ChatMessage, ChatRequest


class TestChatMessageValidation:
    """Test the fixed ChatMessage model."""

    def test_chat_message_accepts_minimal_payload(self):
        """ChatMessage works with minimal required fields."""
        msg = ChatMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_chat_message_accepts_frontend_metadata_fields(self):
        """ChatMessage accepts extra frontend metadata fields."""
        msg = ChatMessage(
            role="user",
            content="Build a CRM",
            response_source="rule",
            isLoading=False,
            choices=["Option 1", "Option 2"],
        )
        assert msg.role == "user"
        assert msg.content == "Build a CRM"
        # Extra fields are silently dropped by Pydantic due to Config.extra = "ignore"
        assert msg.response_source == "rule"
        assert msg.isLoading == False
        assert msg.choices == ["Option 1", "Option 2"]

    def test_chat_message_rejects_invalid_role(self):
        """ChatMessage rejects invalid role."""
        with pytest.raises(Exception):  # Pydantic validation error
            ChatMessage(
                role="invalid",  # Not 'user' or 'assistant'
                content="Hello",
            )

    def test_chat_message_rejects_empty_content(self):
        """ChatMessage rejects empty content."""
        with pytest.raises(Exception):  # Pydantic validation error
            ChatMessage(role="user", content="")

    def test_chat_request_accepts_full_payload(self):
        """ChatRequest accepts a complete frontend payload."""
        request_data = {
            "messages": [
                {
                    "role": "user",
                    "content": "Build a sales CRM",
                    "response_source": "rule",
                    "isLoading": False,
                    "choices": None,
                },
                {
                    "role": "assistant",
                    "content": "What's your industry?",
                    "response_source": "llm",
                    "isLoading": False,
                    "choices": ["SaaS", "Healthcare", "Real Estate"],
                },
            ],
            "generate_now": False,
            "crm_type": None,
        }
        request = ChatRequest(**request_data)
        assert len(request.messages) == 2
        assert request.messages[0].role == "user"
        assert request.messages[0].content == "Build a sales CRM"
        assert request.generate_now == False
        assert request.crm_type is None

    def test_chat_request_accepts_minimal_payload(self):
        """ChatRequest works with minimal required fields."""
        request_data = {
            "messages": [
                {"role": "user", "content": "Hello"},
            ],
        }
        request = ChatRequest(**request_data)
        assert len(request.messages) == 1
        assert request.messages[0].role == "user"
        assert request.generate_now == False
        assert request.crm_type is None

    def test_chat_request_rejects_empty_messages(self):
        """ChatRequest rejects empty messages list."""
        with pytest.raises(Exception):  # Pydantic validation error (min_length=1)
            ChatRequest(messages=[])

    def test_chat_request_accepts_generate_now_flag(self):
        """ChatRequest accepts generate_now=True."""
        request_data = {
            "messages": [
                {"role": "user", "content": "Generate my CRM"},
            ],
            "generate_now": True,
            "crm_type": "sales_pipeline",
        }
        request = ChatRequest(**request_data)
        assert request.generate_now == True
        assert request.crm_type == "sales_pipeline"

    def test_chat_message_handles_unknown_extra_fields(self):
        """ChatMessage ignores completely unknown fields."""
        msg = ChatMessage(
            role="user",
            content="Hello",
            completely_unknown_field="should be ignored",
            another_unknown="also ignored",
        )
        assert msg.role == "user"
        assert msg.content == "Hello"
        # Unknown fields don't cause errors

    def test_integration_frontend_chat_flow(self):
        """Integration test: typical frontend chat flow."""
        # Simulate a conversation
        conversation = [
            {
                "role": "user",
                "content": "I need a CRM",
                "response_source": "user_input",
                "isLoading": False,
            },
            {
                "role": "assistant",
                "content": "What industry?",
                "response_source": "llm",
                "isLoading": False,
                "choices": ["SaaS", "Healthcare"],
            },
            {
                "role": "user",
                "content": "SaaS",
                "response_source": "choice_selection",
                "isLoading": False,
                "choices": None,
            },
        ]

        # Build the request
        request_payload = {
            "messages": conversation,
            "generate_now": False,
            "crm_type": "sales_pipeline",
        }

        # Should not raise 422
        request = ChatRequest(**request_payload)
        assert len(request.messages) == 3
        assert request.messages[0].role == "user"
        assert request.messages[1].role == "assistant"
        assert request.messages[2].role == "user"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
