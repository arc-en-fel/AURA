"""End-to-end test of the chat endpoint.

Simulates a full conversation then generates a CRM.
Run from backend/ directory:
    .venv/Scripts/python.exe scripts/test_chat_endpoint.py
"""
from __future__ import annotations

import time
from fastapi.testclient import TestClient
from jose import jwt
from app.main import create_app
from app.config import get_settings

settings = get_settings()
if not settings.supabase_jwt_secret:
    settings.supabase_jwt_secret = "test-jwt-secret-key-32-chars-minimum-length!"

app = create_app()
client = TestClient(app, raise_server_exceptions=False)

token = jwt.encode(
    {"sub": "00000000-0000-0000-0000-000000000001", "aud": "authenticated", "exp": 9999999999},
    settings.supabase_jwt_secret,
    algorithm="HS256",
)
headers = {"Authorization": f"Bearer {token}"}


def send(messages: list[dict], generate_now: bool = False) -> dict:
    r = client.post(
        "/api/v1/crm/chat",
        json={"messages": messages, "generate_now": generate_now},
        headers=headers,
    )
    assert r.status_code == 200, f"Got {r.status_code}: {r.text[:300]}"
    return r.json()["data"]


print("=" * 60)
print("  AURA CRM Chat — End-to-End Test")
print("=" * 60)

# ── Turn 1: user introduces their business ──────────────────────────
messages = [
    {"role": "user", "content": "I run a small real estate agency and need to track buyer leads, property listings, and deals."},
]
print(f"\n[Turn 1] User: {messages[0]['content']}")
t0 = time.perf_counter()
res = send(messages)
elapsed = time.perf_counter() - t0
reply1 = res["reply"]
print(f"[Turn 1] AURA ({elapsed:.1f}s): {reply1}")
print(f"         ready_to_generate={res['ready_to_generate']}  fallback_used={res.get('fallback_used')}")

# ── Turn 2: user answers ────────────────────────────────────────────
messages += [
    {"role": "assistant", "content": reply1},
    {"role": "user", "content": "I need to track leads, property listings, and sales pipelines with stages like New Inquiry, Site Visit, Offer Made, Closed."},
]
print(f"\n[Turn 2] User: {messages[-1]['content']}")
t0 = time.perf_counter()
res = send(messages)
elapsed = time.perf_counter() - t0
reply2 = res["reply"]
print(f"[Turn 2] AURA ({elapsed:.1f}s): {reply2}")
print(f"         ready_to_generate={res['ready_to_generate']}")

# ── Turn 3 ──────────────────────────────────────────────────────────
messages += [
    {"role": "assistant", "content": reply2},
    {"role": "user", "content": "We have 5 agents. Key fields are budget, location, property type, and contact phone."},
]
print(f"\n[Turn 3] User: {messages[-1]['content']}")
t0 = time.perf_counter()
res = send(messages)
elapsed = time.perf_counter() - t0
reply3 = res["reply"]
print(f"[Turn 3] AURA ({elapsed:.1f}s): {reply3}")
print(f"         ready_to_generate={res['ready_to_generate']}")

# ── Turn 4 ──────────────────────────────────────────────────────────
messages += [
    {"role": "assistant", "content": reply3},
    {"role": "user", "content": "Residential and commercial. The most important thing is following up with leads quickly."},
]
print(f"\n[Turn 4] User: {messages[-1]['content']}")
t0 = time.perf_counter()
res = send(messages)
elapsed = time.perf_counter() - t0
reply4 = res["reply"]
ready = res["ready_to_generate"]
print(f"[Turn 4] AURA ({elapsed:.1f}s): {reply4}")
print(f"         ready_to_generate={ready}")

# ── Generate CRM from conversation ─────────────────────────────────
messages += [{"role": "assistant", "content": reply4}]

print(f"\n{'─' * 60}")
print("  Generating CRM from conversation...")
t0 = time.perf_counter()
gen = send(messages, generate_now=True)
elapsed = time.perf_counter() - t0
print(f"  Generation time: {elapsed:.1f}s")

config = gen.get("configuration", {})
warnings = gen.get("warnings", [])

print(f"\n  CRM Name:        {config.get('name')}")
print(f"  Industry:        {config.get('industry')}")
print(f"  Entities:        {[e['name'] for e in config.get('entities', [])]}")
print(f"  Pipeline stages: {config.get('pipeline_stages')}")
print(f"  Warnings:        {warnings if warnings else 'none (Qwen generated live ✓)'}")

if config.get("entities"):
    for entity in config["entities"]:
        fields = [f['name'] for f in entity.get('fields', [])]
        print(f"  Fields ({entity['name']}): {fields}")

print(f"\n{'=' * 60}")
if not warnings:
    print("  ✅ Live Qwen3-4B generation confirmed — no fallback warnings")
else:
    print("  ⚠️  Fallback used — Ollama unavailable or timed out")
    print(f"     {warnings[0][:80]}...")
print("  ✅ Chat endpoint working end-to-end")
print(f"{'=' * 60}\n")
