"""Backend color assignment utility for CRM pipeline stages.

Generates deterministic stage → palette-key mappings, consistent with
the frontend palette in frontend/src/utils/crmColors.ts.
"""
from __future__ import annotations

from typing import Any

# Palette keys — must stay in sync with frontend PALETTE order
PALETTE_KEYS = [
    "blue", "emerald", "amber", "rose", "violet", "cyan",
    "orange", "indigo", "teal", "pink", "lime", "sky",
    "fuchsia", "red", "yellow", "slate",
]


def _djb2(s: str) -> int:
    """Deterministic djb2 hash matching the frontend implementation."""
    h = 5381
    for ch in s:
        h = ((h << 5) + h + ord(ch)) & 0xFFFFFFFF
    return h


def assign_stage_colors(
    crm_id: str,
    stages: list[str],
    existing_colors: dict[str, str] | None = None,
) -> dict[str, str]:
    """Assign palette keys to pipeline stages.

    - Preserves existing assignments for stages that still exist.
    - Assigns new colors to new stages, avoiding collisions.
    - Returns a dict of stage_name → palette_key.
    """
    result: dict[str, str] = {}
    used_keys: set[str] = set()

    # Preserve existing
    if existing_colors:
        for stage, key in existing_colors.items():
            if stage in stages and key in PALETTE_KEYS:
                result[stage] = key
                used_keys.add(key)

    # Assign new
    for stage in stages:
        if stage in result:
            continue

        h = _djb2(f"{crm_id}::{stage}")
        idx = h % len(PALETTE_KEYS)

        attempts = 0
        while PALETTE_KEYS[idx] in used_keys and attempts < len(PALETTE_KEYS):
            idx = (idx + 1) % len(PALETTE_KEYS)
            attempts += 1

        result[stage] = PALETTE_KEYS[idx]
        used_keys.add(PALETTE_KEYS[idx])

    return result


def ensure_ui_config(config: dict[str, Any], crm_id: str) -> dict[str, Any]:
    """Ensure a CRM configuration has ui_config with stage_colors.

    Call after generating or saving a CRM so colors are persisted.
    Preserves any existing stage_colors, adds colors for new stages.
    """
    stages = config.get("pipeline_stages", [])
    if not stages:
        return config

    ui = config.get("ui_config") or {}
    existing = ui.get("stage_colors") or {}

    ui["stage_colors"] = assign_stage_colors(crm_id, stages, existing)
    config["ui_config"] = ui

    return config


def handle_stage_rename(config: dict[str, Any], old_stage: str, new_stage: str) -> dict[str, Any]:
    """Handle stage rename in ui_config, preserving the old stage's color."""
    ui = config.get("ui_config")
    if not ui or not isinstance(ui, dict):
        return config
    stage_colors = ui.get("stage_colors")
    if isinstance(stage_colors, dict) and old_stage in stage_colors:
        color = stage_colors.pop(old_stage)
        stage_colors[new_stage] = color
    return config


def handle_stage_delete(config: dict[str, Any], stage: str) -> dict[str, Any]:
    """Handle stage deletion in ui_config, removing obsolete mapping."""
    ui = config.get("ui_config")
    if not ui or not isinstance(ui, dict):
        return config
    stage_colors = ui.get("stage_colors")
    if isinstance(stage_colors, dict) and stage in stage_colors:
        stage_colors.pop(stage, None)
    return config
