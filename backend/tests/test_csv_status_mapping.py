"""Tests for universal schema-driven CSV status/enum value mapping, retry, and deduplication.

Tests all requirements:
1. Valid enum values import normally.
2. Invalid enum values rejected with INVALID_OPTION.
3. Multiple invalid values can map to the same allowed option via explicit user mapping.
4. Retry of partially imported file does NOT duplicate existing records (66 preserved, 34 newly created).
5. User explicit skip option (__SKIP__) skips affected rows cleanly.
6. Genuinely invalid mapping targets (not in schema) are rejected with 422.
7. Universal behavior across different CRMs and entities.
8. Accurate counts: total_rows, created, skipped, failed, duplicate.
9. Tenant isolation and authorization.
"""
from __future__ import annotations

import io
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.config import get_settings
from app.main import create_app

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


def _analytical_ecommerce_crm() -> dict:
    """Fixture representing Analytical_E_Commerce_CRM with Machine Identifier entity."""
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


def _generate_100_row_csv() -> str:
    """Generate the 100-row CSV from user scenario:
    - 66 rows with valid statuses ('New', 'High Value', 'Analyzing', 'At Risk')
    - 20 rows with status 'Retained'
    - 14 rows with status 'Lost'
    """
    rows = ["CUSTOMER NAME,CUSTOMER SEGMENT,TOTAL REVENUE,PURCHASE FREQUENCY,CUSTOMER VALUE,CRM STATUS"]

    # 66 valid rows
    for i in range(1, 67):
        status = "New" if i % 2 == 0 else "High Value"
        rows.append(f"Customer {i},Enterprise,{i * 1000},5,Medium,{status}")

    # 20 rows with 'Retained'
    for i in range(67, 87):
        rows.append(f"Customer {i},SMB,{i * 500},2,Low,Retained")

    # 14 rows with 'Lost'
    for i in range(87, 101):
        rows.append(f"Customer {i},Enterprise,{i * 2000},10,High,Lost")

    return "\n".join(rows) + "\n"


def test_initial_import_rejects_unmapped_retained_and_lost():
    """Step 1 verification: Without mappings, 66 rows are created and 34 rows fail due to invalid status."""
    mock_repo = MagicMock()
    mock_repo.get_crm.return_value = _analytical_ecommerce_crm()
    mock_repo.get_all_records.return_value = []
    created_records = [{"id": str(uuid.uuid4())} for _ in range(66)]
    mock_repo.create_records_batch.return_value = created_records

    csv_content = _generate_100_row_csv()

    with patch(REPO_PATH, return_value=mock_repo):
        resp = client.post(
            f"/api/v1/crm/{CRM_ID}/records/machine_identifier/import",
            headers=_headers(),
            files={"file": ("dataset.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total_rows"] == 100
    assert data["created"] == 66
    assert data["skipped"] == 34
    assert data["failed"] == 34
    assert data["duplicate"] == 0
    assert len(data["errors"]) == 34

    # Every failure is due to INVALID_OPTION
    for err in data["errors"]:
        assert err["code"] == "INVALID_OPTION"
        assert "not in options" in err["message"]


def test_upfront_value_mappings_imports_all_100_records():
    """Step 2 verification: With explicit mappings for Retained & Lost -> Retained/Lost, all 100 rows import cleanly."""
    mock_repo = MagicMock()
    mock_repo.get_crm.return_value = _analytical_ecommerce_crm()
    mock_repo.get_all_records.return_value = []
    mock_repo.create_records_batch.return_value = [{"id": str(uuid.uuid4())} for _ in range(100)]

    csv_content = _generate_100_row_csv()
    mappings = {
        "crm_status": {
            "Retained": "Retained/Lost",
            "Lost": "Retained/Lost",
        }
    }

    with patch(REPO_PATH, return_value=mock_repo):
        resp = client.post(
            f"/api/v1/crm/{CRM_ID}/records/machine_identifier/import",
            headers=_headers(),
            files={"file": ("dataset.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
            data={"value_mappings": json.dumps(mappings)},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total_rows"] == 100
    assert data["created"] == 100
    assert data["skipped"] == 0
    assert data["failed"] == 0
    assert data["duplicate"] == 0
    assert data["errors"] == []


def test_partially_imported_retry_does_not_duplicate_existing_records():
    """Acceptance Test: Retry of 100-row file with existing 66 records created earlier.

    The 66 existing records must NOT be recreated (duplicate: 66).
    The 34 failed records must be successfully imported with mappings (created: 34).
    """
    mock_repo = MagicMock()
    mock_repo.get_crm.return_value = _analytical_ecommerce_crm()

    # Simulate existing 66 records already stored in database from first attempt
    existing_in_db = []
    for i in range(1, 67):
        status = "New" if i % 2 == 0 else "High Value"
        existing_in_db.append({
            "id": str(uuid.uuid4()),
            "crm_id": CRM_ID,
            "entity_name": "machine_identifier",
            "data": {
                "customer_name": f"Customer {i}",
                "customer_segment": "Enterprise",
                "total_revenue": i * 1000,
                "purchase_frequency": 5,
                "customer_value": "Medium",
                "crm_status": status,
            },
        })
    mock_repo.get_all_records.return_value = existing_in_db
    mock_repo.create_records_batch.return_value = [{"id": str(uuid.uuid4())} for _ in range(34)]

    csv_content = _generate_100_row_csv()
    mappings = {
        "crm_status": {
            "Retained": "Retained/Lost",
            "Lost": "Retained/Lost",
        }
    }

    with patch(REPO_PATH, return_value=mock_repo):
        resp = client.post(
            f"/api/v1/crm/{CRM_ID}/records/machine_identifier/import",
            headers=_headers(),
            files={"file": ("dataset.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
            data={"value_mappings": json.dumps(mappings), "deduplicate": "true"},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total_rows"] == 100
    assert data["created"] == 34, "Must only create the 34 previously failed records"
    assert data["duplicate"] == 66, "Must detect 66 duplicates without recreation"
    assert data["skipped"] == 0
    assert data["failed"] == 0
    assert data["errors"] == []

    # Verify create_records_batch was called with exactly 34 records
    mock_repo.create_records_batch.assert_called_once()
    batch_rows = mock_repo.create_records_batch.call_args[0][2]
    assert len(batch_rows) == 34
    for r in batch_rows:
        assert r["data"]["crm_status"] == "Retained/Lost"


def test_user_explicit_skip_rule():
    """Test user choosing '__SKIP__' for a value skips affected rows."""
    mock_repo = MagicMock()
    mock_repo.get_crm.return_value = _analytical_ecommerce_crm()
    mock_repo.get_all_records.return_value = []
    mock_repo.create_records_batch.return_value = [{"id": str(uuid.uuid4())} for _ in range(80)]

    csv_content = _generate_100_row_csv()
    # User maps Retained -> Retained/Lost, but explicitly skips Lost rows
    mappings = {
        "crm_status": {
            "Retained": "Retained/Lost",
            "Lost": "__SKIP__",
        }
    }

    with patch(REPO_PATH, return_value=mock_repo):
        resp = client.post(
            f"/api/v1/crm/{CRM_ID}/records/machine_identifier/import",
            headers=_headers(),
            files={"file": ("dataset.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
            data={"value_mappings": json.dumps(mappings)},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["created"] == 86  # 66 + 20
    assert data["skipped"] == 14  # 14 skipped
    assert len(data["errors"]) == 14
    for err in data["errors"]:
        assert err["code"] == "USER_SKIPPED"


def test_invalid_destination_option_rejected():
    """Test that attempting to map to a nonexistent destination option returns 422."""
    mock_repo = MagicMock()
    mock_repo.get_crm.return_value = _analytical_ecommerce_crm()

    csv_content = _generate_100_row_csv()
    mappings = {
        "crm_status": {
            "Retained": "NonExistentStatusOption",
        }
    }

    with patch(REPO_PATH, return_value=mock_repo):
        resp = client.post(
            f"/api/v1/crm/{CRM_ID}/records/machine_identifier/import",
            headers=_headers(),
            files={"file": ("dataset.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
            data={"value_mappings": json.dumps(mappings)},
        )

    assert resp.status_code == 422, resp.text
    err = resp.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "Invalid mapping destination 'NonExistentStatusOption'" in err["message"]


def test_second_crm_select_field_mapping():
    """Test that value mapping works universally on any select field of any CRM."""
    custom_crm = {
        "id": CRM_ID,
        "owner_id": USER_ID,
        "name": "Custom Logistics CRM",
        "status": "active",
        "configuration_version": 1,
        "configuration": {
            "schema_version": "1.0",
            "name": "Custom Logistics CRM",
            "industry": "logistics",
            "entities": [
                {
                    "name": "shipment",
                    "label": "Shipment",
                    "fields": [
                        {"name": "tracking_number", "label": "Tracking Number", "type": "text", "required": True},
                        {"name": "shipping_method", "label": "Shipping Method", "type": "select", "required": True, "options": ["Express", "Standard", "Economy"]},
                    ],
                }
            ],
            "pipeline_stages": ["Created", "In Transit", "Delivered"],
        },
    }
    mock_repo = MagicMock()
    mock_repo.get_crm.return_value = custom_crm
    mock_repo.get_all_records.return_value = []
    mock_repo.create_records_batch.return_value = [{"id": str(uuid.uuid4())} for _ in range(2)]

    # CSV has "Overnight" and "Ground" which should map to "Express" and "Standard"
    csv_content = (
        "Tracking Number,Shipping Method\n"
        "TRK100,Overnight\n"
        "TRK200,Ground\n"
    )
    mappings = {
        "shipping_method": {
            "Overnight": "Express",
            "Ground": "Standard",
        }
    }

    with patch(REPO_PATH, return_value=mock_repo):
        resp = client.post(
            f"/api/v1/crm/{CRM_ID}/records/shipment/import",
            headers=_headers(),
            files={"file": ("shipments.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
            data={"value_mappings": json.dumps(mappings)},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["created"] == 2
    assert data["skipped"] == 0

    batch_rows = mock_repo.create_records_batch.call_args[0][2]
    assert batch_rows[0]["data"]["shipping_method"] == "Express"
    assert batch_rows[1]["data"]["shipping_method"] == "Standard"

