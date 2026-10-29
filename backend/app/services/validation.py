"""Record validation service.

Validates record data against CRM configuration entity definitions.
Enforces required fields, field types, select options, and rejects unknown fields.
"""
from __future__ import annotations

import re
from typing import Any

from app.schemas.crm import CRMConfiguration, CRMEntity, CRMField


# Dangerous spreadsheet formula prefixes to neutralize in data
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def _sanitize_string(value: str) -> str:
    """Neutralize dangerous spreadsheet formula prefixes."""
    if value and value[0] in _FORMULA_PREFIXES:
        return "'" + value
    return value


def find_entity(config: CRMConfiguration, entity_name: str) -> CRMEntity | None:
    """Find an entity definition by machine name or label, case-insensitively."""
    if not config.entities:
        return None
    for entity in config.entities:
        if entity.name == entity_name:
            return entity
    norm_target = entity_name.lower().strip().replace(" ", "_").replace("-", "_")
    for entity in config.entities:
        name = entity.name.lower().strip().replace(" ", "_").replace("-", "_")
        label = (entity.label or "").lower().strip().replace(" ", "_").replace("-", "_")
        if name == norm_target or label == norm_target:
            return entity
    if len(config.entities) == 1:
        return config.entities[0]
    return None


def validate_record_data(
    entity: CRMEntity,
    data: dict[str, Any],
    partial: bool = False,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Validate record data against entity field definitions.

    Args:
        entity: The entity definition from CRM configuration.
        data: The raw data dict from the request.
        partial: If True, skip required-field checks (for PATCH updates).

    Returns:
        (validated_data, errors) where errors is a list of {field, issue} dicts.
    """
    errors: list[dict[str, str]] = []
    validated: dict[str, Any] = {}
    field_map = {f.name: f for f in entity.fields}

    # Check for unknown fields
    for key in data:
        if key not in field_map:
            errors.append({"field": key, "issue": f"Unknown field '{key}' not defined in entity '{entity.name}'."})

    if not partial:
        # Check required fields
        for field in entity.fields:
            if field.required and field.name not in data:
                errors.append({"field": field.name, "issue": f"Required field '{field.name}' is missing."})

    # Validate each provided field
    for key, value in data.items():
        field = field_map.get(key)
        if not field:
            continue  # Already reported as unknown

        err = _validate_field_value(field, value)
        if err:
            errors.append({"field": key, "issue": err})
        else:
            # Sanitize strings
            if isinstance(value, str):
                validated[key] = _sanitize_string(value)
            else:
                validated[key] = value

    return validated, errors


def _validate_field_value(field: CRMField, value: Any) -> str | None:
    """Validate a single field value. Returns error message or None."""
    if value is None:
        if field.required:
            return f"Required field '{field.name}' cannot be null."
        return None

    match field.type:
        case "text" | "textarea" | "phone" | "url":
            if not isinstance(value, str):
                return f"Field '{field.name}' must be a string."
            if len(value) > 10000:
                return f"Field '{field.name}' exceeds maximum length."
        case "email":
            if not isinstance(value, str):
                return f"Field '{field.name}' must be a string."
            if value and not _EMAIL_RE.match(value):
                return f"Field '{field.name}' is not a valid email address."
        case "number" | "currency":
            if not isinstance(value, (int, float)):
                return f"Field '{field.name}' must be a number."
        case "date":
            if not isinstance(value, str):
                return f"Field '{field.name}' must be a date string."
            if not re.match(r"^\d{4}-\d{2}-\d{2}", value):
                return f"Field '{field.name}' must be a valid date (YYYY-MM-DD)."
        case "datetime":
            if not isinstance(value, str):
                return f"Field '{field.name}' must be a datetime string."
        case "boolean":
            if not isinstance(value, bool):
                return f"Field '{field.name}' must be a boolean."
        case "select" | "status":
            if not isinstance(value, str):
                return f"Field '{field.name}' must be a string."
            if field.options and value not in field.options:
                return f"Field '{field.name}' value '{value}' is not in allowed options: {field.options}."
        case _:
            return f"Unsupported field type '{field.type}'."
    return None


def validate_csv_row(
    entity: CRMEntity,
    row: dict[str, str],
    row_number: int,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Validate a CSV row (all values are strings from CSV).

    Returns (coerced_data, errors). If errors, coerced_data is None.
    """
    errors: list[dict[str, Any]] = []
    coerced: dict[str, Any] = {}
    field_map = {f.name: f for f in entity.fields}

    # Check for unknown fields
    for key in row:
        if key not in field_map:
            errors.append({"row": row_number, "code": "UNKNOWN_FIELD", "message": f"Unknown field '{key}'."})

    # Check required fields
    for field in entity.fields:
        if field.required and (field.name not in row or not row[field.name].strip()):
            errors.append({
                "row": row_number,
                "code": "MISSING_REQUIRED",
                "message": f"Required field '{field.name}' is missing or empty.",
            })

    # Validate and coerce
    for key, raw_value in row.items():
        field = field_map.get(key)
        if not field:
            continue

        value = raw_value.strip()
        if not value:
            if not field.required:
                continue
            # Required check already handled above
            continue

        try:
            coerced_val = _coerce_csv_value(field, value)
            coerced[key] = _sanitize_string(coerced_val) if isinstance(coerced_val, str) else coerced_val
        except ValueError as e:
            errors.append({"row": row_number, "code": _error_code_for_type(field.type), "message": str(e)})

    if errors:
        return None, errors
    return coerced, []


def _coerce_csv_value(field: CRMField, value: str) -> Any:
    """Coerce a CSV string value to the appropriate type."""
    match field.type:
        case "text" | "textarea" | "phone":
            return value
        case "email":
            if not _EMAIL_RE.match(value):
                raise ValueError(f"Invalid email: {value}")
            return value
        case "number":
            try:
                if "." in value:
                    return float(value)
                return int(value)
            except (ValueError, TypeError):
                raise ValueError(f"Invalid number: {value}")
        case "date":
            if not re.match(r"^\d{4}-\d{2}-\d{2}", value):
                raise ValueError(f"Invalid date format: {value}")
            return value
        case "boolean":
            lower = value.lower()
            if lower in ("true", "1", "yes"):
                return True
            if lower in ("false", "0", "no"):
                return False
            raise ValueError(f"Invalid boolean: {value}")
        case "select":
            if field.options and value not in field.options:
                raise ValueError(f"Value '{value}' not in options: {field.options}")
            return value
        case _:
            raise ValueError(f"Unsupported field type: {field.type}")


def _error_code_for_type(field_type: str) -> str:
    """Map field type to error code."""
    return {
        "email": "INVALID_EMAIL",
        "number": "INVALID_NUMBER",
        "date": "INVALID_DATE",
        "boolean": "INVALID_BOOLEAN",
        "select": "INVALID_OPTION",
    }.get(field_type, "VALIDATION_ERROR")
