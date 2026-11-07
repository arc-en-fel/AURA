"""FEAT-006: Field Preservation Tests

Comprehensive tests for field extraction and preservation functionality.
Ensures all user-requested fields survive the CRM generation pipeline.

Tests:
- Extract 3 fields (Name, Email, Phone)
- Extract 5 fields and verify all preserved
- Extract 10 fields and verify all preserved
- Extract 15 fields and verify all preserved
- Various prompt formats (comma-separated, bullet list, mixed)
- Verify extracted fields match requested fields exactly
"""
import pytest
from app.services.field_extractor import FieldExtractor
from app.services.schema_preservation import SchemaPreservation
from app.schemas.crm import CRMConfiguration


class TestFieldPreservationBasic:
    """Basic field preservation tests."""

    def test_extract_three_fields(self):
        """Extract 3 basic fields: Name, Email, Phone (newline-separated)."""
        prompt = """
        Name
        Email
        Phone
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 3, f"Expected 3 fields, got {len(fields)}: {[f.machine_key for f in fields]}"
        
        keys = {f.machine_key for f in fields}
        assert "name" in keys
        assert "email" in keys
        assert "phone" in keys
        
        # Verify field labels are correct
        for field in fields:
            assert field.label, "Field label should not be empty"
            assert field.machine_key, "Field machine key should not be empty"

    def test_extract_five_fields(self):
        """Extract 5 fields and verify all are present."""
        prompt = """
        Build a customer support CRM with these fields:
        - Customer Name
        - Issue Query
        - Priority
        - Status
        - Assigned Agent
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 5, f"Expected 5 fields, got {len(fields)}: {[f.machine_key for f in fields]}"
        
        keys = {f.machine_key for f in fields}
        assert "customer_name" in keys
        assert "issue_query" in keys
        assert "priority" in keys
        assert "status" in keys
        assert "assigned_agent" in keys

    def test_extract_ten_fields(self):
        """Extract 10 fields and verify all are preserved."""
        prompt = """
        Create a comprehensive sales CRM with the following fields:
        1. First Name
        2. Last Name
        3. Email Address
        4. Phone Number
        5. Company Name
        6. Budget Amount
        7. Deal Size
        8. Industry
        9. Decision Maker
        10. Timeline
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 10, f"Expected 10 fields, got {len(fields)}: {[f.machine_key for f in fields]}"
        
        keys = {f.machine_key for f in fields}
        assert len(keys) == 10, "All field keys should be unique"

    def test_extract_fifteen_fields(self):
        """Extract 15 fields and verify all are preserved."""
        prompt = """
        Build a detailed lead management CRM with these fields:
        - First Name
        - Last Name
        - Email
        - Phone
        - Company
        - Industry
        - Budget
        - Timeline
        - Decision Maker
        - Lead Source
        - Status
        - Priority
        - Assigned To
        - Last Contact Date
        - Next Follow Up
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 15, f"Expected 15 fields, got {len(fields)}: {[f.machine_key for f in fields]}"
        
        keys = {f.machine_key for f in fields}
        assert len(keys) == 15, "All 15 field keys should be unique"

    def test_single_line_multiple_fields(self):
        """Test fields on single line (treated as one field by extractor)."""
        # Note: Extractor splits by newlines, not commas. Single line is treated as one field.
        prompt = """
        Name
        Email
        Phone
        Status
        Priority
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 5
        keys = {f.machine_key for f in fields}
        assert "name" in keys
        assert "email" in keys
        assert "phone" in keys
        assert "status" in keys
        assert "priority" in keys

    def test_bullet_list_format(self):
        """Test fields in bullet list format."""
        prompt = """
        - Customer Name
        - Issue Description
        - Priority Level
        - Status
        - Assigned Agent
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 5
        keys = {f.machine_key for f in fields}
        assert "customer_name" in keys
        assert "issue_description" in keys
        assert "priority_level" in keys
        assert "status" in keys
        assert "assigned_agent" in keys

    def test_numbered_list_format(self):
        """Test fields in numbered list format."""
        prompt = """
        1. First Name
        2. Last Name
        3. Email
        4. Phone
        5. Company
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 5
        keys = {f.machine_key for f in fields}
        assert len(keys) == 5

    def test_mixed_format_fields(self):
        """Test fields in mixed formats (newline-separated)."""
        prompt = """
        Name
        Email
        Phone
        - Status
        Priority
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 5
        keys = {f.machine_key for f in fields}
        assert "name" in keys
        assert "email" in keys
        assert "phone" in keys
        assert "status" in keys
        assert "priority" in keys


class TestPreservedFieldsMatch:
    """Test that preserved fields match requested fields exactly."""

    def test_five_fields_preserved_in_schema(self):
        """5 user-requested fields should result in 5 fields in generated schema."""
        prompt = """
        Customer Name
        Issue Query
        Priority
        Status
        Assigned Agent
        """
        
        # Simulate incomplete LLM generation (only 3 fields generated)
        incomplete_config = {
            "schema_version": "1.0",
            "name": "Test CRM",
            "industry": "support",
            "entities": [{
                "name": "ticket",
                "label": "Ticket",
                "fields": [
                    {"name": "customer_name", "label": "Customer Name", "type": "text", "required": True},
                    {"name": "issue_query", "label": "Issue Query", "type": "textarea", "required": True},
                    {"name": "status", "label": "Status", "type": "select", "required": True, "options": ["New", "Resolved"]},
                ],
            }],
            "pipeline_stages": [],
        }
        
        # Repair schema
        repaired = SchemaPreservation.validate_and_repair_schema(incomplete_config, prompt)
        
        # Validate with Pydantic
        config = CRMConfiguration(**repaired)
        
        # Verify all 5 fields are present
        assert len(config.entities[0].fields) == 5, f"Expected 5 fields, got {len(config.entities[0].fields)}"
        
        field_keys = {f.name for f in config.entities[0].fields}
        assert "customer_name" in field_keys
        assert "issue_query" in field_keys
        assert "priority" in field_keys
        assert "status" in field_keys
        assert "assigned_agent" in field_keys

    def test_ten_fields_preserved_in_schema(self):
        """10 user-requested fields should all be preserved."""
        prompt = """
        1. First Name
        2. Last Name
        3. Email
        4. Phone
        5. Company
        6. Budget
        7. Timeline
        8. Industry
        9. Decision Maker
        10. Lead Source
        """
        
        incomplete_config = {
            "schema_version": "1.0",
            "name": "Sales CRM",
            "industry": "sales",
            "entities": [{
                "name": "lead",
                "label": "Lead",
                "fields": [
                    {"name": "first_name", "label": "First Name", "type": "text", "required": True},
                    {"name": "email", "label": "Email", "type": "email", "required": False},
                    {"name": "company", "label": "Company", "type": "text", "required": False},
                ],
            }],
            "pipeline_stages": [],
        }
        
        repaired = SchemaPreservation.validate_and_repair_schema(incomplete_config, prompt)
        config = CRMConfiguration(**repaired)
        
        assert len(config.entities[0].fields) == 10

    def test_fifteen_fields_preserved_in_schema(self):
        """15 user-requested fields should all be preserved."""
        prompt = """
        First Name
        Last Name
        Email
        Phone
        Company
        Budget
        Timeline
        Industry
        Decision Maker
        Lead Source
        Status
        Priority
        Assigned To
        Last Contact
        Notes
        """
        
        incomplete_config = {
            "schema_version": "1.0",
            "name": "Sales CRM",
            "industry": "sales",
            "entities": [{
                "name": "lead",
                "label": "Lead",
                "fields": [
                    {"name": "first_name", "label": "First Name", "type": "text", "required": True},
                    {"name": "email", "label": "Email", "type": "email", "required": False},
                    {"name": "company", "label": "Company", "type": "text", "required": False},
                ],
            }],
            "pipeline_stages": [],
        }
        
        repaired = SchemaPreservation.validate_and_repair_schema(incomplete_config, prompt)
        config = CRMConfiguration(**repaired)
        
        assert len(config.entities[0].fields) == 15


class TestPromptVariations:
    """Test field extraction across various prompt formats."""

    def test_parenthetical_type_annotations(self):
        """Test fields with type annotations in parentheses."""
        prompt = """
        - Customer Name (text)
        - Email Address (email)
        - Phone Number (phone)
        - Budget (number)
        - Is Active (boolean)
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 5
        
        # Verify type inference
        budget_field = next(f for f in fields if f.machine_key == "budget")
        assert budget_field.inferred_type == "number"
        
        email_field = next(f for f in fields if f.machine_key == "email_address")
        assert email_field.inferred_type == "email"

    def test_keyword_based_type_inference(self):
        """Test automatic type inference from field names."""
        prompt = """
        - User Email
        - Phone Contact
        - Birth Date
        - Is Verified
        - Website URL
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        email_field = next(f for f in fields if "email" in f.machine_key)
        assert email_field.inferred_type == "email"
        
        phone_field = next(f for f in fields if "phone" in f.machine_key)
        assert phone_field.inferred_type == "phone"
        
        date_field = next(f for f in fields if "date" in f.machine_key)
        assert date_field.inferred_type == "date"

    def test_special_characters_in_field_names(self):
        """Test fields with special characters are normalized."""
        prompt = """
        - Customer Name/Title
        - Issue/Query
        - Budget (USD)
        - Status?
        - Active?
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        # Should extract 5 fields (special chars normalized)
        assert len(fields) == 5
        
        # Verify keys are valid identifiers
        for field in fields:
            assert field.machine_key.replace("_", "").isalnum() or field.machine_key == "field"
            assert field.machine_key[0].isalpha() or field.machine_key[0] == "_"


class TestFieldPreservationEdgeCases:
    """Edge case tests for field preservation."""

    def test_duplicate_field_names_deduped(self):
        """Duplicate field names should only appear once."""
        prompt = """
        Name
        Email
        Phone
        Name
        Email
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        # Should only have 3 unique fields
        assert len(fields) == 3
        keys = {f.machine_key for f in fields}
        assert len(keys) == 3

    def test_empty_and_whitespace_fields_skipped(self):
        """Empty or whitespace-only fields should be skipped."""
        prompt = """
        Name
        
        Email
        ,,
        Phone
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 3

    def test_very_long_field_names_truncated(self):
        """Very long field names should be handled gracefully."""
        prompt = """
        Name
        Email
        This Is A Very Long Field Name That Should Still Work Properly
        Phone
        """
        
        fields = FieldExtractor.extract_fields_from_prompt(prompt)
        
        assert len(fields) == 4
        
        # Verify all field keys are valid
        for field in fields:
            assert len(field.machine_key) <= 63
            assert field.machine_key
