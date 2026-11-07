"""Universal field extractor for CRM generation.

This module extracts all explicitly requested fields from user prompts
and ensures they survive the entire CRM generation pipeline.

Key responsibility: If user requests N fields, generated schema has N fields.
"""
from __future__ import annotations

import re
from typing import Any
from dataclasses import dataclass

import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractedField:
    """A user-requested field with canonical representation."""
    original_name: str  # "Customer Name" - exactly as user wrote it
    machine_key: str    # "customer_name" - normalized machine identifier
    label: str          # "Customer Name" - human-readable label
    inferred_type: str  # "text" - guessed type (can be overridden by LLM)
    required: bool = False


class FieldExtractor:
    """Universal field extraction engine."""

    # Pattern to detect field-like strings
    FIELD_PATTERN = re.compile(
        r"""
        (?:
            ^[-•*+]?\s*              # Optional bullet point
            |,\s*
            |\s+and\s+
            |\s+or\s+
        )
        ([A-Za-z0-9\s\-/()\']+?)     # Field name (allow spaces, hyphens, slashes, parens, quotes)
        (?:
            \s*\(([^)]*)\)            # Optional (type annotation)
            |(?=,)
            |(?=\s+and\s+)
            |(?=\s+or\s+)
            |$
        )
        """,
        re.VERBOSE | re.MULTILINE
    )

    # Type inference keywords
    TYPE_INDICATORS = {
        'email': {'email', 'e-mail', 'address'},
        'phone': {'phone', 'tel', 'telephone', 'mobile', 'cell', 'contact', 'number'},
        'date': {'date', 'born', 'created', 'modified', 'updated', 'deadline', 'when'},
        'boolean': {'active', 'enabled', 'disabled', 'verified', 'approved', 'confirmed', 'yes/no', 'true/false'},
        'number': {'count', 'amount', 'budget', 'price', 'cost', 'size', 'quantity', 'rating', 'score', 'id'},
        'select': {'status', 'stage', 'type', 'category', 'priority', 'level', 'state', 'reason', 'source', 'channel', 'method'},
        'textarea': {'description', 'notes', 'comment', 'feedback', 'message', 'reason', 'details', 'summary'},
        'url': {'url', 'link', 'website', 'homepage', 'site'},
        'text': {},  # Default
    }

    @classmethod
    def extract_fields_from_prompt(cls, prompt: str) -> list[ExtractedField]:
        """
        Extract all explicitly mentioned fields from a user prompt.

        Returns a list of ExtractedField objects in the order they appear.
        """
        if not prompt or len(prompt.strip()) < 3:
            return []

        # Split by common delimiters and newlines
        lines = re.split(r'[\n;]', prompt)
        fields: list[ExtractedField] = []
        seen_keys: set[str] = set()  # Deduplicate by machine_key

        for line in lines:
            line = line.strip()
            if not line or len(line) < 2:
                continue

            # Remove common prefixes/suffixes
            line = re.sub(r'^[-•*+]\s*', '', line)
            line = re.sub(r'^(field|column|attribute|property|data|information)\s*[:=]?\s*', '', line, flags=re.IGNORECASE)
            line = re.sub(r'[.,:;]+$', '', line)
            line = line.strip()

            if not line or len(line) < 2:
                continue

            # Skip common introductory phrases (field count filtering)
            if any(intro in line.lower() for intro in [
                "build", "create", "with", "following", "these fields", "the fields",
                "entities", "records", "data", "information", "requirements"
            ]):
                # Only skip if it's mostly intro (more than 50% is intro keywords)
                intro_count = sum(1 for intro in ["build", "create", "with", "these", "fields"] 
                                 if intro in line.lower())
                if intro_count >= 2 or "Build a" in line or "Create a" in line:
                    continue

            # Extract type annotation if present
            inferred_type = "text"
            match = re.search(r'\(([^)]+)\)', line)
            if match:
                annotation = match.group(1).strip().lower()
                # Map common type annotations
                if annotation in ('email', 'e-mail'):
                    inferred_type = "email"
                elif annotation in ('phone', 'tel', 'telephone', 'mobile'):
                    inferred_type = "phone"
                elif annotation in ('date', 'datetime', 'time'):
                    inferred_type = "date"
                elif annotation in ('bool', 'boolean', 'yes/no', 'true/false', 'checkbox'):
                    inferred_type = "boolean"
                elif annotation in ('select', 'dropdown', 'choice', 'enum', 'list'):
                    inferred_type = "select"
                elif annotation in ('number', 'integer', 'int', 'decimal', 'float', 'numeric'):
                    inferred_type = "number"
                elif annotation in ('text', 'string', 'str'):
                    inferred_type = "text"
                elif annotation in ('textarea', 'longtext', 'multiline', 'description', 'notes'):
                    inferred_type = "textarea"
                elif annotation in ('url', 'link', 'website', 'uri'):
                    inferred_type = "url"

                # Remove the annotation from the field name
                line = re.sub(r'\s*\([^)]*\)', '', line).strip()

            # Remove leading numbers with dots (1. 2. etc)
            line = re.sub(r'^\d+\.\s*', '', line)

            # Infer type from field name keywords if not explicitly annotated
            if inferred_type == "text":
                line_lower = line.lower()
                for ftype, keywords in cls.TYPE_INDICATORS.items():
                    if ftype != "text" and any(kw in line_lower for kw in keywords):
                        inferred_type = ftype
                        break

            # Normalize to machine key
            machine_key = cls._normalize_to_key(line)

            # Skip if empty after normalization or already seen
            if not machine_key or machine_key in seen_keys:
                continue

            seen_keys.add(machine_key)

            extracted = ExtractedField(
                original_name=line,
                machine_key=machine_key,
                label=cls._normalize_to_label(line),
                inferred_type=inferred_type,
                required=False,
            )
            fields.append(extracted)

        logger.info(
            "[FieldExtractor] Extracted %d fields from prompt (%.100s...)",
            len(fields),
            prompt[:100]
        )
        for i, field in enumerate(fields):
            logger.debug(
                "[FieldExtractor] Field %d: key=%s label=%s type=%s",
                i, field.machine_key, field.label, field.inferred_type
            )

        return fields

    @staticmethod
    def _normalize_to_key(field_name: str) -> str:
        """Convert human-readable field name to lowercase machine key.

        Example: "Customer Name" → "customer_name"
                "Budget (USD)" → "budget_usd"
                "Is Active?" → "is_active"
        """
        # Remove type annotations
        key = re.sub(r'\s*\([^)]*\)', '', field_name)

        # Remove punctuation but keep internal structure
        key = re.sub(r'[?!/*#@&]', '', key)

        # Replace spaces and hyphens with underscores
        key = re.sub(r'[\s\-]+', '_', key)

        # Convert to lowercase
        key = key.lower()

        # Remove leading/trailing underscores
        key = key.strip('_')

        # Ensure it's a valid identifier
        if not re.match(r'^[a-z][a-z0-9_]{0,62}$', key):
            # Sanitize further
            key = re.sub(r'[^a-z0-9_]', '', key)
            key = re.sub(r'^[0-9]', 'f', key)  # Can't start with number
            key = key[:63]  # Limit length

        return key or "field"

    @staticmethod
    def _normalize_to_label(field_name: str) -> str:
        """Convert to human-readable label.

        Example: "customer_name" → "Customer Name"
                "is_active?" → "Is Active"
        """
        # Remove type annotations
        label = re.sub(r'\s*\([^)]*\)', '', field_name)

        # Remove trailing punctuation
        label = re.sub(r'[?!;:,]+$', '', label)

        # Replace underscores and hyphens with spaces
        label = re.sub(r'[_\-]+', ' ', label)

        # Title case
        label = ' '.join(word.capitalize() for word in label.split())

        return label or "Field"

    @classmethod
    def extract_pipeline_stages(cls, prompt: str) -> list[str]:
        """Extract pipeline/workflow stages from prompt if mentioned.

        Looks for patterns like:
        - "stages: New, Qualified, Demo, Won, Lost"
        - "workflow: Step A → Step B → Step C"
        - "pipeline stages are: ..."
        """
        stages: list[str] = []

        # Look for explicit stage keywords
        stage_keywords = ['stage', 'workflow', 'pipeline', 'process']
        prompt_lower = prompt.lower()

        found_keyword = False
        for keyword in stage_keywords:
            if keyword in prompt_lower:
                found_keyword = True
                break

        if not found_keyword:
            return stages

        # Extract comma or arrow-separated values after keyword
        patterns = [
            r'(?:stage|workflow|pipeline|process)s?\s*(?:is|are|:|→|->)\s*([^.!?]+)',
            r'(?:stage|workflow|pipeline|process)s?\s*:\s*([^.!?]+)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, prompt, re.IGNORECASE)
            for match in matches:
                # Split by comma, arrow, or newline
                items = re.split(r'[,→\->\n]', match)
                for item in items:
                    item = item.strip()
                    if item and len(item) > 1 and len(item) < 100:
                        # Remove leading/trailing quotes
                        item = re.sub(r'^["\']|["\']$', '', item)
                        # Remove any leading numbers/bullets
                        item = re.sub(r'^[\d.•-]\s*', '', item)
                        if item and item not in stages:
                            stages.append(item)

        return stages[:30]  # Limit to 30 stages
