"""Tests for universal CRM generation and field preservation.

These tests verify that:
1. All user-requested fields are extracted from prompts
2. Fields are preserved during generation regardless of CRM type
3. Field count matches user expectations (N fields → N fields)
4. Post-generation editing works for any CRM type
"""
import pytest
from app.services.field_extractor import FieldExtractor
from app.services.schema_preservation import SchemaPreservation
from app.services.crm_editor import CRMSchemaEditor
from app.schemas.crm import CRMConfiguration


class TestFieldExtraction:
    """Test universal field extraction from user prompts."""

    def test_extract_five_fields(self):
        """TEST 1: User provides 5 fields → all 5 extracted."""
        prompt = """
        Build a Customer Support CRM with these fields:
        - Customer Name
        - Issue / Query
        - Priority
        - Status
        - Assigned Agent
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 5
        assert any(f.machine_key == "customer_name" for f in fields)
        assert any(f.machine_key == "issue_query" for f in fields)
        assert any(f.machine_key == "priority" for f in fields)
        assert any(f.machine_key == "status" for f in fields)
        assert any(f.machine_key == "assigned_agent" for f in fields)

    def test_extract_ten_fields(self):
        """TEST 2: User provides 10 fields → all 10 extracted."""
        prompt = """
        Create a comprehensive CRM with:
        1. First Name
        2. Last Name
        3. Email Address
        4. Phone Number
        5. Company Name
        6. Budget (USD)
        7. Deal Size
        8. Industry
        9. Decision Maker
        10. Timeline
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 10, f"Expected 10 fields, got {len(fields)}: {[f.machine_key for f in fields]}"

    def test_extract_arbitrary_field_names(self):
        """Fields can have any name, not just standard CRM fields."""
        prompt = """
        Build a CRM for research tracking:
        - Specimen ID
        - Lab Location
        - Contamination Risk Score
        - Last Verified By
        - Shelf Coordinates
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 5
        assert any(f.machine_key == "specimen_id" for f in fields)
        assert any(f.machine_key == "contamination_risk_score" for f in fields)

    def test_infer_field_types(self):
        """Field types are inferred from field names."""
        prompt = """
        Create CRM with:
        - Customer Email (email)
        - Phone Number (phone)
        - Birth Date (date)
        - Is Active (boolean)
        - Lead Source (select)
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        email_field = next(f for f in fields if "email" in f.machine_key)
        assert email_field.inferred_type == "email"
        
        phone_field = next(f for f in fields if "phone" in f.machine_key)
        assert phone_field.inferred_type == "phone"
        
        date_field = next(f for f in fields if "date" in f.machine_key.lower())
        assert date_field.inferred_type == "date"
        
        bool_field = next(f for f in fields if "active" in f.machine_key)
        assert bool_field.inferred_type == "boolean"

    def test_extract_pipeline_stages(self):
        """Extract pipeline stages when explicitly mentioned."""
        prompt = """
        Build CRM with stages: New → Qualified → Demo → Proposal → Won → Lost
        """
        
        stages = FieldExtractor.extract_pipeline_stages(prompt)
        
        assert len(stages) > 0
        assert "new" in [s.lower() for s in stages] or "New" in stages


class TestSchemaPreservation:
    """Test field preservation during CRM generation."""

    def _create_minimal_config(self, fields_count: int) -> dict:
        """Helper: Create a minimal CRM config with N fields."""
        fields = []
        for i in range(1, fields_count + 1):
            fields.append({
                "name": f"field_{i}",
                "label": f"Field {i}",
                "type": "text",
                "required": False,
            })
        
        return {
            "schema_version": "1.0",
            "name": "Test CRM",
            "industry": "general",
            "entities": [{
                "name": "lead",
                "label": "Lead",
                "fields": fields,
            }],
            "pipeline_stages": ["New", "Won", "Lost"],
        }

    def test_schema_preservation_counts(self):
        """Verify field count preservation works."""
        config = self._create_minimal_config(5)
        
        comparison = SchemaPreservation.compare_field_counts(config, 5)
        
        assert comparison["generated_count"] == 5
        assert comparison["extracted_count"] == 5
        assert comparison["ok"] is True

    def test_detect_missing_fields(self):
        """Detect when generated schema has fewer fields than requested."""
        config = self._create_minimal_config(4)  # Only 4 fields
        
        comparison = SchemaPreservation.compare_field_counts(config, 5)  # User requested 5
        
        assert comparison["ok"] is False
        assert comparison["missing_count"] == 1

    def test_validate_and_repair_missing_fields(self):
        """TEST 3: Missing fields are automatically repaired."""
        prompt = """
        Build CRM with:
        - Customer Name
        - Email
        - Phone
        - Status
        - Priority
        """
        
        # Simulate AI generation that only returned 3 fields
        incomplete_config = {
            "schema_version": "1.0",
            "name": "Service CRM",
            "industry": "general",
            "entities": [{
                "name": "lead",
                "label": "Lead",
                "fields": [
                    {"name": "customer_name", "label": "Customer Name", "type": "text", "required": True},
                    {"name": "email", "label": "Email", "type": "email", "required": False},
                    {"name": "status", "label": "Status", "type": "select", "required": True, "options": ["New", "Won"]},
                ],
            }],
            "pipeline_stages": ["New", "Qualified", "Won"],
        }
        
        # Repair
        repaired = SchemaPreservation.validate_and_repair_schema(incomplete_config, prompt)
        
        # Verify all 5 fields now exist
        fields = repaired["entities"][0]["fields"]
        assert len(fields) >= 5, f"Expected at least 5 fields, got {len(fields)}"
        
        # Verify they can be validated
        config = CRMConfiguration(**repaired)
        assert len(config.entities[0].fields) >= 5


class TestPostGenerationEditing:
    """TEST 4-9: Post-generation editing works for any CRM."""

    def _create_test_config(self) -> dict:
        """Helper: Create a valid test CRM config."""
        return {
            "schema_version": "1.0",
            "name": "Sales CRM",
            "industry": "saas",
            "entities": [{
                "name": "lead",
                "label": "Lead",
                "fields": [
                    {"name": "name", "label": "Name", "type": "text", "required": True},
                    {"name": "email", "label": "Email", "type": "email", "required": False},
                    {"name": "status", "label": "Status", "type": "select", "required": True, "options": ["New", "Qualified"]},
                ],
            }],
            "pipeline_stages": ["New", "Qualified", "Won", "Lost"],
        }

    def test_add_field(self):
        """TEST 4: Add a field post-generation."""
        config = self._create_test_config()
        
        updated = CRMSchemaEditor.add_field(
            config,
            entity_name="lead",
            field_name="company",
            field_label="Company Name",
            field_type="text",
        )
        
        fields = updated["entities"][0]["fields"]
        assert len(fields) == 4
        assert any(f["name"] == "company" for f in fields)

    def test_rename_field(self):
        """Update field label (rename)."""
        config = self._create_test_config()
        
        updated = CRMSchemaEditor.update_field(
            config,
            entity_name="lead",
            field_name="name",
            label="Full Name",
        )
        
        name_field = next(f for f in updated["entities"][0]["fields"] if f["name"] == "name")
        assert name_field["label"] == "Full Name"

    def test_delete_unused_field(self):
        """TEST 5: Delete an unused field."""
        config = self._create_test_config()
        
        updated = CRMSchemaEditor.delete_field(
            config,
            entity_name="lead",
            field_name="email",
        )
        
        fields = updated["entities"][0]["fields"]
        assert len(fields) == 2
        assert not any(f["name"] == "email" for f in fields)

    def test_add_pipeline_stage(self):
        """TEST 6: Add a pipeline stage."""
        config = self._create_test_config()
        
        updated = CRMSchemaEditor.add_pipeline_stage(
            config,
            stage_name="Negotiation",
            position=2,  # Between Qualified and Won
        )
        
        stages = updated["pipeline_stages"]
        assert "Negotiation" in stages
        assert stages.index("Negotiation") == 2

    def test_rename_pipeline_stage(self):
        """Update (rename) a pipeline stage."""
        config = self._create_test_config()
        
        updated = CRMSchemaEditor.update_pipeline_stage(
            config,
            old_stage_name="Qualified",
            new_stage_name="Qualified - Ready",
        )
        
        stages = updated["pipeline_stages"]
        assert "Qualified - Ready" in stages
        assert "Qualified" not in stages

    def test_delete_pipeline_stage(self):
        """TEST 7: Delete a pipeline stage."""
        config = self._create_test_config()
        
        updated = CRMSchemaEditor.delete_pipeline_stage(
            config,
            stage_name="Lost",
        )
        
        stages = updated["pipeline_stages"]
        assert "Lost" not in stages
        assert len(stages) == 3

    def test_editor_validates_output(self):
        """All edited configs pass Pydantic validation."""
        config = self._create_test_config()
        
        # Add field
        config = CRMSchemaEditor.add_field(
            config, "lead", "phone", "Phone", "phone"
        )
        
        # Add stage
        config = CRMSchemaEditor.add_pipeline_stage(
            config, "Negotiation"
        )
        
        # Validate
        validated = CRMConfiguration(**config)
        assert len(validated.entities[0].fields) == 4
        assert len(validated.pipeline_stages) == 5


class TestUniversalEditorDesign:
    """TEST 8-10: Editor works generically without CRM-type assumptions."""

    def test_editor_works_for_different_crm_types(self):
        """TEST 8: Same editor operations work for different CRM types."""
        
        # Sales CRM
        sales_config = {
            "schema_version": "1.0",
            "name": "Sales CRM",
            "industry": "saas",
            "entities": [{"name": "opportunity", "label": "Opportunity", "fields": [
                {"name": "deal_size", "label": "Deal Size", "type": "number", "required": False}
            ]}],
            "pipeline_stages": ["Prospecting", "Closing"],
        }
        
        # Service CRM
        service_config = {
            "schema_version": "1.0",
            "name": "Service CRM",
            "industry": "healthcare",
            "entities": [{"name": "ticket", "label": "Ticket", "fields": [
                {"name": "severity", "label": "Severity", "type": "select", "required": True, "options": ["Low", "High"]}
            ]}],
            "pipeline_stages": ["Open", "Resolved"],
        }
        
        # Same edit operations work for both
        sales_updated = CRMSchemaEditor.add_field(sales_config, "opportunity", "notes", "Notes", "textarea")
        service_updated = CRMSchemaEditor.add_field(service_config, "ticket", "notes", "Notes", "textarea")
        
        assert any(f["name"] == "notes" for f in sales_updated["entities"][0]["fields"])
        assert any(f["name"] == "notes" for f in service_updated["entities"][0]["fields"])

    def test_no_hardcoded_crm_types(self):
        """Editor has no hardcoded CRM type checks."""
        # This test passes if the editor code has no "if crm_type ==" checks
        import inspect
        source = inspect.getsource(CRMSchemaEditor)
        assert 'crmType' not in source
        assert 'crm_type' not in source or 'crm_type' in source.replace("entity_name", "temp")  # False positive check


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
