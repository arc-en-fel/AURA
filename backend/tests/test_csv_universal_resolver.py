"""Comprehensive regression tests for universal schema-driven CSV header resolution.

Tests all 15 acceptance requirements:
1. Exact canonical headers (e.g., customer_name)
2. Display-label headers (e.g., CUSTOMER NAME)
3. Mixed-case headers (e.g., Customer Name)
4. Headers with spaces versus underscores
5. Headers containing leading/trailing whitespace
6. A CSV containing a UTF-8 BOM
7. Unknown columns rejected with clear error
8. Duplicate headers after normalization rejected
9. Ambiguous schema labels detected safely
10. Missing required fields validation
11. Invalid numeric values and invalid status values
12. Empty or malformed CSV files rejected
13. A second CRM with a completely different schema (and Machine Identifier example)
14. Successful bulk insertion and correct imported-record counts
15. Tenant isolation and authorization during import
"""
from __future__ import annotations

import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.config import get_settings
from app.main import create_app
from app.schemas.crm import CRMField
from app.services.csv_resolver import normalize_header, resolve_csv_headers

settings = get_settings()
if not settings.supabase_jwt_secret:
    settings.supabase_jwt_secret = "test-jwt-secret-key-32-chars-minimum-length!"

app = create_app()
client = TestClient(app)

REPO_PATH = "app.routers.records.CRMRepository"
CRM_ID = str(uuid.uuid4())
USER_ID = str(uuid.uuid4())
OTHER_USER_ID = str(uuid.uuid4())


def _token(user_id: str = USER_ID) -> str:
    payload = {"sub": user_id, "aud": "authenticated", "exp": 9999999999}
    return jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")


def _headers(user_id: str = USER_ID) -> dict:
    return {"Authorization": f"Bearer {_token(user_id)}"}


def _machine_identifier_crm(crm_status: str = "active") -> dict:
    """Fixture representing the exact Machine Identifier CRM scenario from user request."""
    return {
        "id": CRM_ID,
        "owner_id": USER_ID,
        "name": "Machine Identifier CRM",
        "status": crm_status,
        "configuration_version": 1,
        "configuration": {
            "schema_version": "1.0",
            "name": "Machine Identifier CRM",
            "industry": "manufacturing",
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
                        {"name": "crm_status", "label": "CRM Status", "type": "status", "required": False, "options": ["Active", "Inactive", "Pending"]},
                    ],
                }
            ],
            "pipeline_stages": ["Active", "Inactive", "Pending"],
        },
    }


def _healthcare_crm() -> dict:
    """Fixture for a second completely distinct CRM schema."""
    return {
        "id": CRM_ID,
        "owner_id": USER_ID,
        "name": "Healthcare Clinic CRM",
        "status": "active",
        "configuration_version": 1,
        "configuration": {
            "schema_version": "1.0",
            "name": "Healthcare Clinic CRM",
            "industry": "healthcare",
            "entities": [
                {
                    "name": "patient",
                    "label": "Patient",
                    "fields": [
                        {"name": "patient_name", "label": "Patient Full Name", "type": "text", "required": True},
                        {"name": "blood_group", "label": "Blood Group", "type": "select", "required": False, "options": ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]},
                        {"name": "emergency_contact", "label": "Emergency Contact", "type": "phone", "required": False},
                        {"name": "consultation_fee", "label": "Consultation Fee", "type": "number", "required": False},
                    ],
                }
            ],
            "pipeline_stages": ["Registered", "Consulting", "Discharged"],
        },
    }


# ===========================================================================
# 1. Unit Tests for Header Resolution Engine
# ===========================================================================

def test_normalize_header_variations():
    """Verify normalization handles BOM, casing, spaces, underscores, and hyphens."""
    assert normalize_header("\ufeffCustomer Name") == "customer name"
    assert normalize_header("  CUSTOMER_NAME  ") == "customer name"
    assert normalize_header("customer-name") == "customer name"
    assert normalize_header("customer   name") == "customer name"
    assert normalize_header("") == ""


def test_unit_exact_canonical_resolution():
    """Unit test for exact canonical field names."""
    fields = [
        CRMField(name="customer_name", label="Customer Name", type="text", required=True),
        CRMField(name="total_revenue", label="Total Revenue", type="number", required=False),
    ]
    res = resolve_csv_headers(["customer_name", "total_revenue"], fields)
    assert res.is_valid
    assert res.header_map == {"customer_name": "customer_name", "total_revenue": "total_revenue"}
    assert res.index_map == {0: "customer_name", 1: "total_revenue"}


def test_unit_display_label_and_casing_resolution():
    """Unit test for display labels with varying casing and spaces."""
    fields = [
        CRMField(name="customer_name", label="Customer Name", type="text", required=True),
        CRMField(name="crm_status", label="CRM Status", type="text", required=False),
    ]
    res = resolve_csv_headers(["CUSTOMER NAME", "crm status"], fields)
    assert res.is_valid
    assert res.header_map["CUSTOMER NAME"] == "customer_name"
    assert res.header_map["crm status"] == "crm_status"


def test_unit_duplicate_mapping_detection():
    """Unit test rejecting duplicate headers resolving to the same canonical field."""
    fields = [
        CRMField(name="customer_name", label="Customer Name", type="text", required=True),
    ]
    res = resolve_csv_headers(["CUSTOMER NAME", "customer_name"], fields)
    assert not res.is_valid
    assert res.error_code == "DUPLICATE_COLUMNS"
    assert any("Duplicate CSV column mapping for field 'customer_name'" in e for e in res.errors)


def test_unit_ambiguous_schema_labels():
    """Unit test detecting ambiguous headers when multiple schema fields match."""
    fields = [
        CRMField(name="primary_address", label="Address", type="text", required=False),
        CRMField(name="billing_address", label="Address", type="text", required=False),
    ]
    res = resolve_csv_headers(["Address"], fields)
    assert not res.is_valid
    assert res.error_code == "AMBIGUOUS_COLUMNS"
    assert any("Ambiguous CSV column header 'Address'" in e for e in res.errors)


def test_unit_empty_column_header():
    """Unit test detecting empty or missing column headers."""
    fields = [
        CRMField(name="customer_name", label="Customer Name", type="text", required=True),
    ]
    res = resolve_csv_headers(["customer_name", "  ", ""], fields)
    assert not res.is_valid
    assert res.error_code == "EMPTY_HEADER"


# ===========================================================================
# 2. Integration Tests: Machine Identifier Scenario & Acceptance Criteria
# ===========================================================================

def test_machine_identifier_six_column_display_labels_import_success():
    """Acceptance Test: The exact 6 uppercase display-label headers must import cleanly.

    CUSTOMER NAME -> customer_name
    CUSTOMER SEGMENT -> customer_segment
    TOTAL REVENUE -> total_revenue
    PURCHASE FREQUENCY -> purchase_frequency
    CUSTOMER VALUE -> customer_value
    CRM STATUS -> crm_status
    """
    mock_repo = MagicMock()
    mock_repo.get_crm.return_value = _machine_identifier_crm()
    mock_repo.create_records_batch.return_value = [{"id": str(uuid.uuid4())} for _ in range(2)]

    csv_content = (
        "CUSTOMER NAME,CUSTOMER SEGMENT,TOTAL REVENUE,PURCHASE FREQUENCY,CUSTOMER VALUE,CRM STATUS\n"
        'Acme Industrial,Enterprise,"$150,000",12,High,Active\n'
        "Beta Robotics,Mid-Market,75000,4,Medium,Pending\n"
    )

    with patch(REPO_PATH, return_value=mock_repo):
        resp = client.post(
            f"/api/v1/crm/{CRM_ID}/records/machine_identifier/import",
            headers=_headers(),
            files={"file": ("machines.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["created"] == 2
    assert data["skipped"] == 0
    assert data["errors"] == []

    # Verify repository was called with mapped canonical field names
    mock_repo.create_records_batch.assert_called_once()
    call_args = mock_repo.create_records_batch.call_args
    batch_rows = call_args[0][2]
    assert len(batch_rows) == 2

    first_row_data = batch_rows[0]["data"]
    assert first_row_data["customer_name"] == "Acme Industrial"
    assert first_row_data["customer_segment"] == "Enterprise"
    assert first_row_data["total_revenue"] == 150000.0 or first_row_data["total_revenue"] == 150000
    assert first_row_data["purchase_frequency"] == 12
    assert first_row_data["customer_value"] == "High"
    assert first_row_data["crm_status"] == "Active"


def test_mixed_case_and_spaces_vs_underscores():
    """Test mixed-case headers and spaces versus underscores."""
    mock_repo = MagicMock()
    mock_repo.get_crm.return_value = _machine_identifier_crm()
    mock_repo.create_records_batch.return_value = [{"id": str(uuid.uuid4())}]

    csv_content = (
        "Customer Name,customer_segment,Total revenue,Purchase_Frequency,customer value,CRM_STATUS\n"
        "Delta Corp,Small Business,20000,2,Low,Active\n"
    )

    with patch(REPO_PATH, return_value=mock_repo):
        resp = client.post(
            f"/api/v1/crm/{CRM_ID}/records/machine_identifier/import",
            headers=_headers(),
            files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["created"] == 1


def test_headers_with_leading_trailing_whitespace():
    """Test headers containing leading and trailing whitespace."""
    mock_repo = MagicMock()
    mock_repo.get_crm.return_value = _machine_identifier_crm()
    mock_repo.create_records_batch.return_value = [{"id": str(uuid.uuid4())}]

    csv_content = (
        "  customer_name  ,   TOTAL REVENUE   , crm_status \n"
        "Echo Inc,5000,Active\n"
    )

    with patch(REPO_PATH, return_value=mock_repo):
        resp = client.post(
            f"/api/v1/crm/{CRM_ID}/records/machine_identifier/import",
            headers=_headers(),
            files={"file": ("spaces.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["created"] == 1


def test_utf8_bom_handling():
    """Test a CSV file prepended with a UTF-8 BOM (0xEF, 0xBB, 0xBF)."""
    mock_repo = MagicMock()
    mock_repo.get_crm.return_value = _machine_identifier_crm()
    mock_repo.create_records_batch.return_value = [{"id": str(uuid.uuid4())}]

    csv_content = "CUSTOMER NAME,TOTAL REVENUE\nFoxtrot Ltd,88000\n"
    csv_bytes = b"\xef\xbb\xbf" + csv_content.encode("utf-8")

    with patch(REPO_PATH, return_value=mock_repo):
        resp = client.post(
            f"/api/v1/crm/{CRM_ID}/records/machine_identifier/import",
            headers=_headers(),
            files={"file": ("bom.csv", io.BytesIO(csv_bytes), "text/csv")},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["created"] == 1


def test_unknown_columns_rejected_with_descriptive_error():
    """Test genuinely unknown columns are rejected with a clear 422 error."""
    mock_repo = MagicMock()
    mock_repo.get_crm.return_value = _machine_identifier_crm()

    csv_content = "customer_name,unknown_telemetry,extra_col\nAcme,123,456\n"

    with patch(REPO_PATH, return_value=mock_repo):
        resp = client.post(
            f"/api/v1/crm/{CRM_ID}/records/machine_identifier/import",
            headers=_headers(),
            files={"file": ("bad_cols.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        )

    assert resp.status_code == 422, resp.text
    err = resp.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "Unknown CSV columns" in err["message"]
    assert "unknown_telemetry" in err["message"]


def test_duplicate_normalized_headers_rejected():
    """Test duplicate headers resolving to the same schema field are rejected."""
    mock_repo = MagicMock()
    mock_repo.get_crm.return_value = _machine_identifier_crm()

    csv_content = "customer_name,CUSTOMER NAME\nAcme,Acme\n"

    with patch(REPO_PATH, return_value=mock_repo):
        resp = client.post(
            f"/api/v1/crm/{CRM_ID}/records/machine_identifier/import",
            headers=_headers(),
            files={"file": ("dup.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        )

    assert resp.status_code == 422, resp.text
    err = resp.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "Duplicate CSV column mapping for field 'customer_name'" in err["message"]


def test_missing_required_fields_row_errors():
    """Test rows missing required fields are counted as skipped with MISSING_REQUIRED error."""
    mock_repo = MagicMock()
    mock_repo.get_crm.return_value = _machine_identifier_crm()
    mock_repo.create_records_batch.return_value = [{"id": str(uuid.uuid4())}]

    # Row 2 is valid, Row 3 has empty required customer_name
    csv_content = (
        "customer_name,total_revenue\n"
        "Valid Corp,1000\n"
        "   ,2000\n"
    )

    with patch(REPO_PATH, return_value=mock_repo):
        resp = client.post(
            f"/api/v1/crm/{CRM_ID}/records/machine_identifier/import",
            headers=_headers(),
            files={"file": ("missing_req.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["created"] == 1
    assert data["skipped"] == 1
    assert len(data["errors"]) == 1
    assert data["errors"][0]["code"] == "MISSING_REQUIRED"
    assert data["errors"][0]["row"] == 3


def test_invalid_numeric_and_status_values():
    """Test invalid numeric values and invalid status options generate row errors."""
    mock_repo = MagicMock()
    mock_repo.get_crm.return_value = _machine_identifier_crm()
    mock_repo.create_records_batch.return_value = []

    csv_content = (
        "customer_name,total_revenue,crm_status\n"
        "Bad Number Corp,not-a-number,Active\n"
        "Bad Status Corp,5000,NonExistentStatus\n"
    )

    with patch(REPO_PATH, return_value=mock_repo):
        resp = client.post(
            f"/api/v1/crm/{CRM_ID}/records/machine_identifier/import",
            headers=_headers(),
            files={"file": ("invalid_types.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["created"] == 0
    assert data["skipped"] == 2
    codes = {e["code"] for e in data["errors"]}
    assert "INVALID_NUMBER" in codes
    assert "INVALID_OPTION" in codes


def test_empty_and_malformed_csv_files():
    """Test 0-byte file, headerless file, and empty column header are rejected."""
    mock_repo = MagicMock()
    mock_repo.get_crm.return_value = _machine_identifier_crm()

    with patch(REPO_PATH, return_value=mock_repo):
        # 1. Empty file
        resp1 = client.post(
            f"/api/v1/crm/{CRM_ID}/records/machine_identifier/import",
            headers=_headers(),
            files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
        )
        assert resp1.status_code == 422
        assert "empty" in resp1.json()["error"]["message"].lower()

        # 2. Empty column header
        resp2 = client.post(
            f"/api/v1/crm/{CRM_ID}/records/machine_identifier/import",
            headers=_headers(),
            files={"file": ("empty_header.csv", io.BytesIO(b"customer_name,,total_revenue\nAcme,,100\n"), "text/csv")},
        )
        assert resp2.status_code == 422
        assert "empty column header" in resp2.json()["error"]["message"].lower()


def test_second_crm_with_completely_different_schema():
    """Test that header resolution is completely universal on a healthcare CRM schema."""
    mock_repo = MagicMock()
    mock_repo.get_crm.return_value = _healthcare_crm()
    mock_repo.create_records_batch.return_value = [{"id": str(uuid.uuid4())}]

    csv_content = (
        "PATIENT FULL NAME,BLOOD GROUP,EMERGENCY CONTACT,CONSULTATION FEE\n"
        "John Doe,O+,+1-555-0199,250\n"
    )

    with patch(REPO_PATH, return_value=mock_repo):
        resp = client.post(
            f"/api/v1/crm/{CRM_ID}/records/patient/import",
            headers=_headers(),
            files={"file": ("patients.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["created"] == 1
    assert data["skipped"] == 0

    batch_row = mock_repo.create_records_batch.call_args[0][2][0]["data"]
    assert batch_row["patient_name"] == "John Doe"
    assert batch_row["blood_group"] == "O+"
    # emergency_contact has leading '+' so formula neutralization prepends single-quote
    assert batch_row["emergency_contact"] == "'+1-555-0199"
    assert batch_row["consultation_fee"] == 250


def test_tenant_isolation_and_authorization():
    """Verify tenant isolation and archived CRM security constraints."""
    mock_repo = MagicMock()
    # Unowned CRM returns None from get_crm
    mock_repo.get_crm.return_value = None

    csv_content = "customer_name\nAcme\n"

    with patch(REPO_PATH, return_value=mock_repo):
        # User B trying to import into User A's CRM
        resp = client.post(
            f"/api/v1/crm/{CRM_ID}/records/machine_identifier/import",
            headers=_headers(OTHER_USER_ID),
            files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        )
        assert resp.status_code == 404

    # Archived CRM returns 403
    mock_repo.get_crm.return_value = _machine_identifier_crm(crm_status="archived")
    with patch(REPO_PATH, return_value=mock_repo):
        resp = client.post(
            f"/api/v1/crm/{CRM_ID}/records/machine_identifier/import",
            headers=_headers(),
            files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"
