"""Phase 1 Regression: Entity Resolution (C4) and Won-Stages Removal (C5)

Test that:
1. Entity resolution fails clearly when CRM has no entities (C4)
2. No hard-coded fallback to "lead" entity
3. No hard-coded won_stages detection (C5)
4. Analytics properly adapted to universal schema
"""
import pytest
from unittest.mock import MagicMock, patch
from uuid import UUID

from app.routers.evolution import create_proposal
from app.schemas.crm import CRMConfiguration, CRMEntity, CRMField, EvolutionObjectiveRequest
from app.routers.responses import error_response


def _create_test_crm_config(
    name: str,
    industry: str,
    entity_name: str,
    entity_label: str,
    stages: list[str],
) -> CRMConfiguration:
    """Helper to create a test CRM configuration."""
    entity_fields = [
        CRMField(
            name="name",
            label="Name",
            type="text",
            required=True,
        ),
    ]
    entity = CRMEntity(name=entity_name, label=entity_label, fields=entity_fields)
    return CRMConfiguration(
        name=name,
        industry=industry,
        entities=[entity],
        pipeline_stages=stages,
    )


def test_generate_scaffold_proposal_empty_entities_raises_error():
    """C4: generate_scaffold_proposal should raise error for empty entities, not silent fallback."""
    from app.services.laya_system1 import LayaSystem1
    
    crm_config_empty = {
        "name": "Empty CRM",
        "entities": [],  # Empty entities list
        "pipeline_stages": ["New", "Active"],
    }
    
    analytics = {"total_records": 0}
    
    # Should raise ValueError, not silently default to "lead"
    with pytest.raises(ValueError, match="CRM configuration contains no entities"):
        LayaSystem1.generate_scaffold_proposal("improve_follow_up", crm_config_empty, analytics)


def test_generate_scaffold_proposal_entity_with_no_name_raises_error():
    """C4: generate_scaffold_proposal should raise error if entity has no name."""
    from app.services.laya_system1 import LayaSystem1
    
    crm_config_no_name = {
        "name": "CRM with nameless entity",
        "entities": [{"label": "Entity", "fields": []}],  # No 'name' key
        "pipeline_stages": ["New", "Active"],
    }
    
    analytics = {"total_records": 0}
    
    # Should raise ValueError
    with pytest.raises(ValueError, match="has no name"):
        LayaSystem1.generate_scaffold_proposal("improve_follow_up", crm_config_no_name, analytics)


def test_generate_scaffold_proposal_uses_actual_entity_name():
    """C4: generate_scaffold_proposal should use actual entity name from config."""
    from app.services.laya_system1 import LayaSystem1
    
    crm_config = {
        "name": "Healthcare CRM",
        "entities": [{"name": "patient", "label": "Patient", "fields": []}],  # Actual entity name
        "pipeline_stages": ["Intake", "Treatment", "Discharged"],
    }
    
    analytics = {"total_records": 42}
    
    # Should succeed and use "patient" entity
    result = LayaSystem1.generate_scaffold_proposal("improve_follow_up", crm_config, analytics)
    
    # Verify proposal uses 'patient' entity in trigger
    assert result["proposed_change"]["trigger"]["entity"] == "patient"
    # Verify proposal name includes entity name
    assert "patient" in result["proposed_change"]["name"].lower() or result["proposed_change"]["name"].startswith("Quick response follow-up for patient")


@pytest.mark.asyncio
async def test_entity_resolution_uses_first_entity_not_fallback():
    """C4: Should use first entity from config, not fall back to hard-coded 'lead'."""
    config_with_custom = CRMConfiguration(
        name="Custom CRM",
        industry="test",
        entities=[
            CRMEntity(
                name="custom_entity",
                label="Custom Entity",
                fields=[
                    CRMField(
                        name="name",
                        label="Name",
                        type="text",
                        required=True,
                    ),
                ],
            ),
        ],
        pipeline_stages=["New", "Active"],
    )

    with patch("app.routers.evolution._get_repo") as mock_get_repo:
        repo = MagicMock()
        mock_get_repo.return_value = repo
        repo.get_crm.return_value = {
            "id": str(UUID("00000000-0000-0000-0000-000000000001")),
            "status": "active",
            "configuration": config_with_custom.model_dump(),
            "configuration_version": 1,
        }
        repo.count_records.return_value = 5

        with patch("app.routers.evolution.get_ai_provider") as mock_ai:
            mock_provider = MagicMock()
            mock_ai.return_value = mock_provider
            mock_provider.generate_evolution_proposal.return_value = {
                "summary": "Test",
                "proposed_change": {
                    "type": "workflow.create",
                    "name": "Test",
                    "trigger": {"type": "record.created", "entity": "custom_entity"},
                    "actions": [{"type": "create_follow_up_task", "delay_hours": 4}],
                },
                "evidence": [],
            }
            repo.create_proposal.return_value = {
                "id": str(UUID("00000000-0000-0000-0000-000000000010")),
                "status": "pending",
                "summary": "Test",
                "proposed_change": {
                    "type": "workflow.create",
                    "name": "Test",
                    "trigger": {"type": "record.created", "entity": "custom_entity"},
                    "actions": [{"type": "create_follow_up_task", "delay_hours": 4}],
                },
                "evidence": [],
            }

            response = await create_proposal(
                crm_id=UUID("00000000-0000-0000-0000-000000000001"),
                body=EvolutionObjectiveRequest(objective="improve_follow_up"),
                user_id=UUID("00000000-0000-0000-0000-000000000099"),
                settings=MagicMock(llm_provider="mock"),
            )

        # Should succeed
        assert response.status_code == 201
        # Should use 'custom_entity', not fallback to 'lead'
        repo.count_records.assert_called_with(str(UUID("00000000-0000-0000-0000-000000000001")), "custom_entity")


@pytest.mark.asyncio
async def test_entity_resolution_uses_first_entity():
    """C4: Should always use first entity from config, never hard-code 'lead'."""
    # Create a config with non-lead entity as primary
    config = _create_test_crm_config(
        name="Healthcare CRM",
        industry="healthcare",
        entity_name="patient",  # Not 'lead'
        entity_label="Patient",
        stages=["Intake", "Treatment", "Discharged"],
    )

    with patch("app.routers.evolution._get_repo") as mock_get_repo:
        repo = MagicMock()
        mock_get_repo.return_value = repo
        repo.get_crm.return_value = {
            "id": str(UUID("00000000-0000-0000-0000-000000000002")),
            "status": "active",
            "configuration": config.model_dump(),
            "configuration_version": 1,
        }
        repo.count_records.return_value = 42

        with patch("app.routers.evolution.get_ai_provider") as mock_ai:
            mock_provider = MagicMock()
            mock_ai.return_value = mock_provider
            mock_provider.generate_evolution_proposal.return_value = {
                "summary": "Test proposal",
                "proposed_change": {
                    "type": "workflow.create",
                    "name": "Test",
                    "trigger": {"type": "record.created", "entity": "patient"},
                    "actions": [{"type": "create_follow_up_task", "delay_hours": 4}],
                },
                "evidence": [],
            }
            repo.create_proposal.return_value = {
                "id": str(UUID("00000000-0000-0000-0000-000000000011")),
                "status": "pending",
                "summary": "Test proposal",
                "proposed_change": {
                    "type": "workflow.create",
                    "name": "Test",
                    "trigger": {"type": "record.created", "entity": "patient"},
                    "actions": [{"type": "create_follow_up_task", "delay_hours": 4}],
                },
                "evidence": [],
            }

            response = await create_proposal(
                crm_id=UUID("00000000-0000-0000-0000-000000000002"),
                body=EvolutionObjectiveRequest(objective="improve_follow_up"),
                user_id=UUID("00000000-0000-0000-0000-000000000099"),
                settings=MagicMock(llm_provider="mock"),
            )

        # Verify count_records was called with 'patient', not 'lead'
        repo.count_records.assert_called_once_with(str(UUID("00000000-0000-0000-0000-000000000002")), "patient")


@pytest.mark.asyncio
async def test_no_hardcoded_won_stages_in_evolution():
    """C5: Analytics should not compute conversion_rate using hard-coded won_stages."""
    config = _create_test_crm_config(
        name="Custom CRM",
        industry="custom",
        entity_name="record",
        entity_label="Record",
        stages=["Stage1", "Stage2", "Stage3"],  # Non-standard stage names
    )

    with patch("app.routers.evolution._get_repo") as mock_get_repo:
        repo = MagicMock()
        mock_get_repo.return_value = repo
        repo.get_crm.return_value = {
            "id": str(UUID("00000000-0000-0000-0000-000000000003")),
            "status": "active",
            "configuration": config.model_dump(),
            "configuration_version": 1,
        }
        repo.count_records.return_value = 10

        with patch("app.routers.evolution.get_ai_provider") as mock_ai:
            captured_analytics = {}

            def capture_analytics(obj, config, analytics):
                captured_analytics.update(analytics)
                return {
                    "summary": "Test",
                    "proposed_change": {
                        "type": "workflow.create",
                        "name": "Test",
                        "trigger": {"type": "record.created", "entity": "record"},
                        "actions": [{"type": "create_follow_up_task", "delay_hours": 4}],
                    },
                    "evidence": [],
                }

            mock_provider = MagicMock()
            mock_ai.return_value = mock_provider
            mock_provider.generate_evolution_proposal.side_effect = capture_analytics
            repo.create_proposal.return_value = {
                "id": str(UUID("00000000-0000-0000-0000-000000000012")),
                "status": "pending",
                "summary": "Test",
                "proposed_change": {
                    "type": "workflow.create",
                    "name": "Test",
                    "trigger": {"type": "record.created", "entity": "record"},
                    "actions": [{"type": "create_follow_up_task", "delay_hours": 4}],
                },
                "evidence": [],
            }

            await create_proposal(
                crm_id=UUID("00000000-0000-0000-0000-000000000003"),
                body=EvolutionObjectiveRequest(objective="improve_follow_up"),
                user_id=UUID("00000000-0000-0000-0000-000000000099"),
                settings=MagicMock(llm_provider="mock"),
            )

        # Analytics should NOT include conversion_rate
        assert "conversion_rate" not in captured_analytics
        assert "won_leads" not in captured_analytics
        assert "total_records" in captured_analytics
        assert captured_analytics["total_records"] == 10


@pytest.mark.asyncio
async def test_evolution_with_custom_entity_name():
    """Evolution proposal generation should work with any entity name."""
    config = _create_test_crm_config(
        name="E-commerce",
        industry="ecommerce",
        entity_name="customer",  # Custom entity name
        entity_label="Customer",
        stages=["Prospect", "Active", "Churned"],
    )

    with patch("app.routers.evolution._get_repo") as mock_get_repo:
        repo = MagicMock()
        mock_get_repo.return_value = repo
        repo.get_crm.return_value = {
            "id": str(UUID("00000000-0000-0000-0000-000000000004")),
            "status": "active",
            "configuration": config.model_dump(),
            "configuration_version": 1,
        }
        repo.count_records.return_value = 250

        with patch("app.routers.evolution.get_ai_provider") as mock_ai:
            mock_provider = MagicMock()
            mock_ai.return_value = mock_provider
            mock_provider.generate_evolution_proposal.return_value = {
                "summary": "Test proposal",
                "proposed_change": {
                    "type": "workflow.create",
                    "name": "Customer re-engagement",
                    "trigger": {"type": "record.created", "entity": "customer"},
                    "actions": [{"type": "create_follow_up_task", "delay_hours": 24}],
                },
                "evidence": [],
            }
            repo.create_proposal.return_value = {
                "id": str(UUID("00000000-0000-0000-0000-000000000013")),
                "status": "pending",
                "summary": "Test proposal",
                "proposed_change": {
                    "type": "workflow.create",
                    "name": "Customer re-engagement",
                    "trigger": {"type": "record.created", "entity": "customer"},
                    "actions": [{"type": "create_follow_up_task", "delay_hours": 24}],
                },
                "evidence": [],
            }

            response = await create_proposal(
                crm_id=UUID("00000000-0000-0000-0000-000000000004"),
                body=EvolutionObjectiveRequest(objective="improve_follow_up"),
                user_id=UUID("00000000-0000-0000-0000-000000000099"),
                settings=MagicMock(llm_provider="mock"),
            )

        # Should succeed
        assert response.status_code == 201
        # Should use 'customer', not fallback to 'lead'
        repo.count_records.assert_called_once_with(str(UUID("00000000-0000-0000-0000-000000000004")), "customer")
