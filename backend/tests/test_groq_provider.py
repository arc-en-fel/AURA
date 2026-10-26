from types import SimpleNamespace

import pytest

from app.config import Settings
from app.services.groq_provider import GroqProvider, GroqUnavailable, groq_status
from app.services.laya_system1 import LayaSystem1


class FakeCompletions:
    def __init__(self, message):
        self.message = message
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=self.message)])


class FakeClient:
    def __init__(self, message):
        self.chat = SimpleNamespace(completions=FakeCompletions(message))


def _settings(**kwargs):
    return Settings(_env_file=None, debug=False, groq_api_key="test-key", **kwargs)


def test_groq_provider_sends_model_tools_and_normalizes_native_tool_call():
    call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="list_records", arguments='{"entity":"lead"}'),
    )
    client = FakeClient(SimpleNamespace(content=None, tool_calls=[call]))
    provider = GroqProvider(_settings(), client=client)

    result = provider.chat(
        [{"role": "user", "content": "Show my leads"}],
        tools=[{"type": "function", "function": {"name": "list_records"}}],
    )

    sent = client.chat.completions.calls[0]
    assert sent["model"] == "llama-3.3-70b-versatile"
    assert sent["tools"][0]["function"]["name"] == "list_records"
    assert sent["tool_choice"] == "auto"
    assert result["used"] is True
    assert result["tool_calls"][0]["function"]["name"] == "list_records"


def test_groq_missing_api_key_fails_explicitly():
    provider = GroqProvider(Settings(_env_file=None, debug=False, groq_api_key=""))
    with pytest.raises(GroqUnavailable, match="not configured"):
        provider.chat([{"role": "user", "content": "Hello"}])
    assert groq_status(Settings(_env_file=None, debug=False, groq_api_key=""))["status"] == "missing_api_key"


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Add Rahul as a lead", "create_record"),
        ("Show my qualified leads", "list_records"),
        ("Update the deal status", "update_record"),
        ("Delete the duplicate", "delete_record"),
        ("Explain this field", "conversation"),
    ],
)
def test_laya_deterministic_system1_intent_classification(prompt, expected):
    decision = LayaSystem1.classify_request(prompt)
    assert decision["intent"] == expected
    assert decision["mode"] == "deterministic"
    assert decision["model_loaded"] is False
    assert decision["requires_llm"] is True
