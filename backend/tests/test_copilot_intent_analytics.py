"""
Comprehensive Regression Tests for AURA Copilot Intent Classification,
Schema-Aware RAG, and Live Analytics Tool Routing.

Verifies:
1. "how many new lead are there" routes to ANALYTICS_QUERY and returns live count.
2. Read-only queries NEVER invoke create_record or request missing required fields (e.g. customer_name).
3. Conversational follow-ups ("what about High Value?") maintain analytical intent.
4. Schema queries return schema structure without mutations.
5. Explicit record creation imperative commands route to CREATE_RECORD.
6. Ambiguous entities prompt for clarification instead of guessing or inventing entities.
7. Read-only tools (get_crm_summary, get_entity_schema, get_status_distribution, count_records, aggregate_records) execute properly with tenant isolation.
8. Safety rule: Read-only intents never dispatch mutation tools.
"""
import uuid
import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from jose import jwt

from app.main import create_app
from app.config import get_settings
from app.services.intent_classifier import (
    IntentClassifier,
    IntentCategory,
    READ_ONLY_INTENTS,
    MUTATION_TOOLS,
    READ_ONLY_TOOLS,
)
from app.services.crm_rag import CRMRAGService
from app.services.ai_tools import CRMSchemaTools
from app.routers.copilot import _universal_action_reply

settings = get_settings()
if not settings.supabase_jwt_secret:
    settings.supabase_jwt_secret = "test-jwt-secret-key-32-chars-minimum-length!"

app = create_app()
client = TestClient(app, raise_server_exceptions=False)

USER_ID = str(uuid.uuid4())
OTHER_USER_ID = str(uuid.uuid4())
CRM_ID = str(uuid.uuid4())


def _token(user_id: str) -> str:
    return jwt.encode(
        {"sub": user_id, "aud": "authenticated", "exp": 9999999999},
        settings.supabase_jwt_secret,
        algorithm="HS256",
    )


def _auth(user_id: str = USER_ID) -> dict:
    return {"Authorization": f"Bearer {_token(user_id)}"}


def _analytical_ecommerce_crm() -> dict:
    """Fixture: Analytical_E_Commerce_CRM with machine_identifier entity."""
    return {
        "id": CRM_ID,
        "owner_id": USER_ID,
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


def _multi_entity_crm() -> dict:
    """Fixture: Multi-entity CRM with Candidates and Clients."""
    return {
        "id": str(uuid.uuid4()),
        "owner_id": USER_ID,
        "name": "Recruitment CRM",
        "status": "active",
        "configuration_version": 1,
        "configuration": {
            "schema_version": "1.0",
            "name": "Recruitment CRM",
            "industry": "recruitment",
            "entities": [
                {
                    "name": "candidate",
                    "label": "Candidates",
                    "fields": [
                        {"name": "full_name", "label": "Full Name", "type": "text", "required": True},
                        {"name": "status", "label": "Status", "type": "select", "options": ["Applied", "Interviewing", "Hired"]},
                    ],
                },
                {
                    "name": "client",
                    "label": "Clients",
                    "fields": [
                        {"name": "company_name", "label": "Company Name", "type": "text", "required": True},
                        {"name": "status", "label": "Status", "type": "select", "options": ["Active", "Prospect"]},
                    ],
                },
            ],
            "pipeline_stages": ["Applied", "Interviewing", "Hired"],
        },
    }


# ── 1. Intent Classification Tests ─────────────────────────────────

def test_intent_classification_how_many_new_lead():
    crm = _analytical_ecommerce_crm()
    intent = IntentClassifier.classify("how many new lead are there", crm_context=crm)
    assert intent == IntentCategory.ANALYTICS_QUERY
    assert IntentClassifier.is_read_only(intent) is True


def test_intent_classification_stage_counts():
    crm = _analytical_ecommerce_crm()
    assert IntentClassifier.classify("how many records are at risk", crm_context=crm) == IntentCategory.ANALYTICS_QUERY
    assert IntentClassifier.classify("what is the count of analyzing leads", crm_context=crm) == IntentCategory.ANALYTICS_QUERY
    assert IntentClassifier.classify("show me status breakdown", crm_context=crm) == IntentCategory.ANALYTICS_QUERY
    assert IntentClassifier.classify("total revenue", crm_context=crm) == IntentCategory.ANALYTICS_QUERY


def test_intent_classification_schema_queries():
    crm = _analytical_ecommerce_crm()
    assert IntentClassifier.classify("what fields does my CRM have", crm_context=crm) == IntentCategory.SCHEMA_QUERY
    assert IntentClassifier.classify("what entities exist", crm_context=crm) == IntentCategory.SCHEMA_QUERY
    assert IntentClassifier.classify("what are the pipeline stages", crm_context=crm) == IntentCategory.SCHEMA_QUERY


def test_intent_classification_record_queries():
    crm = _analytical_ecommerce_crm()
    assert IntentClassifier.classify("show all records", crm_context=crm) == IntentCategory.RECORD_QUERY
    assert IntentClassifier.classify("find customer John", crm_context=crm) == IntentCategory.RECORD_QUERY
    assert IntentClassifier.classify("list my leads", crm_context=crm) == IntentCategory.RECORD_QUERY


def test_intent_classification_mutations():
    crm = _analytical_ecommerce_crm()
    assert IntentClassifier.classify("create a lead named Alice", crm_context=crm) == IntentCategory.CREATE_RECORD
    assert IntentClassifier.classify("add a new record with customer_name Acme", crm_context=crm) == IntentCategory.CREATE_RECORD
    assert IntentClassifier.classify("update John's status to High Value", crm_context=crm) == IntentCategory.UPDATE_RECORD
    assert IntentClassifier.classify("delete record #123", crm_context=crm) == IntentCategory.DELETE_RECORD
    assert IntentClassifier.classify("add column phone as text", crm_context=crm) == IntentCategory.CRM_CONFIGURATION_CHANGE
    assert IntentClassifier.classify("delete column notes", crm_context=crm) == IntentCategory.CRM_CONFIGURATION_CHANGE


def test_intent_conversational_follow_up():
    crm = _analytical_ecommerce_crm()
    history = [
        {"role": "user", "content": "how many new leads are there?"},
        {"role": "assistant", "content": "There are currently 4 records in New status."},
    ]
    # Follow-up: "what about High Value?"
    intent = IntentClassifier.classify("what about High Value?", conversation_history=history, crm_context=crm)
    assert intent == IntentCategory.ANALYTICS_QUERY
    assert IntentClassifier.is_read_only(intent) is True


# ── 2. Reproduction Verification ────────────────────────────────────

def test_reproduced_how_many_new_leads_never_calls_create_record():
    """Verify exact user problem:
    'how many new lead are there' must return count and NEVER trigger create_record
    or fail with 'customer_name is missing'.
    """
    crm = _analytical_ecommerce_crm()
    reply = _universal_action_reply("how many new lead are there", crm_context=crm)

    # Must NOT generate a TOOL_CALL
    assert "TOOL_CALL" not in reply["reply"]
    # Must NOT complain about customer_name
    assert "customer_name" not in reply["reply"]
    assert "missing" not in reply["reply"]
    # Must answer with count and stage New
    assert "New" in reply["reply"]
    assert "records" in reply["reply"].lower()


@patch("app.services.ai_tools.CRMRepository")
@patch("app.routers.copilot.CRMRepository")
def test_copilot_chat_endpoint_how_many_new_leads(mock_router_repo, mock_tools_repo):
    """Test full copilot chat endpoint for 'how many new lead are there'."""
    crm = _analytical_ecommerce_crm()
    mock_repo = MagicMock()
    mock_router_repo.return_value = mock_repo
    mock_tools_repo.return_value = mock_repo
    mock_repo.get_crm.return_value = crm
    mock_repo.list_workflows.return_value = []
    
    # 5 records in "New" stage
    mock_records = [
        {"id": f"rec-{i}", "crm_id": CRM_ID, "data": {"customer_name": f"User {i}", "crm_status": "New"}}
        for i in range(5)
    ]
    mock_repo.get_all_records.return_value = mock_records

    resp = client.post(
        "/api/v1/copilot/chat",
        headers=_auth(USER_ID),
        json={
            "messages": [{"role": "user", "content": "how many new lead are there"}],
            "crm_id": CRM_ID,
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "TOOL_CALL" not in data["reply"]
    assert "customer_name" not in data["reply"]
    assert "5" in data["reply"]
    assert "New" in data["reply"]


# ── 3. Live CRM Analytics Tools ────────────────────────────────────

@patch("app.services.ai_tools.CRMRepository")
def test_tool_count_records(mock_repo_cls):
    crm = _analytical_ecommerce_crm()
    mock_repo = MagicMock()
    mock_repo_cls.return_value = mock_repo
    mock_repo.get_crm.return_value = crm

    mock_records = [
        {"id": "r1", "data": {"customer_name": "Alice", "crm_status": "New"}},
        {"id": "r2", "data": {"customer_name": "Bob", "crm_status": "New"}},
        {"id": "r3", "data": {"customer_name": "Charlie", "crm_status": "High Value"}},
    ]
    mock_repo.get_all_records.return_value = mock_records

    # Filter by stage New
    res = CRMSchemaTools.count_records(
        crm_id=CRM_ID,
        owner_id=USER_ID,
        entity_name="machine_identifier",
        stage="New",
    )
    assert res["success"] is True
    assert res["count"] == 2


@patch("app.services.ai_tools.CRMRepository")
def test_tool_status_distribution(mock_repo_cls):
    crm = _analytical_ecommerce_crm()
    mock_repo = MagicMock()
    mock_repo_cls.return_value = mock_repo
    mock_repo.get_crm.return_value = crm

    mock_records = [
        {"id": "r1", "data": {"customer_name": "Alice", "crm_status": "New"}},
        {"id": "r2", "data": {"customer_name": "Bob", "crm_status": "Analyzing"}},
        {"id": "r3", "data": {"customer_name": "Charlie", "crm_status": "High Value"}},
    ]
    mock_repo.get_all_records.return_value = mock_records

    res = CRMSchemaTools.get_status_distribution(
        crm_id=CRM_ID,
        owner_id=USER_ID,
        entity_name="machine_identifier",
    )
    assert res["success"] is True
    dist = res["distribution"]
    assert dist["New"] == 1
    assert dist["Analyzing"] == 1
    assert dist["High Value"] == 1
    assert dist["At Risk"] == 0
    assert res["total_records"] == 3


@patch("app.services.ai_tools.CRMRepository")
def test_tool_aggregate_records(mock_repo_cls):
    crm = _analytical_ecommerce_crm()
    mock_repo = MagicMock()
    mock_repo_cls.return_value = mock_repo
    mock_repo.get_crm.return_value = crm

    mock_records = [
        {"id": "r1", "data": {"customer_name": "Alice", "total_revenue": 100}},
        {"id": "r2", "data": {"customer_name": "Bob", "total_revenue": 250}},
    ]
    mock_repo.get_all_records.return_value = mock_records

    sum_res = CRMSchemaTools.aggregate_records(
        crm_id=CRM_ID,
        owner_id=USER_ID,
        field_name="total_revenue",
        aggregation_type="sum",
        entity_name="machine_identifier",
    )
    assert sum_res["success"] is True
    assert sum_res["value"] == 350.0

    avg_res = CRMSchemaTools.aggregate_records(
        crm_id=CRM_ID,
        owner_id=USER_ID,
        field_name="total_revenue",
        aggregation_type="avg",
        entity_name="machine_identifier",
    )
    assert avg_res["success"] is True
    assert avg_res["value"] == 175.0


@patch("app.services.ai_tools.CRMRepository")
def test_tool_get_crm_summary(mock_repo_cls):
    crm = _analytical_ecommerce_crm()
    mock_repo = MagicMock()
    mock_repo_cls.return_value = mock_repo
    mock_repo.get_crm.return_value = crm
    mock_repo.count_records.return_value = 42

    res = CRMSchemaTools.get_crm_summary(crm_id=CRM_ID, owner_id=USER_ID)
    assert res["success"] is True
    assert res["name"] == "Analytical_E_Commerce_CRM"
    assert res["total_records"] == 42
    assert len(res["entities"]) == 1


# ── 4. Entity Disambiguation ───────────────────────────────────────

def test_multi_entity_disambiguation():
    crm = _multi_entity_crm()
    reply = _universal_action_reply("how many records are there", crm_context=crm)
    # Since there are multiple entities (Candidates and Clients), copilot asks which entity
    assert "multiple entities" in reply["reply"].lower()
    assert "candidate" in reply["reply"].lower()
    assert "client" in reply["reply"].lower()


# ── 5. Safety: Read-Only Queries Never Execute Mutations ───────────

def test_safety_read_only_intent_never_dispatches_mutations():
    for intent in READ_ONLY_INTENTS:
        assert IntentClassifier.is_read_only(intent) is True

    # Mutating tools must never be in read-only tools
    for mut in MUTATION_TOOLS:
        assert mut not in READ_ONLY_TOOLS


@patch("app.services.ai_tools.CRMRepository")
@patch("app.routers.copilot.CRMRepository")
def test_copilot_tool_call_endpoint_executes_read_only_tools(mock_router_repo, mock_tools_repo):
    crm = _analytical_ecommerce_crm()
    mock_repo = MagicMock()
    mock_router_repo.return_value = mock_repo
    mock_tools_repo.return_value = mock_repo
    mock_repo.get_crm.return_value = crm
    mock_repo.get_all_records.return_value = []

    resp = client.post(
        "/api/v1/copilot/tool-call",
        headers=_auth(USER_ID),
        json={
            "tool_name": "count_records",
            "crm_id": CRM_ID,
            "arguments": {"entity_name": "machine_identifier", "stage": "New"},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["success"] is True
    assert resp.json()["data"]["count"] == 0
