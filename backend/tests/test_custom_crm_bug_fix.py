"""Tests: Custom CRM Bug Fix

Verifies that "Other / Custom CRM" type with explicit user answers
does NOT get replaced by "General CRM" template.

Bug: User selects "Custom CRM" and provides answers:
- Fields: lead, email, phone, product, status
- Stages: New, In Progress, Done
- But system generates "General CRM" with predefined fields/stages

Fix: System now respects user answers and generates custom CRM.
"""
import pytest
from app.services.laya_system1 import LayaSystem1
from app.schemas.crm import CRMConfiguration


class TestCustomCRMBugFix:
    """Test the custom CRM generation from structured answers."""

    def test_generate_custom_crm_from_user_fields(self):
        """User-provided fields should be preserved, not replaced."""
        config = LayaSystem1.generate_custom_crm_from_answers(
            crm_type="custom",
            tracks="leads and deals",
            pipeline_stages="New, In Progress, Done",
            key_fields="lead, email, phone, product, status",
            team_size="Just me",
        )

        assert config["name"] == "Custom CRM" or "Lead" in config["name"]
        
        # Get the first entity
        entity = config["entities"][0]
        field_names = [f["name"] for f in entity["fields"]]
        
        # All user fields should be present
        assert "lead" in field_names
        assert "email" in field_names
        assert "phone" in field_names
        assert "product" in field_names
        assert "status" in field_names
        
        # Should NOT contain general CRM fields like "company", "lead_source"
        assert "company" not in field_names
        assert "lead_source" not in field_names
        field_names_lower = [f.lower() for f in field_names]
        assert "arr_estimate" not in field_names_lower

    def test_custom_crm_preserves_exact_stages(self):
        """User-provided stages should not be replaced with defaults."""
        config = LayaSystem1.generate_custom_crm_from_answers(
            crm_type="custom",
            tracks="projects and tasks",
            pipeline_stages="New → In Progress → Done",  # Arrow format
            key_fields="name, description, assigned_to",
            team_size=None,
        )

        stages = config["pipeline_stages"]
        
        # Should have exactly the user's 3 stages
        assert len(stages) == 3
        assert "New" in stages
        assert "In Progress" in stages
        assert "Done" in stages
        
        # Should NOT have sales CRM stages like "Demo Scheduled", "Proposal", etc.
        assert "Discovery" not in stages
        assert "Demo Scheduled" not in stages
        assert "Proposal" not in stages
        assert "Negotiation" not in stages

    def test_custom_crm_without_explicit_stages_gets_defaults(self):
        """If user omits stages, sensible defaults should be provided."""
        config = LayaSystem1.generate_custom_crm_from_answers(
            crm_type="custom",
            tracks="tasks",
            pipeline_stages=None,  # User didn't specify stages
            key_fields="name, due_date",
            team_size=None,
        )

        stages = config["pipeline_stages"]
        
        # Should have default stages
        assert len(stages) > 0
        # Should be reasonable defaults, not sales CRM stages
        assert "New" in stages or "Open" in stages

    def test_custom_crm_infers_field_types_correctly(self):
        """Field types should be inferred from field names."""
        config = LayaSystem1.generate_custom_crm_from_answers(
            crm_type="custom",
            tracks="contacts",
            pipeline_stages="Active, Archived",
            key_fields="name, email, phone, website, cost, priority, status",
            team_size=None,
        )

        entity = config["entities"][0]
        fields_by_name = {f["name"]: f for f in entity["fields"]}

        # Email field should be detected as email type
        assert fields_by_name["email"]["type"] == "email"
        
        # Phone field should be detected as phone type
        assert fields_by_name["phone"]["type"] == "phone"
        
        # Cost should be detected as number
        assert fields_by_name["cost"]["type"] == "number"
        
        # Status should be detected as select
        assert fields_by_name["status"]["type"] == "select"

    def test_not_general_crm(self):
        """Generated custom CRM should NOT be "General CRM"."""
        config = LayaSystem1.generate_custom_crm_from_answers(
            crm_type="custom",
            tracks="custom tracking",
            pipeline_stages="Stage1, Stage2",
            key_fields="field1, field2",
            team_size=None,
        )

        # Name should not be "General CRM"
        assert config["name"] != "General CRM"
        
        # Industry should not be "saas" (sales CRM default)
        assert config["industry"] in ("general", "custom", "generic") or config["industry"] != "saas"

    def test_validation_passes_for_custom_crm(self):
        """Generated custom CRM should pass Pydantic validation."""
        config = LayaSystem1.generate_custom_crm_from_answers(
            crm_type="custom",
            tracks="leads and opportunities",
            pipeline_stages="New,Contacted,Qualified,Proposal,Won,Lost",
            key_fields="lead_name,email,phone,company,deal_value,next_action",
            team_size="Small team",
        )

        # Should validate successfully
        validated = CRMConfiguration(**config)
        assert validated.schema_version == "1.0"
        assert len(validated.entities) >= 1
        assert len(validated.entities[0].fields) >= 1

    def test_compare_custom_vs_general(self):
        """Verify custom CRM is different from general CRM scaffold."""
        # Custom CRM from answers
        custom = LayaSystem1.generate_custom_crm_from_answers(
            crm_type="custom",
            tracks="leads",
            pipeline_stages="New, In Progress, Done",
            key_fields="lead, email, status",
            team_size=None,
        )

        # General CRM from plain text
        general = LayaSystem1.generate_scaffold_config("Build a CRM")

        # They should have different structures
        custom_fields = {f["name"] for entity in custom["entities"] for f in entity["fields"]}
        general_fields = {f["name"] for entity in general["entities"] for f in entity["fields"]}

        # Custom should have only user-requested fields
        assert "lead" in custom_fields
        
        # General should have default fields
        assert "full_name" in general_fields or "company" in general_fields

    def test_arrow_format_stages(self):
        """Pipeline stages with arrows should be parsed correctly."""
        config = LayaSystem1.generate_custom_crm_from_answers(
            crm_type="custom",
            tracks="sales",
            pipeline_stages="New → Contacted → Qualified → Proposal → Won",
            key_fields="name",
            team_size=None,
        )

        stages = config["pipeline_stages"]
        
        # Should have exactly 5 stages (arrow format)
        assert len(stages) == 5
        assert "New" in stages
        assert "Contacted" in stages
        assert "Qualified" in stages
        assert "Proposal" in stages
        assert "Won" in stages

    def test_custom_crm_with_minimal_input(self):
        """Custom CRM generation should work even with minimal input."""
        config = LayaSystem1.generate_custom_crm_from_answers(
            crm_type="custom",
            tracks=None,
            pipeline_stages=None,
            key_fields=None,
            team_size=None,
        )

        # Should generate valid CRM with defaults
        validated = CRMConfiguration(**config)
        assert len(validated.entities) >= 1
        assert len(validated.entities[0].fields) >= 1

    def test_custom_crm_does_not_include_general_defaults(self):
        """Custom CRM should not include General CRM default fields like ARR, Lead Source, etc."""
        config = LayaSystem1.generate_custom_crm_from_answers(
            crm_type="custom",
            tracks="project management",
            pipeline_stages="Backlog,Active,Completed",
            key_fields="title,description,assignee,due_date",
            team_size=None,
        )

        entity = config["entities"][0]
        field_names = {f["name"] for f in entity["fields"]}

        # Should NOT contain sales CRM fields
        forbidden_fields = {"full_name", "email", "company", "lead_source", "arr_estimate", "deal_size"}
        
        # Most forbidden fields should not be present (allow some overlap like "email")
        unexpected = field_names & forbidden_fields
        # Only allow "email" as overlap
        if "email" in unexpected:
            unexpected.discard("email")
        
        # Should have very few or no overlaps
        assert len(unexpected) < 2, f"Custom CRM has unexpected fields: {unexpected}"


class TestCustomCRMRegressions:
    """Ensure existing CRM types still work after the fix."""

    def test_sales_crm_still_works(self):
        """Sales CRM generation should not be broken."""
        config = LayaSystem1.generate_scaffold_config("Build a SaaS sales CRM for B2B leads and deals")
        
        # Should be detected as SaaS
        assert config["industry"] == "saas"
        
        # Should have predefined sales fields
        entity = config["entities"][0]
        field_names = {f["name"] for f in entity["fields"]}
        
        # Sales CRM should have expected fields
        assert "full_name" in field_names or "email" in field_names

    def test_healthcare_crm_still_works(self):
        """Healthcare CRM generation should not be broken."""
        config = LayaSystem1.generate_scaffold_config("Build a healthcare CRM for patient management")
        
        # Should be detected as healthcare
        assert config["industry"] == "healthcare"
        
        # Should have healthcare entity
        entity_names = {e["name"] for e in config["entities"]}
        assert "patient" in entity_names

    def test_real_estate_crm_still_works(self):
        """Real estate CRM generation should not be broken."""
        config = LayaSystem1.generate_scaffold_config("Build a real estate CRM for property listings and viewings")
        
        # Should be detected as real_estate
        assert config["industry"] == "real_estate"
        
        # Should have real_estate entity
        entity_names = {e["name"] for e in config["entities"]}
        assert "property_lead" in entity_names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
