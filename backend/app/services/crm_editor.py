"""CRM schema editing operations.

Universal, CRM-type-agnostic operations for:
- Adding, updating, deleting, reordering fields
- Adding, updating, deleting, reordering pipeline stages
- Preserving existing records when editing

No hardcoded CRM type checks. Works for ANY CRM.
"""
from __future__ import annotations

from typing import Any
import logging
from uuid import UUID

from app.schemas.crm import CRMConfiguration, CRMEntity, CRMField, FieldType

logger = logging.getLogger(__name__)


class CRMSchemaEditor:
    """Generic CRM schema editing operations."""

    @staticmethod
    def add_field(
        config: dict[str, Any],
        entity_name: str,
        field_name: str,
        field_label: str,
        field_type: FieldType = "text",
        required: bool = False,
        options: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Add a new field to an entity in the CRM configuration.

        Args:
            config: Current CRM configuration
            entity_name: Which entity to add the field to (e.g., "lead")
            field_name: Machine-readable field name (lowercase, underscores)
            field_label: Human-readable field label
            field_type: Type of field (text, email, select, etc.)
            required: Whether the field is required
            options: For select fields, list of available options

        Returns: Updated configuration

        Raises:
            ValueError: If entity not found, field already exists, or invalid input
        """
        config = CRMConfiguration(**config).model_dump()  # Validate

        entity = CRMSchemaEditor._get_entity(config, entity_name)
        if not entity:
            raise ValueError(f"Entity '{entity_name}' not found in CRM")

        # Check if field already exists
        existing_keys = {f["name"] for f in entity["fields"]}
        if field_name in existing_keys:
            raise ValueError(f"Field '{field_name}' already exists in entity '{entity_name}'")

        # Create new field
        new_field: dict[str, Any] = {
            "name": field_name,
            "label": field_label,
            "type": field_type,
            "required": required,
        }

        if field_type == "select":
            new_field["options"] = options or ["Option 1", "Option 2"]

        # Add to entity
        entity["fields"].append(new_field)

        logger.info(
            "[CRMEditor] Added field '%s' (type: %s) to entity '%s'",
            field_name,
            field_type,
            entity_name
        )

        return config

    @staticmethod
    def update_field(
        config: dict[str, Any],
        entity_name: str,
        field_name: str,
        label: str | None = None,
        field_type: FieldType | None = None,
        required: bool | None = None,
        options: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update an existing field's properties."""
        config = CRMConfiguration(**config).model_dump()  # Validate

        entity = CRMSchemaEditor._get_entity(config, entity_name)
        if not entity:
            raise ValueError(f"Entity '{entity_name}' not found")

        field = next((f for f in entity["fields"] if f["name"] == field_name), None)
        if not field:
            raise ValueError(f"Field '{field_name}' not found in entity '{entity_name}'")

        # Update specified properties
        if label is not None:
            field["label"] = label
        if field_type is not None:
            field["type"] = field_type
        if required is not None:
            field["required"] = required
        if options is not None:
            field["options"] = options

        logger.info(
            "[CRMEditor] Updated field '%s' in entity '%s'",
            field_name,
            entity_name
        )

        return config

    @staticmethod
    def delete_field(
        config: dict[str, Any],
        entity_name: str,
        field_name: str,
    ) -> dict[str, Any]:
        """Delete a field from an entity."""
        config = CRMConfiguration(**config).model_dump()  # Validate

        entity = CRMSchemaEditor._get_entity(config, entity_name)
        if not entity:
            raise ValueError(f"Entity '{entity_name}' not found")

        field_count_before = len(entity["fields"])
        entity["fields"] = [f for f in entity["fields"] if f["name"] != field_name]

        if len(entity["fields"]) == field_count_before:
            raise ValueError(f"Field '{field_name}' not found in entity '{entity_name}'")

        if not entity["fields"]:
            raise ValueError("Cannot delete last field in entity")

        logger.info(
            "[CRMEditor] Deleted field '%s' from entity '%s'",
            field_name,
            entity_name
        )

        return config

    @staticmethod
    def reorder_fields(
        config: dict[str, Any],
        entity_name: str,
        field_order: list[str],
    ) -> dict[str, Any]:
        """Reorder fields in an entity."""
        config = CRMConfiguration(**config).model_dump()  # Validate

        entity = CRMSchemaEditor._get_entity(config, entity_name)
        if not entity:
            raise ValueError(f"Entity '{entity_name}' not found")

        # Validate all fields exist
        existing_keys = {f["name"] for f in entity["fields"]}
        provided_keys = set(field_order)

        if provided_keys != existing_keys:
            missing = existing_keys - provided_keys
            extra = provided_keys - existing_keys
            raise ValueError(
                f"Field order mismatch. Missing: {missing}, Extra: {extra}"
            )

        # Reorder
        field_map = {f["name"]: f for f in entity["fields"]}
        entity["fields"] = [field_map[name] for name in field_order]

        logger.info(
            "[CRMEditor] Reordered %d fields in entity '%s'",
            len(field_order),
            entity_name
        )

        return config

    @staticmethod
    def add_pipeline_stage(
        config: dict[str, Any],
        stage_name: str,
        position: int | None = None,
    ) -> dict[str, Any]:
        """Add a new pipeline stage."""
        config = CRMConfiguration(**config).model_dump()  # Validate

        if stage_name in config["pipeline_stages"]:
            raise ValueError(f"Stage '{stage_name}' already exists")

        if position is None:
            config["pipeline_stages"].append(stage_name)
        else:
            if position < 0 or position > len(config["pipeline_stages"]):
                raise ValueError(f"Invalid position {position}")
            config["pipeline_stages"].insert(position, stage_name)

        logger.info(
            "[CRMEditor] Added pipeline stage '%s' at position %s",
            stage_name,
            position or "end"
        )

        return config

    @staticmethod
    def update_pipeline_stage(
        config: dict[str, Any],
        old_stage_name: str,
        new_stage_name: str,
    ) -> dict[str, Any]:
        """Rename a pipeline stage."""
        config = CRMConfiguration(**config).model_dump()  # Validate

        idx = next((i for i, s in enumerate(config["pipeline_stages"]) if s == old_stage_name), None)
        if idx is None:
            raise ValueError(f"Stage '{old_stage_name}' not found")

        if new_stage_name in config["pipeline_stages"]:
            raise ValueError(f"Stage '{new_stage_name}' already exists")

        config["pipeline_stages"][idx] = new_stage_name

        logger.info(
            "[CRMEditor] Renamed stage '%s' → '%s'",
            old_stage_name,
            new_stage_name
        )

        return config

    @staticmethod
    def delete_pipeline_stage(
        config: dict[str, Any],
        stage_name: str,
    ) -> dict[str, Any]:
        """Delete a pipeline stage."""
        config = CRMConfiguration(**config).model_dump()  # Validate

        if stage_name not in config["pipeline_stages"]:
            raise ValueError(f"Stage '{stage_name}' not found")

        if len(config["pipeline_stages"]) <= 1:
            raise ValueError("Cannot delete last pipeline stage")

        config["pipeline_stages"] = [s for s in config["pipeline_stages"] if s != stage_name]

        logger.info("[CRMEditor] Deleted pipeline stage '%s'", stage_name)

        return config

    @staticmethod
    def reorder_pipeline_stages(
        config: dict[str, Any],
        stage_order: list[str],
    ) -> dict[str, Any]:
        """Reorder pipeline stages."""
        config = CRMConfiguration(**config).model_dump()  # Validate

        if set(stage_order) != set(config["pipeline_stages"]):
            raise ValueError("Provided stage order does not match existing stages")

        config["pipeline_stages"] = stage_order

        logger.info("[CRMEditor] Reordered %d pipeline stages", len(stage_order))

        return config

    @staticmethod
    def _get_entity(config: dict[str, Any], entity_name: str) -> dict[str, Any] | None:
        """Get an entity from the configuration by name."""
        for entity in config.get("entities", []):
            if entity.get("name") == entity_name:
                return entity
        return None
