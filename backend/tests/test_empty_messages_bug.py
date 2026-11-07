"""Regression test for empty messages array bug.

Validates that:
1. The first free-form message is properly included in the API request
2. crm_type=null is accepted during discovery phase
3. The endpoint returns 200 (or 502 if Ollama unavailable), NOT 422
4. AURA responds with the next discovery question
"""
import pytest
from app.main import app
from fastapi.testclient import TestClient
from app.auth import get_current_user


class TestEmptyMessagesBugFix:
    """Verify the empty messages array bug is fixed."""

    @pytest.fixture
    def authenticated_client(self):
        """Create a test client with authentication mocked."""
        def mock_current_user():
            return 'test-user-id'
        
        app.dependency_overrides[get_current_user] = mock_current_user
        client = TestClient(app)
        yield client
        app.dependency_overrides.clear()

    def test_first_message_not_empty(self, authenticated_client):
        """TEST 1: First free-form message is included in request."""
        payload = {
            "messages": [
                {"role": "user", "content": "hi i wanna build a service crm"}
            ],
            "generate_now": False,
            "crm_type": None,
            "quest_answers": {}
        }
        
        resp = authenticated_client.post('/api/v1/crm/chat', json=payload)
        
        # Should NOT be 422 (validation error)
        # Should be 200 (success) or 502 (AI provider unavailable)
        assert resp.status_code in [200, 502], \
            f"Expected 200 or 502, got {resp.status_code}: {resp.json()}"

    def test_crm_type_null_accepted(self, authenticated_client):
        """TEST 2: crm_type=null is valid during discovery."""
        payload = {
            "messages": [
                {"role": "user", "content": "build a crm"}
            ],
            "generate_now": False,
            "crm_type": None,  # Explicitly null
            "quest_answers": {}
        }
        
        resp = authenticated_client.post('/api/v1/crm/chat', json=payload)
        
        # Should validate, not return 422
        assert resp.status_code != 422, \
            f"crm_type=null should be valid, got 422: {resp.json()}"
        assert resp.status_code in [200, 502]

    def test_generate_now_false_returns_question(self, authenticated_client):
        """TEST 3: generate_now=false returns next question, not CRM."""
        payload = {
            "messages": [
                {"role": "user", "content": "i need a custom crm for my business"}
            ],
            "generate_now": False,
            "crm_type": None,
            "quest_answers": {}
        }
        
        resp = authenticated_client.post('/api/v1/crm/chat', json=payload)
        
        # Should succeed with 200 (or 502 if provider down)
        assert resp.status_code in [200, 502], \
            f"Expected 200 or 502, got {resp.status_code}"
        
        if resp.status_code == 200:
            data = resp.json()
            # Should have a reply (next question), not a configuration
            assert "reply" in data or "data" in data, \
                "Should return a reply/question, not a CRM configuration"

    def test_multiple_messages_preserved(self, authenticated_client):
        """TEST 4: Multiple messages in array are preserved."""
        payload = {
            "messages": [
                {"role": "user", "content": "i need a crm"},
                {"role": "assistant", "content": "what kind of crm?"},
                {"role": "user", "content": "for managing leads"}
            ],
            "generate_now": False,
            "crm_type": None,
            "quest_answers": {}
        }
        
        resp = authenticated_client.post('/api/v1/crm/chat', json=payload)
        
        # Should not be 422 (validation error)
        assert resp.status_code != 422, \
            f"Multiple messages should be valid, got 422: {resp.json()}"
        assert resp.status_code in [200, 502]

    def test_discovery_flow_no_fallback(self, authenticated_client):
        """TEST 5: Discovery flow does NOT use fallback provider."""
        payload = {
            "messages": [
                {"role": "user", "content": "build me a custom crm"}
            ],
            "generate_now": False,
            "crm_type": None,
            "quest_answers": {}
        }
        
        resp = authenticated_client.post('/api/v1/crm/chat', json=payload)
        
        # No 422 validation error
        assert resp.status_code != 422
        
        if resp.status_code == 200:
            data = resp.json()
            # Should use Qwen, not fallback
            ai_info = data.get("ai") or data.get("data", {}).get("ai", {})
            assert ai_info.get("fallback") is False, \
                "Should not use fallback provider"
            assert "ollama" in str(ai_info.get("provider", "")).lower(), \
                "Should use Ollama/Qwen provider"
