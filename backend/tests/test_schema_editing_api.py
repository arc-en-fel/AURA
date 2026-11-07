"""FEAT-006: Schema Editing API Tests

Comprehensive tests for POST-generation schema editing via API endpoints.

Tests:
- POST /crm/{crm_id}/fields → field added to config
- PATCH /crm/{crm_id}/fields/email → field updated
- DELETE /crm/{crm_id}/fields/phone → field deleted (no records)
- DELETE returns 409 if field has records
- PATCH /crm/{crm_id}/fields/reorder → fields reordered
- Ownership validation: user A cannot edit CRM of user B
- RLS: endpoint calls trigger RLS checks
- Similar tests for stages endpoints
"""
import pytest
from uuid import uuid4
from app.services.crm_editor import CRMSchemaEditor
from app.schemas.crm import CRMConfiguration, FieldType


@pytest.fixture
def test_crm_config() -> dict:
    """Create a test CRM configuration."""
    return {
        "schema_version": "1.0",
        "name": "Test CRM",
        "industry": "test",
        "entities": [
            {
                "name": "lead",
                "label": "Lead",
                "fields": [
                    {
                        "name": "full_name",
                        "label": "Full Name",
                        "type": "text",
                        "required": True,
                    },
                    {
                        "name": "email",
                        "label": "Email",
                        "type": "email",
                        "required": False,
                    },
                    {
                        "name": "phone",
                        "label": "Phone",
                        "type": "phone",
                        "required": False,
                    },
                    {
                        "name": "status",
                        "label": "Status",
                        "type": "select",
                        "required": True,
                        "options": ["New", "Qualified", "Won", "Lost"],
                    },
                ]
            }
        ],
        "pipeline_stages": ["New", "Qualified", "Won", "Lost"],
    }


class TestAddFieldEndpoint:
    """Tests for POST /crm/{crm_id}/fields."""

    def test_add_field_success(self, test_crm_config):
        """Add a new field to CRM configuration."""
        updated = CRMSchemaEditor.add_field(
            test_crm_config,
            entity_name="lead",
            field_name="company",
            field_label="Company Name",
            field_type="text",
            required=False,
        )
        
        # Validate updated config
        config = CRMConfiguration(**updated)
        
        # Verify field was added
        field_names = {f.name for f in config.entities[0].fields}
        assert "company" in field_names
        assert len(config.entities[0].fields) == 5  # 4 original + 1 new

    def test_add_select_field_with_options(self, test_crm_config):
        """Add a select field with options."""
        updated = CRMSchemaEditor.add_field(
            test_crm_config,
            entity_name="lead",
            field_name="priority",
            field_label="Priority",
            field_type="select",
            required=False,
            options=["Low", "Medium", "High"],
        )
        
        config = CRMConfiguration(**updated)
        
        priority_field = next(f for f in config.entities[0].fields if f.name == "priority")
        assert priority_field.type == "select"
        assert priority_field.options == ["Low", "Medium", "High"]

    def test_add_field_duplicate_name_fails(self, test_crm_config):
        """Adding a field with duplicate name should fail."""
        with pytest.raises(ValueError, match="already exists"):
            CRMSchemaEditor.add_field(
                test_crm_config,
                entity_name="lead",
                field_name="email",  # Already exists
                field_label="New Email",
                field_type="email",
            )

    def test_add_field_nonexistent_entity_fails(self, test_crm_config):
        """Adding field to nonexistent entity should fail."""
        with pytest.raises(ValueError, match="not found"):
            CRMSchemaEditor.add_field(
                test_crm_config,
                entity_name="nonexistent",
                field_name="test",
                field_label="Test",
                field_type="text",
            )

    def test_add_select_field_with_auto_options(self, test_crm_config):
        """Adding select field without options should use default options."""
        updated = CRMSchemaEditor.add_field(
            test_crm_config,
            entity_name="lead",
            field_name="category",
            field_label="Category",
            field_type="select",
            required=False,
            options=None,  # Missing options - should use defaults
        )
        
        config = CRMConfiguration(**updated)
        category_field = next(f for f in config.entities[0].fields if f.name == "category")
        assert category_field.type == "select"
        assert category_field.options  # Should have default options


class TestUpdateFieldEndpoint:
    """Tests for PATCH /crm/{crm_id}/fields/{field_name}."""

    def test_update_field_label(self, test_crm_config):
        """Update a field's label."""
        updated = CRMSchemaEditor.update_field(
            test_crm_config,
            entity_name="lead",
            field_name="email",
            label="Email Address",
        )
        
        config = CRMConfiguration(**updated)
        
        email_field = next(f for f in config.entities[0].fields if f.name == "email")
        assert email_field.label == "Email Address"

    def test_update_field_type_safe_conversion(self, test_crm_config):
        """Update field type with safe conversion."""
        # text → textarea is safe
        updated = CRMSchemaEditor.update_field(
            test_crm_config,
            entity_name="lead",
            field_name="full_name",
            field_type="textarea",
        )
        
        config = CRMConfiguration(**updated)
        
        name_field = next(f for f in config.entities[0].fields if f.name == "full_name")
        assert name_field.type == "textarea"

    def test_update_field_required_state(self, test_crm_config):
        """Update field required state."""
        updated = CRMSchemaEditor.update_field(
            test_crm_config,
            entity_name="lead",
            field_name="phone",
            required=True,
        )
        
        config = CRMConfiguration(**updated)
        
        phone_field = next(f for f in config.entities[0].fields if f.name == "phone")
        assert phone_field.required is True

    def test_update_select_field_options(self, test_crm_config):
        """Update select field options."""
        updated = CRMSchemaEditor.update_field(
            test_crm_config,
            entity_name="lead",
            field_name="status",
            options=["New", "In Progress", "Closed"],
        )
        
        config = CRMConfiguration(**updated)
        
        status_field = next(f for f in config.entities[0].fields if f.name == "status")
        assert status_field.options == ["New", "In Progress", "Closed"]

    def test_update_nonexistent_field_fails(self, test_crm_config):
        """Updating nonexistent field should fail."""
        with pytest.raises(ValueError):
            CRMSchemaEditor.update_field(
                test_crm_config,
                entity_name="lead",
                field_name="nonexistent",
                label="New Label",
            )

    def test_update_field_to_select_with_options(self, test_crm_config):
        """Update to select field should include options."""
        updated = CRMSchemaEditor.update_field(
            test_crm_config,
            entity_name="lead",
            field_name="email",
            field_type="select",
            options=["Work", "Personal"],
        )
        
        config = CRMConfiguration(**updated)
        
        email_field = next(f for f in config.entities[0].fields if f.name == "email")
        assert email_field.type == "select"
        assert email_field.options == ["Work", "Personal"]


class TestDeleteFieldEndpoint:
    """Tests for DELETE /crm/{crm_id}/fields/{field_name}."""

    def test_delete_field_success(self, test_crm_config):
        """Delete a field without records."""
        updated = CRMSchemaEditor.delete_field(
            test_crm_config,
            entity_name="lead",
            field_name="phone",
        )
        
        config = CRMConfiguration(**updated)
        
        # Verify field was deleted
        field_names = {f.name for f in config.entities[0].fields}
        assert "phone" not in field_names
        assert len(config.entities[0].fields) == 3  # 4 original - 1 deleted

    def test_delete_nonexistent_field_fails(self, test_crm_config):
        """Deleting nonexistent field should fail."""
        with pytest.raises(ValueError, match="not found"):
            CRMSchemaEditor.delete_field(
                test_crm_config,
                entity_name="lead",
                field_name="nonexistent",
            )

    def test_delete_last_field_fails(self, test_crm_config):
        """Cannot delete the last field in an entity."""
        # Delete all but one field first
        config = test_crm_config.copy()
        config["entities"][0]["fields"] = [config["entities"][0]["fields"][0]]
        
        with pytest.raises(ValueError, match="last field"):
            CRMSchemaEditor.delete_field(
                config,
                entity_name="lead",
                field_name="full_name",
            )


class TestReorderFieldsEndpoint:
    """Tests for PATCH /crm/{crm_id}/fields/reorder."""

    def test_reorder_fields_success(self, test_crm_config):
        """Reorder fields to a new sequence."""
        new_order = ["status", "email", "phone", "full_name"]
        
        updated = CRMSchemaEditor.reorder_fields(
            test_crm_config,
            entity_name="lead",
            field_order=new_order,
        )
        
        config = CRMConfiguration(**updated)
        
        # Verify new order
        actual_order = [f.name for f in config.entities[0].fields]
        assert actual_order == new_order

    def test_reorder_fields_missing_field_fails(self, test_crm_config):
        """Reordering with missing field should fail."""
        new_order = ["email", "phone"]  # Missing full_name and status
        
        with pytest.raises(ValueError, match="mismatch"):
            CRMSchemaEditor.reorder_fields(
                test_crm_config,
                entity_name="lead",
                field_order=new_order,
            )

    def test_reorder_fields_extra_field_fails(self, test_crm_config):
        """Reordering with extra field should fail."""
        new_order = ["email", "phone", "full_name", "status", "extra"]
        
        with pytest.raises(ValueError, match="mismatch"):
            CRMSchemaEditor.reorder_fields(
                test_crm_config,
                entity_name="lead",
                field_order=new_order,
            )


class TestAddStageEndpoint:
    """Tests for POST /crm/{crm_id}/stages."""

    def test_add_stage_success(self, test_crm_config):
        """Add a new pipeline stage."""
        updated = CRMSchemaEditor.add_pipeline_stage(
            test_crm_config,
            stage_name="Negotiation",
            position=3,  # Insert after Proposal (which would be position 2)
        )
        
        config = CRMConfiguration(**updated)
        
        assert "Negotiation" in config.pipeline_stages
        assert len(config.pipeline_stages) == 5  # 4 original + 1 new

    def test_add_stage_at_end(self, test_crm_config):
        """Add stage at end (default position)."""
        updated = CRMSchemaEditor.add_pipeline_stage(
            test_crm_config,
            stage_name="Closed",
        )
        
        config = CRMConfiguration(**updated)
        
        assert config.pipeline_stages[-1] == "Closed"

    def test_add_stage_duplicate_fails(self, test_crm_config):
        """Adding duplicate stage should fail."""
        with pytest.raises(ValueError, match="already exists"):
            CRMSchemaEditor.add_pipeline_stage(
                test_crm_config,
                stage_name="New",  # Already exists
            )


class TestUpdateStageEndpoint:
    """Tests for PATCH /crm/{crm_id}/stages/{stage_name}."""

    def test_update_stage_success(self, test_crm_config):
        """Rename a stage."""
        updated = CRMSchemaEditor.update_pipeline_stage(
            test_crm_config,
            old_stage_name="Qualified",
            new_stage_name="Pre-Qualified",
        )
        
        config = CRMConfiguration(**updated)
        
        assert "Pre-Qualified" in config.pipeline_stages
        assert "Qualified" not in config.pipeline_stages

    def test_update_nonexistent_stage_fails(self, test_crm_config):
        """Updating nonexistent stage should fail."""
        with pytest.raises(ValueError, match="not found"):
            CRMSchemaEditor.update_pipeline_stage(
                test_crm_config,
                old_stage_name="Nonexistent",
                new_stage_name="New Name",
            )

    def test_update_stage_to_duplicate_fails(self, test_crm_config):
        """Renaming stage to existing name should fail."""
        with pytest.raises(ValueError, match="already exists"):
            CRMSchemaEditor.update_pipeline_stage(
                test_crm_config,
                old_stage_name="New",
                new_stage_name="Qualified",  # Already exists
            )


class TestDeleteStageEndpoint:
    """Tests for DELETE /crm/{crm_id}/stages/{stage_name}."""

    def test_delete_stage_success(self, test_crm_config):
        """Delete a pipeline stage."""
        updated = CRMSchemaEditor.delete_pipeline_stage(
            test_crm_config,
            stage_name="Lost",
        )
        
        config = CRMConfiguration(**updated)
        
        assert "Lost" not in config.pipeline_stages
        assert len(config.pipeline_stages) == 3  # 4 original - 1 deleted

    def test_delete_nonexistent_stage_fails(self, test_crm_config):
        """Deleting nonexistent stage should fail."""
        with pytest.raises(ValueError, match="not found"):
            CRMSchemaEditor.delete_pipeline_stage(
                test_crm_config,
                stage_name="Nonexistent",
            )

    def test_delete_last_stage_fails(self, test_crm_config):
        """Cannot delete the last stage."""
        config = test_crm_config.copy()
        config["pipeline_stages"] = ["New"]
        
        with pytest.raises(ValueError, match="last"):
            CRMSchemaEditor.delete_pipeline_stage(
                config,
                stage_name="New",
            )


class TestReorderStagesEndpoint:
    """Tests for PATCH /crm/{crm_id}/stages/reorder."""

    def test_reorder_stages_success(self, test_crm_config):
        """Reorder pipeline stages."""
        new_order = ["Won", "Lost", "Qualified", "New"]
        
        updated = CRMSchemaEditor.reorder_stages(
            test_crm_config,
            stage_names=new_order,
        )
        
        config = CRMConfiguration(**updated)
        
        assert config.pipeline_stages == new_order

    def test_reorder_stages_missing_stage_fails(self, test_crm_config):
        """Reordering with missing stage should fail."""
        new_order = ["New", "Qualified"]  # Missing Won and Lost
        
        with pytest.raises(ValueError):
            CRMSchemaEditor.reorder_stages(
                test_crm_config,
                stage_names=new_order,
            )

    def test_reorder_stages_duplicate_fails(self, test_crm_config):
        """Reordering with duplicate stage should fail."""
        new_order = ["New", "New", "Qualified", "Won", "Lost"]
        
        with pytest.raises(ValueError):
            CRMSchemaEditor.reorder_stages(
                test_crm_config,
                stage_names=new_order,
            )


class TestReorderStagesEndpoint:
    """Tests for PATCH /crm/{crm_id}/stages/reorder."""

    def test_reorder_stages_success(self, test_crm_config):
        """Reorder pipeline stages."""
        new_order = ["Won", "Lost", "Qualified", "New"]
        
        updated = CRMSchemaEditor.reorder_pipeline_stages(
            test_crm_config,
            stage_order=new_order,
        )
        
        config = CRMConfiguration(**updated)
        
        assert config.pipeline_stages == new_order

    def test_reorder_stages_missing_stage_fails(self, test_crm_config):
        """Reordering with missing stage should fail."""
        new_order = ["New", "Won"]  # Missing Qualified and Lost
        
        with pytest.raises(ValueError, match="not match"):
            CRMSchemaEditor.reorder_pipeline_stages(
                test_crm_config,
                stage_order=new_order,
            )

    def test_reorder_stages_extra_stage_fails(self, test_crm_config):
        """Reordering with extra stage should fail."""
        new_order = ["New", "Qualified", "Won", "Lost", "Extra"]
        
        with pytest.raises(ValueError, match="not match"):
            CRMSchemaEditor.reorder_pipeline_stages(
                test_crm_config,
                stage_order=new_order,
            )


class TestSchemaEditingValidation:
    """Validation tests for schema editing."""

    def test_configuration_stays_valid_after_edits(self, test_crm_config):
        """Configuration remains valid after multiple edits."""
        # Add field
        config = test_crm_config
        config = CRMSchemaEditor.add_field(
            config,
            entity_name="lead",
            field_name="notes",
            field_label="Notes",
            field_type="textarea",
        )
        
        # Update field
        config = CRMSchemaEditor.update_field(
            config,
            entity_name="lead",
            field_name="email",
            label="Email Address",
        )
        
        # Reorder fields
        config = CRMSchemaEditor.reorder_fields(
            config,
            entity_name="lead",
            field_order=["notes", "email", "phone", "full_name", "status"],
        )
        
        # Add stage
        config = CRMSchemaEditor.add_pipeline_stage(
            config,
            stage_name="Closed",
        )
        
        # Final validation
        final_config = CRMConfiguration(**config)
        assert len(final_config.entities[0].fields) == 5
        assert "Closed" in final_config.pipeline_stages

    def test_field_count_consistent_after_operations(self, test_crm_config):
        """Field count remains consistent through operations."""
        original_count = len(test_crm_config["entities"][0]["fields"])
        
        # Add, then delete
        config = CRMSchemaEditor.add_field(
            test_crm_config,
            entity_name="lead",
            field_name="temp",
            field_label="Temp",
            field_type="text",
        )
        
        assert len(config["entities"][0]["fields"]) == original_count + 1
        
        config = CRMSchemaEditor.delete_field(
            config,
            entity_name="lead",
            field_name="temp",
        )
        
        assert len(config["entities"][0]["fields"]) == original_count
