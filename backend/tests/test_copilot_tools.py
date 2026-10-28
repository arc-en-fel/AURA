"""Tests for AURA Copilot CRM schema modification tools (FEAT-004).

Tests cover:
- Tool execution via endpoint
- Authorization checks
- Input validation
- Successful schema modifications
- Error handling and response formats

NOTE: These tests require a working Supabase connection with users already seeded
in the auth.users table. The user IDs used in tests must exist in the database.
"""
import pytest
from fastapi.testclient import TestClient
from jose import jwt
import uuid
import json
import os

from app.main import create_app
from app.config import get_settings
from app.database import CRMRepository, get_supabase_client
from app.schemas.crm import CRMConfiguration

settings = get_settings()
if not settings.supabase_jwt_secret:
    settings.supabase_jwt_secret = "test-jwt-secret-key-32-chars-minimum-length!"

app = create_app()
client = TestClient(app)

# Use known test user IDs that should exist in auth.users table
# If these don't exist, tests will be skipped or fail gracefully
TEST_USER_A = os.getenv("TEST_USER_A_ID", "11111111-1111-1111-1111-111111111111")
TEST_USER_B = os.getenv("TEST_USER_B_ID", "22222222-2222-2222-2222-222222222222")


def create_valid_token(user_id: str) -> str:
    """Create a valid JWT token for testing."""
    payload = {
        "sub": user_id,
        "aud": "authenticated",
        "exp": 9999999999,
    }
    return jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")


def create_test_crm(owner_id: str) -> dict | None:
    """Create a test CRM and return its details. Returns None if user doesn't exist in DB."""
    repo = CRMRepository()
    config = {
        "schema_version": "1.0",
        "name": "Test CRM",
        "industry": "sales",
        "entities": [
            {
                "name": "lead",
                "label": "Lead",
                "fields": [
                    {"name": "name", "label": "Name", "type": "text", "required": True},
                    {"name": "email", "label": "Email", "type": "email", "required": False},
                    {"name": "status", "label": "Status", "type": "select", "required": True, "options": ["New", "Contacted", "Won"]},
                ]
            }
        ],
        "pipeline_stages": ["New", "Contacted", "Won"],
    }
    CRMConfiguration(**config)  # Validate
    try:
        crm = repo.create_crm(owner_id=owner_id, name="Test CRM", configuration=config)
        return crm
    except Exception as e:
        # User doesn't exist in auth.users table
        pytest.skip(f"Cannot create test CRM: {str(e)}. Test users may not exist in database.")


class TestToolCallEndpoint:
    """Tests for POST /api/v1/copilot/tool-call endpoint."""

    def test_unauthenticated_tool_call_rejected(self):
        """Unauthenticated requests to tool-call should return 401."""
        response = client.post("/api/v1/copilot/tool-call", json={
            "tool_name": "add_crm_field",
            "crm_id": str(uuid.uuid4()),
            "arguments": {}
        })
        assert response.status_code == 401
        err = response.json()
        assert err["error"]["code"] == "UNAUTHENTICATED"

    def test_invalid_tool_name_rejected(self):
        """Invalid tool names should return 400."""
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "nonexistent_tool",
            "crm_id": str(uuid.uuid4()),
            "arguments": {}
        })
        assert response.status_code == 400
        err = response.json()
        assert err["error"]["code"] == "INVALID_TOOL"

    def test_crm_not_found(self):
        """Calling a tool on a non-existent CRM should return 404."""
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        fake_crm_id = str(uuid.uuid4())
        
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "add_crm_field",
            "crm_id": fake_crm_id,
            "arguments": {
                "field_name": "test_field",
                "label": "Test Field",
            }
        })
        assert response.status_code == 404
        err = response.json()
        assert err["error"]["code"] == "NOT_FOUND"

    def test_unauthorized_user_cannot_call_tool(self):
        """User B should not be able to modify User A's CRM."""
        # Create CRM owned by TEST_USER_A
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        
        # Try to modify with TEST_USER_B token
        token_b = create_valid_token(TEST_USER_B)
        headers = {"Authorization": f"Bearer {token_b}"}
        
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "add_crm_field",
            "crm_id": str(crm["id"]),
            "arguments": {
                "field_name": "new_field",
                "label": "New Field",
            }
        })
        assert response.status_code == 404
        err = response.json()
        assert err["error"]["code"] == "NOT_FOUND"


class TestAddFieldTool:
    """Tests for add_crm_field tool."""

    def test_add_field_successfully(self):
        """Successfully add a field to a CRM."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "add_crm_field",
            "crm_id": str(crm["id"]),
            "arguments": {
                "field_name": "priority",
                "label": "Priority",
                "field_type": "select",
                "options": ["High", "Medium", "Low"],
                "required": False,
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["success"] is True
        assert data["data"]["crm_id"] == str(crm["id"])
        
        config = data["data"]["configuration"]
        entity = config["entities"][0]
        field_names = [f["name"] for f in entity["fields"]]
        assert "priority" in field_names
        
        # Verify new field has correct properties
        priority_field = next(f for f in entity["fields"] if f["name"] == "priority")
        assert priority_field["label"] == "Priority"
        assert priority_field["type"] == "select"
        assert set(priority_field["options"]) == {"High", "Medium", "Low"}

    def test_add_field_derives_label_from_name(self):
        """Label is derived from field_name if not provided."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "add_crm_field",
            "crm_id": str(crm["id"]),
            "arguments": {
                "field_name": "assigned_agent",
                # No label provided
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["success"] is True
        
        config = data["data"]["configuration"]
        entity = config["entities"][0]
        assigned_field = next(f for f in entity["fields"] if f["name"] == "assigned_agent")
        assert assigned_field["label"] == "Assigned Agent"  # Derived from field name

    def test_add_duplicate_field_fails(self):
        """Adding a field that already exists should fail with 409."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        # Try to add 'email' field which already exists
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "add_crm_field",
            "crm_id": str(crm["id"]),
            "arguments": {
                "field_name": "email",
                "label": "Email Address",
            }
        })
        assert response.status_code == 409
        err = response.json()
        assert err["error"]["code"] == "CONFLICT"
        assert "already exists" in err["error"]["message"]

    def test_add_invalid_field_name(self):
        """Invalid field names should be rejected."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        # Invalid field name (starts with number)
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "add_crm_field",
            "crm_id": str(crm["id"]),
            "arguments": {
                "field_name": "123invalid",
                "label": "Invalid",
            }
        })
        assert response.status_code == 422
        err = response.json()
        assert err["error"]["code"] == "VALIDATION_ERROR"


class TestUpdateFieldTool:
    """Tests for update_crm_field tool."""

    def test_update_field_label(self):
        """Update a field's label."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "update_crm_field",
            "crm_id": str(crm["id"]),
            "arguments": {
                "field_name": "email",
                "label": "Email Address (Updated)",
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["success"] is True
        
        config = data["data"]["configuration"]
        entity = config["entities"][0]
        email_field = next(f for f in entity["fields"] if f["name"] == "email")
        assert email_field["label"] == "Email Address (Updated)"

    def test_update_field_type(self):
        """Update a field's type."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "update_crm_field",
            "crm_id": str(crm["id"]),
            "arguments": {
                "field_name": "email",
                "field_type": "text",  # Change from email to text
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["success"] is True
        
        config = data["data"]["configuration"]
        entity = config["entities"][0]
        email_field = next(f for f in entity["fields"] if f["name"] == "email")
        assert email_field["type"] == "text"

    def test_update_nonexistent_field(self):
        """Updating a non-existent field should fail with 404."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "update_crm_field",
            "crm_id": str(crm["id"]),
            "arguments": {
                "field_name": "nonexistent_field",
                "label": "Something",
            }
        })
        assert response.status_code == 404
        err = response.json()
        assert err["error"]["code"] == "NOT_FOUND"


class TestDeleteFieldTool:
    """Tests for delete_crm_field tool."""

    def test_delete_field_successfully(self):
        """Successfully delete a field."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "delete_crm_field",
            "crm_id": str(crm["id"]),
            "arguments": {
                "field_name": "email",
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["success"] is True
        
        config = data["data"]["configuration"]
        entity = config["entities"][0]
        field_names = [f["name"] for f in entity["fields"]]
        assert "email" not in field_names

    def test_delete_nonexistent_field(self):
        """Deleting a non-existent field should fail with 404."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "delete_crm_field",
            "crm_id": str(crm["id"]),
            "arguments": {
                "field_name": "nonexistent_field",
            }
        })
        assert response.status_code == 404
        err = response.json()
        assert err["error"]["code"] == "NOT_FOUND"


class TestAddStageTool:
    """Tests for add_crm_stage tool."""

    def test_add_stage_successfully(self):
        """Successfully add a pipeline stage."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "add_crm_stage",
            "crm_id": str(crm["id"]),
            "arguments": {
                "stage_name": "Qualified",
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["success"] is True
        
        config = data["data"]["configuration"]
        assert "Qualified" in config["pipeline_stages"]

    def test_add_stage_at_position(self):
        """Add a stage at a specific position."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        # Add "Negotiation" at position 2 (between "Contacted" and "Won")
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "add_crm_stage",
            "crm_id": str(crm["id"]),
            "arguments": {
                "stage_name": "Negotiation",
                "position": 2,
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["success"] is True
        
        config = data["data"]["configuration"]
        stages = config["pipeline_stages"]
        assert stages[2] == "Negotiation"

    def test_add_duplicate_stage(self):
        """Adding a stage that already exists should fail."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "add_crm_stage",
            "crm_id": str(crm["id"]),
            "arguments": {
                "stage_name": "New",  # Already exists
            }
        })
        assert response.status_code == 409
        err = response.json()
        assert err["error"]["code"] == "CONFLICT"


class TestDeleteStageTool:
    """Tests for delete_crm_stage tool."""

    def test_delete_stage_successfully(self):
        """Successfully delete a pipeline stage."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "delete_crm_stage",
            "crm_id": str(crm["id"]),
            "arguments": {
                "stage_name": "Contacted",
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["success"] is True
        
        config = data["data"]["configuration"]
        assert "Contacted" not in config["pipeline_stages"]

    def test_delete_nonexistent_stage(self):
        """Deleting a non-existent stage should fail."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "delete_crm_stage",
            "crm_id": str(crm["id"]),
            "arguments": {
                "stage_name": "NonexistentStage",
            }
        })
        assert response.status_code == 404
        err = response.json()
        assert err["error"]["code"] == "NOT_FOUND"


class TestReorderFieldsTool:
    """Tests for reorder_crm_fields tool."""

    def test_reorder_fields_successfully(self):
        """Successfully reorder fields."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        # Reorder to: email, name, status
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "reorder_crm_fields",
            "crm_id": str(crm["id"]),
            "arguments": {
                "field_order": ["email", "name", "status"],
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["success"] is True
        
        config = data["data"]["configuration"]
        entity = config["entities"][0]
        field_order = [f["name"] for f in entity["fields"]]
        assert field_order == ["email", "name", "status"]

    def test_reorder_invalid_field_order(self):
        """Invalid field order (missing fields) should fail."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        # Missing 'name' field
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "reorder_crm_fields",
            "crm_id": str(crm["id"]),
            "arguments": {
                "field_order": ["email", "status"],
            }
        })
        assert response.status_code == 422
        err = response.json()
        assert err["error"]["code"] == "VALIDATION_ERROR"


class TestReorderStagesTool:
    """Tests for reorder_crm_stages tool."""

    def test_reorder_stages_successfully(self):
        """Successfully reorder pipeline stages."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        # Reorder to: Won, New, Contacted
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "reorder_crm_stages",
            "crm_id": str(crm["id"]),
            "arguments": {
                "stage_order": ["Won", "New", "Contacted"],
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["success"] is True
        
        config = data["data"]["configuration"]
        assert config["pipeline_stages"] == ["Won", "New", "Contacted"]

    def test_reorder_invalid_stage_order(self):
        """Invalid stage order should fail."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        # Missing 'Contacted' stage
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "reorder_crm_stages",
            "crm_id": str(crm["id"]),
            "arguments": {
                "stage_order": ["New", "Won"],
            }
        })
        assert response.status_code == 422
        err = response.json()
        assert err["error"]["code"] == "VALIDATION_ERROR"


class TestToolResultFormat:
    """Tests for tool response format compatibility."""

    def test_successful_tool_response_format(self):
        """Successful tool response includes all required fields."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "add_crm_field",
            "crm_id": str(crm["id"]),
            "arguments": {
                "field_name": "test_field",
                "label": "Test Field",
            }
        })
        
        data = response.json()
        tool_result = data["data"]
        
        # Check required fields
        assert "success" in tool_result
        assert tool_result["success"] is True
        assert "crm_id" in tool_result
        assert "configuration" in tool_result
        assert "configuration_version" in tool_result
        
        # Check configuration is valid
        assert isinstance(tool_result["configuration"], dict)
        assert "entities" in tool_result["configuration"]
        assert "pipeline_stages" in tool_result["configuration"]

    def test_failed_tool_response_format(self):
        """Failed tool response includes error fields."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        # Try to add duplicate field
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "add_crm_field",
            "crm_id": str(crm["id"]),
            "arguments": {
                "field_name": "email",  # Already exists
                "label": "Email",
            }
        })
        
        err = response.json()
        
        # Check error fields
        assert "error" in err
        assert "code" in err["error"]
        assert "message" in err["error"]
        assert "request_id" in err["error"]


class TestConfigurationVersionIncrement:
    """Tests that tool calls increment configuration_version."""

    def test_configuration_version_increments(self):
        """Each tool call increments configuration_version."""
        crm = create_test_crm(TEST_USER_A)
        if crm is None:
            pytest.skip("Could not create test CRM")
        initial_version = crm["configuration_version"]
        token = create_valid_token(TEST_USER_A)
        headers = {"Authorization": f"Bearer {token}"}
        
        response = client.post("/api/v1/copilot/tool-call", headers=headers, json={
            "tool_name": "add_crm_field",
            "crm_id": str(crm["id"]),
            "arguments": {
                "field_name": "test_field",
                "label": "Test Field",
            }
        })
        
        data = response.json()
        new_version = data["data"]["configuration_version"]
        assert new_version > initial_version
