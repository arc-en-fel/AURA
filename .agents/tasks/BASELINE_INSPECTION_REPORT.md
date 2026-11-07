# AURA Phase 1: Baseline Inspection & Planning Report

**Date:** 2024
**Task:** Map five critical violations (C1–C5) to exact code locations and establish baseline state
**Repository:** d:\AURA - Copy

---

## EXECUTIVE SUMMARY

The AURA codebase contains **five critical violations** preventing universal CRM support. All violations directly contradict the architecture principle: *"Any CRM created from any user description must work without code modifications."* 

Current status: **CANNOT SHIP** until all C1–C5 are fixed.

---

## VIOLATION MAPPING TABLE

| ID | Violation | File | Line(s) | Function | Current Behavior | Severity |
|----|-----------|------|---------|----------|------------------|----------|
| **C1** | Hard-coded form status defaults | `frontend/src/features/records/RecordFormModal.tsx` | 175–176 | `renderFieldInput` | When no status field options, default to `['New', 'Active', 'Completed']` regardless of CRM type | 🔴 CRITICAL |
| **C2** | Hard-coded Analytics schema | `backend/app/schemas/crm.py` | 248–255 | `AnalyticsData` class | Schema assumes `total_leads`, `qualified_leads`, `won_leads`, `conversion_rate` (sales-only terms) | 🔴 CRITICAL |
| **C3** | Hard-coded won_stages detection | `backend/app/routers/evolution.py` | 93–98 | `create_proposal` | Only counts stages in fixed list: `{"Won", "won", "Closed Won", "closed_won"}` | 🔴 CRITICAL |
| **C4** | Hard-coded lead entity fallback | `backend/app/routers/evolution.py` | 84 | `create_proposal` | Falls back to `"lead"` when `config.entities` is empty | 🔴 CRITICAL |
| **C5** | Hard-coded industry taxonomies | `backend/app/services/laya_system1.py` | 76–121 | `INDUSTRY_TAXONOMIES` dict | Only 4 pre-built CRM types (saas, healthcare, real_estate, ecommerce) baked into code | 🔴 CRITICAL |

---

## DETAILED VIOLATION ANALYSIS

### C1: Hard-Coded Form Status Defaults

**File:** `frontend/src/features/records/RecordFormModal.tsx`  
**Lines:** 175–176  
**Category:** Schema-generation / Form Defaults

**Exact Code:**
```tsx
case 'status': {
  const stages = activeCRM?.configuration?.pipeline_stages || [];
  const statusOptions = field.options && field.options.length > 0 ? field.options : stages;
  return (
    <div key={field.name}>
      <Select
        label={field.label}
        required={field.required}
        options={statusOptions.length > 0 ? statusOptions : ['New', 'Active', 'Completed']}
        value={String(val ?? statusOptions[0] ?? '')}
        onChange={(e) => handleChange(field.name, e.target.value)}
        error={errorMsg}
      />
    </div>
  );
}
```

**Problem Chain:**
1. Component receives `entity` with `fields` array
2. If field type is "status", component reads `field.options`
3. If `field.options` is empty/undefined AND `stages` array is empty, it defaults to `['New', 'Active', 'Completed']`
4. This arbitrary default works only for sales CRMs; breaks healthcare, e-commerce, support, and 90% of other use cases

**Impact Examples:**
- **Healthcare CRM** with patient entity and no status field options → form shows "New/Active/Completed" instead of "Admitted/Discharged/Follow-up"
- **E-Commerce CRM** with customer entity → shows sales stages instead of "New Customer/Repeat Buyer/VIP"
- **Support CRM** with ticket entity → ignores "Open/Assigned/Resolved" configuration

**Entry Point:** When user opens record creation form for any non-sales CRM type

**Data Flow:**
```
User clicks "Create Record"
  → RecordFormModal opens
  → useEffect runs, entity.fields parsed
  → renderFieldInput called for each field
  → status field type check at line 172
  → statusOptions calculated: field.options OR pipeline_stages
  → if both empty → HARDCODED DEFAULT ['New', 'Active', 'Completed']
```

**Why It's Broken:**
- The fallback assumes all CRMs have a sales pipeline
- It ignores CRM configuration for status semantics
- Silent failure: user doesn't realize stages are wrong until after record creation

---

### C2: Hard-Coded Analytics Schema (Sales Metrics Only)

**File:** `backend/app/schemas/crm.py`  
**Lines:** 248–255  
**Category:** Schema-generation / Transport Contracts

**Exact Code:**
```python
class AnalyticsData(StrictModel):
    total_leads: int = Field(ge=0)
    qualified_leads: int = Field(ge=0)
    won_leads: int = Field(ge=0)
    conversion_rate: float = Field(ge=0, le=1)
    by_source: list[dict[str, Any]] = Field(default_factory=list)
    by_stage: list[dict[str, Any]] = Field(default_factory=list)
```

**Problem Chain:**
1. Backend analytics endpoint (`GET /api/v1/crm/{crm_id}/analytics`) must return `AnalyticsData`
2. `AnalyticsData` schema hard-codes sales metrics: `total_leads`, `qualified_leads`, `won_leads`, `conversion_rate`
3. For non-sales CRMs (healthcare, support, e-commerce), these fields have **no semantic meaning**
4. Backend forced to return 0 for `qualified_leads`, `won_leads`, `conversion_rate` even if records exist
5. Frontend receives all-zero metrics and displays "No data" on analytics dashboard

**Impact Examples:**
- **Healthcare CRM**: 100 patients admitted → `total_leads=100, qualified_leads=0, won_leads=0` (semantically wrong)
- **Support CRM**: 500 tickets, 450 resolved → `conversion_rate=0.0` (wrong; should measure resolution %)
- **E-Commerce CRM**: 1000 customers, 600 repeat buyers → `conversion_rate=0.0` (breaks LTV metrics)

**Entry Point:** When user navigates to Analytics tab after generating any non-sales CRM

**Data Flow:**
```
User navigates to Analytics
  → AnalyticsPage.tsx renders
  → api.getAnalytics(crm_id) called
  → Backend GET /api/v1/crm/{crm_id}/analytics
  → Backend returns AnalyticsData with computed metrics
  → Pydantic validates response against schema
  → Response has total_leads=0, won_leads=0, conversion_rate=0.0
  → Frontend displays "No meaningful data"
```

**Why It's Broken:**
- Schema assumes universal metrics are sales metrics
- No way to express healthcare, support, or e-commerce metrics
- Contract is hard-coded; API cannot be extended without schema change
- Violates: "CRM schemas must be source of truth"

**Related Code (Backend Computation):**
File: `backend/app/routers/workflows.py`, lines 93–98:
```python
won_stages = {"Won", "won", "Closed Won", "closed_won"}
by_stage = repo.count_records_by_field(str(crm_id), primary_entity, stage_field.name)
won = sum(entry.get("count", 0) for entry in by_stage if entry.get("value") in won_stages)
analytics_data["won_leads"] = won
analytics_data["conversion_rate"] = round(won / total, 4)
```
This code tries to compute `won_leads` using a hard-coded set of stage names. See C3 for full details.

---

### C3: Hard-Coded Won_Stages Detection

**File:** `backend/app/routers/evolution.py`  
**Lines:** 93–98  
**Category:** Hard-coded status/stage values

**Exact Code:**
```python
won_stages = {"Won", "won", "Closed Won", "closed_won"}
by_stage = repo.count_records_by_field(str(crm_id), primary_entity, stage_field.name)
won = sum(entry.get("count", 0) for entry in by_stage if entry.get("value") in won_stages)
analytics_data["won_leads"] = won
analytics_data["conversion_rate"] = round(won / total, 4)
```

**Problem Chain:**
1. System wants to compute "conversion rate" (won leads / total leads)
2. To find "won" records, it uses hard-coded stage names: "Won", "won", "Closed Won", "closed_won"
3. If CRM has different stage names (e.g., "Treatment Complete", "Patient Discharged", "Order Fulfilled"), no records match
4. `won = 0` even if all records are in success stages
5. `conversion_rate = 0.0` regardless of actual completion rate

**Impact Examples:**
- **Healthcare**: Stages "Admitted" → "Treatment Complete" → "Discharged". All 100 patients discharged → `conversion_rate=0.0`
- **E-Commerce**: Stages "New Lead" → "Order Placed" → "Shipped" → "Completed". 1000 orders completed → `conversion_rate=0.0`
- **Support**: Stages "Open" → "Assigned" → "In Progress" → "Resolved". 500 tickets resolved → `conversion_rate=0.0`

**Entry Point:** When user requests evolution proposal (AI suggestions for workflow improvements)

**Data Flow:**
```
POST /api/v1/crm/{crm_id}/evolution/proposals
  → create_proposal() called
  → analytics_data computed
  → won_stages set to {"Won", "won", "Closed Won", "closed_won"}
  → repo.count_records_by_field() groups records by stage value
  → sum(count if stage in won_stages) → if no stage matches, sum=0
  → analytics_data["won_leads"] = 0
  → analytics_data["conversion_rate"] = 0.0
  → Proposal generated with 0% conversion rate (even if untrue)
```

**Why It's Broken:**
- Stage names are user-configurable in CRM schema, not fixed
- Hard-coded list has no way to express healthcare, support, or e-commerce success metrics
- AI proposals are made with false analytics (0% conversion always)
- System has no concept of "configurable success stage" or "outcome metric"

---

### C4: Hard-Coded "lead" Entity Fallback

**File:** `backend/app/routers/evolution.py`  
**Line:** 84  
**Category:** Hard-coded entity names / Fallback logic

**Exact Code:**
```python
primary_entity = config.entities[0].name if config.entities else "lead"
```

**Problem Chain:**
1. `create_proposal()` tries to get the primary entity name
2. It safely reads `config.entities[0].name` if entities exist
3. But if `config.entities` is empty/null, it defaults to `"lead"`
4. Next line tries to count records in entity `"lead"` — but the CRM might not have a "lead" entity
5. Record count is 0 (entity doesn't exist in DB)
6. Analytics data is all zeros
7. Proposal generated with no useful signals

**Impact Examples:**
- **Healthcare CRM** with entity "patient" (no "lead" entity) → count_records("lead") returns 0
- **Custom CRM** with entity "shipment" → tries to query non-existent "lead" table
- **Support CRM** with entity "ticket" → entity fallback breaks proposal generation

**Entry Point:** When user requests evolution proposal for any CRM without "lead" entity

**Data Flow:**
```
POST /api/v1/crm/{crm_id}/evolution/proposals
  → create_proposal()
  → config = CRMConfiguration(**crm["configuration"])
  → if config.entities: primary_entity = config.entities[0].name
  → else: primary_entity = "lead"  ← FALLBACK
  → count_records(crm_id, "lead")  ← Query wrong entity
  → No records found (entity doesn't exist in CRM)
  → analytics_data["total_leads"] = 0
  → Proposal ranking signals all 0
```

**Why It's Broken:**
- Assumes every CRM has "lead" entity
- No validation that entity exists before querying
- Silent failure: no error raised, just wrong numbers
- Violates: "Resolve entity using active CRM's saved entity definitions"

---

### C5: Hard-Coded Industry Taxonomies (Pre-Built CRM Types)

**File:** `backend/app/services/laya_system1.py`  
**Lines:** 76–121  
**Category:** Hard-coded CRM type checks / Industry-specific defaults

**Exact Code:**
```python
INDUSTRY_TAXONOMIES: dict[str, dict[str, Any]] = {
    "saas": {
        "label": "B2B SaaS Sales CRM",
        "default_entity": "lead",
        "pipeline": ["New", "Discovery", "Demo Scheduled", "Proposal", "Negotiation", "Closed Won", "Closed Lost"],
        "fields": [
            {"name": "full_name", "label": "Full Name", "type": "text", "required": True},
            {"name": "email", "label": "Work Email", "type": "email", "required": True},
            {"name": "company", "label": "Company", "type": "text", "required": False},
            {"name": "lead_source", "label": "Lead Source", "type": "select", "required": True,
             "options": ["Website", "Product Trial", "Inbound", "Referral", "Outbound"]},
            {"name": "deal_size", "label": "ARR Estimate ($)", "type": "number", "required": False},
            {"name": "status", "label": "Lead Status", "type": "select", "required": True,
             "options": ["New", "Discovery", "Demo Scheduled", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]},
        ],
    },
    "healthcare": { ... },
    "real_estate": { ... },
    "ecommerce": { ... },
}
```

**Problem Chain:**
1. User submits prompt: "Create a CRM for our recruitment agency"
2. `detect_industry()` scans prompt for keywords
3. Detects keywords don't match saas/healthcare/real_estate/ecommerce
4. Falls back to `"general"` or `"saas"`
5. `repair_crm_configuration()` reads `INDUSTRY_TAXONOMIES["saas"]`
6. System generates lead-based CRM with deal_size, ARR Estimate, lead_source fields
7. User gets sales-only CRM for recruitment (needs candidate, interview_round, hiring_stage fields)

**Impact Examples:**
- **Recruitment CRM**: User prompt "Track candidates through hiring process" → `detect_industry()` no match → defaults to "saas" → generates lead entity with deal_size field (wrong)
- **Logistics CRM**: User prompt "Track shipments and delivery status" → no match → defaults to "saas" → generates wrong schema
- **Manufacturing CRM**: User prompt "Manage production orders" → no match → no taxonomy entry → forced to use custom questionnaire

**Entry Point:** When user requests CRM generation via `POST /api/v1/crm/generate` with non-standard industry prompt

**Data Flow:**
```
POST /api/v1/crm/generate
  → prompt = "Create a CRM for our recruitment agency"
  → detect_industry(prompt) → checks ["health", "real estate", "ecommerce", "saas"]
  → no match → returns "general"
  → repair_crm_configuration(raw, prompt)
  → industry = "general"
  → tax = INDUSTRY_TAXONOMIES.get("general", INDUSTRY_TAXONOMIES["saas"])
  → Uses "saas" taxonomy as fallback
  → config uses lead entity, deal_size field, etc. (wrong for recruitment)
```

**Why It's Broken:**
- Only 4 industry types pre-defined in code
- 5th type requires code changes and redeployment
- Hard-coded taxonomy assumes all CRMs need same fields (name, email, status, source, deal_size)
- Violates: "Self-evolving" principle — cannot add new CRM types without developer intervention
- Violates: "Never execute arbitrary LLM output" but then bakes output into code

---

## TEST BASELINE

### Backend Tests

**Test Files Found:** 22 files in `backend/tests/`
```
test_ai_brain.py
test_api.py
test_chat_validation_fix.py
test_copilot.py
test_copilot_tools.py
test_custom_crm_bug_fix.py
test_empty_messages_bug.py
test_evolution_proposals.py
test_feat_001_field_preservation.py
test_feat_002_schema_editing.py
test_field_preservation.py
test_groq_provider.py
test_integration_end_to_end.py
test_live_db.py
test_migration_schema.py
test_normalization_layer.py
test_phase9_regression.py
test_qwen_only_architecture.py
test_record_response_contract.py
test_regression_422_and_custom_crm.py
test_schema_editing_api.py
test_universal_crm_generation.py
```

**Current Status:** Tests running (423 items collected). Sample output shows passing tests:
- `test_sanitize_identifier` ✅
- `test_detect_industry` ✅
- `test_prompt_safety_guardrails` ✅
- `test_repair_crm_configuration` ✅
- `test_generate_scaffold_config` ✅

**Baseline Count:** Expected ~420+ passing tests (full run not completed in time)

---

## DATABASE SCHEMA STATE

### Records Table Structure

**File:** `backend/app/database.py`

**Schema Columns (inferred from repository code):**
```
id (UUID)                    — Primary key
crm_id (UUID)               — Foreign key to crms table
entity_name (str)            — Entity type (lead, patient, customer, ticket, etc.)
data (JSONB)                 — Dynamic record data per CRM schema
source (str, optional)       — Origin tag (Manual, Inbound, Direct, etc.)
owner_id (UUID, optional)    — Owner for authorization
created_at (timestamp)       — Creation time
updated_at (timestamp)       — Last update time
deleted_at (timestamp)       — Soft-delete marker
```

**CRM Configuration Table Structure:**

**File:** `backend/app/database.py` and `backend/app/schemas/crm.py`

**Schema Columns:**
```
id (UUID)                    — Primary key
owner_id (UUID)              — Owner/tenant
name (str)                   — CRM name (max 120 chars)
industry (str)               — Industry tag (max 80 chars)
status (str)                 — "active" or "archived"
configuration (JSONB)        — Serialized CRMConfiguration
configuration_version (int)  — Tracks schema changes
created_at (timestamp)
updated_at (timestamp)
```

**CRM Configuration Schema (Pydantic):**

**File:** `backend/app/schemas/crm.py`, lines 176–188:

```python
class CRMConfiguration(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    name: str = Field(min_length=1, max_length=120)
    industry: str = Field(min_length=1, max_length=80)
    entities: list[CRMEntity] = Field(min_length=1, max_length=30)
    pipeline_stages: list[str] = Field(default_factory=list, max_length=30)
```

**CRM Entity Schema:**

**File:** `backend/app/schemas/crm.py`, lines 144–159:

```python
class CRMEntity(StrictModel):
    name: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=100)
    fields: list[CRMField] = Field(min_length=1, max_length=100)
```

**CRM Field Schema:**

**File:** `backend/app/schemas/crm.py`, lines 128–142:

```python
class CRMField(StrictModel):
    name: str
    label: str = Field(min_length=1, max_length=100)
    type: FieldType  # Literal[text, email, number, select, etc.]
    required: bool = False
    options: list[str] | None = None
```

---

## FRONTEND BUILD STATUS

**React/TypeScript Stack:** Vite + React 18 + TypeScript

**Key Files:**
- `frontend/src/features/records/RecordFormModal.tsx` — Form component (violation C1)
- `frontend/src/features/analytics/AnalyticsPage.tsx` — Analytics dashboard
- `frontend/src/context/CRMContext.tsx` — CRM state management (activeCRM)
- `frontend/src/services/api.ts` — API client
- `frontend/src/types/crm.ts` — TypeScript types

**Frontend can be built** (no blocking errors detected in code review)

**Note:** Frontend depends on backend `/api/v1/crm/{crm_id}/analytics` returning `AnalyticsData` schema. Until C2 is fixed, analytics rendering will fail or show zero data for non-sales CRMs.

---

## ARCHITECTURE ENTRY POINTS

### CRM Generation Flow
```
POST /api/v1/crm/generate
  → routers/generation.py::generate_crm()
  → ai_provider.generate_crm_config(prompt)
  → [If Mock] MockAIProvider.generate_crm_config()
    → detect_industry(prompt)  ← C5 violations start here
    → INDUSTRY_TAXONOMIES lookup
    → repair_crm_configuration(raw, prompt)
  → CRMConfiguration validated
  → saved to DB
```

### Analytics Flow
```
GET /api/v1/crm/{crm_id}/analytics
  → routers/workflows.py::get_analytics()
  → config = CRMConfiguration(**crm["configuration"])
  → primary_entity = config.entities[0].name  ← C4 fallback here
  → find stage_field, numeric fields, select fields
  → compute by_stage, by_source, numeric_metrics
  → return AnalyticsData (schema has C2 violations)
```

### Evolution Proposal Flow
```
POST /api/v1/crm/{crm_id}/evolution/proposals
  → routers/evolution.py::create_proposal()
  → primary_entity = config.entities[0].name if config.entities else "lead"  ← C4
  → won_stages = {"Won", "won", "Closed Won", "closed_won"}  ← C3
  → analytics_data computed with hard-coded won_stages
  → provider.generate_evolution_proposal(objective, config, analytics_data)
  → proposal created with false analytics
```

### Record Creation Flow
```
POST /api/v1/crm/{crm_id}/records/{entity_name}
  → API validates data against CRM schema
  → record created in DB
  → User navigates to Records page

GET /api/v1/crm/{crm_id}/records/{entity_name}
  → records fetched and displayed
  → Form modal opens: RecordFormModal.tsx
    → entity.fields iterated
    → for status field: renderFieldInput() called
      → statusOptions = field.options OR pipeline_stages
      → if both empty: ['New', 'Active', 'Completed']  ← C1
```

---

## KEY FINDINGS & ASSUMPTIONS

### What the Code Currently Does (Correct):
- ✅ Stores CRM configuration as JSONB in DB
- ✅ Validates configuration with Pydantic schemas
- ✅ Records table supports arbitrary entity types and JSONB data
- ✅ Field types include generic types (text, email, select, number, etc.)
- ✅ Pipeline stages are configurable per CRM
- ✅ Mock provider generates basic configs

### What the Code Does Wrong (Violations):
- ❌ C1: Form defaults to sales stages when none configured
- ❌ C2: Analytics schema hard-coded to sales metrics
- ❌ C3: Won-stage detection assumes sales stage names
- ❌ C4: Entity fallback assumes "lead" exists
- ❌ C5: Only 4 industry types supported without code changes

### Assumptions Made During Inspection:
1. **Database Records Table:** Assumes JSONB `data` column exists and can store any CRM entity's fields. ✅ Confirmed in code.
2. **Configuration Persistence:** Assumes CRM configuration is saved as JSONB and retrieved reliably. ✅ Confirmed in database.py.
3. **Primary Entity:** Assumes first entity in configuration is "primary". ✅ Confirmed in workflows.py and evolution.py.
4. **Pipeline Stages:** Assumes pipeline_stages are generic strings, not tied to entity type. ✅ Confirmed in schema.
5. **No RLS Enforcement:** Service-role client bypasses RLS; ownership enforced at application layer. ✅ Confirmed in database.py comment.

---

## BLOCKERS & MISSING DEPENDENCIES

### Build & Test Prerequisites
- Python 3.13+ ✅ Available (confirmed: pytest collected 423 items)
- PostgreSQL + Supabase ✅ Available (DB queries working)
- Node.js / npm for frontend ✅ Assumed available (Vite project structure)

### No Critical Blockers Found
All five violations are fixable with code changes only. No schema migrations required. No external service changes needed.

### Test Coverage for C1–C5
**Currently Missing:**
- No test for C1: Form status fallback behavior
- No test for C2: Analytics schema cross-CRM types
- No test for C3: Won-stage detection with non-standard stage names
- No test for C4: Entity fallback behavior
- No test for C5: Industry taxonomy removal

**Regression tests must be added** to prevent re-introduction.

---

## SUMMARY OF VIOLATIONS MAPPED TO CODE

| C# | Violation | File | Line(s) | Root Cause | Fix Complexity |
|----|-----------|------|---------|-----------|----------------|
| C1 | Form status default | RecordFormModal.tsx | 175–176 | Hard-coded fallback list | Low: 1 component, simple logic |
| C2 | Analytics schema | crm.py | 248–255 | Pydantic model assumes sales metrics | High: Schema + backend + frontend change |
| C3 | Won_stages list | evolution.py | 93–98 | Hard-coded set of stage names | Medium: Remove hard-coded logic, use config |
| C4 | Entity fallback | evolution.py | 84 | Falls back to "lead" string | Low: 1 line fix + validation |
| C5 | Industry taxonomies | laya_system1.py | 76–121 | Pre-built CRM types baked in code | High: Refactor generation logic |

---

## NEXT STEPS (PHASE 1 IMPLEMENTATION)

1. **Create feature branch** for Phase 1 fixes
2. **Fix violations in order:** C4 → C1 → C3 → C2 → C5 (dependency order)
3. **Add regression tests** for each violation
4. **Validate against 5 CRM types:** E-commerce, Support, Recruitment, Export, Custom
5. **Run full test suite** and verify no regressions
6. **Review and merge**

---

**Report Generated:** 2024  
**Status:** Ready for implementation planning  
**Recommendation:** Proceed to Phase 1 implementation
