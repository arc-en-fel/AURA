"""AURA AI Brain — Performance Benchmark Script.

Measures latency and throughput for every layer of the generation pipeline.
Runs entirely without Ollama or any external service.

Usage (from backend/ directory):
    .venv/Scripts/python.exe -m scripts.benchmark

All timings are wall-clock milliseconds measured with time.perf_counter().
Results are printed to stdout in a readable table.
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
from typing import Any

# ── Helpers ────────────────────────────────────────────────────────

REAL_ESTATE_PROMPT = (
    "Build a CRM for a small real-estate agency to manage leads, "
    "property listings, viewing appointments, and sales pipelines."
)
SAAS_PROMPT = "Build a B2B SaaS CRM to track enterprise software leads and demos."
HEALTHCARE_PROMPT = "Build a CRM for a healthcare clinic to manage patients and appointments."


def _ms(t: float) -> str:
    return f"{t:.2f}ms"


def _row(label: str, n: int, times: list[float]) -> None:
    mn = min(times)
    mean = statistics.mean(times)
    mx = max(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    print(f"  {label:<48} n={n:>3}  min={_ms(mn):>10}  mean={_ms(mean):>10}  p95={_ms(p95):>10}  max={_ms(mx):>10}")


def _header(title: str) -> None:
    print(f"\n{'─' * 80}")
    print(f"  {title}")
    print(f"{'─' * 80}")


# ── 1. LayaSystem1 (pure Python, no network) ───────────────────────

def bench_laya_system1() -> None:
    _header("1. Laya System 1 — Deterministic Layer (no network)")
    from app.services.laya_system1 import LayaSystem1
    from app.schemas.crm import CRMConfiguration

    # Industry detection
    times: list[float] = []
    for _ in range(100):
        t0 = time.perf_counter()
        LayaSystem1.detect_industry(REAL_ESTATE_PROMPT)
        times.append((time.perf_counter() - t0) * 1000)
    _row("detect_industry()", 100, times)

    # Prompt safety validation
    times = []
    for _ in range(100):
        t0 = time.perf_counter()
        LayaSystem1.validate_prompt_safety(REAL_ESTATE_PROMPT)
        times.append((time.perf_counter() - t0) * 1000)
    _row("validate_prompt_safety()", 100, times)

    # Scaffold generation
    times = []
    for _ in range(50):
        t0 = time.perf_counter()
        LayaSystem1.generate_scaffold_config(REAL_ESTATE_PROMPT)
        times.append((time.perf_counter() - t0) * 1000)
    _row("generate_scaffold_config()", 50, times)

    # Schema repair
    raw = LayaSystem1.generate_scaffold_config(REAL_ESTATE_PROMPT)
    times = []
    for _ in range(50):
        t0 = time.perf_counter()
        LayaSystem1.repair_crm_configuration(raw, REAL_ESTATE_PROMPT)
        times.append((time.perf_counter() - t0) * 1000)
    _row("repair_crm_configuration()", 50, times)

    # Pydantic validation
    repaired = LayaSystem1.repair_crm_configuration(raw, REAL_ESTATE_PROMPT)
    times = []
    for _ in range(100):
        t0 = time.perf_counter()
        CRMConfiguration(**repaired)
        times.append((time.perf_counter() - t0) * 1000)
    _row("CRMConfiguration(**repaired) Pydantic v2", 100, times)

    # Full scaffold pipeline (detect + scaffold + validate)
    times = []
    for _ in range(50):
        t0 = time.perf_counter()
        config = LayaSystem1.generate_scaffold_config(REAL_ESTATE_PROMPT)
        repaired = LayaSystem1.repair_crm_configuration(config, REAL_ESTATE_PROMPT)
        CRMConfiguration(**repaired)
        times.append((time.perf_counter() - t0) * 1000)
    _row("Full scaffold pipeline (detect+scaffold+repair+validate)", 50, times)

    # Candidate ranking
    candidates = [
        {
            "summary": "Follow-up",
            "proposed_change": {
                "type": "workflow.create",
                "name": "Quick follow_up",
                "trigger": {"type": "record.created", "entity": "lead"},
                "actions": [{"type": "create_follow_up_task", "delay_hours": 4}],
            },
        },
        {
            "summary": "Stage alert",
            "proposed_change": {
                "type": "workflow.create",
                "name": "Stage conversion alert",
                "trigger": {"type": "record.stage_changed", "entity": "lead"},
                "actions": [{"type": "notify_owner"}],
            },
        },
    ]
    crm_cfg = LayaSystem1.generate_scaffold_config(SAAS_PROMPT)
    times = []
    for _ in range(100):
        t0 = time.perf_counter()
        LayaSystem1.rank_and_filter_candidates(candidates, "improve_conversion", {"conversion_rate": 0.1})
        times.append((time.perf_counter() - t0) * 1000)
    _row("rank_and_filter_candidates()", 100, times)


# ── 2. OllamaAIProvider fallback (offline Ollama) ──────────────────

def bench_fallback_sync() -> None:
    _header("2. OllamaAIProvider — Sync Fallback Path (Ollama offline)")
    from app.services.ollama_provider import OllamaAIProvider

    # Use unreachable port with minimal timeout to measure fallback cost
    provider = OllamaAIProvider(
        base_url="http://127.0.0.1:59999",
        timeout=0.1,
        enable_fallback=True,
    )

    times: list[float] = []
    for prompt in [REAL_ESTATE_PROMPT, SAAS_PROMPT, HEALTHCARE_PROMPT] * 3:
        t0 = time.perf_counter()
        provider.generate_crm_config(prompt)
        times.append((time.perf_counter() - t0) * 1000)
    _row("generate_crm_config() [offline, fallback=True, timeout=0.1s]", 9, times)

    print(
        f"\n  NOTE: Production timeout is 12000ms. These numbers reflect the test timeout "
        f"(0.1s).\n  Add ~12000ms to the mean for a worst-case cold production fallback."
    )


async def _bench_fallback_async() -> None:
    from app.services.ollama_provider import OllamaAIProvider

    provider = OllamaAIProvider(
        base_url="http://127.0.0.1:59999",
        timeout=0.1,
        enable_fallback=True,
    )
    times: list[float] = []
    for prompt in [REAL_ESTATE_PROMPT, SAAS_PROMPT, HEALTHCARE_PROMPT] * 3:
        t0 = time.perf_counter()
        await provider.generate_crm_config_async(prompt)
        times.append((time.perf_counter() - t0) * 1000)
    _row("generate_crm_config_async() [offline, fallback=True, timeout=0.1s]", 9, times)


def bench_fallback_async() -> None:
    _header("3. OllamaAIProvider — Async Fallback Path (Ollama offline)")
    asyncio.run(_bench_fallback_async())
    print(
        f"\n  NOTE: Production timeout is 12000ms. Async and sync paths have similar "
        f"fallback cost."
    )


# ── 3. Concurrency (mocked Ollama, semaphore verification) ─────────

async def _bench_concurrency() -> dict[str, Any]:
    import httpx
    from app.services.ollama_provider import OllamaAIProvider
    import app.services.ollama_provider as op

    raw_json = json.dumps({
        "name": "SaaS CRM",
        "industry": "saas",
        "entities": [{
            "name": "lead",
            "label": "Lead",
            "fields": [{"name": "full_name", "label": "Full Name", "type": "text", "required": True}],
        }],
        "pipeline_stages": ["New", "Won"],
    })

    active = 0
    peak_active = 0
    request_count = 0

    class MockResp:
        status_code = 200
        text = ""
        def json(self): return {"response": raw_json}

    SIMULATED_LATENCY_S = 0.05  # 50ms per mock request

    async def mock_post(*args: Any, **kwargs: Any) -> MockResp:
        nonlocal active, peak_active, request_count
        active += 1
        peak_active = max(peak_active, active)
        request_count += 1
        await asyncio.sleep(SIMULATED_LATENCY_S)
        active -= 1
        return MockResp()

    orig_post = httpx.AsyncClient.post
    orig_semaphore = op._async_generation_semaphore
    httpx.AsyncClient.post = mock_post
    op._async_generation_semaphore = asyncio.BoundedSemaphore(4)

    try:
        provider = OllamaAIProvider(enable_fallback=False)
        n_requests = 8

        t0 = time.perf_counter()
        results = await asyncio.gather(*[
            provider.generate_crm_config_async(f"Build CRM {i}")
            for i in range(n_requests)
        ])
        total_ms = (time.perf_counter() - t0) * 1000

        return {
            "n_requests": n_requests,
            "succeeded": len([r for r in results if isinstance(r, dict)]),
            "peak_concurrent": peak_active,
            "total_ms": total_ms,
            "simulated_latency_ms": SIMULATED_LATENCY_S * 1000,
        }
    finally:
        httpx.AsyncClient.post = orig_post
        op._async_generation_semaphore = orig_semaphore


def bench_concurrency() -> None:
    _header("4. Concurrency — BoundedSemaphore(4) under 8 simultaneous requests")
    result = asyncio.run(_bench_concurrency())
    print(f"  Requests issued:          {result['n_requests']}")
    print(f"  Requests succeeded:       {result['succeeded']}")
    print(f"  Peak concurrent:          {result['peak_concurrent']} (limit=4)")
    print(f"  Simulated per-request:    {result['simulated_latency_ms']:.0f}ms")
    print(f"  Total wall time:          {result['total_ms']:.0f}ms")
    batches = (result["n_requests"] + 3) // 4
    theoretical = batches * result["simulated_latency_ms"]
    print(f"  Theoretical minimum:      {theoretical:.0f}ms ({batches} batch(es) × {result['simulated_latency_ms']:.0f}ms)")
    semaphore_respected = result["peak_concurrent"] <= 4
    print(f"  Semaphore respected:      {'YES ✓' if semaphore_respected else 'NO ✗'}")


# ── 4. Mock vs Laya provider selection ────────────────────────────

def bench_provider_factory() -> None:
    _header("5. Provider Factory — Instantiation Cost")
    from app.services.ai_provider import get_ai_provider

    times: list[float] = []
    for _ in range(50):
        t0 = time.perf_counter()
        get_ai_provider("mock")
        times.append((time.perf_counter() - t0) * 1000)
    _row("get_ai_provider('mock')", 50, times)

    times = []
    for _ in range(50):
        t0 = time.perf_counter()
        get_ai_provider("local")
        times.append((time.perf_counter() - t0) * 1000)
    _row("get_ai_provider('local') [no model load]", 50, times)


# ── 5. Config summary ──────────────────────────────────────────────

def print_config_summary() -> None:
    _header("6. Runtime Configuration Summary")
    from app.config import get_settings
    settings = get_settings()

    print(f"  LLM_PROVIDER:             {settings.llm_provider}")
    print(f"  LOCAL_LLM_BASE_URL:       {settings.local_llm_base_url}")
    print(f"  LOCAL_LLM_MODEL:          {settings.local_llm_model}")
    print(f"  Configured timeout:       12000ms (hardcoded in OllamaAIProvider)")
    print(f"  Max concurrent requests:  4 (asyncio.BoundedSemaphore)")
    print(f"  Max repair attempts:      1 (MAX_REPAIR_ATTEMPTS)")
    print(f"  Fallback enabled:         True (enable_fallback=True in factory)")
    print(f"  Supabase URL:             {'configured' if 'localhost' not in settings.supabase_url else 'unconfigured'}")
    print(f"  JWT secret:               {'configured' if settings.supabase_jwt_secret else 'NOT SET'}")
    print(f"  Service role key:         {'configured' if settings.supabase_service_role_key else 'NOT SET'}")


# ── Entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 80)
    print("  AURA AI Brain — Performance Benchmark")
    print("  All measurements run without Ollama (offline fallback path).")
    print("  Laya model load may add ~2-5s on first call if not cached.")
    print("=" * 80)

    bench_laya_system1()
    bench_fallback_sync()
    bench_fallback_async()
    bench_concurrency()
    bench_provider_factory()
    print_config_summary()

    print(f"\n{'=' * 80}")
    print("  Benchmark complete.")
    print("  To measure live Ollama latency, set LLM_PROVIDER=local and run:")
    print("    .venv/Scripts/python.exe -m scripts.benchmark")
    print("  with Ollama running: ollama serve (in a separate terminal)")
    print(f"{'=' * 80}\n")
