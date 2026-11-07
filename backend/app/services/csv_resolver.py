"""Universal schema-driven CSV header resolver.

Resolves CSV column headers against an entity's canonical field definitions and display labels.
Supports:
1. Whitespace trimming and UTF-8 BOM removal.
2. Case-insensitive matching.
3. Safe formatting differences (underscores vs. spaces vs. hyphens).
4. Schema display labels and aliases.
5. Detection of genuinely unknown columns with descriptive errors.
6. Detection of duplicate columns that resolve to the same field.
7. Detection of ambiguous headers matching multiple schema fields.
8. Handling of empty or malformed column headers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

from app.schemas.crm import CRMField


def normalize_header(value: str) -> str:
    """Normalize a header string for fuzzy format matching.

    1. Strips leading and trailing whitespace.
    2. Strips UTF-8 BOM characters (\\ufeff, \\uffef).
    3. Converts to lowercase.
    4. Collapses runs of whitespace, underscores, and hyphens into a single space.
    """
    if not value:
        return ""
    cleaned = value.lstrip("\ufeff\uffef").strip()
    cleaned = cleaned.lower()
    cleaned = re.sub(r"[\s_\-]+", " ", cleaned).strip()
    return cleaned


@dataclass(frozen=True)
class ResolvedHeader:
    """Represents a successfully resolved CSV column."""
    index: int
    raw_header: str
    canonical_name: str
    display_label: str
    match_tier: str
    field_def: CRMField


@dataclass
class HeaderResolutionResult:
    """Outcome of resolving all column headers in a CSV."""
    is_valid: bool
    # raw_header -> canonical_name (first occurrence if no duplicates)
    header_map: dict[str, str] = field(default_factory=dict)
    # column_index -> canonical_name
    index_map: dict[int, str] = field(default_factory=dict)
    # List of detailed resolved objects in column order
    resolved_headers: list[ResolvedHeader] = field(default_factory=list)
    # User-facing error messages
    errors: list[str] = field(default_factory=list)
    # Category of error: EMPTY_FILE, EMPTY_HEADER, UNKNOWN_COLUMNS, DUPLICATE_COLUMNS, AMBIGUOUS_COLUMNS
    error_code: str | None = None
    # Diagnostic breakdowns
    unknown_headers: list[str] = field(default_factory=list)
    duplicate_mappings: dict[str, list[str]] = field(default_factory=dict)
    ambiguous_headers: dict[str, list[str]] = field(default_factory=dict)


def resolve_csv_headers(
    headers: Sequence[str | None],
    fields: Sequence[CRMField],
    entity_label: str = "Entity",
) -> HeaderResolutionResult:
    """Resolve an ordered list of CSV headers against the active entity's fields.

    Uses a tiered matching strategy:
      Tier 1: Exact canonical field name (e.g., 'customer_name' == 'customer_name')
      Tier 2: Exact display label or alias (e.g., 'Customer Name' == 'Customer Name')
      Tier 3: Case-insensitive canonical name (e.g., 'CUSTOMER_NAME' == 'customer_name')
      Tier 4: Case-insensitive display label or alias (e.g., 'CUSTOMER NAME' == 'Customer Name')
      Tier 5: Normalized separators & whitespace (e.g., 'customer name' == 'customer_name')

    Ambiguity is detected at each tier if more than one field matches.
    Duplicates are detected if multiple CSV columns resolve to the same canonical field.
    """
    if not headers:
        return HeaderResolutionResult(
            is_valid=False,
            errors=["CSV has no header row."],
            error_code="EMPTY_HEADER",
        )

    # 1. Check for empty headers
    empty_positions: list[int] = []
    cleaned_headers: list[str] = []
    for idx, raw in enumerate(headers):
        if raw is None:
            empty_positions.append(idx + 1)
            cleaned_headers.append("")
        else:
            cleaned = str(raw).lstrip("\ufeff\uffef").strip()
            if not cleaned:
                empty_positions.append(idx + 1)
            cleaned_headers.append(cleaned)

    if empty_positions:
        pos_str = ", ".join(str(p) for p in empty_positions)
        return HeaderResolutionResult(
            is_valid=False,
            errors=[f"CSV contains empty column header at position(s): {pos_str}."],
            error_code="EMPTY_HEADER",
        )

    resolved_list: list[ResolvedHeader] = []
    unknown_headers: list[str] = []
    ambiguous_headers: dict[str, list[str]] = {}

    # 2. Match each header against entity fields
    for idx, (raw_orig, cleaned_h) in enumerate(zip(headers, cleaned_headers)):
        raw_str = str(raw_orig) if raw_orig is not None else ""
        norm_h = normalize_header(cleaned_h)

        matched_field: CRMField | None = None
        matched_tier: str | None = None

        # Tier 1: Exact match on canonical field name
        t1_matches = [f for f in fields if cleaned_h == f.name]
        if len(t1_matches) == 1:
            matched_field = t1_matches[0]
            matched_tier = "exact_canonical"
        elif len(t1_matches) > 1:
            ambiguous_headers[raw_str] = [f.name for f in t1_matches]
            continue

        # Tier 2: Exact match on display label or exact alias
        if not matched_field:
            t2_matches = [
                f for f in fields
                if cleaned_h == f.label or cleaned_h in (getattr(f, "aliases", None) or [])
            ]
            if len(t2_matches) == 1:
                matched_field = t2_matches[0]
                matched_tier = "exact_label"
            elif len(t2_matches) > 1:
                ambiguous_headers[raw_str] = [f.name for f in t2_matches]
                continue

        # Tier 3: Case-insensitive match on canonical name
        if not matched_field:
            t3_matches = [f for f in fields if cleaned_h.lower() == f.name.lower()]
            if len(t3_matches) == 1:
                matched_field = t3_matches[0]
                matched_tier = "case_canonical"
            elif len(t3_matches) > 1:
                ambiguous_headers[raw_str] = [f.name for f in t3_matches]
                continue

        # Tier 4: Case-insensitive match on display label or alias
        if not matched_field:
            t4_matches = [
                f for f in fields
                if cleaned_h.lower() == f.label.lower()
                or any(cleaned_h.lower() == a.lower() for a in (getattr(f, "aliases", None) or []))
            ]
            if len(t4_matches) == 1:
                matched_field = t4_matches[0]
                matched_tier = "case_label"
            elif len(t4_matches) > 1:
                ambiguous_headers[raw_str] = [f.name for f in t4_matches]
                continue

        # Tier 5: Normalized match (safe separators: underscores vs spaces vs hyphens)
        if not matched_field:
            t5_matches = [
                f for f in fields
                if norm_h == normalize_header(f.name)
                or norm_h == normalize_header(f.label)
                or any(norm_h == normalize_header(a) for a in (getattr(f, "aliases", None) or []))
            ]
            if len(t5_matches) == 1:
                matched_field = t5_matches[0]
                matched_tier = "normalized"
            elif len(t5_matches) > 1:
                ambiguous_headers[raw_str] = [f.name for f in t5_matches]
                continue

        if matched_field:
            resolved_list.append(
                ResolvedHeader(
                    index=idx,
                    raw_header=raw_str,
                    canonical_name=matched_field.name,
                    display_label=matched_field.label,
                    match_tier=matched_tier or "unknown",
                    field_def=matched_field,
                )
            )
        else:
            unknown_headers.append(raw_str)

    # 3. Validation checks
    errors: list[str] = []
    error_code: str | None = None

    if unknown_headers:
        error_code = "UNKNOWN_COLUMNS"
        quoted = ", ".join(f"'{h}'" if " " in h else h for h in unknown_headers)
        errors.append(
            f"Unknown CSV columns: {quoted}. Column(s) do not match any field name or display label in entity '{entity_label}'."
        )

    if ambiguous_headers:
        error_code = error_code or "AMBIGUOUS_COLUMNS"
        for raw_h, candidates in ambiguous_headers.items():
            cand_str = ", ".join(f"'{c}'" for c in sorted(candidates))
            errors.append(
                f"Ambiguous CSV column header '{raw_h}': matches multiple fields ({cand_str})."
            )

    # 4. Check for duplicate headers that resolve to the same canonical field
    field_to_headers: dict[str, list[str]] = {}
    for r in resolved_list:
        field_to_headers.setdefault(r.canonical_name, []).append(r.raw_header)

    duplicates = {fname: hdrs for fname, hdrs in field_to_headers.items() if len(hdrs) > 1}
    if duplicates:
        error_code = error_code or "DUPLICATE_COLUMNS"
        for fname, hdrs in duplicates.items():
            hdrs_str = ", ".join(f"'{h}'" for h in hdrs)
            errors.append(
                f"Duplicate CSV column mapping for field '{fname}': multiple columns resolve to this field ({hdrs_str})."
            )

    if errors:
        return HeaderResolutionResult(
            is_valid=False,
            header_map={},
            index_map={},
            resolved_headers=[],
            errors=errors,
            error_code=error_code,
            unknown_headers=unknown_headers,
            duplicate_mappings=duplicates,
            ambiguous_headers=ambiguous_headers,
        )

    header_map = {r.raw_header: r.canonical_name for r in resolved_list}
    index_map = {r.index: r.canonical_name for r in resolved_list}

    return HeaderResolutionResult(
        is_valid=True,
        header_map=header_map,
        index_map=index_map,
        resolved_headers=resolved_list,
        errors=[],
        error_code=None,
    )

