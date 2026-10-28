"""Schema preservation and validation layer.

Ensures that:
1. All user-requested fields are extracted
2. Generated schema is validated against extracted fields
3. Missing fields are detected and can be repaired
4. Field count matches user expectations
"""
from __future__ import annotations

from typing import Any
import logging

from app.schemas.crm import CRMConfiguration, CRMEntity, CRMField, FieldType
from app.services.field_extractor import FieldExtractor, ExtractedField

logger = logging.getLogger(__name__)


class SchemaPreservation:
    """Validation and repair of generated CRM schemas."""

    @staticmethod
    def validate_and_repair_schema(
        generated_config: dict[str, Any],
        user_prompt: str,
    ) -> dict[str, Any]:
        """
        Validate a generated CRM configuration against user expectations.

        1. Extract fields explicitly mentioned in the prompt
        2. Check if generated schema has all those fields
        3. Repair/add missing fields if needed
        4. Validate the final schema with Pydantic

        Returns: A repaired, validated configuration dict ready for CRMConfiguration()
        """
        # Extract explicitly requested fields from prompt
        extracted_fields = FieldExtractor.extract_fields_from_prompt(user_prompt)
        extracted_stages = FieldExtractor.extract_pipeline_stages(user_prompt)

        logger.info(
            "[SchemaPreservation] Validating schema. Prompt has %d extracted fields, %d stages",
            len(extracted_fields),
            len(extracted_stages)
        )

        # Get the main entity (usually 'lead' or first entity)
        if not generated_config.get("entities"):
            raise ValueError("Generated configuration has no entities")

        # For now, work with the first entity (most CRMs start with one main entity)
        entity = generated_config["entities"][0]
        entity_name = entity.get("name", "lead")

        # Build a map of existing fields by machine key
        existing_fields_by_key: dict[str, dict[str, Any]] = {}
        if "fields" in entity:
            for field in entity["fields"]:
                key = field.get("name", "").lower()
                if key:
                    existing_fields_by_key[key] = field

        logger.debug(
            "[SchemaPreservation] Entity %s has %d existing fields",
            entity_name,
            len(existing_fields_by_key)
        )

        # Check for missing extracted fields
        missing_fields: list[ExtractedField] = []
        for extracted in extracted_fields:
            if extracted.machine_key not in existing_fields_by_key:
                missing_fields.append(extracted)
                logger.warning(
                    "[SchemaPreservation] Field not found in generated schema: %s (key: %s)",
                    extracted.label,
                    extracted.machine_key
                )

        # Add missing fields to the schema
        if missing_fields:
            logger.info(
                "[SchemaPreservation] Adding %d missing fields to schema",
                len(missing_fields)
            )
            for extracted in missing_fields:
                new_field = {
                    "name": extracted.machine_key,
                    "label": extracted.label,
                    "type": SchemaPreservation._validate_field_type(extracted.inferred_type),
                    "required": extracted.required,
                }

                # Handle select fields
                if new_field["type"] == "select":
                    new_field["options"] = ["Option 1", "Option 2"]

                entity["fields"].append(new_field)
                logger.debug(
                    "[SchemaPreservation] Added field: %s (type: %s)",
                    extracted.machine_key,
                    new_field["type"]
                )

        # Handle explicitly mentioned pipeline stages
        if extracted_stages and generated_config.get("pipeline_stages"):
            current_stages = generated_config["pipeline_stages"]
            logger.info(
                "[SchemaPreservation] Generated %d stages, user mentioned %d stages",
                len(current_stages),
                len(extracted_stages)
            )

            # If user explicitly listed stages that differ significantly, use those
            if len(extracted_stages) > 0 and len(extracted_stages) != len(current_stages):
                logger.info(
                    "[SchemaPreservation] Replacing pipeline stages with user-extracted stages"
                )
                generated_config["pipeline_stages"] = extracted_stages

        # Final validation with Pydantic
        try:
            validated = CRMConfiguration(**generated_config)
            logger.info(
                "[SchemaPreservation] Schema validation passed. Final entity has %d fields",
                len(validated.entities[0].fields) if validated.entities else 0
            )
            return validated.model_dump()
        except Exception as exc:
            logger.error("[SchemaPreservation] Schema validation failed: %s", exc)
            raise ValueError(f"Failed to validate repaired schema: {exc}")

    @staticmethod
    def _validate_field_type(field_type: str) -> FieldType:
        """Validate and normalize field type."""
        valid_types = {"text", "textarea", "email", "number", "date", "boolean", "select", "phone", "url"}

        normalized = field_type.lower().strip()
        if normalized not in valid_types:
            logger.debug(
                "[SchemaPreservation] Invalid field type %s, using 'text'",
                normalized
            )
            return "text"
        return normalized  # type: ignore

    @staticmethod
    def compare_field_counts(
        generated_config: dict[str, Any],
        extracted_count: int,
    ) -> dict[str, Any]:
        """
        Compare field counts and report any discrepancies.

        Returns: dict with "generated_count", "extracted_count", "missing_count", "ok"
        """
        if not generated_config.get("entities"):
            return {
                "generated_count": 0,
                "extracted_count": extracted_count,
                "missing_count": extracted_count,
                "ok": False,
                "reason": "No entities in generated config",
            }

        generated_count = len(generated_config["entities"][0].get("fields", []))

        return {
            "generated_count": generated_count,
            "extracted_count": extracted_count,
            "missing_count": max(0, extracted_count - generated_count),
            "ok": generated_count >= extracted_count,
            "reason": (
                "All fields preserved"
                if generated_count >= extracted_count
                else f"{extracted_count - generated_count} field(s) lost"
            ),
        }
