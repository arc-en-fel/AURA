"""Tests verifying Qwen is the single CRM generation provider (no fallback).

Validates that:
1. Qwen success returns valid CRM proposal
2. Qwen unavailability returns controlled error (no fallback)
3. Custom CRM configuration is sent to Qwen and preserved
4. No fallback provider message in the response
5. No scaffold fallback is called when Qwen fails
"""
import pytest
from unittest.mock import patch
from app.services.ollama_provider import OllamaAIProvider
from app.schemas.crm import CRMConfiguration


class TestQwenOnlyArchitecture:
    """Verify Qwen is the single CRM generation provider."""

    def test_qwen_success_returns_crm(self):
        """TEST 1: Qwen succeeds → valid CRM proposal returned."""
        valid_response = """{
            "schema_version": "1.0",
            "name": "Sales CRM",
            "industry": "saas",
            "entities": [
                {
                    "name": "lead",
                    "label": "Lead",
                    "fields": [
                        {"name": "name", "label": "Name", "type": "text", "required": true},
                        {"name": "email", "label": "Email", "type": "email", "required": true}
                    ]
                }
            ],
            "pipeline_stages": ["New", "Won"]
        }"""
        
        provider = OllamaAIProvider()
        with patch.object(provider, '_call_ollama_generate', return_value=valid_response):
            config = provider.generate_crm_config("Create a SaaS CRM")
            CRMConfiguration(**config)
            assert config["industry"] == "saas"

    def test_qwen_unavailable_raises_error(self):
        """TEST 2: Qwen unavailable → controlled error (no fallback)."""
        provider = OllamaAIProvider()
        with patch.object(provider, '_call_ollama_generate', return_value=None):
            with pytest.raises(ValueError) as exc_info:
                provider.generate_crm_config("Create a CRM")
            
            error_msg = str(exc_info.value).lower()
            assert "qwen" in error_msg or "unavailable" in error_msg
            assert "fallback" not in error_msg

    def test_no_fallback_provider_called(self):
        """TEST 3: Qwen fails → NO fallback provider is called."""
        provider = OllamaAIProvider()
        with patch.object(provider, '_call_ollama_generate', return_value=None):
            with patch('app.services.laya_system1.LayaSystem1.generate_scaffold_config') as mock_scaffold:
                with pytest.raises(ValueError):
                    provider.generate_crm_config("Create a CRM")
                mock_scaffold.assert_not_called()

    def test_custom_config_sent_to_qwen(self):
        """TEST 4: Custom CRM configuration is sent to Qwen."""
        valid_response = """{
            "schema_version": "1.0",
            "name": "Custom CRM",
            "industry": "custom",
            "entities": [{
                "name": "record",
                "label": "Record",
                "fields": [{"name": "field1", "label": "Field 1", "type": "text", "required": true}]
            }],
            "pipeline_stages": ["New", "Done"]
        }"""
        
        provider = OllamaAIProvider()
        custom_prompt = "Custom CRM\nTrack: leads\nStages: New → Done\nFields: lead,email,status"
        
        with patch.object(provider, '_call_ollama_generate', return_value=valid_response) as mock_call:
            config = provider.generate_crm_config(custom_prompt)
            mock_call.assert_called_once()
            assert "Custom CRM" in mock_call.call_args[0][1]

    def test_custom_fields_preserved(self):
        """TEST 5: Custom fields and stages preserved in Qwen output."""
        custom_response = """{
            "schema_version": "1.0",
            "name": "Custom CRM",
            "industry": "custom",
            "entities": [{
                "name": "lead",
                "label": "Lead",
                "fields": [
                    {"name": "lead", "label": "Lead", "type": "text", "required": true},
                    {"name": "email", "label": "Email", "type": "email", "required": true},
                    {"name": "phone", "label": "Phone", "type": "phone", "required": true},
                    {"name": "status", "label": "Status", "type": "select", "required": true, "options": ["New", "Active", "Won"]}
                ]
            }],
            "pipeline_stages": ["New", "Active", "Won"]
        }"""
        
        provider = OllamaAIProvider()
        with patch.object(provider, '_call_ollama_generate', return_value=custom_response):
            config = provider.generate_crm_config("Custom CRM")
            fields = config["entities"][0]["fields"]
            assert any(f["name"] == "lead" for f in fields)
            assert any(f["name"] == "email" for f in fields)
            assert any(f["name"] == "phone" for f in fields)
            assert config["pipeline_stages"] == ["New", "Active", "Won"]

    def test_no_fallback_message(self):
        """TEST 6: No fallback message in response."""
        valid_response = """{
            "schema_version": "1.0",
            "name": "Test CRM",
            "industry": "test",
            "entities": [{
                "name": "lead",
                "label": "Lead",
                "fields": [{"name": "name", "label": "Name", "type": "text", "required": true}]
            }],
            "pipeline_stages": ["New"]
        }"""
        
        provider = OllamaAIProvider()
        with patch.object(provider, '_call_ollama_generate', return_value=valid_response):
            config = provider.generate_crm_config("Create a CRM")
            assert provider.last_warnings == []
            assert "fallback" not in str(config).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
