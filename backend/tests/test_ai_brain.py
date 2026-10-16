"""Unit and integration tests for AURA AI Brain (Member 1).

Tests:
1. Laya System 1 structured decision engine (taxonomy, safety, repair, scaffolding).
2. Ollama AI provider (Qwen3-4B integration, fallback resilience, prompt formatting).
3. AI provider factory (mock, local/ollama, unsupported).
4. Full Pydantic v2 schema conformity against CRMConfiguration and ProposedChange.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.crm import (
    CRMConfiguration,
    CRMEntity,
    CRMField,
    ProposedChange,
)
from app.services.ai_provider import (
    MockAIProvider,
    get_ai_provider,
)
from app.services.laya_system1 import (
    LayaSystem1,
    INDUSTRY_TAXONOMIES,
)
from app.services.laya_runtime import EvolutionDecision, GenerationDecision, LayaDecisionEngine
from app.services.ollama_provider import OllamaAIProvider


class TestLayaSystem1:
    """Test suite for Laya System 1 structured decision-intelligence engine."""

    def test_sanitize_identifier(self):
        assert LayaSystem1.sanitize_identifier("Full Name") == "full_name"
        assert LayaSystem1.sanitize_identifier("email-address") == "email_address"
        assert LayaSystem1.sanitize_identifier("123field") == "field_123field"
        # Reserved word collision avoidance
        assert LayaSystem1.sanitize_identifier("id") == "custom_id"
        assert LayaSystem1.sanitize_identifier("owner_id") == "custom_owner_id"

    def test_detect_industry(self):
        assert LayaSystem1.detect_industry("We need a clinic management system for patient intake") == "healthcare"
        assert LayaSystem1.detect_industry("Commercial real estate listings and escrow pipeline") == "real_estate"
        assert LayaSystem1.detect_industry("E-commerce store with orders and cart recovery") == "ecommerce"
        assert LayaSystem1.detect_industry("B2B SaaS subscription and ARR deal tracking") == "saas"
        assert LayaSystem1.detect_industry("Generic tracking tool") == "general"

    def test_prompt_safety_guardrails(self):
        # SQL injection attempts must be blocked
        with pytest.raises(ValueError, match="unsafe SQL commands"):
            LayaSystem1.validate_prompt_safety("Create a CRM UNION SELECT * FROM users--")

        with pytest.raises(ValueError, match="unsafe SQL commands"):
            LayaSystem1.validate_prompt_safety("Track leads; DROP TABLE crms; --")

        # Code execution attempts must be blocked
        with pytest.raises(ValueError, match="prohibited code execution"):
            LayaSystem1.validate_prompt_safety("Track leads and run import os; os.system('calc')")

    def test_extract_json_payload_from_markdown(self):
        markdown_text = (
            "Here is your CRM configuration:\n"
            "```json\n"
            "{\n"
            '  "name": "Test CRM",\n'
            '  "industry": "saas",\n'
            '  "entities": [],\n'
            '  "pipeline_stages": ["New", "Won"]\n'
            "}\n"
            "```\n"
            "Hope this helps!"
        )
        parsed = LayaSystem1.extract_json_payload(markdown_text)
        assert parsed["name"] == "Test CRM"
        assert parsed["industry"] == "saas"

    def test_repair_crm_configuration(self):
        # Messy payload with uppercase, missing select options, reserved fields
        messy_payload = {
            "name": "Messy Startup CRM",
            "industry": "SaaS Platform",
            "entities": [
                {
                    "name": "Enterprise Lead",
                    "label": "Enterprise Lead",
                    "fields": [
                        {"name": "Full Name", "label": "Full Name", "type": "text", "required": True},
                        {"name": "id", "label": "ID", "type": "text", "required": False},  # Reserved
                        {"name": "status", "label": "Status", "type": "select", "options": []},  # Empty options
                        {"name": "phone", "label": "Phone", "type": "INVALID_TYPE"},  # Invalid type
                    ],
                }
            ],
            "pipeline_stages": ["Prospect", "Prospect", "Closed Won"],  # Duplicated
        }
        repaired = LayaSystem1.repair_crm_configuration(messy_payload, "Create a SaaS CRM")
        validated = CRMConfiguration(**repaired)

        assert validated.name == "Messy Startup CRM"
        assert validated.industry == "saas_platform"
        assert validated.entities[0].name == "enterprise_lead"
        # Reserved name was prefixed
        field_names = [f.name for f in validated.entities[0].fields]
        assert "custom_id" in field_names
        # Select options were populated
        status_field = next(f for f in validated.entities[0].fields if f.name == "status")
        assert status_field.type == "select"
        assert len(status_field.options) > 0
        # Invalid type was converted to valid fallback
        phone_field = next(f for f in validated.entities[0].fields if f.name == "phone")
        assert phone_field.type == "text"
        # Duplicate pipeline stages were deduplicated
        assert validated.pipeline_stages == ["Prospect", "Closed Won"]

    def test_generate_scaffold_config(self):
        for ind, tax in INDUSTRY_TAXONOMIES.items():
            config_dict = LayaSystem1.generate_scaffold_config(f"Create a high quality {ind} CRM")
            config = CRMConfiguration(**config_dict)
            assert config.schema_version == "1.0"
            assert len(config.entities) >= 1
            for entity in config.entities:
                assert entity.name.islower()
                for field in entity.fields:
                    assert field.name.islower()
                    if field.type == "select":
                        assert field.options is not None and len(field.options) > 0
            assert len(config.pipeline_stages) >= 2


class TestOllamaAIProvider:
    """Test suite for Qwen3-4B Ollama provider."""

    def test_provider_initialization(self):
        provider = OllamaAIProvider(base_url="http://localhost:11434", model="qwen3:4b")
        assert provider.base_url == "http://localhost:11434"
        assert provider.model == "qwen3:4b"
        assert provider.enable_fallback is True

    def test_offline_fallback_resilience(self):
        # Point to an unreachable port to test graceful fallback
        provider = OllamaAIProvider(
            base_url="http://127.0.0.1:59999",
            model="qwen3:4b",
            timeout=0.2,
            enable_fallback=True,
        )
        config_dict = provider.generate_crm_config("Create a B2B SaaS CRM to track enterprise leads")
        validated = CRMConfiguration(**config_dict)
        assert validated.schema_version == "1.0"
        assert validated.industry == "saas"
        assert len(validated.entities) >= 1

    def test_evolution_proposal_generation(self):
        provider = OllamaAIProvider()
        crm_config = LayaSystem1.generate_scaffold_config("Create a real estate CRM")

        # Test improve_follow_up
        p1 = provider.generate_evolution_proposal("improve_follow_up", crm_config, {})
        change1 = ProposedChange(**p1["proposed_change"])
        assert change1.type == "workflow.create"
        assert change1.trigger.type == "record.created"
        assert change1.actions[0].type == "create_follow_up_task"
        assert change1.actions[0].delay_hours == 4

        # Test improve_conversion
        p2 = provider.generate_evolution_proposal("improve_conversion", crm_config, {})
        change2 = ProposedChange(**p2["proposed_change"])
        assert change2.type == "workflow.create"
        assert change2.trigger.type == "record.stage_changed"

        # Test reduce_manual_work
        p3 = provider.generate_evolution_proposal("reduce_manual_work", crm_config, {})
        change3 = ProposedChange(**p3["proposed_change"])
        assert change3.type == "workflow.create"
        assert change3.trigger.type == "record.updated"

    def test_official_laya_generation_decision_changes_fallback_configuration(self):
        """A typed System 1 decision must alter downstream generation behavior."""
        class DecisionEngine:
            def decide_generation(self, prompt):
                return GenerationDecision("healthcare", "case_management", "test-laya")

        provider = OllamaAIProvider(
            base_url="http://127.0.0.1:59999",
            timeout=0.01,
            enable_fallback=True,
            decision_engine=DecisionEngine(),
        )

        config = provider.generate_crm_config("Create a CRM for a local business")

        assert config["industry"] == "healthcare"
        assert any(entity["name"] == "patient" for entity in config["entities"])

    def test_official_laya_template_changes_generic_qwen_entity(self, monkeypatch):
        """A real System 1 template selection changes normalized Qwen output."""
        import json

        class DecisionEngine:
            def decide_generation(self, prompt):
                return GenerationDecision("real_estate", "transaction_tracking", "test-laya")

        raw_qwen = {
            "name": "CRM",
            "industry": "general",
            "entities": [{
                "name": "lead",
                "label": "Lead",
                "fields": [{"name": "full_name", "label": "Full Name", "type": "text", "required": True}],
            }],
            "pipeline_stages": ["New", "Won"],
        }
        provider = OllamaAIProvider(enable_fallback=False, decision_engine=DecisionEngine())
        monkeypatch.setattr(provider, "_call_ollama_generate", lambda *args: json.dumps(raw_qwen))

        config = provider.generate_crm_config("Create a generic CRM")

        assert config["industry"] == "real_estate"
        assert config["entities"][0]["name"] == "property_lead"

    def test_official_laya_evolution_priority_changes_candidate_selection(self):
        """The Laya priority must select a different allowlisted proposal."""
        class DecisionEngine:
            def decide_evolution(self, objective, crm_config, analytics):
                return EvolutionDecision("improve_conversion", True, "test-laya")

        provider = OllamaAIProvider(decision_engine=DecisionEngine())
        crm_config = LayaSystem1.generate_scaffold_config("Create a SaaS CRM")

        proposal = provider.generate_evolution_proposal("improve_follow_up", crm_config, {})

        assert "stage" in proposal["proposed_change"]["name"].lower()


class TestOfficialLayaRuntimeAdapter:
    def test_generation_decision_validates_official_typed_shape(self):
        class Agent:
            def predict(self, state, questions):
                return {
                    "model": "laya-rl-agent",
                    "answers": {
                        "industry": {"choice": "real_estate"},
                        "strategy": {"choice": "transaction_tracking"},
                    },
                }

        engine = LayaDecisionEngine(loader=lambda model_id: Agent())

        decision = engine.decide_generation("Manage property listings and buyers")

        assert decision.industry == "real_estate"
        assert decision.strategy == "transaction_tracking"
        assert decision.model_id == "laya-rl-agent"

    def test_evolution_decision_converts_official_noul_probability_to_review_signal(self):
        class Agent:
            def predict(self, state, questions):
                return {
                    "model": "laya-rl-agent",
                    "answers": {
                        "priority": {"choice": "improve_conversion"},
                        "requires_human_review": {"noul": 0.8},
                    },
                }

        engine = LayaDecisionEngine(loader=lambda model_id: Agent())

        decision = engine.decide_evolution("improve_conversion", {"entities": []}, {})

        assert decision.priority == "improve_conversion"
        assert decision.requires_human_review is True


class TestAIProviderFactory:
    """Test suite for factory function."""

    def test_get_mock_provider(self):
        provider = get_ai_provider("mock")
        assert isinstance(provider, MockAIProvider)

    def test_get_local_provider(self):
        provider = get_ai_provider("local")
        assert isinstance(provider, OllamaAIProvider)
        assert isinstance(provider.decision_engine, LayaDecisionEngine)

        provider_ollama = get_ai_provider("ollama")
        assert isinstance(provider_ollama, OllamaAIProvider)
        assert isinstance(provider_ollama.decision_engine, LayaDecisionEngine)

    def test_unsupported_provider(self):
        with pytest.raises(ValueError, match="Unsupported AI provider"):
            get_ai_provider("unsupported_provider_xyz")


class TestOllamaMockedResponses:
    """Mock-based unit tests for Ollama runtime behavior without external network access."""

    def test_ollama_mocked_success_response(self, monkeypatch):
        """Test happy path with mocked Ollama API response."""
        mock_json_content = {
            "name": "Custom Logistics CRM",
            "industry": "logistics",
            "entities": [
                {
                    "name": "shipment_lead",
                    "label": "Shipment Lead",
                    "fields": [
                        {"name": "tracking_number", "label": "Tracking Number", "type": "text", "required": True},
                        {"name": "carrier", "label": "Carrier", "type": "select", "required": True, "options": ["FedEx", "DHL", "UPS"]},
                    ],
                }
            ],
            "pipeline_stages": ["Booked", "In Transit", "Delivered"],
        }

        import json
        from unittest.mock import MagicMock
        import httpx

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": json.dumps(mock_json_content)}

        def mock_post(*args, **kwargs):
            # Verify request payload structure
            json_payload = kwargs.get("json", {})
            assert json_payload.get("model") == "qwen3:4b"
            assert json_payload.get("format") == "json"
            assert json_payload.get("stream") is False
            return mock_resp

        monkeypatch.setattr(httpx.Client, "post", mock_post)

        provider = OllamaAIProvider(model="qwen3:4b", enable_fallback=False)
        result = provider.generate_crm_config("Create a logistics CRM to track shipments")

        assert result["name"] == "Custom Logistics CRM"
        assert result["industry"] == "logistics"
        assert result["entities"][0]["name"] == "shipment_lead"
        CRMConfiguration(**result)

    def test_ollama_malformed_json_fallback(self, monkeypatch):
        """Test that malformed JSON from Ollama triggers bounded repair and fallback."""
        from unittest.mock import MagicMock
        import httpx

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "NOT VALID JSON AT ALL {{{{}}}}"}

        monkeypatch.setattr(httpx.Client, "post", lambda *args, **kwargs: mock_resp)

        # With fallback enabled -> returns valid scaffold
        provider_with_fallback = OllamaAIProvider(model="qwen3:4b", enable_fallback=True)
        res = provider_with_fallback.generate_crm_config("Create a SaaS CRM")
        assert res["industry"] == "saas"
        CRMConfiguration(**res)

        # With fallback disabled -> raises ValueError
        provider_no_fallback = OllamaAIProvider(model="qwen3:4b", enable_fallback=False)
        with pytest.raises(ValueError, match="failed to generate a valid CRM configuration"):
            provider_no_fallback.generate_crm_config("Create a SaaS CRM")

    def test_laya_decision_routing_affects_generation(self):
        """Verify Laya decision taxonomy directly shapes generated entities and pipeline."""
        p_health = OllamaAIProvider(enable_fallback=True).generate_crm_config("Clinic and patient management CRM")
        assert p_health["industry"] == "healthcare"
        assert any(e["name"] == "patient" for e in p_health["entities"])

        p_realty = OllamaAIProvider(enable_fallback=True).generate_crm_config("Real estate brokerage CRM")
        assert p_realty["industry"] == "real_estate"
        assert any(e["name"] == "property_lead" for e in p_realty["entities"])

    def test_crm_generation_endpoint_is_draft_only(self):
        """Verify POST /api/v1/crm/generate returns draft without persistence side-effects."""
        from fastapi.testclient import TestClient
        from jose import jwt
        from app.config import get_settings
        from app.main import create_app

        settings = get_settings()
        if not settings.supabase_jwt_secret:
            settings.supabase_jwt_secret = "test-jwt-secret-key-32-chars-minimum-length!"

        token = jwt.encode(
            {"sub": "11111111-1111-1111-1111-111111111111", "aud": "authenticated", "exp": 9999999999},
            settings.supabase_jwt_secret,
            algorithm="HS256",
        )
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/crm/generate",
            json={"prompt": "Create an e-commerce customer store CRM"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "configuration" in data["data"]
        # Ensure it has schema_version and name
        assert data["data"]["configuration"]["schema_version"] == "1.0"
        assert data["data"]["configuration"]["industry"] == "ecommerce"

    def test_laya_candidate_ranking_and_filtering(self):
        """Verify Laya System 1 filters non-allowlisted candidates and ranks by priority."""
        candidates = [
            # Disallowed action
            {
                "summary": "Execute malicious code",
                "proposed_change": {
                    "type": "workflow.create",
                    "name": "Code exec",
                    "trigger": {"type": "record.created", "entity": "lead"},
                    "actions": [{"type": "execute_arbitrary_shell"}],
                },
            },
            # Allowlisted follow-up
            {
                "summary": "Follow-up workflow",
                "proposed_change": {
                    "type": "workflow.create",
                    "name": "Quick follow_up",
                    "trigger": {"type": "record.created", "entity": "lead"},
                    "actions": [{"type": "create_follow_up_task", "delay_hours": 2}],
                },
            },
            # Allowlisted stage progression
            {
                "summary": "Conversion progression",
                "proposed_change": {
                    "type": "workflow.create",
                    "name": "Stage conversion alert",
                    "trigger": {"type": "record.stage_changed", "entity": "lead"},
                    "actions": [{"type": "notify_owner"}],
                },
            },
        ]

        ranked = LayaSystem1.rank_and_filter_candidates(candidates, "improve_conversion", {"conversion_rate": 0.05})
        # The malicious candidate must be filtered out
        assert len(ranked) == 2
        # The conversion candidate must rank first for improve_conversion objective
        assert "conversion" in ranked[0]["proposed_change"]["name"].lower()

    @pytest.mark.asyncio
    async def test_ollama_async_generation(self):
        """Verify asynchronous CRM generation path does not block event loop."""
        provider = OllamaAIProvider(enable_fallback=True)
        config_dict = await provider.generate_crm_config_async("Create a B2B SaaS CRM")
        CRMConfiguration(**config_dict)
        assert config_dict["industry"] == "saas"
        # Verify fallback warning is observable
        assert len(provider.last_warnings) > 0
        assert "fallback" in provider.last_warnings[0].lower()

    @pytest.mark.asyncio
    async def test_async_timeout_uses_observable_fallback(self, monkeypatch):
        """Timeouts must fail safely without a cloud-provider retry."""
        import httpx

        async def timeout_post(*args, **kwargs):
            raise httpx.ReadTimeout("local Ollama timed out")

        monkeypatch.setattr(httpx.AsyncClient, "post", timeout_post)
        provider = OllamaAIProvider(enable_fallback=True, timeout=0.01)

        config = await provider.generate_crm_config_async("Create a SaaS CRM")

        CRMConfiguration(**config)
        assert len(provider.last_warnings) == 1
        assert "fallback" in provider.last_warnings[0].lower()

    @pytest.mark.asyncio
    async def test_async_generation_is_bounded_to_four_requests(self, monkeypatch):
        """The local daemon must not receive unbounded concurrent requests."""
        import asyncio
        import httpx

        active = 0
        peak_active = 0

        class Response:
            status_code = 200
            text = ""

            @staticmethod
            def json():
                return {"response": '{"name":"Test CRM","industry":"saas","entities":[{"name":"lead","label":"Lead","fields":[{"name":"full_name","label":"Full Name","type":"text","required":true}]}],"pipeline_stages":["New","Won"]}'}

        async def delayed_post(*args, **kwargs):
            nonlocal active, peak_active
            active += 1
            peak_active = max(peak_active, active)
            await asyncio.sleep(0.02)
            active -= 1
            return Response()

        monkeypatch.setattr(httpx.AsyncClient, "post", delayed_post)
        provider = OllamaAIProvider(enable_fallback=False)

        configs = await asyncio.gather(*[
            provider.generate_crm_config_async(f"Create SaaS CRM {index}")
            for index in range(6)
        ])

        assert peak_active <= 4
        assert len(configs) == 6
        assert all(config["industry"] == "saas" for config in configs)

    @pytest.mark.asyncio
    async def test_warning_concurrency_isolation(self):
        """Verify ContextVar prevents warning cross-contamination across concurrent tasks."""
        import asyncio
        provider = OllamaAIProvider(enable_fallback=True)

        async def worker(task_id: str, delay: float, fallback: bool):
            if fallback:
                provider.last_warnings = [f"fallback_{task_id}"]
            else:
                provider.last_warnings = []
            await asyncio.sleep(delay)
            return task_id, list(provider.last_warnings)

        t1 = asyncio.create_task(worker("t1", 0.03, False))
        t2 = asyncio.create_task(worker("t2", 0.01, True))
        r1, r2 = await asyncio.gather(t1, t2)

        assert r1[1] == [], "Live task t1 should retain empty warnings"
        assert r2[1] == ["fallback_t2"], "Fallback task t2 should retain its own warning"
