"""Tests for backend dynamic color assignment and persistence."""
import pytest
from app.schemas.crm import CRMConfiguration, UIConfig
from app.services.color_assignment import (
    assign_stage_colors,
    ensure_ui_config,
    handle_stage_rename,
    handle_stage_delete,
    PALETTE_KEYS,
)
from app.services.crm_editor import CRMSchemaEditor


def test_assign_stage_colors_distinctness():
    """Different stages receive distinguishable palette keys."""
    stages = ["New", "Analyzing", "High Value", "At Risk", "Retained/Lost"]
    colors = assign_stage_colors("test-crm-1", stages)

    assert len(colors) == len(stages)
    assert len(set(colors.values())) == len(stages), "All 5 stages received unique colors"
    for stage, key in colors.items():
        assert key in PALETTE_KEYS, f"Color {key} is in curated palette"


def test_assign_stage_colors_preserves_existing():
    """Existing stage colors remain unchanged when adding a new stage."""
    stages = ["New", "Analyzing", "High Value"]
    initial = assign_stage_colors("test-crm-1", stages)

    extended_stages = ["New", "Analyzing", "High Value", "At Risk"]
    updated = assign_stage_colors("test-crm-1", extended_stages, initial)

    for s in stages:
        assert updated[s] == initial[s], f"Stage {s} preserved its initial color"
    assert "At Risk" in updated
    assert updated["At Risk"] in PALETTE_KEYS


def test_deterministic_stability():
    """Same CRM ID and stages yield identical assignments."""
    stages = ["Lead", "Opportunity", "Won", "Lost"]
    run1 = assign_stage_colors("crm-xyz", stages)
    run2 = assign_stage_colors("crm-xyz", stages)
    assert run1 == run2, "Color assignment is 100% deterministic"


def test_independent_crm_colors():
    """Different CRMs receive independent mappings."""
    stages = ["Lead", "Opportunity", "Won", "Lost"]
    crm_a = assign_stage_colors("crm-alpha-123", stages)
    crm_b = assign_stage_colors("crm-beta-999", stages)
    assert len(crm_a) == len(stages)
    assert len(crm_b) == len(stages)


def test_ensure_ui_config():
    """ensure_ui_config attaches stage_colors into configuration.ui_config."""
    config = {
        "schema_version": "1.0",
        "name": "Sales CRM",
        "industry": "sales",
        "entities": [
            {
                "name": "lead",
                "label": "Lead",
                "fields": [
                    {"name": "name", "label": "Name", "type": "text", "required": True}
                ],
            }
        ],
        "pipeline_stages": ["New", "Demo", "Closed"],
    }
    updated = ensure_ui_config(config, "crm-id-001")
    assert "ui_config" in updated
    assert "stage_colors" in updated["ui_config"]
    assert len(updated["ui_config"]["stage_colors"]) == 3

    # Validate with Pydantic
    parsed = CRMConfiguration(**updated)
    assert parsed.ui_config is not None
    assert len(parsed.ui_config.stage_colors) == 3


def test_handle_stage_rename():
    """Renaming a stage preserves its assigned color."""
    config = {
        "pipeline_stages": ["New", "Qualified", "Won"],
        "ui_config": {
            "stage_colors": {"New": "blue", "Qualified": "emerald", "Won": "cyan"}
        },
    }
    updated = handle_stage_rename(config, "Qualified", "Prospect Qualified")
    assert "Qualified" not in updated["ui_config"]["stage_colors"]
    assert updated["ui_config"]["stage_colors"]["Prospect Qualified"] == "emerald"


def test_handle_stage_delete():
    """Deleting a stage safely removes its color mapping."""
    config = {
        "pipeline_stages": ["New", "Qualified", "Won"],
        "ui_config": {
            "stage_colors": {"New": "blue", "Qualified": "emerald", "Won": "cyan"}
        },
    }
    updated = handle_stage_delete(config, "Qualified")
    assert "Qualified" not in updated["ui_config"]["stage_colors"]
    assert updated["ui_config"]["stage_colors"]["New"] == "blue"


def test_crm_editor_stage_lifecycle_preserves_colors():
    """Full lifecycle with CRMSchemaEditor: add, rename, and delete stages."""
    config = {
        "schema_version": "1.0",
        "name": "E-Commerce CRM",
        "industry": "ecommerce",
        "entities": [
            {
                "name": "order",
                "label": "Order",
                "fields": [
                    {"name": "order_id", "label": "Order ID", "type": "text", "required": True}
                ],
            }
        ],
        "pipeline_stages": ["Pending", "Shipped"],
        "ui_config": {
            "stage_colors": {"Pending": "amber", "Shipped": "cyan"}
        },
    }

    # 1. Add stage
    config1 = CRMSchemaEditor.add_pipeline_stage(config, "Delivered")
    assert "Delivered" in config1["pipeline_stages"]
    assert "Delivered" in config1["ui_config"]["stage_colors"]
    assert config1["ui_config"]["stage_colors"]["Pending"] == "amber"
    assert config1["ui_config"]["stage_colors"]["Shipped"] == "cyan"

    # 2. Rename stage
    config2 = CRMSchemaEditor.update_pipeline_stage(config1, "Pending", "Awaiting Payment")
    assert "Awaiting Payment" in config2["pipeline_stages"]
    assert "Pending" not in config2["pipeline_stages"]
    assert config2["ui_config"]["stage_colors"]["Awaiting Payment"] == "amber"

    # 3. Delete stage
    config3 = CRMSchemaEditor.delete_pipeline_stage(config2, "Shipped")
    assert "Shipped" not in config3["pipeline_stages"]
    assert "Shipped" not in config3["ui_config"]["stage_colors"]
    assert "Awaiting Payment" in config3["ui_config"]["stage_colors"]

