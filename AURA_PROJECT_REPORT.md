# AURA — Self-Evolving CRM: Project Report

**Version:** 1.0.0  
**Role:** Member 1 — AI Brain, CRM Generator, and Evolution Intelligence  
**Date:** October 2026  

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack](#2-tech-stack)
3. [System Architecture](#3-system-architecture)
4. [Database Schema](#4-database-schema)
5. [AI Brain Components](#5-ai-brain-components)
6. [API Endpoints](#6-api-endpoints)
7. [Frontend Structure](#7-frontend-structure)
8. [Testing Coverage](#8-testing-coverage)
9. [Performance Metrics](#9-performance-metrics)
10. [Security Model](#10-security-model)
11. [Drawbacks and Limitations](#11-drawbacks-and-limitations)
12. [Future Improvements](#12-future-improvements)

---

## 1. Project Overview

AURA is a **self-evolving CRM platform** that uses local AI inference to generate custom CRM configurations from natural language descriptions and propose workflow improvements over time.

Unlike traditional CRMs with fixed schemas, AURA generates the entire CRM structure — entities, fields, pipelines, and workflows — based on what a user describes about their business. The system can then observe how the CRM is being used and propose targeted improvements through an evolution proposal lifecycle that requires explicit human approval before any change is applied.

### Core Capabilities

| Capability | Description |
|---|---|
| **CRM Generation** | Natural language → validated JSON schema → active CRM |
| **Interactive Chat Generation** | Multi-turn AI conversation → CRM tailored to user responses |
| **Dynamic Records** | CRUD for any entity type defined in the CRM configuration |
| **CSV Import** | Bulk record import with per-row validation |
| **Workflow Automation** | Trigger-action workflows on record events |
| **Analytics** | Live conversion rates, pipeline stage breakdowns |
| **Evolution Proposals** | AI-generated improvement suggestions with 2-stage human approval |
| **Audit Logging** | Immutable log of every configuration change |

---

## 2. Tech Stack

### Backend

| Layer | Technology | Version |
|---|---|---|
| Language | Python | 3.11+ |
| Web framework | FastAPI | ≥ 0.115 |
| ASGI server | Uvicorn | ≥ 0.30 |
| Data validation | Pydantic v2 | ≥ 2.7 |
| Settings management | pydantic-settings | ≥ 2.3 |
| JWT verification | python-jose[cryptography] | ≥ 3.3 |
| HTTP client | httpx (async + sync) | ≥ 0.27 |
| Supabase SDK | supabase-py | ≥ 2.5 |
| File upload | python-multipart | ≥ 0.0.9 |
| AI runtime (optional) | convaiinnovations/laya | latest |
| Test framework | pytest + pytest-asyncio | ≥ 8.0 / ≥ 0.23 |

### Frontend

| Layer | Technology | Version |
|---|---|---|
| Language | TypeScript | 5.7+ |
| UI framework | React | 18.3 |
| Build tool | Vite | 6.1 |
| Routing | React Router DOM | 6.29 |
| Styling | Tailwind CSS | 3.4 |
| Auth client | @supabase/supabase-js | 2.49 |
| Charts | Recharts | 2.15 |
| Icons | lucide-react | 0.475 |

### Database and Auth

| Component | Technology |
|---|---|
| Database | Supabase PostgreSQL (hosted) |
| Auth provider | Supabase Auth (GoTrue) |
| Row-Level Security | PostgreSQL RLS policies |
| Stored procedures | PostgreSQL PL/pgSQL functions |
| JWT algorithm | HS256 (legacy) / ES256 (new signing keys) |

### AI Layer

| Component | Technology |
|---|---|
| Local LLM runtime | Ollama (v0.40+) |
| Language model | Qwen3-4B (Q4_K_M quantized, ~2.6 GB) |
| Decision intelligence | Laya System 1 (`convaiinnovations/laya`) |
| Deterministic fallback | AURA LayaSystem1 (rule-based, always available) |
| Inference mode | Local only — no cloud LLM calls |

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Browser (React / Vite)                    │
│  Auth via Supabase SDK   →   All data via FastAPI /api/v1   │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTPS / Vite proxy
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   FastAPI (port 8000)                        │
│                                                             │
│  auth.py ──── JWT verify (HS256 / ES256 via GoTrue)        │
│  database.py ─ Supabase service-role client                 │
│                                                             │
│  Routers:                                                   │
│  ├── /crm          → CRM CRUD, generate (draft)            │
│  ├── /crm/chat     → Interactive CRM chat generation        │
│  ├── /crm/*/records  → Dynamic record CRUD + CSV import    │
│  ├── /crm/*/workflows → Workflow management                 │
│  ├── /crm/*/analytics → Conversion metrics                 │
│  └── /crm/*/evolution → 2-stage proposal lifecycle         │
│                                                             │
│  Services:                                                  │
│  ├── laya_system1.py   → Deterministic safety + scaffold   │
│  ├── laya_runtime.py   → Official Laya ML adapter          │
│  ├── ollama_provider.py → Qwen3-4B via Ollama              │
│  ├── ai_provider.py    → Provider factory (mock/local)     │
│  └── validation.py     → Record field validation           │
└──────────────┬────────────────────┬────────────────────────┘
               │                    │
               ▼                    ▼
┌──────────────────────┐  ┌────────────────────────────────────┐
│  Supabase PostgreSQL │  │  Ollama (localhost:11434)           │
│                      │  │  Model: qwen3:4b (Q4_K_M)          │
│  crms                │  │  think=false, timeout=120s         │
│  records             │  │  BoundedSemaphore(4)               │
│  workflows           │  └────────────────────────────────────┘
│  evolution_proposals │
│  audit_logs          │
└──────────────────────┘
```

### Data flow — CRM generation (single prompt)

```
User prompt
    → validate_prompt_safety()          [SQL/code injection check]
    → LayaDecisionEngine.decide()       [Laya ML industry classification]
    → OllamaAIProvider._call_ollama()   [Qwen3-4B inference, think=false]
    → LayaSystem1.extract_json()        [JSON extraction from raw output]
    → LayaSystem1.repair_crm_config()   [Normalization + identifier repair]
    → CRMConfiguration(**data)          [Pydantic v2 strict validation]
    → Return draft (NOT saved)
    ↓ fallback if Ollama unavailable
    → LayaSystem1.generate_scaffold()   [Deterministic, industry-matched]
```

### Data flow — Interactive chat generation

```
User message N
    → POST /api/v1/crm/chat {messages, generate_now: false}
    → _call_ollama_chat() with consultant system prompt
    → Strip <think>...</think> leakage from response
    → Return {reply, ready_to_generate}
    ↓ When user clicks "Generate My CRM"
    → POST /api/v1/crm/chat {messages, generate_now: true}
    → _call_ollama_generate() with full conversation context
    → Repair + Pydantic validation
    → Return draft CRM built from conversation
```

### Data flow — Evolution proposal lifecycle

```
User requests proposal
    → LayaDecisionEngine.decide_evolution()  [priority classification]
    → LayaSystem1.rank_and_filter_candidates() [allowlist enforcement]
    → INSERT evolution_proposals (status=pending)
    ↓ Human reviews and approves
    → POST /approve → status=approved
    ↓ Human applies
    → Supabase RPC apply_evolution_proposal()
        → SELECT FOR UPDATE (proposal + crm rows)
        → Validate allowlisted change type
        → Mutate workflow
        → configuration_version++
        → status=applied
        → INSERT audit_logs
    → Atomic PostgreSQL transaction (all or nothing)
```

---

## 4. Database Schema

### Tables

#### `crms`
| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | CRM identifier |
| `owner_id` | UUID NOT NULL | Supabase Auth user |
| `name` | TEXT NOT NULL | Human-readable name |
| `configuration` | JSONB NOT NULL | Full CRM config (entities, fields, pipelines) |
| `configuration_version` | INTEGER DEFAULT 1 | Monotonic version for optimistic locking |
| `status` | TEXT DEFAULT 'active' | `active` or `archived` |
| `created_at` | TIMESTAMPTZ | Auto-set |
| `updated_at` | TIMESTAMPTZ | Auto-set |

#### `records`
| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Record identifier |
| `crm_id` | UUID FK → crms | Parent CRM |
| `entity_name` | TEXT NOT NULL | e.g. `lead`, `patient` |
| `data` | JSONB NOT NULL | Customer-defined field values |
| `source` | TEXT | e.g. `Website`, `CSV`, `Manual` |
| `owner_id` | UUID | Record owner |
| `created_at` / `updated_at` | TIMESTAMPTZ | Timestamps |
| `deleted_at` | TIMESTAMPTZ | Soft-delete marker (`NULL` = active) |

#### `workflows`
| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Workflow identifier |
| `crm_id` | UUID FK → crms | Parent CRM |
| `name` | TEXT NOT NULL | Display name |
| `trigger` | JSONB | `{type, entity}` — allowlisted trigger types |
| `actions` | JSONB | Array of allowlisted action objects |
| `status` | TEXT | `draft`, `active`, or `disabled` |

#### `evolution_proposals`
| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Proposal identifier |
| `crm_id` | UUID FK → crms | Target CRM |
| `status` | TEXT | `pending → approved → applied` or `rejected/failed` |
| `summary` | TEXT | Human-readable description |
| `proposed_change` | JSONB | Allowlisted change payload |
| `evidence` | JSONB | Metrics supporting the proposal |
| `configuration_version_at_creation` | INTEGER | Staleness detection |
| `approved_at` / `approved_by` | TIMESTAMPTZ / UUID | Stage 1 record |
| `applied_at` / `applied_by` | TIMESTAMPTZ / UUID | Stage 2 record |
| `rejected_at` / `rejected_by` / `rejection_reason` | — | Rejection record |
| `application_error` | TEXT | Server-side failure detail (not exposed to client) |

#### `audit_logs`
| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Log entry |
| `crm_id` | UUID FK → crms | Associated CRM |
| `crm_owner_id` | UUID | CRM owner at time of event |
| `user_id` | UUID | Acting user |
| `action` | TEXT | e.g. `apply_evolution_proposal` |
| `entity_type` | TEXT | e.g. `workflow`, `record` |
| `entity_id` | UUID | Target entity |
| `old_values` / `new_values` | JSONB | Before/after snapshot |
| `metadata` | JSONB | Additional context |

### Migrations applied

| File | Purpose |
|---|---|
| `0001_initial_crm_schema.sql` | Core tables, RLS policies, indexes |
| `0002_fix_records_soft_delete_rls.sql` | Soft-delete RLS fix |
| `0003_fix_apply_evolution_proposal_workflow_create.sql` | Atomic apply function |
| `0004_fix_workflow_create_record_assignment.sql` | Variable assignment fix |
| `0005_fix_evolution_proposal_terminal_state_approval_fields.sql` | Terminal state consistency |

### Stored procedures

| Procedure | Description |
|---|---|
| `approve_evolution_proposal(uuid)` | Validates ownership, status, staleness → sets approved |
| `apply_evolution_proposal(uuid)` | Atomic transaction: mutate workflow + version++ + audit log |
| `reject_evolution_proposal(uuid, reason)` | Sets rejected status with reason |

---

## 5. AI Brain Components

### LayaSystem1 (`laya_system1.py`)
The always-available deterministic cognitive layer. Never requires a model download.

| Method | Purpose |
|---|---|
| `detect_industry(prompt)` | Rule-based keyword classification into 4 industry types |
| `validate_prompt_safety(prompt)` | Blocks SQL injection and code execution attempts |
| `extract_json_payload(raw)` | 3-strategy JSON extraction from LLM output |
| `repair_crm_configuration(data, prompt)` | Normalizes identifiers, deduplicates, fills missing options |
| `generate_scaffold_config(prompt)` | Full deterministic CRM generation (no model needed) |
| `rank_and_filter_candidates(candidates, objective, analytics)` | Allowlist enforcement + priority scoring for evolution |
| `generate_scaffold_proposal(objective, crm, analytics)` | Deterministic evolution proposal generation |

**Industry taxonomies**: `saas`, `healthcare`, `real_estate`, `ecommerce`

### LayaDecisionEngine (`laya_runtime.py`)
Adapter for the official `convaiinnovations/laya` ML runtime.

| Decision | Questions asked |
|---|---|
| `decide_generation()` | Classifies industry (5 choices) + strategy (3 choices) |
| `decide_evolution()` | Priority (3 choices) + requires human review (noul probability) |

Lazy-loaded with double-checked locking. Gracefully degrades if not installed.

### OllamaAIProvider (`ollama_provider.py`)
Local Qwen3-4B inference via the Ollama daemon.

| Parameter | Value |
|---|---|
| Model | `qwen3:4b` (configurable via `LOCAL_LLM_MODEL`) |
| Timeout | 120 seconds |
| Thinking mode | Disabled (`think=false`) |
| Concurrency limit | 4 simultaneous requests (`asyncio.BoundedSemaphore`) |
| Max repair attempts | 1 |
| Warning isolation | `ContextVar` per request (prevents cross-request bleed) |
| Fallback | `LayaSystem1.generate_scaffold_config()` on any failure |

---

## 6. API Endpoints

### Base path: `/api/v1`

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/health` | Health check | No |
| POST | `/crm/generate` | Generate CRM draft from prompt | Yes |
| POST | `/crm/chat` | Interactive CRM chat | Yes |
| POST | `/crm` | Save CRM | Yes |
| GET | `/crm` | List user's CRMs | Yes |
| GET | `/crm/{id}` | Get single CRM | Yes |
| PATCH | `/crm/{id}/configuration` | Update CRM (→ 403, use evolution) | Yes |
| POST | `/crm/{id}/records/{entity}` | Create record | Yes |
| GET | `/crm/{id}/records/{entity}` | List records (paginated) | Yes |
| PATCH | `/crm/{id}/records/{entity}/{rid}` | Update record | Yes |
| DELETE | `/crm/{id}/records/{entity}/{rid}` | Soft-delete record | Yes |
| POST | `/crm/{id}/records/{entity}/import` | CSV import | Yes |
| GET | `/crm/{id}/workflows` | List workflows | Yes |
| POST | `/crm/{id}/workflows` | Create workflow | Yes |
| GET | `/crm/{id}/analytics` | CRM analytics | Yes |
| GET | `/crm/{id}/evolution/proposals` | List proposals | Yes |
| POST | `/crm/{id}/evolution/proposals` | Create proposal | Yes |
| POST | `/crm/{id}/evolution/proposals/{pid}/approve` | Approve (Stage 1) | Yes |
| POST | `/crm/{id}/evolution/proposals/{pid}/apply` | Apply (Stage 2) | Yes |
| POST | `/crm/{id}/evolution/proposals/{pid}/reject` | Reject proposal | Yes |

---

## 7. Frontend Structure

```
frontend/src/
├── App.tsx                          # Routing, provider hierarchy
├── services/
│   ├── api.ts                       # 18-method API adapter (mock + live)
│   └── supabase.ts                  # Supabase client init
├── context/
│   ├── AuthContext.tsx              # Auth state, demo mode, OAuth
│   ├── CRMContext.tsx               # Active CRM state, entity navigation
│   └── ToastContext.tsx             # Toast notification system
├── features/
│   ├── auth/                        # Login, Register, OAuth callback
│   ├── crm-generator/               # Single-prompt CRM generation page
│   ├── crm-chat/                    # Interactive chat-based generation
│   ├── crms/                        # CRM list and detail pages
│   ├── records/                     # Records CRUD, CSV import
│   ├── workflows/                   # Workflow management
│   ├── analytics/                   # Recharts dashboards
│   ├── evolution/                   # 2-stage proposal lifecycle
│   ├── dashboard/                   # Overview dashboard
│   ├── ai-assistant/                # Sidebar AI copilot (rule-based)
│   └── settings/                    # Settings page
└── components/
    ├── layout/                      # AppLayout, Navbar, Sidebar
    └── ui/                          # Button, Card, Modal, Input, Badge, etc.
```

### API adapter modes

| Mode | Trigger | Behavior |
|---|---|---|
| **Mock** | `VITE_USE_MOCK=true` or demo login | In-memory state, no backend needed |
| **Live** | `VITE_USE_MOCK=false` + real Supabase login | All calls to FastAPI at `/api/v1` |

---

## 8. Testing Coverage

### Backend — 179 tests

| Test file | Count | Scope |
|---|---|---|
| `test_ai_brain.py` | 26 | Laya System 1, Ollama provider, factory, concurrency |
| `test_evolution_proposals.py` | 36 | Full lifecycle, tenant isolation, staleness, audit |
| `test_migration_schema.py` | 46 | Migration SQL assertions for all 5 migrations |
| `test_phase9_regression.py` | 56 | Security, cross-tenant, allowlists, schema validation |
| `test_api.py` | 6 | Health, auth, generate, validation, contract |
| `test_record_response_contract.py` | 9 | Record response field names, CSV, schema |
| `test_live_db.py` | 6 | Live Supabase tests (skipped without `RUN_LIVE_DB_TESTS=1`) |

**Command:** `pytest tests/ --ignore=tests/test_live_db.py` → **179 passed**

### Frontend — 45 tests

Custom test runner (`tsx src/tests/run.ts`) using mock mode:

| Group | Tests | Scope |
|---|---|---|
| CRM generation | 4 | Draft response shape, schema version |
| CRM save | 3 | UUID, version 1, status active |
| Records CRUD | 6 | Create, list, update, soft-delete |
| CSV import | 2 | Created count, skipped count |
| Analytics | 4 | Types and array shapes |
| Workflows | 3 | Create, list |
| Evolution lifecycle | 9 | Pending→approved→applied, rejection |
| Supabase OAuth audit | 7 | Anon key role, OAuth URL generation |
| Live adapter isolation | 5 | Mode toggle, no silent fallback |

**Command:** `npm test` → **45 passed**

---

## 9. Performance Metrics

Measured on Windows 11 / Python 3.11.9 / Qwen3-4B Q4_K_M:

| Operation | Mean latency |
|---|---|
| Industry detection (rule-based) | < 0.01 ms |
| Prompt safety validation | 0.01 ms |
| Full deterministic scaffold pipeline | 0.13 ms |
| Pydantic v2 strict validation | 0.02 ms |
| Sync fallback (Ollama offline, 0.1s timeout) | ~582 ms |
| **Qwen3-4B chat response (CPU)** | **25 – 120 seconds** |
| **Qwen3-4B CRM generation (CPU)** | **28 – 90 seconds** |
| 8 concurrent requests, semaphore=4 | 2 batches × latency |
| Provider factory instantiation | < 1 ms |

> Times for Qwen3-4B vary significantly based on CPU/GPU, available RAM, and prompt length.

---

## 10. Security Model

| Control | Implementation |
|---|---|
| **Authentication** | Supabase JWT verified server-side on every request (HS256 legacy + ES256 via GoTrue) |
| **Authorization** | CRM ownership checked on every scoped operation via `WHERE owner_id = authenticated_user_id` |
| **Row-Level Security** | RLS enabled on all tables; defense-in-depth alongside app-layer checks |
| **Prompt injection** | SQL patterns (`UNION SELECT`, `DROP TABLE`) and code execution (`import os`, `eval()`) blocked before LLM call |
| **LLM output safety** | All LLM output treated as untrusted; never executed as SQL or code |
| **AI approval boundary** | AI cannot approve or apply its own proposals — requires explicit human POST |
| **Evolution allowlisting** | Change types enforced at Python layer AND PostgreSQL stored procedure |
| **Atomic application** | PostgreSQL `SELECT FOR UPDATE` + single transaction prevents race conditions |
| **Secret protection** | Service-role key and JWT secret server-side only; never in responses |
| **No stack traces in responses** | Global exception handler returns generic messages only |
| **Tenant isolation** | Cross-tenant access returns 404 (not 403) to avoid resource enumeration |
| **Warning isolation** | `ContextVar` prevents fallback warnings from leaking across concurrent requests |

---

## 11. Drawbacks and Limitations

### 11.1 AI Performance — Local Inference Is Slow

**Severity: High**

Qwen3-4B running on CPU takes **25–120 seconds per response** in the interactive chat, and **28–90 seconds** to generate a full CRM. This is the most significant usability limitation. Users must wait for each AI turn in the conversation, making the chat feel sluggish.

- Root cause: 4B parameter model on CPU without GPU acceleration
- Workaround: Install Ollama with CUDA support on a machine with an NVIDIA GPU (reduces latency to 2–5 seconds per response)
- Alternative: Switch to a smaller model like `qwen3:1.7b` for faster responses at the cost of quality

---

### 11.2 No Real-Time Streaming

**Severity: Medium**

The backend calls Ollama with `stream: false` and waits for the complete response before returning. Users see the loading spinner for the full duration with no indication of progress.

- Better UX would stream tokens as they arrive using SSE (Server-Sent Events) or WebSockets
- Not implemented due to added complexity in the fallback path and response repair logic

---

### 11.3 Laya Package Not in requirements.txt

**Severity: Medium**

The `convaiinnovations/laya` package is used for ML-based industry and priority classification but is not listed in `requirements.txt`. It is silently skipped if not installed, falling back to rule-based classification. A fresh developer environment will not have it installed without manual intervention.

- The fallback behavior is correct and tested
- The limitation is documentation/discoverability, not correctness

---

### 11.4 Single-Tenant Ownership Model

**Severity: Medium**

Each CRM has exactly one `owner_id`. There is no concept of teams, shared access, or role-based permissions within a CRM.

- A second user cannot access or collaborate on another user's CRM
- This was an intentional MVP constraint but limits real-world team usage
- The schema supports extension (`crm_members` table was discussed but not built)

---

### 11.5 PATCH /crm/{id}/configuration Always Returns 403

**Severity: Low–Medium**

There is no way to update a CRM's metadata (e.g. rename it) without going through the evolution proposal flow. This was an intentional MVP constraint to enforce the approval lifecycle, but it means even trivial changes require a full proposal cycle.

---

### 11.6 Analytics Computed In-Process (No SQL Aggregation)

**Severity: Medium at Scale**

The `count_records_by_field()` method in `database.py` fetches all records' JSONB data into Python memory and groups them in-app. For a CRM with tens of thousands of records this will be slow and memory-intensive.

- Should be replaced with a PostgreSQL-level `GROUP BY` query using JSONB operators
- Acceptable for MVP scale (hundreds of records)

---

### 11.7 No Rate Limiting

**Severity: Medium**

The API contract defines a `429 RATE_LIMITED` error code but no rate limiting middleware is implemented. Any authenticated user can issue unlimited generation requests, potentially overloading the local Ollama daemon.

- The `BoundedSemaphore(4)` limits concurrent Ollama calls but does not limit request frequency
- Recommended: Add `slowapi` or a similar middleware before production deployment

---

### 11.8 AI Assistant Drawer Is Fully Simulated

**Severity: Low**

The "AI Copilot" sidebar drawer (`AIAssistantDrawer.tsx`) uses hardcoded keyword-matching responses with simulated latency. It does not call the backend or Ollama. Users may expect it to be the same AI that generated their CRM, but it is a scripted rule-based system.

---

### 11.9 No Token Refresh in Backend API Calls

**Severity: Low**

Supabase JWTs expire after 1 hour. The frontend's Supabase SDK auto-refreshes tokens, but the backend verifies each request independently against the token at the time of the call. If a request is made just after a token expires (before the SDK refreshes it), the user gets a 401 and must retry.

- In practice this is rare due to the SDK's proactive refresh
- A more robust solution would accept tokens within a grace window or verify via the Supabase session endpoint

---

### 11.10 Evolution Proposals Are Workflow-Only

**Severity: Low–Medium**

The current allowlist for evolution proposals only supports `workflow.update` and `workflow.create`. The system cannot propose adding new fields, changing pipeline stages, creating new entity types, or archiving unused entities. These would require schema migration logic and were explicitly deferred from the MVP.

---

### 11.11 Dashboard Analytics Failure Is Silent

**Severity: Low**

The dashboard calls `api.getAnalytics().catch(() => {})`, silently swallowing any error and displaying `0` everywhere. Users have no indication that analytics failed to load.

---

### 11.12 `frontend/.env` Committed to Repository

**Severity: Low**

The `frontend/.env` file containing the Supabase anon key is committed to the repository. The anon key is designed to be publicly safe (it is the publishable key), but committing `.env` files is bad practice and should be addressed before open-sourcing the project.

---

## 12. Future Improvements

| Priority | Improvement |
|---|---|
| 🔴 High | Stream Qwen3-4B responses via SSE for real-time chat UX |
| 🔴 High | GPU acceleration for Ollama to reduce inference to 2–5 seconds |
| 🟠 Medium | Replace in-process analytics aggregation with PostgreSQL GROUP BY |
| 🟠 Medium | Add rate limiting middleware (slowapi or similar) |
| 🟠 Medium | Implement team membership (`crm_members` table) for shared CRMs |
| 🟠 Medium | Allow evolution proposals for field additions and pipeline stage changes |
| 🟠 Medium | Add `laya` to `requirements.txt` as an optional dependency |
| 🟡 Low | Wire `AIAssistantDrawer` to the real backend chat endpoint |
| 🟡 Low | Add `PATCH /crm/{id}/configuration` for safe metadata updates |
| 🟡 Low | Implement token refresh grace window in backend auth |
| 🟡 Low | Add `frontend/.env` to `.gitignore` and use `.env.example` only |
| 🟡 Low | Replace dashboard silent analytics failure with user-visible error state |
| 🟢 Future | Multi-model support (Grok API, GPT-4 fallback when Ollama unavailable) |
| 🟢 Future | Automated evolution: CRM watches its own analytics and suggests proposals proactively |
| 🟢 Future | Record deduplication and data quality checks on import |

---

## Summary

AURA demonstrates a working end-to-end self-evolving CRM that generates customized database schemas, UIs, and workflows from natural language — without any fixed templates. The AI brain runs entirely locally (no data leaves the user's machine to an LLM provider), the approval lifecycle prevents any AI change from being applied without human sign-off, and the system degrades gracefully when the AI model is unavailable.

The primary constraint for production readiness is inference speed — local CPU inference with a 4B model is functional but not fast enough for a consumer product without GPU hardware. Everything else — the API contracts, security model, testing coverage, and data architecture — is production-grade.

---

*Generated: October 2026 · AURA v1.0.0 · Member 1 scope*
