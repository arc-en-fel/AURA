"""
Tests for AURA Copilot Entity Resolution Fixes

Tests the root causes fixed:
- RC-001: Silent entity fallback
- RC-002: Hardcoded entity names in system prompt
- RC-003: Missing explicit entity list in CRM context
- RC-004: No entity validation before tool execution

Test scenarios:
- TS-001: CRM with Lead entity → "add a lead" → correct entity used
- TS-002: CRM with Contact but no Lead → "add a lead" → clarification requested
- TS-004: CRM with only Machine Identifier entity → "add a lead" → entity mismatch explained
- TS-010: LLM returns hardcoded entity name not in CRM → backend rejects with suggestions
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from jose import jwt

from app.main import create_app
from app.config import get_settings

settings = get_settings()
if not settings.supabase_jwt_secret:
    settings.supabase_jwt_secret = "test-jwt-secret-key-32-chars-minimum-length!"

app = create_app()
client = TestClient(app, raise_server_exceptions=False)

USER_ID = str(uuid.uuid4())
CRM_ID_WITH_LEAD = str(uuid.uuid4())
CRM_ID_WITHOUT_LEAD = str(uuid.uuid4())
CRM_ID_MACHINE_ONLY = str(uuid.uuid4())


def _token(user_id: str) -> str:
    return jwt.encode(
        {"sub": user_id, "aud": "authenticated", "exp": 9999999999},
        settings.supabase_jwt_secret,
        algorithm="HS256",
    )


def _auth(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_token(user_id)}"}


def _crm_with_lead():
    """CRM with Lead and Contact entities."""
    return {
        "id": CRM_ID_WITH_LEAD,
        "owner_id": USER_ID,
        "name": "Sales CRM with Lead",
        "configuration": {
            "schema_version": "1.0",
            "name": "Sales CRM with Lead",
            "industry": "saas",
            "entities": [
                {
                    "name": "lead",
                    "label": "Lead",
                    "fields": [
                        {"name": "name", "label": "Name", "type": "text", "required": True},
                        {"name": "email", "label": "Email", "type": "email", "required": False},
                    ],
                },
                {
                    "name": "contact",
                    "label": "Contact",
                    "fields": [
                        {"name": "name", "label": "Name", "type": "text", "required": True},
                    ],
                },
            ],
            "pipeline_stages": ["New", "Contacted", "Won"],
        },
        "configuration_version": 1,
    }


def _crm_without_lead():
    """CRM with Contact but no Lead entity."""
    return {
        "id": CRM_ID_WITHOUT_LEAD,
        "owner_id": USER_ID,
        "name": "Service CRM without Lead",
        "configuration": {
            "schema_version": "1.0",
            "name": "Service CRM without Lead",
            "industry": "service",
            "entities": [
                {
                    "name": "contact",
                    "label": "Contact",
                    "fields": [
                        {"name": "name", "label": "Name", "type": "text", "required": True},
                    ],
                },
                {
                    "name": "ticket",
                    "label": "Support Ticket",
                    "fields": [
                        {"name": "subject", "label": "Subject", "type": "text", "required": True},
                    ],
                },
            ],
            "pipeline_stages": ["Open", "In Progress", "Closed"],
        },
        "configuration_version": 1,
    }


def _crm_machine_only():
    """CRM with only Machine Identifier entity (no Lead, Contact, etc.)."""
    return {
        "id": CRM_ID_MACHINE_ONLY,
        "owner_id": USER_ID,
        "name": "Machine CRM",
        "configuration": {
            "schema_version": "1.0",
            "name": "Machine CRM",
            "industry": "inventory",
            "entities": [
                {
                    "name": "machine_identifier",
                    "label": "Machine ID",
                    "fields": [
                        {"name": "serial_number", "label": "Serial Number", "type": "text", "required": True},
                        {"name": "model", "label": "Model", "type": "text", "required": False},
                    ],
                },
            ],
            "pipeline_stages": ["Registered", "Active", "Retired"],
        },
        "configuration_version": 1,
    }


# ── TS-001: CRM with Lead entity → "add a lead" → correct entity used ────

@patch("app.routers.copilot.CRMRepository")
def test_ts001_system_prompt_includes_valid_entity_names(mock_repo_class):
    """
    RC-002, RC-003: System prompt should include actual entity names from CRM.
    When user says 'add a lead' and CRM has a lead entity, copilot should use it.
    """
    mock_repo = MagicMock()
    mock_repo_class.return_value = mock_repo
    mock_repo.get_crm.return_value = _crm_with_lead()
    mock_repo.list_workflows.return_value = []

    # Test that system prompt is built with CRM context
    from app.routers.copilot import _build_system_prompt
    
    crm = _crm_with_lead()
    crm_context = {
        "configuration": crm["configuration"],
        "configuration_version": 1,
        "workflows": [],
    }
    
    system = _build_system_prompt(crm_context)
    
    # RC-003: Check that VALID ENTITY NAMES is explicitly listed
    assert "VALID ENTITY NAMES:" in system, "System prompt should include VALID ENTITY NAMES section"
    assert "lead (Lead)" in system, "System prompt should list 'lead (Lead)' entity"
    assert "contact (Contact)" in system, "System prompt should list 'contact (Contact)' entity"
    
    # RC-002: Should NOT have hardcoded examples with assumed entity names
    # The system prompt should guide LLM to use the actual entities from the list
    assert "MUST be from VALID ENTITY NAMES" in system, "Prompt should emphasize valid entity names"


# ── TS-002: CRM with Contact but no Lead → "add a lead" → clarification ────

@patch("app.routers.copilot.CRMRepository")
def test_ts002_invalid_entity_returns_available_options(mock_repo_class):
    """
    RC-001, RC-004: When LLM generates entity_name='lead' but CRM only has contact,
    backend should reject with available entities, not silently create in wrong entity.
    """
    mock_repo = MagicMock()
    mock_repo_class.return_value = mock_repo
    mock_repo.get_crm.return_value = _crm_without_lead()

    # Call tool with entity_name='lead' (which doesn't exist in this CRM)
    r = client.post(
        "/api/v1/copilot/tool-call",
        json={
            "tool_name": "create_record",
            "crm_id": CRM_ID_WITHOUT_LEAD,
            "arguments": {
                "entity_name": "lead",
                "data": {"name": "John"},
            },
        },
        headers=_auth(USER_ID),
    )

    # Should return 400 with error explaining entity not found
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.json()}"
    error = r.json()
    assert error["error"]["code"] == "INVALID_ENTITY"
    assert "lead" in error["error"]["message"].lower()
    
    # Error should list available entities
    assert "contact" in error["error"]["message"].lower()
    assert "ticket" in error["error"]["message"].lower()


# ── TS-004: CRM with only Machine Identifier → "add a lead" → mismatch ────

@patch("app.routers.copilot.CRMRepository")
def test_ts004_entity_mismatch_suggests_alternatives(mock_repo_class):
    """
    RC-004: When user requests 'lead' but CRM has only 'machine_identifier',
    backend should reject with clear error, not silently create in machine_identifier.
    """
    mock_repo = MagicMock()
    mock_repo_class.return_value = mock_repo
    mock_repo.get_crm.return_value = _crm_machine_only()

    r = client.post(
        "/api/v1/copilot/tool-call",
        json={
            "tool_name": "create_record",
            "crm_id": CRM_ID_MACHINE_ONLY,
            "arguments": {
                "entity_name": "lead",
                "data": {"serial_number": "ABC123"},
            },
        },
        headers=_auth(USER_ID),
    )

    # Should reject with clear error
    assert r.status_code == 400
    error = r.json()
    assert "lead" in error["error"]["message"].lower()
    assert "machine_identifier" in error["error"]["message"].lower() or "Machine ID" in error["error"]["message"]


# ── TS-010: LLM returns hardcoded entity name not in CRM ────

@patch("app.routers.copilot.CRMRepository")
def test_ts010_entity_validation_before_execution(mock_repo_class):
    """
    RC-004: Entity names are validated BEFORE tool execution.
    Invalid entity names are rejected with available entities listed.
    """
    mock_repo = MagicMock()
    mock_repo_class.return_value = mock_repo
    mock_repo.get_crm.return_value = _crm_without_lead()

    # Try to create record with hardcoded entity name 'customer' that doesn't exist
    r = client.post(
        "/api/v1/copilot/tool-call",
        json={
            "tool_name": "create_record",
            "crm_id": CRM_ID_WITHOUT_LEAD,
            "arguments": {
                "entity_name": "customer",
                "data": {"name": "Bob"},
            },
        },
        headers=_auth(USER_ID),
    )

    # Should fail with validation error
    assert r.status_code == 400
    error = r.json()
    assert error["error"]["code"] == "INVALID_ENTITY"
    assert "customer" in error["error"]["message"].lower()
    
    # Should suggest available entities
    assert "contact" in error["error"]["message"].lower() or "Contact" in error["error"]["message"]


# ── RC-001 Fix: Silent fallback eliminated ────

@patch("app.routers.copilot.CRMRepository")
def test_rc001_no_silent_fallback_to_first_entity(mock_repo_class):
    """
    RC-001: _resolve_entity should return None (not entities[0]) when no match found.
    This ensures explicit entity selection instead of silent fallback.
    """
    from app.services.ai_tools import CRMSchemaTools
    
    config = _crm_with_lead()["configuration"]
    
    # Test 1: No entity identifier → should return None, not entities[0]
    result = CRMSchemaTools._resolve_entity(config, None)
    assert result is None, "RC-001: _resolve_entity should return None for None input, not entities[0]"
    
    # Test 2: Invalid entity name → should return None, not entities[0]
    result = CRMSchemaTools._resolve_entity(config, "nonexistent_entity")
    assert result is None, "RC-001: _resolve_entity should return None for invalid entity, not entities[0]"
    
    # Test 3: Valid entity → should return the entity
    result = CRMSchemaTools._resolve_entity(config, "lead")
    assert result is not None
    assert result["name"] == "lead"


# ── RC-003 Fix: Explicit entity names in system prompt ────

@patch("app.routers.copilot.CRMRepository")
def test_rc003_explicit_valid_entity_names_section(mock_repo_class):
    """
    RC-003: System prompt should have explicit "VALID ENTITY NAMES: ..." section.
    This gives LLM a clear list of valid entities to use.
    """
    from app.routers.copilot import _build_system_prompt
    
    crm_context = {
        "configuration": _crm_with_lead()["configuration"],
        "configuration_version": 1,
        "workflows": [],
    }
    
    system = _build_system_prompt(crm_context)
    
    # Check for explicit VALID ENTITY NAMES section
    assert "VALID ENTITY NAMES:" in system
    
    # Should list all entities in that section
    lines = system.split("\n")
    entity_section_idx = None
    for i, line in enumerate(lines):
        if "VALID ENTITY NAMES:" in line:
            entity_section_idx = i
            break
    
    assert entity_section_idx is not None
    entity_line = lines[entity_section_idx]
    
    # Both entities should be in the valid names line
    assert "lead" in entity_line.lower()
    assert "contact" in entity_line.lower()


# ── System Prompt Content Validation ────

@patch("app.routers.copilot.CRMRepository")
def test_system_prompt_includes_entity_resolution_rules(mock_repo_class):
    """
    RC-002, RC-003: System prompt should include clear entity resolution rules.
    """
    from app.routers.copilot import _build_system_prompt
    
    crm_context = {
        "configuration": _crm_with_lead()["configuration"],
        "configuration_version": 1,
        "workflows": [],
    }
    
    system = _build_system_prompt(crm_context)
    
    # Should include entity resolution section
    assert "ENTITY RESOLUTION" in system
    
    # Should emphasize never using invalid entity names
    assert "NEVER use an entity name that is NOT" in system or "NEVER" in system
    
    # Should instruct LLM to match against valid list
    assert "VALID ENTITY NAMES" in system


@patch("app.routers.copilot.CRMRepository")
def test_system_prompt_includes_required_fields_info(mock_repo_class):
    """
    RC-007 (future): System prompt should include required field information
    so LLM knows which fields must be collected.
    """
    from app.routers.copilot import _build_system_prompt
    
    crm_context = {
        "configuration": _crm_with_lead()["configuration"],
        "configuration_version": 1,
        "workflows": [],
    }
    
    system = _build_system_prompt(crm_context)
    
    # Should mention required fields in entity details
    # Lead has required 'name' field
    assert "required:" in system or "Name" in system
