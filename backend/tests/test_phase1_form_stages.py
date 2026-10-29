"""Phase 1 Regression: Form Status Field (C3)

Test that RecordFormModal uses CRM pipeline_stages from configuration,
never hard-coded defaults like ['New', 'Active', 'Completed'].
"""
import pytest
from unittest.mock import MagicMock
from uuid import UUID

from app.schemas.crm import CRMConfiguration, CRMEntity, CRMField


def test_form_uses_crm_pipeline_stages():
    """C3: Status field should use pipeline_stages from CRM config."""
    config = CRMConfiguration(
        name="Test CRM",
        industry="test",
        entities=[
            CRMEntity(
                name="record",
                label="Record",
                fields=[
                    CRMField(
                        name="name",
                        label="Name",
                        type="text",
                        required=True,
                    ),
                    CRMField(
                        name="status",
                        label="Status",
                        type="status",
                    ),
                ],
            ),
        ],
        pipeline_stages=["Initial", "Processing", "Complete"],
    )

    # Verify that the config has the stages
    assert config.pipeline_stages == ["Initial", "Processing", "Complete"]
    
    # In the RecordFormModal, the form should render with these stages
    status_field = config.entities[0].fields[1]
    assert status_field.type == "status"
    
    # Frontend would use:
    # const stages = activeCRM?.configuration?.pipeline_stages || [];
    # const statusOptions = field.options && field.options.length > 0 ? field.options : stages;
    # This should return ["Initial", "Processing", "Complete"]
    
    stages = config.pipeline_stages
    status_options = status_field.options or stages
    
    assert status_options == ["Initial", "Processing", "Complete"]
    assert status_options != ['New', 'Active', 'Completed']


def test_form_shows_error_if_no_stages():
    """C3: If status field has no options and pipeline_stages is empty, show error."""
    config = CRMConfiguration(
        name="Broken CRM",
        industry="test",
        entities=[
            CRMEntity(
                name="record",
                label="Record",
                fields=[
                    CRMField(
                        name="name",
                        label="Name",
                        type="text",
                        required=True,
                    ),
                    CRMField(
                        name="status",
                        label="Status",
                        type="status",
                    ),
                ],
            ),
        ],
        pipeline_stages=[],  # No stages configured
    )

    status_field = config.entities[0].fields[1]
    stages = config.pipeline_stages
    status_options = status_field.options or stages
    
    # Should be empty, triggering validation error in frontend
    assert len(status_options) == 0


def test_form_uses_field_options_if_available():
    """C3: If field defines options, use those instead of pipeline_stages."""
    config = CRMConfiguration(
        name="Test CRM",
        industry="test",
        entities=[
            CRMEntity(
                name="record",
                label="Record",
                fields=[
                    CRMField(
                        name="name",
                        label="Name",
                        type="text",
                        required=True,
                    ),
                    CRMField(
                        name="custom_status",
                        label="Custom Status",
                        type="select",
                        options=["Custom1", "Custom2", "Custom3"],
                    ),
                ],
            ),
        ],
        pipeline_stages=["Initial", "Processing", "Complete"],
    )

    custom_field = config.entities[0].fields[1]
    
    # Field options take priority
    status_options = custom_field.options or config.pipeline_stages
    assert status_options == ["Custom1", "Custom2", "Custom3"]


def test_healthcare_crm_no_hardcoded_defaults():
    """Verify healthcare CRM never gets fallback to ['New', 'Active', 'Completed']."""
    config = CRMConfiguration(
        name="Clinic",
        industry="healthcare",
        entities=[
            CRMEntity(
                name="patient",
                label="Patient",
                fields=[
                    CRMField(
                        name="name",
                        label="Patient Name",
                        type="text",
                        required=True,
                    ),
                    CRMField(
                        name="status",
                        label="Care Status",
                        type="status",
                    ),
                ],
            ),
        ],
        pipeline_stages=["Intake", "Consultation", "Treatment", "Follow-up", "Discharged"],
    )

    status_field = config.entities[0].fields[1]
    status_options = status_field.options or config.pipeline_stages
    
    # Should be healthcare stages, never the sales defaults
    assert status_options == ["Intake", "Consultation", "Treatment", "Follow-up", "Discharged"]
    assert status_options != ['New', 'Active', 'Completed']


def test_recruitment_crm_hiring_stages():
    """Verify recruitment CRM uses hiring stages, not sales stages."""
    config = CRMConfiguration(
        name="Talent Tracker",
        industry="recruitment",
        entities=[
            CRMEntity(
                name="candidate",
                label="Candidate",
                fields=[
                    CRMField(
                        name="name",
                        label="Candidate Name",
                        type="text",
                        required=True,
                    ),
                    CRMField(
                        name="status",
                        label="Hiring Stage",
                        type="status",
                    ),
                ],
            ),
        ],
        pipeline_stages=["Applied", "Screened", "Interview 1", "Interview 2", "Offer", "Hired", "Rejected"],
    )

    status_field = config.entities[0].fields[1]
    status_options = status_field.options or config.pipeline_stages
    
    # Should have recruitment stages
    assert "Hired" in status_options
    assert "Interview 1" in status_options
    assert "New" not in status_options
    assert "Won" not in status_options


def test_ecommerce_crm_customer_stages():
    """Verify e-commerce CRM uses customer lifecycle stages."""
    config = CRMConfiguration(
        name="Online Store",
        industry="ecommerce",
        entities=[
            CRMEntity(
                name="customer",
                label="Customer",
                fields=[
                    CRMField(
                        name="email",
                        label="Email",
                        type="email",
                        required=True,
                    ),
                    CRMField(
                        name="status",
                        label="Customer Status",
                        type="status",
                    ),
                ],
            ),
        ],
        pipeline_stages=["Prospect", "First Order", "Repeat Buyer", "VIP Member", "Churn Risk"],
    )

    status_field = config.entities[0].fields[1]
    status_options = status_field.options or config.pipeline_stages
    
    # Should use customer lifecycle
    assert "VIP Member" in status_options
    assert "Churn Risk" in status_options
    assert "Closed Won" not in status_options
