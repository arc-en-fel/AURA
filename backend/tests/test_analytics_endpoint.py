"""Unit tests for CRM Analytics endpoint GET /api/v1/crm/{crm_id}/analytics.

Verifies canonical status aggregation, chart synchronization, dynamic schema detection,
and data integrity across workflow stages.
"""
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: "00000000-0000-0000-0000-000000000001"
    return TestClient(app)


def test_analytics_endpoint_crm_not_found(client):
    """Returns 404 when CRM is not found (tenant isolation / missing CRM)."""
    crm_id = str(uuid4())
    with patch("app.routers.crm._get_repo") as mock_get_repo:
        repo = MagicMock()
        repo.get_crm.return_value = None
        mock_get_repo.return_value = repo

        res = client.get(f"/api/v1/crm/{crm_id}/analytics")
        assert res.status_code == 404
        data = res.json()
        assert data["error"]["code"] == "NOT_FOUND"


def test_canonical_status_distribution_all_71_records_in_new(client):
    """Scenario 1 & 5: When all 71 records have 'New' status, both status_distribution
    and by_stage report exactly 71 under 'New', 0 for other stages, and 100% percentage.
    """
    crm_id = str(uuid4())
    pipeline_stages = ["New", "Analyzing", "High Value", "At Risk", "Retained/Lost"]
    mock_crm = {
        "id": crm_id,
        "name": "Analytical E-Commerce CRM",
        "configuration": {
            "pipeline_stages": pipeline_stages,
            "entities": [
                {
                    "name": "machine_identifier",
                    "label": "Machine Identifier",
                    "fields": [
                        {"name": "customer_name", "label": "Customer Name", "type": "text", "required": True},
                        {"name": "total_revenue", "label": "Total Revenue", "type": "currency", "required": False},
                        {"name": "crm_status", "label": "CRM Status", "type": "status", "required": False, "options": pipeline_stages},
                    ],
                }
            ],
        },
    }

    # 71 records all in 'New' status under field 'crm_status'
    mock_records = [
        {
            "id": f"rec-{i}",
            "source": "CSV",
            "data": {
                "customer_name": f"Customer {i}",
                "total_revenue": 100.0 * i,
                "crm_status": "New",
            },
        }
        for i in range(1, 72)
    ]
    assert len(mock_records) == 71

    with patch("app.routers.crm._get_repo") as mock_get_repo:
        repo = MagicMock()
        repo.get_crm.return_value = mock_crm
        repo.get_all_records.return_value = mock_records
        mock_get_repo.return_value = repo

        res = client.get(f"/api/v1/crm/{crm_id}/analytics")
        assert res.status_code == 200
        payload = res.json()["data"]

        # Check total records
        assert payload["total_records"] == 71

        # Check status_distribution and by_stage are identical canonical data
        assert payload["status_distribution"] == payload["by_stage"]
        dist = payload["status_distribution"]

        # All 5 configured stages present in configured order
        stage_names = [s["status"] for s in dist]
        assert stage_names == pipeline_stages

        new_stage = next(s for s in dist if s["status"] == "New")
        assert new_stage["count"] == 71
        assert new_stage["percentage"] == 100.0

        for stage in dist:
            if stage["status"] != "New":
                assert stage["count"] == 0
                assert stage["percentage"] == 0.0

        # Sum of status counts matches total valid records
        assert sum(s["count"] for s in dist) == 71

        # crm_status MUST NOT be duplicated inside categorical_metrics
        assert "crm_status" not in payload.get("categorical_metrics", {})


def test_status_update_moves_record_from_new_to_analyzing(client):
    """Scenario 2 & 6: Moving a record from New to Analyzing immediately updates
    canonical status distribution (New: 70, Analyzing: 1).
    """
    crm_id = str(uuid4())
    pipeline_stages = ["New", "Analyzing", "High Value", "At Risk", "Retained/Lost"]
    mock_crm = {
        "id": crm_id,
        "name": "Analytical E-Commerce CRM",
        "configuration": {
            "pipeline_stages": pipeline_stages,
            "entities": [
                {
                    "name": "machine_identifier",
                    "label": "Machine Identifier",
                    "fields": [
                        {"name": "crm_status", "label": "CRM Status", "type": "status", "required": False},
                    ],
                }
            ],
        },
    }

    mock_records = [
        {"id": f"rec-{i}", "source": "Manual", "data": {"crm_status": "Analyzing" if i == 1 else "New"}}
        for i in range(1, 72)
    ]

    with patch("app.routers.crm._get_repo") as mock_get_repo:
        repo = MagicMock()
        repo.get_crm.return_value = mock_crm
        repo.get_all_records.return_value = mock_records
        mock_get_repo.return_value = repo

        res = client.get(f"/api/v1/crm/{crm_id}/analytics")
        assert res.status_code == 200
        payload = res.json()["data"]

        dist = payload["status_distribution"]
        new_stage = next(s for s in dist if s["status"] == "New")
        analyzing_stage = next(s for s in dist if s["status"] == "Analyzing")

        assert new_stage["count"] == 70
        assert analyzing_stage["count"] == 1
        assert sum(s["count"] for s in dist) == 71


def test_missing_statuses_handled_separately(client):
    """Scenario 7: Records with missing/null status are reported in missing_status_count
    and never silently coerced to 'New'.
    """
    crm_id = str(uuid4())
    mock_crm = {
        "id": crm_id,
        "name": "CRM With Missing Statuses",
        "configuration": {
            "pipeline_stages": ["New", "Won"],
            "entities": [
                {
                    "name": "lead",
                    "label": "Lead",
                    "fields": [{"name": "status", "label": "Status", "type": "status"}],
                }
            ],
        },
    }

    mock_records = [
        {"id": "r1", "data": {"status": "New"}},
        {"id": "r2", "data": {"status": None}},
        {"id": "r3", "data": {}},
        {"id": "r4", "data": {"status": "   "}},
    ]

    with patch("app.routers.crm._get_repo") as mock_get_repo:
        repo = MagicMock()
        repo.get_crm.return_value = mock_crm
        repo.get_all_records.return_value = mock_records
        mock_get_repo.return_value = repo

        res = client.get(f"/api/v1/crm/{crm_id}/analytics")
        assert res.status_code == 200
        payload = res.json()["data"]

        assert payload["total_records"] == 4
        assert payload["missing_status_count"] == 3

        dist = payload["status_distribution"]
        new_stage = next(s for s in dist if s["status"] == "New")
        # Only 1 record actually had 'New' status!
        assert new_stage["count"] == 1


def test_arbitrary_crm_schema_with_different_status_identifier(client):
    """Scenario 12: Works dynamically for Healthcare/Recruitment CRM with custom
    entity 'applicant', status field 'application_phase', and custom stages.
    """
    crm_id = str(uuid4())
    custom_stages = ["Applied", "Screening", "Interview", "Offer", "Hired"]
    mock_crm = {
        "id": crm_id,
        "name": "Recruitment CRM",
        "configuration": {
            "pipeline_stages": custom_stages,
            "entities": [
                {
                    "name": "applicant",
                    "label": "Job Applicant",
                    "fields": [
                        {"name": "candidate_name", "label": "Candidate Name", "type": "text"},
                        {"name": "application_phase", "label": "Application Phase", "type": "status", "options": custom_stages},
                        {"name": "expected_salary", "label": "Expected Salary", "type": "currency"},
                    ],
                }
            ],
        },
    }

    mock_records = [
        {"id": "a1", "data": {"candidate_name": "Alice", "application_phase": "Interview", "expected_salary": 120000}},
        {"id": "a2", "data": {"candidate_name": "Bob", "application_phase": "Offer", "expected_salary": 140000}},
        {"id": "a3", "data": {"candidate_name": "Charlie", "application_phase": "Applied", "expected_salary": 95000}},
    ]

    with patch("app.routers.crm._get_repo") as mock_get_repo:
        repo = MagicMock()
        repo.get_crm.return_value = mock_crm
        repo.get_all_records.return_value = mock_records
        mock_get_repo.return_value = repo

        res = client.get(f"/api/v1/crm/{crm_id}/analytics")
        assert res.status_code == 200
        payload = res.json()["data"]

        assert payload["schema_info"]["stage_field_name"] == "application_phase"
        assert payload["schema_info"]["stage_field_label"] == "Application Phase"
        dist = payload["status_distribution"]

        interview = next(s for s in dist if s["status"] == "Interview")
        assert interview["count"] == 1
        applied = next(s for s in dist if s["status"] == "Applied")
        assert applied["count"] == 1
        screening = next(s for s in dist if s["status"] == "Screening")
        assert screening["count"] == 0
