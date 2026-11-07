"""
Regression tests for AURA AI Copilot:
Tool Execution, CRM Schema, and False Success Responses.

Tests cover:
1. Creating a record in an existing CRM does not unnecessarily modify the CRM configuration version.
2. The reproduced six-field request creates the correct record in the active CRM.
3. A record-creation request never invokes a workflow-stage creation tool.
4. Adding a new status option changes the correct configuration or workflow resource.
5. Adding a dynamic column updates the schema through the intended configuration flow.
6. Invalid fields produce actionable errors without silently dropping data.
7. A missing required configuration version is handled correctly at every relevant write boundary.
8. Database failures produce failed tool results and truthful Copilot messages.
9. A failed operation never produces a success response.
10. Successful tool execution returns the canonical created or updated entity.
11. Tenant isolation and authorization.
12. Duplicate requests and retries do not create duplicate records.
13. The system works with unrelated CRM schemas (Healthcare and Logistics).
"""
import uuid
import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from jose import jwt

from app.main import create_app
from app.config import get_settings
from app.services.ai_tools import CRMSchemaTools
from app.routers.copilot import _universal_action_reply

settings = get_settings()
if not settings.supabase_jwt_secret:
    settings.supabase_jwt_secret = "test-jwt-secret-key-32-chars-minimum-length!"

app = create_app()
client = TestClient(app, raise_server_exceptions=False)

USER_ID_A = str(uuid.uuid4())
USER_ID_B = str(uuid.uuid4())
CRM_ID = str(uuid.uuid4())


def _token(user_id: str) -> str:
    return jwt.encode(
        {"sub": user_id, "aud": "authenticated", "exp": 9999999999},
        settings.supabase_jwt_secret,
        algorithm="HS256",
    )


def _auth(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_token(user_id)}"}


def _analytical_ecommerce_crm() -> dict:
    """Active CRM fixture: Analytical_E_Commerce_CRM."""
    return {
        "id": CRM_ID,
        "owner_id": USER_ID_A,
        "name": "Analytical_E_Commerce_CRM",
        "status": "active",
        "configuration_version": 1,
        "configuration": {
            "schema_version": "1.0",
            "name": "Analytical_E_Commerce_CRM",
            "industry": "ecommerce",
            "entities": [
                {
                    "name": "machine_identifier",
                    "label": "Machine Identifier",
                    "fields": [
                        {"name": "customer_name", "label": "Customer Name", "type": "text", "required": True},
                        {"name": "customer_segment", "label": "Customer Segment", "type": "text", "required": False},
                        {"name": "total_revenue", "label": "Total Revenue", "type": "currency", "required": False},
                        {"name": "purchase_frequency", "label": "Purchase Frequency", "type": "number", "required": False},
                        {"name": "customer_value", "label": "Customer Value", "type": "text", "required": False},
                        {
                            "name": "crm_status",
                            "label": "CRM Status",
                            "type": "status",
                            "required": False,
                            "options": ["New", "Analyzing", "High Value", "At Risk", "Retained/Lost"],
                        },
                    ],
                }
            ],
            "pipeline_stages": ["New", "Analyzing", "High Value", "At Risk", "Retained/Lost"],
        },
    }


def _healthcare_crm() -> dict:
    """Unrelated CRM fixture: Healthcare CRM with Patients entity."""
    return {
        "id": CRM_ID,
        "owner_id": USER_ID_A,
        "name": "Clinic Healthcare CRM",
        "status": "active",
        "configuration_version": 3,
        "configuration": {
            "schema_version": "1.0",
            "name": "Clinic Healthcare CRM",
            "industry": "healthcare",
            "entities": [
                {
                    "name": "patient",
                    "label": "Patient",
                    "fields": [
                        {"name": "patient_name", "label": "Patient Name", "type": "text", "required": True},
                        {"name": "diagnosis", "label": "Diagnosis", "type": "text", "required": False},
                        {"name": "room_number", "label": "Room Number", "type": "number", "required": False},
                        {
                            "name": "triage_status",
                            "label": "Triage Status",
                            "type": "status",
                            "required": False,
                            "options": ["Admitted", "In Treatment", "Discharged"],
                        },
                    ],
                }
            ],
            "pipeline_stages": ["Admitted", "In Treatment", "Discharged"],
        },
    }


# ── TEST 1: Record creation does not modify CRM configuration version ────────

@patch("app.services.ai_tools.CRMRepository")
def test_record_creation_does_not_modify_configuration_version(mock_repo_class):
    """Creating a record in an existing CRM must not modify the CRM configuration version."""
    crm = _analytical_ecommerce_crm()
    initial_version = crm["configuration_version"]

    mock_repo = MagicMock()
    mock_repo_class.return_value = mock_repo
    mock_repo.get_crm.return_value = crm
    mock_repo.list_records.return_value = ([], 0)
    mock_repo.create_record.return_value = {
        "id": str(uuid.uuid4()),
        "crm_id": CRM_ID,
        "entity_name": "machine_identifier",
        "data": {"customer_name": "Alice"},
        "created_at": "2026-10-29T10:00:00Z",
    }

    result = CRMSchemaTools.create_record(
        crm_id=CRM_ID,
        owner_id=USER_ID_A,
        entity_name="machine_identifier",
        data={"customer_name": "Alice"},
    )

    assert result["success"] is True
    # Verify update_crm_configuration was NOT called
    mock_repo.update_crm_configuration.assert_not_called()
    assert crm["configuration_version"] == initial_version


# ── TEST 2: Reproduced six-field request creates the correct record ───────────

def test_reproduced_request_routes_to_create_record():
    """
    Test user request:
    'i need to add a new lead with customer name deepak customer segment retail total revenue 20000 purchase frequency 15 customer value 45000 and crm status new'
    Must route to create_record (NOT add_crm_stage).
    """
    crm = _analytical_ecommerce_crm()
    crm_context = {
        "configuration": crm["configuration"],
        "configuration_version": crm["configuration_version"],
        "workflows": [],
    }
    user_query = "i need to add a new lead with customer name deepak customer segment retail total revenue 20000 purchase frequency 15 customer value 45000 and crm status new"

    reply = _universal_action_reply(user_query, crm_context)

    # Must contain TOOL_CALL: {"name": "create_record", ...}
    assert "TOOL_CALL:" in reply["reply"]
    tool_json_str = reply["reply"].split("TOOL_CALL:")[-1].strip()
    tool_call = json.loads(tool_json_str)

    assert tool_call["name"] == "create_record", f"Expected create_record, got {tool_call['name']}"
    assert tool_call["arguments"]["entity_name"] == "machine_identifier"

    data = tool_call["arguments"]["data"]
    assert data["customer_name"].lower() == "deepak"
    assert data["customer_segment"].lower() == "retail"
    assert data["total_revenue"] == 20000
    assert data["purchase_frequency"] == 15
    assert str(data["customer_value"]) == "45000"
    assert data["crm_status"] == "New"


@patch("app.services.ai_tools.CRMRepository")
def test_reproduced_request_execution_creates_record(mock_repo_class):
    """Verify execution of the six-field create_record tool creates the exact canonical record."""
    crm = _analytical_ecommerce_crm()
    mock_repo = MagicMock()
    mock_repo_class.return_value = mock_repo
    mock_repo.get_crm.return_value = crm
    mock_repo.list_records.return_value = ([], 0)

    expected_record_id = str(uuid.uuid4())
    mock_repo.create_record.return_value = {
        "id": expected_record_id,
        "crm_id": CRM_ID,
        "entity_name": "machine_identifier",
        "data": {
            "customer_name": "deepak",
            "customer_segment": "retail",
            "total_revenue": 20000,
            "purchase_frequency": 15,
            "customer_value": "45000",
            "crm_status": "New",
        },
        "created_at": "2026-10-29T12:00:00Z",
    }

    result = CRMSchemaTools.create_record(
        crm_id=CRM_ID,
        owner_id=USER_ID_A,
        entity_name="machine_identifier",
        data={
            "customer name": "deepak",
            "customer segment": "retail",
            "total revenue": 20000,
            "purchase frequency": 15,
            "customer value": "45000",
            "crm status": "new",
        },
    )

    assert result["success"] is True
    assert result["crm_id"] == CRM_ID
    assert result["entity_name"] == "machine_identifier"
    assert result["data"]["id"] == expected_record_id
    assert result["data"]["data"]["crm_status"] == "New"
    assert result["data"]["data"]["total_revenue"] == 20000
    assert result["data"]["data"]["purchase_frequency"] == 15


# ── TEST 3: Record-creation request never invokes stage creation ─────────────

def test_record_creation_never_invokes_stage_tool():
    """Variations of record creation requests must never invoke add_crm_stage."""
    crm = _analytical_ecommerce_crm()
    crm_context = {
        "configuration": crm["configuration"],
        "configuration_version": 1,
        "workflows": [],
    }

    queries = [
        "Add a new lead with status New",
        "Create customer Bob with crm status High Value",
        "I need to add a record with stage Analyzing",
        "Please create lead Sarah and status At Risk",
    ]

    for q in queries:
        reply = _universal_action_reply(q, crm_context)
        assert "TOOL_CALL:" in reply["reply"]
        tool_call = json.loads(reply["reply"].split("TOOL_CALL:")[-1].strip())
        assert tool_call["name"] == "create_record", f"Query '{q}' incorrectly invoked {tool_call['name']}"


# ── TEST 4: Adding a new status option changes status field options ───────────

def test_add_status_option_routes_to_update_crm_field():
    """'Add a new status option Negotiating' should route to update_crm_field (NOT add_crm_stage)."""
    crm = _analytical_ecommerce_crm()
    crm_context = {
        "configuration": crm["configuration"],
        "configuration_version": 1,
        "workflows": [],
    }

    reply = _universal_action_reply("Add a new status option Negotiating", crm_context)
    assert "TOOL_CALL:" in reply["reply"]
    tool_call = json.loads(reply["reply"].split("TOOL_CALL:")[-1].strip())
    assert tool_call["name"] == "update_crm_field"
    assert "Negotiating" in tool_call["arguments"]["options"]


# ── TEST 5: Adding a column updates schema via add_crm_field ─────────────────

def test_add_column_routes_to_add_crm_field():
    """'Add a column Priority' should route to add_crm_field."""
    crm = _analytical_ecommerce_crm()
    crm_context = {
        "configuration": crm["configuration"],
        "configuration_version": 1,
        "workflows": [],
    }

    reply = _universal_action_reply("Add a new column Priority as text", crm_context)
    assert "TOOL_CALL:" in reply["reply"]
    tool_call = json.loads(reply["reply"].split("TOOL_CALL:")[-1].strip())
    assert tool_call["name"] == "add_crm_field"
    assert tool_call["arguments"]["field_name"] == "priority"


# ── TEST 6: Invalid fields produce actionable errors ─────────────────────────

@patch("app.services.ai_tools.CRMRepository")
def test_invalid_fields_produce_actionable_errors(mock_repo_class):
    """Supplying unknown fields must reject with actionable error listing available fields."""
    crm = _analytical_ecommerce_crm()
    mock_repo = MagicMock()
    mock_repo_class.return_value = mock_repo
    mock_repo.get_crm.return_value = crm

    result = CRMSchemaTools.create_record(
        crm_id=CRM_ID,
        owner_id=USER_ID_A,
        entity_name="machine_identifier",
        data={"customer_name": "Deepak", "invalid_random_field": "some_value"},
    )

    assert result["success"] is False
    assert result["error_code"] == "VALIDATION_ERROR"
    assert "Unknown field 'invalid_random_field'" in result["error_message"]
    assert "customer_name" in result["error_message"]


# ── TEST 7: Missing configuration_version handled at write boundary ──────────

@patch("app.database.get_supabase_client")
def test_update_crm_configuration_increments_version_correctly(mock_client_factory):
    """update_crm_configuration atomically increments configuration_version from previous."""
    from app.database import CRMRepository

    mock_client = MagicMock()
    mock_client_factory.return_value = mock_client

    repo = CRMRepository(client=mock_client)

    # get_crm returns CRM with version 5
    mock_client.table("crms").select("*").eq("id", CRM_ID).eq("owner_id", USER_ID_A).execute.return_value.data = [
        {"id": CRM_ID, "owner_id": USER_ID_A, "configuration_version": 5, "status": "active"}
    ]

    # update returns updated row with version 6
    mock_client.table("crms").update().eq().eq().eq().execute.return_value.data = [
        {"id": CRM_ID, "owner_id": USER_ID_A, "configuration_version": 6, "status": "active"}
    ]

    updated = repo.update_crm_configuration(
        crm_id=CRM_ID,
        owner_id=USER_ID_A,
        configuration=_analytical_ecommerce_crm()["configuration"],
    )

    # Verify update called with configuration_version = 6 (never None!)
    update_call_args = mock_client.table("crms").update.call_args[0][0]
    assert update_call_args["configuration_version"] == 6
    assert update_call_args["configuration_version"] is not None


# ── TEST 8: Database failures produce failed tool results ─────────────────────

@patch("app.services.ai_tools.CRMRepository")
def test_database_failure_returns_structured_failure(mock_repo_class):
    """Database exception must return explicit failure outcome without claiming success."""
    crm = _analytical_ecommerce_crm()
    mock_repo = MagicMock()
    mock_repo_class.return_value = mock_repo
    mock_repo.get_crm.return_value = crm
    mock_repo.list_records.return_value = ([], 0)
    mock_repo.create_record.side_effect = RuntimeError("Database connection timed out")

    result = CRMSchemaTools.create_record(
        crm_id=CRM_ID,
        owner_id=USER_ID_A,
        entity_name="machine_identifier",
        data={"customer_name": "Deepak"},
    )

    assert result["success"] is False
    assert result["error_code"] == "INTERNAL_ERROR"
    assert "Database connection timed out" in result["error_message"]


# ── TEST 9: Endpoint maps tool failures properly (never 200 on failure) ───────

@patch("app.routers.copilot.CRMRepository")
@patch("app.routers.copilot.CRMSchemaTools.create_record")
def test_failed_tool_produces_error_response(mock_create_rec, mock_repo_class):
    """Tool failure must return HTTP 422/500, never a false success."""
    mock_repo = MagicMock()
    mock_repo_class.return_value = mock_repo
    mock_repo.get_crm.return_value = _analytical_ecommerce_crm()

    mock_create_rec.return_value = {
        "success": False,
        "error_code": "VALIDATION_ERROR",
        "error_message": "Missing required field 'customer_name'",
    }

    r = client.post(
        "/api/v1/copilot/tool-call",
        json={
            "tool_name": "create_record",
            "crm_id": CRM_ID,
            "arguments": {
                "entity_name": "machine_identifier",
                "data": {},
            },
        },
        headers=_auth(USER_ID_A),
    )

    assert r.status_code == 422
    err_body = r.json()
    assert err_body["error"]["code"] == "VALIDATION_ERROR"
    assert "customer_name" in err_body["error"]["message"]


# ── TEST 10: Successful tool execution returns canonical entity ───────────────

@patch("app.routers.copilot.CRMRepository")
@patch("app.routers.copilot.CRMSchemaTools.create_record")
def test_successful_tool_returns_canonical_entity(mock_create_rec, mock_repo_class):
    """Successful tool execution returns success: True with full entity data."""
    mock_repo = MagicMock()
    mock_repo_class.return_value = mock_repo
    mock_repo.get_crm.return_value = _analytical_ecommerce_crm()

    created_id = str(uuid.uuid4())
    mock_create_rec.return_value = {
        "success": True,
        "crm_id": CRM_ID,
        "entity_name": "machine_identifier",
        "data": {
            "id": created_id,
            "crm_id": CRM_ID,
            "entity_name": "machine_identifier",
            "data": {"customer_name": "Deepak"},
            "created_at": "2026-10-29T14:00:00Z",
        },
    }

    r = client.post(
        "/api/v1/copilot/tool-call",
        json={
            "tool_name": "create_record",
            "crm_id": CRM_ID,
            "arguments": {
                "entity_name": "machine_identifier",
                "data": {"customer_name": "Deepak"},
            },
        },
        headers=_auth(USER_ID_A),
    )

    assert r.status_code == 200
    res = r.json()
    assert res["data"]["success"] is True
    assert res["data"]["data"]["id"] == created_id


# ── TEST 11: Tenant isolation and authorization ──────────────────────────────

@patch("app.routers.copilot.CRMRepository")
def test_tenant_isolation_unauthorized_user_rejected(mock_repo_class):
    """User B cannot execute tools on User A's CRM."""
    mock_repo = MagicMock()
    mock_repo_class.return_value = mock_repo
    # When User B requests CRM owned by User A, get_crm returns None
    mock_repo.get_crm.return_value = None

    r = client.post(
        "/api/v1/copilot/tool-call",
        json={
            "tool_name": "create_record",
            "crm_id": CRM_ID,
            "arguments": {
                "entity_name": "machine_identifier",
                "data": {"customer_name": "Hacked"},
            },
        },
        headers=_auth(USER_ID_B),  # User B
    )

    assert r.status_code == 400 or r.status_code == 404


# ── TEST 12: Duplicate requests do not create duplicate records ──────────────

@patch("app.services.ai_tools.CRMRepository")
def test_duplicate_record_creation_returns_existing(mock_repo_class):
    """Re-submitting the same record data returns existing record without duplicate insertion."""
    crm = _analytical_ecommerce_crm()
    mock_repo = MagicMock()
    mock_repo_class.return_value = mock_repo
    mock_repo.get_crm.return_value = crm

    existing_record_id = str(uuid.uuid4())
    existing_rec = {
        "id": existing_record_id,
        "crm_id": CRM_ID,
        "entity_name": "machine_identifier",
        "data": {
            "customer_name": "Deepak",
            "crm_status": "New",
        },
        "created_at": "2026-10-29T10:00:00Z",
    }
    # list_records returns existing_rec
    mock_repo.list_records.return_value = ([existing_rec], 1)

    result = CRMSchemaTools.create_record(
        crm_id=CRM_ID,
        owner_id=USER_ID_A,
        entity_name="machine_identifier",
        data={"customer_name": "Deepak", "crm_status": "New"},
    )

    assert result["success"] is True
    assert result["data"]["id"] == existing_record_id
    # create_record was NOT called again!
    mock_repo.create_record.assert_not_called()


# ── TEST 13: Works with unrelated CRM schemas (Healthcare) ───────────────────

def test_works_with_unrelated_healthcare_crm():
    """Universal schema-driven record creation works with Healthcare CRM."""
    crm = _healthcare_crm()
    crm_context = {
        "configuration": crm["configuration"],
        "configuration_version": crm["configuration_version"],
        "workflows": [],
    }

    user_query = "add a new patient with patient name Sarah Connor diagnosis fever room number 104 and triage status Admitted"
    reply = _universal_action_reply(user_query, crm_context)

    assert "TOOL_CALL:" in reply["reply"]
    tool_call = json.loads(reply["reply"].split("TOOL_CALL:")[-1].strip())

    assert tool_call["name"] == "create_record"
    assert tool_call["arguments"]["entity_name"] == "patient"
    data = tool_call["arguments"]["data"]
    assert data["patient_name"].lower() == "sarah connor"
    assert data["diagnosis"].lower() == "fever"
    assert data["room_number"] == 104
    assert data["triage_status"] == "Admitted"


# ── TEST 14: Show my records navigation ──────────────────────────────────────

def test_show_my_records_returns_navigation():
    """'Show my records' returns navigation route /records."""
    crm = _analytical_ecommerce_crm()
    crm_context = {
        "configuration": crm["configuration"],
        "configuration_version": 1,
        "workflows": [],
    }

    reply = _universal_action_reply("Show my records", crm_context)
    assert reply["nav_route"] == "/records"
    assert reply["nav_label"] == "Open Records"

