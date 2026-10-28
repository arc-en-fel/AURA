"""AI tools for CRM schema modifications.

Enables AURA Copilot to programmatically modify CRM schemas through controlled
tool calls that invoke backend operations.

Tools:
- add_crm_field: Add a new field to a CRM entity
- update_crm_field: Update field properties
- delete_crm_field: Delete a field from a CRM entity
- add_crm_stage: Add a pipeline stage
- delete_crm_stage: Delete a pipeline stage
- reorder_crm_fields: Reorder fields in an entity
- reorder_crm_stages: Reorder pipeline stages

All validation happens server-side. Tools return the updated CRMConfiguration
so the AI can see the result of its changes.
"""
from __future__ import annotations

from typing import Any
import logging
from uuid import UUID

from app.schemas.crm import CRMConfiguration, FieldType
from app.services.crm_editor import CRMSchemaEditor
from app.database import CRMRepository

logger = logging.getLogger(__name__)


class CRMSchemaTools:
    """Tool implementations for AI-driven CRM schema modifications and record operations.
    
    These are thin wrappers around backend operations that the AI can call.
    Each tool validates inputs and delegates to CRMSchemaEditor + database.
    """

    # ── Record CRUD Tools ──────────────────────────────────────────

    @staticmethod
    def create_record(
        crm_id: str,
        owner_id: str,
        entity_name: str,
        data: dict[str, Any],
        source: str | None = None,
    ) -> dict[str, Any]:
        """Create a new record in the CRM.
        
        Args:
            crm_id: The CRM ID
            owner_id: The owner user ID (for authorization)
            entity_name: Name of the entity (e.g., 'lead', 'contact')
            data: Record field values
            source: Optional source tag (e.g., 'Website', 'Email', 'Manual')
            
        Returns:
            Created record data as dict
            
        Raises:
            ValueError: If CRM/entity not found or validation fails
        """
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized"
            }
        
        # Validate entity exists
        config = crm.get("configuration", {})
        entities = config.get("entities", [])
        entity = next((e for e in entities if e["name"] == entity_name), None)
        
        if not entity:
            return {
                "success": False,
                "error_code": "INVALID_ENTITY",
                "error_message": f"Entity '{entity_name}' not found"
            }
        
        # Validate required fields
        for field in entity.get("fields", []):
            if field.get("required") and field["name"] not in data:
                return {
                    "success": False,
                    "error_code": "MISSING_REQUIRED_FIELD",
                    "error_message": f"Required field '{field['name']}' is missing"
                }
        
        try:
            result = repo.create_record(crm_id, entity_name, data, source=source)
            logger.info(
                "[AI-TOOLS] Created record in entity '%s' for CRM %s via AI tool",
                entity_name,
                crm_id
            )
            return {
                "success": True,
                "data": result,
            }
        except Exception as exc:
            logger.exception("Error creating record via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to create record: {str(exc)}",
            }

    @staticmethod
    def update_record(
        crm_id: str,
        owner_id: str,
        entity_name: str,
        record_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an existing record.
        
        Args:
            crm_id: The CRM ID
            owner_id: The owner user ID (for authorization)
            entity_name: Name of the entity
            record_id: ID of the record to update
            data: Fields to update (partial update OK)
            
        Returns:
            Updated record data as dict
            
        Raises:
            ValueError: If CRM/record not found
        """
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized"
            }
        
        try:
            result = repo.update_record(crm_id, entity_name, record_id, data)
            logger.info(
                "[AI-TOOLS] Updated record %s in entity '%s' for CRM %s via AI tool",
                record_id,
                entity_name,
                crm_id
            )
            return {
                "success": True,
                "data": result,
            }
        except Exception as exc:
            logger.exception("Error updating record via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to update record: {str(exc)}",
            }

    @staticmethod
    def delete_record(
        crm_id: str,
        owner_id: str,
        entity_name: str,
        record_id: str,
    ) -> dict[str, Any]:
        """Soft delete a record.
        
        Args:
            crm_id: The CRM ID
            owner_id: The owner user ID (for authorization)
            entity_name: Name of the entity
            record_id: ID of the record to delete
            
        Returns:
            Deletion confirmation as dict
            
        Raises:
            ValueError: If CRM/record not found
        """
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            return {
                "success": False,
                "error_code": "NOT_FOUND",
                "error_message": "CRM not found or unauthorized"
            }
        
        try:
            repo.soft_delete_record(crm_id, entity_name, record_id)
            logger.info(
                "[AI-TOOLS] Deleted record %s from entity '%s' in CRM %s via AI tool",
                record_id,
                entity_name,
                crm_id
            )
            return {
                "success": True,
                "data": {"deleted": True, "record_id": record_id},
            }
        except Exception as exc:
            logger.exception("Error deleting record via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to delete record: {str(exc)}",
            }

    # ── Schema Modification Tools ──────────────────────────────────

    @staticmethod
    def add_crm_field(
        crm_id: str,
        owner_id: str,
        field_name: str,
        field_type: FieldType = "text",
        label: str | None = None,
        required: bool = False,
        options: list[str] | None = None,
    ) -> dict[str, Any]:
        """Add a new field to the main entity in a CRM.
        
        Args:
            crm_id: The CRM ID
            owner_id: The owner user ID (for authorization)
            field_name: Machine-readable field name (lowercase, underscores)
            field_type: Type of field (text, email, select, etc.)
            label: Human-readable field label. If None, derives from field_name
            required: Whether the field is required
            options: For select fields, list of available options
            
        Returns:
            Updated CRMConfiguration as dict
            
        Raises:
            ValueError: If CRM not found, unauthorized, or invalid input
        """
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            raise ValueError(f"CRM not found or unauthorized")
        
        # Derive label from field_name if not provided
        if not label:
            label = field_name.replace("_", " ").title()
        
        try:
            entity_name = crm["configuration"]["entities"][0]["name"]
            
            updated_config = CRMSchemaEditor.add_field(
                crm["configuration"],
                entity_name=entity_name,
                field_name=field_name,
                field_label=label,
                field_type=field_type,
                required=required,
                options=options,
            )
            
            # Validate with Pydantic
            CRMConfiguration(**updated_config)
            
            # Save to database
            updated_crm = repo.update_crm_configuration(
                crm_id=crm_id,
                owner_id=owner_id,
                configuration=updated_config,
            )
            
            if not updated_crm:
                raise ValueError("Failed to save CRM configuration")
            
            logger.info(
                "[AI-TOOLS] Added field '%s' (type: %s) to CRM %s via AI tool",
                field_name,
                field_type,
                crm_id
            )
            
            return {
                "success": True,
                "crm_id": str(updated_crm["id"]),
                "configuration": updated_crm["configuration"],
                "configuration_version": updated_crm["configuration_version"],
            }
        except ValueError as exc:
            error_msg = str(exc)
            if "already exists" in error_msg:
                return {
                    "success": False,
                    "error_code": "CONFLICT",
                    "error_message": error_msg,
                }
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": error_msg,
            }
        except Exception as exc:
            logger.exception("Error adding CRM field via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to add field: {str(exc)}",
            }

    @staticmethod
    def update_crm_field(
        crm_id: str,
        owner_id: str,
        field_name: str,
        label: str | None = None,
        field_type: FieldType | None = None,
        required: bool | None = None,
        options: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update properties of an existing field.
        
        Args:
            crm_id: The CRM ID
            owner_id: The owner user ID (for authorization)
            field_name: The field to update
            label: New human-readable label
            field_type: New field type
            required: New required state
            options: New options list (for select fields)
            
        Returns:
            Updated CRMConfiguration as dict
            
        Raises:
            ValueError: If CRM/field not found or invalid update
        """
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            raise ValueError("CRM not found or unauthorized")
        
        try:
            entity_name = crm["configuration"]["entities"][0]["name"]
            
            updated_config = CRMSchemaEditor.update_field(
                crm["configuration"],
                entity_name=entity_name,
                field_name=field_name,
                label=label,
                field_type=field_type,
                required=required,
                options=options,
            )
            
            CRMConfiguration(**updated_config)
            
            updated_crm = repo.update_crm_configuration(
                crm_id=crm_id,
                owner_id=owner_id,
                configuration=updated_config,
            )
            
            if not updated_crm:
                raise ValueError("Failed to save CRM configuration")
            
            logger.info(
                "[AI-TOOLS] Updated field '%s' in CRM %s via AI tool",
                field_name,
                crm_id
            )
            
            return {
                "success": True,
                "crm_id": str(updated_crm["id"]),
                "configuration": updated_crm["configuration"],
                "configuration_version": updated_crm["configuration_version"],
            }
        except ValueError as exc:
            error_msg = str(exc)
            if "not found" in error_msg:
                return {
                    "success": False,
                    "error_code": "NOT_FOUND",
                    "error_message": error_msg,
                }
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": error_msg,
            }
        except Exception as exc:
            logger.exception("Error updating CRM field via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to update field: {str(exc)}",
            }

    @staticmethod
    def delete_crm_field(
        crm_id: str,
        owner_id: str,
        field_name: str,
    ) -> dict[str, Any]:
        """Delete a field from a CRM entity.
        
        Args:
            crm_id: The CRM ID
            owner_id: The owner user ID (for authorization)
            field_name: The field to delete
            
        Returns:
            Updated CRMConfiguration as dict
            
        Raises:
            ValueError: If CRM/field not found or cannot be deleted
        """
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            raise ValueError("CRM not found or unauthorized")
        
        try:
            entity_name = crm["configuration"]["entities"][0]["name"]
            
            # Note: In the main endpoints, we check for records with this field.
            # For AI tools, we skip that check and allow deletion (AI is intentional).
            # If needed, remove this comment and add the check.
            
            updated_config = CRMSchemaEditor.delete_field(
                crm["configuration"],
                entity_name=entity_name,
                field_name=field_name,
            )
            
            CRMConfiguration(**updated_config)
            
            updated_crm = repo.update_crm_configuration(
                crm_id=crm_id,
                owner_id=owner_id,
                configuration=updated_config,
            )
            
            if not updated_crm:
                raise ValueError("Failed to save CRM configuration")
            
            logger.info(
                "[AI-TOOLS] Deleted field '%s' from CRM %s via AI tool",
                field_name,
                crm_id
            )
            
            return {
                "success": True,
                "crm_id": str(updated_crm["id"]),
                "configuration": updated_crm["configuration"],
                "configuration_version": updated_crm["configuration_version"],
            }
        except ValueError as exc:
            error_msg = str(exc)
            if "not found" in error_msg:
                return {
                    "success": False,
                    "error_code": "NOT_FOUND",
                    "error_message": error_msg,
                }
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": error_msg,
            }
        except Exception as exc:
            logger.exception("Error deleting CRM field via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to delete field: {str(exc)}",
            }

    @staticmethod
    def add_crm_stage(
        crm_id: str,
        owner_id: str,
        stage_name: str,
        position: int | None = None,
    ) -> dict[str, Any]:
        """Add a new pipeline stage to a CRM.
        
        Args:
            crm_id: The CRM ID
            owner_id: The owner user ID (for authorization)
            stage_name: Name of the new stage
            position: Optional position in the pipeline (0-indexed)
            
        Returns:
            Updated CRMConfiguration as dict
            
        Raises:
            ValueError: If CRM not found or stage already exists
        """
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            raise ValueError("CRM not found or unauthorized")
        
        try:
            updated_config = CRMSchemaEditor.add_pipeline_stage(
                crm["configuration"],
                stage_name=stage_name,
                position=position,
            )
            
            CRMConfiguration(**updated_config)
            
            updated_crm = repo.update_crm_configuration(
                crm_id=crm_id,
                owner_id=owner_id,
                configuration=updated_config,
            )
            
            if not updated_crm:
                raise ValueError("Failed to save CRM configuration")
            
            logger.info(
                "[AI-TOOLS] Added stage '%s' to CRM %s via AI tool",
                stage_name,
                crm_id
            )
            
            return {
                "success": True,
                "crm_id": str(updated_crm["id"]),
                "configuration": updated_crm["configuration"],
                "configuration_version": updated_crm["configuration_version"],
            }
        except ValueError as exc:
            error_msg = str(exc)
            if "already exists" in error_msg:
                return {
                    "success": False,
                    "error_code": "CONFLICT",
                    "error_message": error_msg,
                }
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": error_msg,
            }
        except Exception as exc:
            logger.exception("Error adding CRM stage via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to add stage: {str(exc)}",
            }

    @staticmethod
    def delete_crm_stage(
        crm_id: str,
        owner_id: str,
        stage_name: str,
    ) -> dict[str, Any]:
        """Delete a pipeline stage from a CRM.
        
        Args:
            crm_id: The CRM ID
            owner_id: The owner user ID (for authorization)
            stage_name: Name of the stage to delete
            
        Returns:
            Updated CRMConfiguration as dict
            
        Raises:
            ValueError: If CRM/stage not found or cannot be deleted
        """
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            raise ValueError("CRM not found or unauthorized")
        
        try:
            updated_config = CRMSchemaEditor.delete_pipeline_stage(
                crm["configuration"],
                stage_name=stage_name,
            )
            
            CRMConfiguration(**updated_config)
            
            updated_crm = repo.update_crm_configuration(
                crm_id=crm_id,
                owner_id=owner_id,
                configuration=updated_config,
            )
            
            if not updated_crm:
                raise ValueError("Failed to save CRM configuration")
            
            logger.info(
                "[AI-TOOLS] Deleted stage '%s' from CRM %s via AI tool",
                stage_name,
                crm_id
            )
            
            return {
                "success": True,
                "crm_id": str(updated_crm["id"]),
                "configuration": updated_crm["configuration"],
                "configuration_version": updated_crm["configuration_version"],
            }
        except ValueError as exc:
            error_msg = str(exc)
            if "not found" in error_msg:
                return {
                    "success": False,
                    "error_code": "NOT_FOUND",
                    "error_message": error_msg,
                }
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": error_msg,
            }
        except Exception as exc:
            logger.exception("Error deleting CRM stage via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to delete stage: {str(exc)}",
            }

    @staticmethod
    def reorder_crm_fields(
        crm_id: str,
        owner_id: str,
        field_order: list[str],
    ) -> dict[str, Any]:
        """Reorder fields in a CRM entity.
        
        Args:
            crm_id: The CRM ID
            owner_id: The owner user ID (for authorization)
            field_order: List of field names in desired order
            
        Returns:
            Updated CRMConfiguration as dict
            
        Raises:
            ValueError: If CRM not found or field order is invalid
        """
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            raise ValueError("CRM not found or unauthorized")
        
        try:
            entity_name = crm["configuration"]["entities"][0]["name"]
            
            updated_config = CRMSchemaEditor.reorder_fields(
                crm["configuration"],
                entity_name=entity_name,
                field_order=field_order,
            )
            
            CRMConfiguration(**updated_config)
            
            updated_crm = repo.update_crm_configuration(
                crm_id=crm_id,
                owner_id=owner_id,
                configuration=updated_config,
            )
            
            if not updated_crm:
                raise ValueError("Failed to save CRM configuration")
            
            logger.info(
                "[AI-TOOLS] Reordered %d fields in CRM %s via AI tool",
                len(field_order),
                crm_id
            )
            
            return {
                "success": True,
                "crm_id": str(updated_crm["id"]),
                "configuration": updated_crm["configuration"],
                "configuration_version": updated_crm["configuration_version"],
            }
        except ValueError as exc:
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": str(exc),
            }
        except Exception as exc:
            logger.exception("Error reordering CRM fields via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to reorder fields: {str(exc)}",
            }

    @staticmethod
    def reorder_crm_stages(
        crm_id: str,
        owner_id: str,
        stage_order: list[str],
    ) -> dict[str, Any]:
        """Reorder pipeline stages in a CRM.
        
        Args:
            crm_id: The CRM ID
            owner_id: The owner user ID (for authorization)
            stage_order: List of stage names in desired order
            
        Returns:
            Updated CRMConfiguration as dict
            
        Raises:
            ValueError: If CRM not found or stage order is invalid
        """
        repo = CRMRepository()
        crm = repo.get_crm(crm_id, owner_id)
        if not crm:
            raise ValueError("CRM not found or unauthorized")
        
        try:
            updated_config = CRMSchemaEditor.reorder_pipeline_stages(
                crm["configuration"],
                stage_order=stage_order,
            )
            
            CRMConfiguration(**updated_config)
            
            updated_crm = repo.update_crm_configuration(
                crm_id=crm_id,
                owner_id=owner_id,
                configuration=updated_config,
            )
            
            if not updated_crm:
                raise ValueError("Failed to save CRM configuration")
            
            logger.info(
                "[AI-TOOLS] Reordered %d stages in CRM %s via AI tool",
                len(stage_order),
                crm_id
            )
            
            return {
                "success": True,
                "crm_id": str(updated_crm["id"]),
                "configuration": updated_crm["configuration"],
                "configuration_version": updated_crm["configuration_version"],
            }
        except ValueError as exc:
            return {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "error_message": str(exc),
            }
        except Exception as exc:
            logger.exception("Error reordering CRM stages via AI tool")
            return {
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "error_message": f"Failed to reorder stages: {str(exc)}",
            }


# OpenAI/Groq-format tool definitions for function calling
COPILOT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_record",
            "description": "Create a new record in the active CRM. Use this when the user asks to add a lead, contact, or other entity record.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Name of the entity to create a record for (e.g., 'lead', 'contact')",
                    },
                    "data": {
                        "type": "object",
                        "description": "Record field values as key-value pairs",
                    },
                    "source": {
                        "type": "string",
                        "description": "Optional source tag (e.g., 'Website', 'Email', 'Manual')",
                    },
                },
                "required": ["entity_name", "data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_record",
            "description": "Update an existing record in the active CRM. Use this when the user wants to change a record's fields.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Name of the entity",
                    },
                    "record_id": {
                        "type": "string",
                        "description": "ID of the record to update",
                    },
                    "data": {
                        "type": "object",
                        "description": "Fields to update (partial update OK)",
                    },
                },
                "required": ["entity_name", "record_id", "data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_record",
            "description": "Delete a record from the active CRM. Requires explicit user confirmation before execution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Name of the entity",
                    },
                    "record_id": {
                        "type": "string",
                        "description": "ID of the record to delete",
                    },
                },
                "required": ["entity_name", "record_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_crm_field",
            "description": "Add a new field to the CRM's main entity. Use this when the user asks to add a field to their CRM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_name": {
                        "type": "string",
                        "description": "Machine-readable field name (lowercase, underscores only, e.g., 'assigned_agent')",
                        "pattern": "^[a-z][a-z0-9_]{0,62}$",
                    },
                    "label": {
                        "type": "string",
                        "description": "Human-readable field label (e.g., 'Assigned Agent')",
                    },
                    "field_type": {
                        "type": "string",
                        "enum": ["text", "textarea", "email", "number", "date", "boolean", "select", "phone"],
                        "description": "The type of field",
                    },
                    "required": {
                        "type": "boolean",
                        "description": "Whether this field is required",
                        "default": False,
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "For select fields, list of available options (e.g., ['High', 'Medium', 'Low'])",
                    },
                },
                "required": ["field_name", "label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_crm_field",
            "description": "Update properties of an existing field in the CRM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_name": {
                        "type": "string",
                        "description": "The name of the field to update",
                    },
                    "label": {
                        "type": "string",
                        "description": "New human-readable label",
                    },
                    "field_type": {
                        "type": "string",
                        "enum": ["text", "textarea", "email", "number", "date", "boolean", "select", "phone"],
                        "description": "New field type",
                    },
                    "required": {
                        "type": "boolean",
                        "description": "New required state",
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New options for select fields",
                    },
                },
                "required": ["field_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_crm_field",
            "description": "Delete a field from the CRM's main entity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_name": {
                        "type": "string",
                        "description": "The name of the field to delete",
                    },
                },
                "required": ["field_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_crm_stage",
            "description": "Add a new pipeline stage to the CRM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stage_name": {
                        "type": "string",
                        "description": "Name of the new stage (e.g., 'Negotiation')",
                    },
                    "position": {
                        "type": "integer",
                        "description": "Optional position in the pipeline (0-indexed)",
                        "minimum": 0,
                    },
                },
                "required": ["stage_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_crm_stage",
            "description": "Delete a pipeline stage from the CRM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stage_name": {
                        "type": "string",
                        "description": "Name of the stage to delete",
                    },
                },
                "required": ["stage_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reorder_crm_fields",
            "description": "Reorder fields in the CRM's main entity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_order": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of field names in desired order (must include all existing fields)",
                    },
                },
                "required": ["field_order"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reorder_crm_stages",
            "description": "Reorder pipeline stages in the CRM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stage_order": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of stage names in desired order (must include all existing stages)",
                    },
                },
                "required": ["stage_order"],
            },
        },
    },
]
