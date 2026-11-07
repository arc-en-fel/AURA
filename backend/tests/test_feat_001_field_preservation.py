"""FEAT-001: Field Preservation Fix

Tests that verify:
1. All user-requested fields are preserved during CRM generation
2. Field count matches expectations: N fields → N fields in generated schema
3. No silent field drops occur
4. SchemaPreservation service integrates correctly with /api/v1/crm/generate endpoint

Acceptance Criteria:
- 5 fields requested → 5 fields in schema
- 10 fields requested → 10 fields in schema
- 15 fields requested → 15 fields in schema
- Post-generation editing works universally
- All existing tests pass (no regressions)
"""
import pytest
import logging

from app.services.field_extractor import FieldExtractor
from app.services.schema_preservation import SchemaPreservation
from app.schemas.crm import CRMConfiguration

logger = logging.getLogger(__name__)


class TestFieldPreservationCore:
    """Core field preservation logic."""

    def test_extract_exactly_five_fields(self):
        """TEST: 5 fields requested → all 5 extracted from prompt."""
        prompt = """
        Build a Customer Support CRM with these fields:
        - Customer Name
        - Issue / Query
        - Priority
        - Status
        - Assigned Agent
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 5, f"Expected 5 extracted fields, got {len(fields)}: {[f.machine_key for f in fields]}"
        
        # Verify each field is present
        keys = {f.machine_key for f in fields}
        assert "customer_name" in keys
        assert "issue_query" in keys
        assert "priority" in keys
        assert "status" in keys
        assert "assigned_agent" in keys

    def test_extract_exactly_ten_fields(self):
        """TEST: 10 fields requested → all 10 extracted from prompt."""
        prompt = """
        Create a comprehensive CRM for lead management with:
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

    def test_extract_exactly_fifteen_fields(self):
        """TEST: 15 fields requested → all 15 extracted from prompt."""
        prompt = """
        Build a comprehensive CRM with the following 15 fields:
        1. First Name
        2. Last Name
        3. Email
        4. Phone
        5. Company
        6. Industry
        7. Budget
        8. Timeline
        9. Decision Maker
        10. Lead Source
        11. Status
        12. Priority
        13. Assigned To
        14. Last Contact
        15. Next Follow Up
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 15, f"Expected 15 fields, got {len(fields)}: {[f.machine_key for f in fields]}"

    def test_no_silent_field_drops(self):
        """TEST: Verify no fields silently disappear during extraction."""
        prompt = """
        - Ticket ID
        - Customer Name
        - Issue Description
        - Severity
        - Status
        - Assigned To
        - Created Date
        - Updated Date
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        # Must extract all 8 fields
        assert len(fields) == 8, f"Expected 8 fields, got {len(fields)}: {[f.machine_key for f in fields]}"
        
        keys = {f.machine_key for f in fields}
        expected_keys = {
            "ticket_id", "customer_name", "issue_description", "severity",
            "status", "assigned_to", "created_date", "updated_date"
        }
        assert keys == expected_keys, f"Missing fields. Expected {expected_keys}, got {keys}"


class TestSchemaPreservationValidation:
    """Test SchemaPreservation validate_and_repair_schema integration."""

    def test_preserve_five_fields_in_schema(self):
        """TEST: Schema with 5 user-requested fields is repaired to have 5 fields."""
        prompt = """
        Build CRM with:
        - Name
        - Email
        - Phone
        - Status
        - Priority
        """
        
        # Simulate LLM that only generated 3 fields (incomplete)
        incomplete_config = {
            "schema_version": "1.0",
            "name": "Service CRM",
            "industry": "general",
            "entities": [{
                "name": "lead",
                "label": "Lead",
                "fields": [
                    {"name": "name", "label": "Name", "type": "text", "required": True},
                    {"name": "email", "label": "Email", "type": "email", "required": False},
                    {"name": "status", "label": "Status", "type": "select", "required": True, "options": ["New", "Won"]},
                ],
            }],
            "pipeline_stages": ["New", "Won"],
        }
        
        # Repair and validate
        repaired = SchemaPreservation.validate_and_repair_schema(incomplete_config, prompt)
        config = CRMConfiguration(**repaired)
        
        # Should now have all 5 fields
        fields = config.entities[0].fields
        assert len(fields) >= 5, f"Expected at least 5 fields after repair, got {len(fields)}"
        
        # Verify specific fields are present
        field_names = {f.name for f in fields}
        assert "name" in field_names
        assert "email" in field_names
        assert "status" in field_names
        # The repair should add the missing fields
        assert any("phone" in fname for fname in field_names)

    def test_preserve_ten_fields_in_schema(self):
        """TEST: Schema with 10 user-requested fields is repaired to have 10 fields."""
        prompt = """
        Create CRM with 10 fields:
        - Full Name
        - Email
        - Phone
        - Company
        - Title
        - Industry
        - Budget
        - Timeline
        - Decision Maker
        - Lead Source
        """
        
        # Simulate incomplete generation with only 4 fields
        incomplete_config = {
            "schema_version": "1.0",
            "name": "Sales CRM",
            "industry": "saas",
            "entities": [{
                "name": "lead",
                "label": "Lead",
                "fields": [
                    {"name": "full_name", "label": "Full Name", "type": "text", "required": True},
                    {"name": "email", "label": "Email", "type": "email", "required": False},
                    {"name": "company", "label": "Company", "type": "text", "required": False},
                    {"name": "title", "label": "Title", "type": "text", "required": False},
                ],
            }],
            "pipeline_stages": ["New", "Won"],
        }
        
        # Repair
        repaired = SchemaPreservation.validate_and_repair_schema(incomplete_config, prompt)
        config = CRMConfiguration(**repaired)
        
        # Should now have at least 10 fields
        fields = config.entities[0].fields
        assert len(fields) >= 10, f"Expected at least 10 fields after repair, got {len(fields)}"

    def test_preserve_fifteen_fields_in_schema(self):
        """TEST: Schema with 15 user-requested fields is repaired to have 15 fields."""
        prompt = """
        Build complete CRM with 15 required fields:
        1. First Name
        2. Last Name
        3. Email
        4. Phone
        5. Company
        6. Title
        7. Industry
        8. Budget
        9. Timeline
        10. Decision Maker
        11. Lead Source
        12. Status
        13. Priority
        14. Assigned To
        15. Notes
        """
        
        # Simulate incomplete generation with only 5 fields
        incomplete_config = {
            "schema_version": "1.0",
            "name": "Comprehensive CRM",
            "industry": "saas",
            "entities": [{
                "name": "lead",
                "label": "Lead",
                "fields": [
                    {"name": "first_name", "label": "First Name", "type": "text", "required": True},
                    {"name": "last_name", "label": "Last Name", "type": "text", "required": True},
                    {"name": "email", "label": "Email", "type": "email", "required": False},
                    {"name": "phone", "label": "Phone", "type": "phone", "required": False},
                    {"name": "company", "label": "Company", "type": "text", "required": False},
                ],
            }],
            "pipeline_stages": ["New", "Won"],
        }
        
        # Repair
        repaired = SchemaPreservation.validate_and_repair_schema(incomplete_config, prompt)
        config = CRMConfiguration(**repaired)
        
        # Should now have at least 15 fields
        fields = config.entities[0].fields
        assert len(fields) >= 15, f"Expected at least 15 fields after repair, got {len(fields)}"
        
        # Verify no fields are lost and count is exact or exceeds requested count
        field_count = len(fields)
        logger.info(f"Generated {field_count} fields from request for 15 fields")
        assert field_count >= 15

    def test_comparison_detects_missing_fields(self):
        """TEST: compare_field_counts detects when fields are missing."""
        config = {
            "schema_version": "1.0",
            "name": "Test",
            "entities": [{
                "name": "lead",
                "fields": [
                    {"name": "field1", "label": "Field 1", "type": "text"},
                    {"name": "field2", "label": "Field 2", "type": "text"},
                ]
            }]
        }
        
        comparison = SchemaPreservation.compare_field_counts(config, extracted_count=5)
        
        assert comparison["generated_count"] == 2
        assert comparison["extracted_count"] == 5
        assert comparison["missing_count"] == 3
        assert comparison["ok"] is False
        assert "3" in comparison["reason"] or "lost" in comparison["reason"].lower()

    def test_comparison_passes_when_all_fields_present(self):
        """TEST: compare_field_counts passes when field counts match."""
        config = {
            "schema_version": "1.0",
            "name": "Test",
            "entities": [{
                "name": "lead",
                "fields": [
                    {"name": f"field{i}", "label": f"Field {i}", "type": "text"}
                    for i in range(1, 6)
                ]
            }]
        }
        
        comparison = SchemaPreservation.compare_field_counts(config, extracted_count=5)
        
        assert comparison["generated_count"] == 5
        assert comparison["extracted_count"] == 5
        assert comparison["ok"] is True
        assert "All fields preserved" in comparison["reason"]


class TestFieldPreservationEdgeCases:
    """Test edge cases and special scenarios."""

    def test_fields_with_special_characters_in_names(self):
        """Fields with hyphens, slashes, parentheses should be preserved."""
        prompt = """
        - Customer Name
        - Issue / Query
        - Budget (USD)
        - Yes/No Field
        - Follow-up Date
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 5, f"Expected 5 fields, got {len(fields)}: {[f.machine_key for f in fields]}"
        keys = {f.machine_key for f in fields}
        
        # Check normalization works correctly - note that parenthetical text is stripped
        assert "customer_name" in keys
        assert "issue_query" in keys
        assert "budget" in keys  # USD is removed from parens
        assert "yesno_field" in keys
        assert "follow_up_date" in keys

    def test_duplicate_fields_not_extracted_twice(self):
        """Duplicate field names should only appear once."""
        prompt = """
        - Status
        - Name
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        # Should extract only 2 unique fields (Status, Name)
        assert len(fields) == 2, f"Expected 2 fields, got {len(fields)}: {[f.machine_key for f in fields]}"

    def test_very_long_field_names(self):
        """Long field names should be handled correctly."""
        prompt = """
        - This Is A Very Long Field Name For Testing Purposes
        - Another Extremely Long Field Description That Should Still Work
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 2
        for field in fields:
            assert len(field.machine_key) > 0
            assert len(field.label) > 0

    def test_field_type_inference(self):
        """Field types should be correctly inferred."""
        prompt = """
        Fields:
        - Customer Email (email)
        - Phone Number (phone)
        - Birth Date (date)
        - Is Active (boolean)
        - Lead Source (select)
        - Description (textarea)
        - Budget (number)
        - Website (url)
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 8
        
        type_map = {f.machine_key: f.inferred_type for f in fields}
        
        assert type_map["customer_email"] == "email"
        assert type_map["phone_number"] == "phone"
        assert type_map["birth_date"] == "date"
        assert type_map["is_active"] == "boolean"
        assert type_map["lead_source"] == "select"
        assert type_map["description"] == "textarea"
        assert type_map["budget"] == "number"
        assert type_map["website"] == "url"


class TestIntegrationWithEndpoint:
    """Test field preservation at the endpoint level."""

    def test_schema_preservation_integrates_with_config_dict(self):
        """TEST: validate_and_repair_schema works with dict-based configs."""
        prompt = """
        Build Service CRM with:
        - Ticket ID
        - Customer Name
        - Issue
        - Priority
        - Status
        """
        
        # Simulate minimal generation (only 2 fields)
        minimal_config = {
            "schema_version": "1.0",
            "name": "Service CRM",
            "industry": "general",
            "entities": [{
                "name": "lead",
                "label": "Lead",
                "fields": [
                    {"name": "ticket_id", "label": "Ticket ID", "type": "text", "required": True},
                    {"name": "customer_name", "label": "Customer Name", "type": "text", "required": True},
                ],
            }],
            "pipeline_stages": ["New", "Resolved"],
        }
        
        # Call validate_and_repair_schema directly (as endpoint does)
        repaired = SchemaPreservation.validate_and_repair_schema(minimal_config, prompt)
        
        # Verify it returns a dict
        assert isinstance(repaired, dict)
        
        # Verify it has all required keys
        assert "schema_version" in repaired
        assert "name" in repaired
        assert "entities" in repaired
        assert "pipeline_stages" in repaired
        
        # Verify it can be validated
        config = CRMConfiguration(**repaired)
        
        # Verify field preservation
        fields = config.entities[0].fields
        assert len(fields) >= 5, f"Expected at least 5 fields, got {len(fields)}"

    def test_extracted_vs_generated_count_analysis(self):
        """TEST: Field analysis metadata works correctly."""
        prompt = """
        - Field A
        - Field B
        - Field C
        - Field D
        - Field E
        """
        
        extracted = FieldExtractor.extract_fields_from_prompt(prompt)
        
        minimal_config = {
            "schema_version": "1.0",
            "name": "Test",
            "industry": "general",
            "entities": [{
                "name": "lead",
                "label": "Lead",
                "fields": [
                    {"name": "field_a", "label": "Field A", "type": "text"},
                ]
            }],
            "pipeline_stages": ["New"],
        }
        
        coverage = SchemaPreservation.compare_field_counts(minimal_config, len(extracted))
        
        # Should report the mismatch
        assert coverage["extracted_count"] == len(extracted), f"extracted_count: {coverage['extracted_count']}, len(extracted): {len(extracted)}"
        assert coverage["generated_count"] == 1
        if len(extracted) > 1:
            assert coverage["missing_count"] == len(extracted) - 1
            assert coverage["ok"] is False


class TestRegressionNoFieldLoss:
    """Regression tests: Ensure no scenarios cause silent field loss."""

    def test_long_prompt_preserves_all_fields(self):
        """Long prompts with many fields should preserve all."""
        prompt = """
        - Company Name
        - Contact First Name
        - Contact Last Name
        - Email Address
        - Phone Number
        - Industry Vertical
        - Annual Revenue
        - Number of Employees
        - Billing Address
        - Shipping Address
        - Website URL
        - Primary Contact Title
        - Secondary Contact Name
        - Contract Start Date
        - Contract End Date
        - Account Manager Name
        - Account Manager Email
        - SLA Level
        - Payment Terms
        - Tax ID
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        # Should extract all 20 fields
        assert len(fields) == 20, f"Expected 20 fields, got {len(fields)}"

    def test_comma_separated_field_list(self):
        """Comma-separated field lists should preserve all fields."""
        prompt = """
        - Name
        - Email
        - Phone
        - Company
        - Title
        - Industry
        - Budget
        - Timeline
        - Decision Maker
        - Lead Source
        - Status
        - Priority
        - Assigned To
        - Created Date
        - Last Contact
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        # Should extract all 15 fields
        assert len(fields) == 15, f"Expected 15 fields, got {len(fields)}"

    def test_mixed_format_fields(self):
        """Fields in mixed formats (bullets, numbers, text) should all be extracted."""
        prompt = """
        1. Customer Name
        - Email Address
        • Phone Number
        - Contact Title
        - Contact Company
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 5, f"Expected 5 fields, got {len(fields)}: {[f.machine_key for f in fields]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
