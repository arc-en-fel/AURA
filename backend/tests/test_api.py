import pytest
from fastapi.testclient import TestClient
from jose import jwt
import uuid

from app.main import create_app
from app.config import get_settings

settings = get_settings()
# Set a test secret if not set
if not settings.supabase_jwt_secret:
    settings.supabase_jwt_secret = "test-jwt-secret-key-32-chars-minimum-length!"

app = create_app()
client = TestClient(app)

def create_valid_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "aud": "authenticated",
        "exp": 9999999999,
    }
    return jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")

def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert data["data"]["status"] == "ok"
    assert "meta" in data
    assert "request_id" in data["meta"]

def test_unauthenticated_requests_rejected():
    response = client.get("/api/v1/crm")
    assert response.status_code == 401
    err = response.json()
    assert "error" in err
    assert err["error"]["code"] == "UNAUTHENTICATED"

def test_invalid_token_rejected():
    headers = {"Authorization": "Bearer invalid.jwt.token"}
    response = client.get("/api/v1/crm", headers=headers)
    assert response.status_code == 401
    err = response.json()
    assert "error" in err
    assert err["error"]["code"] == "UNAUTHENTICATED"

def test_ai_generate_crm():
    user_id = str(uuid.uuid4())
    token = create_valid_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "prompt": "Create a CRM for real estate agents with properties and leads"
    }
    response = client.post("/api/v1/crm/generate", headers=headers, json=payload)
    # May return 200 if Ollama is reachable, or 502 if not
    # Both are acceptable for this test - we're checking the basic contract
    if response.status_code == 200:
        res = response.json()
        assert "data" in res
        assert "configuration" in res["data"]
        config = res["data"]["configuration"]
        assert "name" in config
        assert "entities" in config
        assert len(config["entities"]) > 0
    else:
        assert response.status_code == 502

def test_validation_service():
    from app.services.validation import validate_record_data
    from app.schemas.crm import CRMEntity, CRMField

    entity = CRMEntity(
        name="lead",
        label="Lead",
        fields=[
            CRMField(name="email", label="Email", type="email", required=True),
            CRMField(name="stage", label="Stage", type="select", options=["new", "won"], required=True),
            CRMField(name="age", label="Age", type="number", required=False),
        ]
    )

    # Valid data
    valid_data, errors = validate_record_data(entity, {"email": "test@example.com", "stage": "new", "age": 30})
    assert len(errors) == 0
    assert valid_data["email"] == "test@example.com"

    # Missing required field
    _, errors = validate_record_data(entity, {"stage": "new"})
    assert len(errors) == 1
    assert errors[0]["field"] == "email"

    # Invalid select option
    _, errors = validate_record_data(entity, {"email": "a@b.com", "stage": "invalid_option"})
    assert len(errors) == 1
    assert errors[0]["field"] == "stage"

    # Unknown field
    _, errors = validate_record_data(entity, {"email": "a@b.com", "stage": "new", "unknown_field": "val"})
    assert len(errors) == 1
    assert errors[0]["field"] == "unknown_field"

def test_workflow_trigger_contract_uses_type_field():
    from pathlib import Path
    from pydantic import ValidationError
    from app.schemas.crm import WorkflowTrigger
    contract = (Path(__file__).resolve().parents[2] / "docs" / "API_CONTRACTS.md").read_text(encoding="utf-8")
    assert '"trigger": {"type": "record.created", "entity": "lead"}' in contract
    assert WorkflowTrigger(type="record.created", entity="lead").type == "record.created"
    with pytest.raises(ValidationError):
        WorkflowTrigger(event="record.created", entity="lead")
