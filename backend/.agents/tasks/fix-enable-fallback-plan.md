# Implementation Plan: Remove `enable_fallback` Parameter from OllamaAIProvider

## Context

The `OllamaAIProvider` class has been refactored to remove the `enable_fallback` parameter. The class now implements Qwen-only behavior (no fallback). When Ollama is unavailable, it raises a `ValueError` with a clear, actionable error message instead of falling back to a deterministic scaffold.

The current `__init__()` signature (line 37-42 in `ollama_provider.py`) is:
```python
def __init__(
    self,
    base_url: str = "http://localhost:11434",
    model: str = "qwen2.5:3b",
    timeout: float = 120.0,
    decision_engine: LayaDecisionEngine | None = None,
) -> None:
```

Architecture decision: Qwen-only, no fallback. If Qwen/Ollama is unavailable, return a clear, actionable error (not a scaffold). Tests that expected fallback behavior must now expect `ValueError` when Ollama is unavailable.

## Files to Modify

### Test Files
1. `backend/tests/test_ai_brain.py` — 12 test methods using `enable_fallback`
2. `backend/tests/test_evolution_proposals.py` — 1 test using `enable_fallback`
3. `backend/tests/test_phase9_regression.py` — 4 test methods using `enable_fallback`

### Script Files
4. `backend/scripts/benchmark.py` — 2 instances of `enable_fallback=True` in fallback benchmarking
5. `backend/scripts/smoke_test_ollama.py` — 1 instance of `enable_fallback=False`

### Documentation Files
6. `docs/INTEGRATION_EXAMPLES.md` — Fallback code example references `self.enable_fallback`

---

# Implementation Plan

- [ ] 1. Update test_ai_brain.py: Remove `enable_fallback` parameter from OllamaAIProvider() calls and update expectations.
      
      Update 12 test methods:
      - `test_default_ollama_factory()` — remove assertion `assert provider.enable_fallback is True`
      - `test_offline_fallback_resilience()` — remove `enable_fallback=True` param; expect ValueError on offline
      - `test_official_laya_generation_decision_changes_fallback_configuration()` — remove `enable_fallback=True` param
      - `test_mock_ai_provider_validation()` — remove `enable_fallback=False` param
      - `test_ollama_malformed_json_fallback()` — remove both `enable_fallback` params; expect ValueError instead of scaffold
      - `test_laya_decision_routing_affects_generation()` — remove both `enable_fallback=True` params
      - `test_ollama_async_generation()` — remove `enable_fallback=True` param
      - `test_async_timeout_uses_observable_fallback()` — remove `enable_fallback=True` param; expect ValueError on timeout
      - `test_async_concurrent_requests_isolation()` — remove `enable_fallback=False` param
      - `test_contextvar_warning_isolation()` — remove `enable_fallback=True` param
      - `test_repair_max_attempts_exhausted()` — remove `enable_fallback=False` param (if present)
      
      For tests that expected fallback behavior (returning a scaffold), update to expect `ValueError` with match="failed to generate|unavailable". Keep the mock infrastructure and test logic; only change parameter passing and assertions.
      
      Files: `backend/tests/test_ai_brain.py`
      Verify: `pytest backend/tests/test_ai_brain.py -v` — all test methods pass (currently failing with "unexpected keyword argument 'enable_fallback'")

- [ ] 2. Update test_evolution_proposals.py: Remove `enable_fallback` parameter from OllamaAIProvider() call.
      
      Update the test method:
      - Line 901: Change `OllamaAIProvider(enable_fallback=True)` to `OllamaAIProvider()`
      - This test verifies that `generate_evolution_proposal()` clears last_warnings. The fixture change does not alter test logic.
      
      Files: `backend/tests/test_evolution_proposals.py`
      Verify: `pytest backend/tests/test_evolution_proposals.py::test_evolution_proposal_clears_warnings_after_generation -v` — test passes

- [ ] 3. Update test_phase9_regression.py: Remove `enable_fallback` parameters from OllamaAIProvider() calls and update expectations.
      
      Update 4 test methods:
      - `test_concurrent_fallback_and_success_warnings_are_isolated()` — remove both `enable_fallback=True` params
      - `test_evolution_proposal_clears_warnings_after_generation()` — remove `enable_fallback=True` param
      - `test_contextvar_isolation_under_contention()` — remove `enable_fallback=True` param
      - Line 484: remove `enable_fallback=False` param from OllamaAIProvider call
      - Lines 546, 670: remove `enable_fallback=True` params
      
      For tests that relied on fallback behavior providing a valid result, update to expect ValueError on Ollama failure. Adjust test assertions accordingly.
      
      Files: `backend/tests/test_phase9_regression.py`
      Verify: `pytest backend/tests/test_phase9_regression.py -v` — all regression tests pass

- [ ] 4. Update benchmark.py: Remove `enable_fallback` parameter from benchmarking functions.
      
      Update lines 147 and 169 in `_bench_fallback()`:
      - Remove `enable_fallback=True,` parameter
      
      Update line 232 in `bench_fallback_quick()`:
      - Change `OllamaAIProvider(enable_fallback=False)` to `OllamaAIProvider()`
      - Expect ValueError and handle it with try-except to skip the benchmark (Ollama offline is expected)
      
      Update lines 303 (comment):
      - Remove comment line: `print(f"  Fallback enabled:         True (enable_fallback=True in factory)")`
      
      The fallback benchmark functions will now trigger ValueError when Ollama is offline, which is expected behavior. Update the test to skip gracefully or catch the exception.
      
      Files: `backend/scripts/benchmark.py`
      Verify: `python -m backend.scripts.benchmark` runs without TypeError; fallback benches are skipped or handle ValueError gracefully

- [ ] 5. Update smoke_test_ollama.py: Remove `enable_fallback` parameter.
      
      Update line 43:
      - Change `OllamaAIProvider(base_url=base_url, model=target_model, timeout=30.0, enable_fallback=False)` 
      - To: `OllamaAIProvider(base_url=base_url, model=target_model, timeout=30.0)`
      
      Files: `backend/scripts/smoke_test_ollama.py`
      Verify: `python -m backend.scripts.smoke_test_ollama` runs without TypeError

- [ ] 6. Update INTEGRATION_EXAMPLES.md: Remove fallback code block or update it to reflect Qwen-only behavior.
      
      Update lines 155-162 (the fallback block):
      - Remove the entire `if self.enable_fallback:` block and replace with documentation explaining Qwen-only behavior
      - Change from: "Fallback to scaffold on Ollama failure"
      - To: "Qwen-only behavior: raises ValueError if Ollama is unavailable"
      - Update the error handling documentation to show that ValueError is now the expected behavior when Ollama fails
      
      Files: `docs/INTEGRATION_EXAMPLES.md`
      Verify: Documentation accurately reflects Qwen-only architecture (manual inspection)

- [ ] 7. Run full test suite to verify all tests pass and no other `enable_fallback` references remain.
      
      Execute:
      ```bash
      cd backend
      pytest tests/ -v --tb=short
      ```
      
      Expected: All 25+ tests that were failing due to `enable_fallback` parameter now pass. Total test suite passes.
      
      If any test still references `enable_fallback` or fails with related errors, investigate and fix.
      
      Files: All test files (verification only)
      Verify: `pytest tests/ -v` — all tests pass, exit code 0

- [ ] 8. Verify no remaining references to `enable_fallback` in codebase.
      
      Execute:
      ```bash
      cd backend && grep -r "enable_fallback" --include="*.py" .
      ```
      
      Expected: No matches (or only in comments/docstrings explaining the removal).
      
      Files: N/A (verification only)
      Verify: `grep` returns no results or only matches in .git history

---

## Rationale & Key Changes

### Why These Changes?
1. **Architecture Decision**: Qwen-only behavior removes complexity and test maintenance burden.
2. **Failing Tests**: 25+ tests reference the old parameter signature, causing "TypeError: unexpected keyword argument 'enable_fallback'".
3. **Test Expectations Update**: Tests that expected fallback behavior (deterministic scaffold) must now expect `ValueError`.
4. **Documentation Alignment**: Examples and comments must reflect the new Qwen-only architecture.

### Test Logic Preservation
- Mocking, fixtures, and test structure remain unchanged.
- Only parameter passing and assertions are updated.
- Tests still validate:
  - CRM generation works with valid Ollama responses
  - Invalid/malformed responses are detected
  - Async paths work correctly
  - Context variables prevent cross-contamination
  - Evolution proposals clear warnings
  
### Error Handling
- When Ollama is unavailable: raise `ValueError("Qwen CRM generation is currently unavailable. Please check your Ollama connection and try again.")`
- Benchmarks and smoke tests handle ValueError gracefully (skip or log and exit)
- No silent fallback to deterministic scaffolds

---

## Verification Commands

After each step:
```bash
cd d:\AURA - Copy\backend

# Individual test files
pytest tests/test_ai_brain.py -v
pytest tests/test_evolution_proposals.py -v
pytest tests/test_phase9_regression.py -v

# All tests
pytest tests/ -v

# Check for remaining references
grep -r "enable_fallback" --include="*.py" .
```

Expected outcome: All tests pass, no remaining `enable_fallback` references.
