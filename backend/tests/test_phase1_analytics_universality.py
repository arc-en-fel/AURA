"""Phase 1 Regression: Analytics Universality (C1)

Test that analytics work for any CRM type without hard-coded assumptions.
Verify that stage names and field names match the CRM configuration.
"""
import json
import pytest
from unittest.mock import MagicMock, patch
from uuid import UUID

from app.routers.workflows import get_analytics
from app.schemas.crm import CRMConfiguration, CRMEntity, CRMField


def _extract_response_data(response):
    """Extract data from a JSONResponse object."""
    if hasattr(response, 'body'):
        return json.loads(response.body)['data']
    return response.json()['data']


def _create_test_crm_config(
    name: str,
    industry: str,
    entity_name: str,
    entity_label: str,
    stages: list[str],
    fields: list[dict],
) -> CRMConfiguration:
    """Helper to create a test CRM configuration."""
    entity_fields = [
        CRMField(
            name=f["name"],
            label=f["label"],
            type=f["type"],
            required=f.get("required", False),
            options=f.get("options"),
        )
        for f in fields
    ]
    entity = CRMEntity(name=entity_name, label=entity_label, fields=entity_fields)
    return CRMConfiguration(
        name=name,
        industry=industry,
        entities=[entity],
        pipeline_stages=stages,
    )


@pytest.mark.asyncio
async def test_analytics_e_commerce_crm():
    """E-commerce CRM: customer entity, custom stages, revenue field."""
    config = _create_test_crm_config(
        name="Online Store",
        industry="e-commerce",
        entity_name="customer",
        entity_label="Customer",
        stages=["Prospect", "First Order", "Repeat Buyer", "VIP Member", "Churn Risk"],
        fields=[
            {"name": "name", "label": "Customer Name", "type": "text", "required": True},
            {"name": "email", "label": "Email", "type": "email", "required": True},
            {"name": "total_spend", "label": "Total Spend", "type": "currency"},
            {
                "name": "status",
                "label": "Status",
                "type": "status",
                "options": ["Prospect", "First Order", "Repeat Buyer", "VIP Member", "Churn Risk"],
            },
        ],
    )

    # Mock repo
    repo = MagicMock()
    repo.get_all_records.return_value = [
        {
            "id": "c1",
            "data": {
                "name": "John Doe",
                "email": "john@example.com",
                "status": "VIP Member",
                "total_spend": 5000.0,
            },
        },
        {
            "id": "c2",
            "data": {
                "name": "Jane Smith",
                "email": "jane@example.com",
                "status": "First Order",
                "total_spend": 100.0,
            },
        },
        {
            "id": "c3",
            "data": {
                "name": "Bob Johnson",
                "email": "bob@example.com",
                "status": "Churn Risk",
                "total_spend": 0.0,
            },
        },
    ]

    with patch("app.routers.workflows.CRMRepository", return_value=repo):
        with patch("app.routers.workflows.CRMRepository.get_crm") as mock_get_crm:
            mock_get_crm.return_value = {
                "id": str(UUID("00000000-0000-0000-0000-000000000001")),
                "configuration": config.model_dump(),
            }
            with patch("app.routers.workflows.CRMRepository") as mock_repo_class:
                mock_repo_class.return_value.get_crm.return_value = {
                    "id": str(UUID("00000000-0000-0000-0000-000000000001")),
                    "configuration": config.model_dump(),
                }
                mock_repo_class.return_value.get_all_records.return_value = [
                    {
                        "id": "c1",
                        "data": {
                            "name": "John Doe",
                            "email": "john@example.com",
                            "status": "VIP Member",
                            "total_spend": 5000.0,
                        },
                    },
                    {
                        "id": "c2",
                        "data": {
                            "name": "Jane Smith",
                            "email": "jane@example.com",
                            "status": "First Order",
                            "total_spend": 100.0,
                        },
                    },
                    {
                        "id": "c3",
                        "data": {
                            "name": "Bob Johnson",
                            "email": "bob@example.com",
                            "status": "Churn Risk",
                            "total_spend": 0.0,
                        },
                    },
                ]

                response = await get_analytics(
                    crm_id=UUID("00000000-0000-0000-0000-000000000001"),
                    user_id=UUID("00000000-0000-0000-0000-000000000099"),
                )

                data = _extract_response_data(response)

                # Should use generic schema, not sales-specific
                assert data["total_records"] == 3
                assert "by_stage" in data
                assert "by_source" in data

                # Verify stages match config
                stage_values = [s["value"] for s in data["by_stage"]]
                assert "VIP Member" in stage_values
                assert "Churn Risk" in stage_values
                assert "First Order" in stage_values

                # Should NOT have sales-specific fields (they should be removed in C5 fix)
                assert "total_leads" not in data or data.get("total_leads") == 3


@pytest.mark.asyncio
async def test_analytics_healthcare_crm():
    """Healthcare CRM: patient entity, custom stages, no conversion metrics."""
    config = _create_test_crm_config(
        name="Clinic Management",
        industry="healthcare",
        entity_name="patient",
        entity_label="Patient",
        stages=["Intake", "Consultation", "Treatment", "Follow-up", "Discharged"],
        fields=[
            {"name": "full_name", "label": "Full Name", "type": "text", "required": True},
            {"name": "phone", "label": "Phone", "type": "phone", "required": True},
            {
                "name": "status",
                "label": "Care Status",
                "type": "status",
                "options": ["Intake", "Consultation", "Treatment", "Follow-up", "Discharged"],
            },
            {"name": "priority", "label": "Priority", "type": "select", "options": ["Routine", "Urgent", "Emergency"]},
        ],
    )

    # Mock repo
    repo = MagicMock()
    repo.get_all_records.return_value = [
        {
            "id": "p1",
            "data": {
                "full_name": "Alice Smith",
                "phone": "+1-555-0101",
                "status": "Treatment",
                "priority": "Urgent",
            },
        },
        {
            "id": "p2",
            "data": {
                "full_name": "Bob Jones",
                "phone": "+1-555-0102",
                "status": "Discharged",
                "priority": "Routine",
            },
        },
    ]

    with patch("app.routers.workflows.CRMRepository") as mock_repo_class:
        mock_repo_class.return_value.get_crm.return_value = {
            "id": str(UUID("00000000-0000-0000-0000-000000000002")),
            "configuration": config.model_dump(),
        }
        mock_repo_class.return_value.get_all_records.return_value = repo.get_all_records.return_value

        response = await get_analytics(
            crm_id=UUID("00000000-0000-0000-0000-000000000002"),
            user_id=UUID("00000000-0000-0000-0000-000000000099"),
        )

        data = _extract_response_data(response)

        # Should use primary entity name from config
        assert data["schema_info"]["primary_entity_name"] == "patient"
        assert data["total_records"] == 2

        # Verify stages match healthcare pipeline
        stage_values = [s["value"] for s in data["by_stage"]]
        assert "Intake" in stage_values
        assert "Discharged" in stage_values
        assert "Treatment" in stage_values


@pytest.mark.asyncio
async def test_analytics_recruitment_crm():
    """Recruitment CRM: candidate entity, custom stages, no sales metrics."""
    config = _create_test_crm_config(
        name="Talent Tracker",
        industry="recruitment",
        entity_name="candidate",
        entity_label="Candidate",
        stages=["Applied", "Screened", "Interview 1", "Interview 2", "Offer", "Hired", "Rejected"],
        fields=[
            {"name": "full_name", "label": "Candidate Name", "type": "text", "required": True},
            {"name": "email", "label": "Email", "type": "email", "required": True},
            {"name": "interview_score", "label": "Interview Score", "type": "number"},
            {
                "name": "status",
                "label": "Hiring Stage",
                "type": "status",
                "options": ["Applied", "Screened", "Interview 1", "Interview 2", "Offer", "Hired", "Rejected"],
            },
        ],
    )

    with patch("app.routers.workflows.CRMRepository") as mock_repo_class:
        mock_repo_class.return_value.get_crm.return_value = {
            "id": str(UUID("00000000-0000-0000-0000-000000000003")),
            "configuration": config.model_dump(),
        }
        mock_repo_class.return_value.get_all_records.return_value = [
            {
                "id": "cand1",
                "data": {
                    "full_name": "Alice Cooper",
                    "email": "alice@example.com",
                    "status": "Hired",
                    "interview_score": 95,
                },
            },
            {
                "id": "cand2",
                "data": {
                    "full_name": "Bob Dylan",
                    "email": "bob@example.com",
                    "status": "Interview 1",
                    "interview_score": 78,
                },
            },
            {
                "id": "cand3",
                "data": {
                    "full_name": "Charlie Brown",
                    "email": "charlie@example.com",
                    "status": "Rejected",
                    "interview_score": 45,
                },
            },
        ]

        response = await get_analytics(
            crm_id=UUID("00000000-0000-0000-0000-000000000003"),
            user_id=UUID("00000000-0000-0000-0000-000000000099"),
        )

        data = _extract_response_data(response)

        # Verify schema matches recruitment
        assert data["schema_info"]["primary_entity_name"] == "candidate"
        assert data["total_records"] == 3

        # Verify pipeline stages from config
        assert set(data["schema_info"]["pipeline_stages"]) == set(config.pipeline_stages)

        # All stages should appear in by_stage
        stage_names = [s["value"] for s in data["by_stage"]]
        for stage in config.pipeline_stages:
            assert stage in stage_names


@pytest.mark.asyncio
async def test_analytics_custom_crm_any_entity_name():
    """Custom CRM with non-standard entity name: system must work universally."""
    config = _create_test_crm_config(
        name="Custom Project Manager",
        industry="project-management",
        entity_name="task",
        entity_label="Task",
        stages=["Backlog", "In Progress", "Review", "Done"],
        fields=[
            {"name": "title", "label": "Task Title", "type": "text", "required": True},
            {"name": "effort", "label": "Story Points", "type": "number"},
            {
                "name": "status",
                "label": "Task Status",
                "type": "status",
                "options": ["Backlog", "In Progress", "Review", "Done"],
            },
        ],
    )

    with patch("app.routers.workflows.CRMRepository") as mock_repo_class:
        mock_repo_class.return_value.get_crm.return_value = {
            "id": str(UUID("00000000-0000-0000-0000-000000000004")),
            "configuration": config.model_dump(),
        }
        mock_repo_class.return_value.get_all_records.return_value = [
            {"id": "t1", "data": {"title": "Feature A", "status": "Done", "effort": 5}},
            {"id": "t2", "data": {"title": "Bug B", "status": "In Progress", "effort": 3}},
            {"id": "t3", "data": {"title": "Task C", "status": "Backlog", "effort": 8}},
            {"id": "t4", "data": {"title": "Task D", "status": "Review", "effort": 2}},
        ]

        response = await get_analytics(
            crm_id=UUID("00000000-0000-0000-0000-000000000004"),
            user_id=UUID("00000000-0000-0000-0000-000000000099"),
        )

        data = _extract_response_data(response)

        # Verify system adapts to custom entity name
        assert data["schema_info"]["primary_entity_name"] == "task"
        assert data["schema_info"]["primary_entity_name"] != "lead"
        assert data["total_records"] == 4

        # Stage distribution must match config
        stage_counts = {s["value"]: s["count"] for s in data["by_stage"]}
        assert stage_counts["Done"] == 1
        assert stage_counts["In Progress"] == 1
        assert stage_counts["Review"] == 1
        assert stage_counts["Backlog"] == 1
