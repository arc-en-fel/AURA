# AURA Self-Evolving CRM — Setup Guide

**Member 1 — AI Brain, CRM Generator, and Evolution Intelligence**  
Stack: Qwen3-4B via Ollama · Laya System 1 · Python/FastAPI · Supabase · React/Vite

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | Tested on 3.11.9 |
| Node.js | 18+ | For the frontend |
| Git | any | |
| Supabase project | — | Required for DB and auth |
| Ollama | latest | Optional — system works without it via deterministic fallback |

---

## 1. Clone and configure

```bash
git clone <repo-url>
cd AURA
```

---

## 2. Backend setup

### 2a. Create the virtual environment

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2b. Configure environment variables

Copy the example and fill in real values:

```powershell
copy .env.example .env
```

Open `backend/.env` and set these required values:

```env
# Supabase — find these at: https://supabase.com/dashboard/project/<your-ref>/settings/api
SUPABASE_URL=https://<your-ref>.supabase.co
SUPABASE_ANON_KEY=<your-anon-key>
SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>
SUPABASE_JWT_SECRET=<your-jwt-secret>

# AI provider — use "local" for Ollama+Laya, "mock" for no-model demo
LLM_PROVIDER=local

# Ollama (only needed when LLM_PROVIDER=local)
LOCAL_LLM_BASE_URL=http://localhost:11434
LOCAL_LLM_MODEL=qwen3:4b
```

**Where to find Supabase values:**

| Key | Location in Dashboard |
|---|---|
| `SUPABASE_URL` | Project Settings → General → Reference ID |
| `SUPABASE_ANON_KEY` | Project Settings → API → Project API keys → `anon` |
| `SUPABASE_SERVICE_ROLE_KEY` | Project Settings → API → Project API keys → `service_role` (Reveal) |
| `SUPABASE_JWT_SECRET` | Project Settings → JWT Keys → Legacy JWT Secret → Copy |

> **Security**: Never commit `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_JWT_SECRET`. Both are in `.gitignore`.

### 2c. Apply database migrations

The migrations live in `supabase/migrations/`. Apply them via the Supabase dashboard SQL editor or Supabase CLI:

```bash
supabase db push
```

Migrations in order:
- `0001_initial_crm_schema.sql` — core tables, RLS, indexes
- `0002_fix_records_soft_delete_rls.sql` — soft-delete RLS fix
- `0003_fix_apply_evolution_proposal_workflow_create.sql` — atomic apply function
- `0004_fix_workflow_create_record_assignment.sql` — variable assignment fix
- `0005_fix_evolution_proposal_terminal_state_approval_fields.sql` — terminal state consistency

### 2d. Start the backend

```powershell
cd backend
.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
```

Confirm it is running:
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health"
# Expected: { "data": { "status": "ok" }, ... }
```

---

## 3. Ollama and Qwen3-4B setup (optional — required for live AI generation)

### 3a. Install Ollama

Download and install from: https://ollama.com/download

Verify:
```powershell
ollama --version
```

### 3b. Pull the Qwen3-4B model

**Disk space required: ~2.6 GB**

```powershell
ollama pull qwen3:4b
```

This downloads once and is cached locally. Do not run this automatically — it requires explicit approval.

### 3c. Start the Ollama service

```powershell
ollama serve
```

Verify it is reachable:
```powershell
Invoke-RestMethod -Uri "http://localhost:11434/api/tags"
# Expected: { "models": [{ "name": "qwen3:4b", ... }] }
```

### 3d. Verify the model tag matches

The backend defaults to `qwen3:4b`. If you pulled a different tag, set it explicitly:

```env
LOCAL_LLM_MODEL=qwen3:4b
```

---

## 4. Laya System 1 setup

Laya is the `convaiinnovations/laya` package, used for industry classification and evolution priority decisions.

### 4a. Check if it is installed

```powershell
cd backend
.venv\Scripts\python.exe -c "import laya; print('Laya available')"
```

If this prints `Laya available`, no further action is needed.

### 4b. Install (if missing)

```powershell
.venv\Scripts\pip install laya
```

The package downloads checkpoint files on first use (~200MB, cached by HuggingFace Hub).

### 4c. Behavior without Laya

If Laya is not installed, the system operates correctly using the rule-based industry detection in `LayaSystem1`. The `LayaDecisionEngine` raises `LayaRuntimeError`, which is caught and handled as a graceful skip. All functionality remains available; Laya decisions simply do not influence generation.

---

## 5. Frontend setup

```powershell
cd frontend
npm install
```

Configure `frontend/.env`:

```env
VITE_API_BASE_URL=/api/v1
VITE_SUPABASE_URL=https://<your-ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<your-anon-key>
VITE_USE_MOCK=false
```

Start the dev server:

```powershell
npm run dev
```

The Vite proxy forwards all `/api/v1/*` requests to `http://localhost:8000`.

Open: http://localhost:5173

---

## 6. Running tests

### Backend — full suite (no Ollama required)

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests/ --ignore=tests/test_live_db.py -q
```

Expected: **179 passed**

### Backend — live database tests (requires Supabase)

```powershell
$env:RUN_LIVE_DB_TESTS = "1"
.venv\Scripts\python.exe -m pytest tests/test_live_db.py -v
```

### Backend — contract audit script

```powershell
.venv\Scripts\python.exe -m scripts.phase7_contract_audit
```

Expected: **24/24 checks passed**

### Backend — performance benchmark

```powershell
.venv\Scripts\python.exe -m scripts.benchmark
```

### Frontend — full test suite

```powershell
cd frontend
npm test
```

Expected: **45 passed**

---

## 7. Running in demo/mock mode (no backend required)

The frontend has a built-in mock adapter for evaluation without a backend:

1. Open http://localhost:5173
2. Click **"Instant Demo Access"** on the login page
3. All API calls use in-memory mock data — no Supabase, no Ollama needed

To revert to live mode: sign out and log in with a real Supabase account.

---

## 8. Performance characteristics

Measured on Windows 11 / Python 3.11.9 (no Ollama running):

| Operation | Mean latency |
|---|---|
| Industry detection (rule-based) | <0.01ms |
| Prompt safety validation | ~0.01ms |
| Scaffold config generation | ~0.08ms |
| Schema repair + Pydantic validation | ~0.13ms |
| Full fallback pipeline (detect→scaffold→repair→validate) | ~0.13ms |
| Sync fallback (Ollama offline, 0.1s timeout) | ~582ms |
| Async fallback (Ollama offline, 0.1s timeout) | ~583ms |
| Provider factory instantiation | <1ms |

**With Ollama running (qwen3:4b):**

| Operation | Expected latency |
|---|---|
| Cold inference (first request after model load) | 15–40s depending on hardware |
| Warm inference (subsequent requests) | 8–20s |
| Fallback trigger timeout | 12s (configured) |

**Concurrency limits:**

| Parameter | Value |
|---|---|
| Max concurrent Ollama requests | 4 (BoundedSemaphore) |
| Ollama request timeout | 12 000ms |
| Max JSON repair attempts | 1 |

---

## 9. Operational limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| Ollama/Qwen not running | AI generation uses deterministic fallback; amber warning shown in UI | Run `ollama serve` and `ollama pull qwen3:4b` |
| `laya` package not installed | Industry/priority decisions use rule-based layer only | `pip install laya` |
| `SUPABASE_SERVICE_ROLE_KEY` not set | All DB write operations fail with 500 | Add key from Supabase dashboard |
| `SUPABASE_JWT_SECRET` wrong | All authenticated requests fail with 401 | Copy Legacy JWT Secret from Supabase |
| No rate limiting | No `429` responses; backend relies on `BoundedSemaphore` for Ollama protection only | Add rate limiting middleware for production |
| `PATCH /crm/{id}/configuration` always 403 | Configuration changes must go through evolution proposal flow | Intentional MVP constraint |
| Live DB tests skipped by default | `test_live_db.py` requires `RUN_LIVE_DB_TESTS=1` | Set env var with live Supabase credentials |

---

## 10. Architecture summary

```
Browser (React/Vite)
    │  Authorization: Bearer <Supabase JWT>
    ▼
FastAPI (port 8000) ─── Supabase Auth (JWT verify)
    │
    ├── POST /crm/generate
    │       │
    │       ├── LayaSystem1.validate_prompt_safety()      [always]
    │       ├── LayaDecisionEngine.decide_generation()    [if laya installed]
    │       ├── OllamaAIProvider → Qwen3-4B (qwen3:4b)   [if Ollama running]
    │       ├── LayaSystem1.extract_json_payload()
    │       ├── LayaSystem1.repair_crm_configuration()
    │       ├── CRMConfiguration (Pydantic v2 strict)
    │       └── fallback: LayaSystem1.generate_scaffold_config()
    │
    ├── POST /crm/{id}/evolution/proposals
    │       │
    │       ├── LayaDecisionEngine.decide_evolution()     [if laya installed]
    │       ├── LayaSystem1.generate_scaffold_proposal()
    │       ├── LayaSystem1.rank_and_filter_candidates()  [allowlist enforced]
    │       ├── ProposedChange (Pydantic v2 strict)
    │       └── INSERT evolution_proposals (status=pending)
    │
    └── POST /crm/{id}/evolution/proposals/{id}/apply
            │
            └── Supabase RPC apply_evolution_proposal()  [atomic PostgreSQL txn]
                    ├── SELECT FOR UPDATE (proposal + crm rows)
                    ├── Allowlist check (trigger + action types)
                    ├── Workflow mutation
                    ├── configuration_version++
                    ├── proposal.status = 'applied'
                    └── INSERT audit_logs

Supabase PostgreSQL
    ├── crms          (owner_id, configuration JSONB, configuration_version)
    ├── records       (crm_id, entity_name, data JSONB, deleted_at)
    ├── workflows     (crm_id, trigger JSONB, actions JSONB, status)
    ├── evolution_proposals (crm_id, proposed_change JSONB, status)
    └── audit_logs    (crm_id, user_id, action, entity_type, old/new_values)
```

---

## 11. Security checklist

- [x] Service-role key never exposed to frontend
- [x] JWT verified server-side on every request
- [x] CRM ownership enforced on every scoped operation
- [x] Prompt SQL/code injection blocked before LLM call
- [x] LLM output never executed as SQL or code
- [x] Evolution proposals require explicit human approval before application
- [x] Atomic application via PostgreSQL stored procedure (no Python race conditions)
- [x] RLS enabled on all tables (defense-in-depth)
- [x] No stack traces, secrets, or raw DB errors in API responses
- [x] ContextVar prevents warning bleed between concurrent requests
