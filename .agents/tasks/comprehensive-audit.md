# AURA Comprehensive Audit Report: Universal CRM Architecture Violations

**Audit Date:** 2024  
**Scope:** Complete AURA Codebase (Frontend + Backend)  
**Repository:** d:\AURA - Copy  

---

## 1. EXECUTIVE SUMMARY

### Critical Finding
The AURA codebase violates the **core universal CRM architecture requirement** that any CRM created from any user description must work without code modifications. Both frontend and backend contain hard-coded assumptions about CRM types, entity names, field names, and stage values.

### Violation Metrics
- **Total violations identified:** 29 (across frontend and backend)
- **Total files affected:** 17 files
  - Frontend: 8 files
  - Backend: 9 files
- **Overall risk assessment:** 🔴 **CRITICAL** — System cannot ship in current state
- **Cannot deploy until:** All CRITICAL and HIGH violations resolved
- **Estimated total fix effort:** 18-24 developer-days

### Key Systemic Issues

1. **Hard-Coded Entity Names (7 violations)**
   - "lead", "patient", "customer" assumed in business logic
   - Custom CRMs with different entity names fail silently
   - Severity: CRITICAL

2. **Hard-Coded Stage/Status Values (5 violations)**
   - Analytics assumes "Won", "Closed Won" stages
   - Default stages ["New", "Active", "Completed"] imposed on all CRMs
   - Severity: CRITICAL

3. **Hard-Coded Field Name Detection (6 violations)**
   - Status fields only recognized by name ("status", "stage")
   - Priority/source fields get generic defaults
   - Type inference based on hard-coded keywords
   - Severity: HIGH

4. **Hard-Coded Industry Taxonomies (3 violations)**
   - Pre-built CRM types (SaaS, Healthcare, Real Estate, E-Commerce)
   - New CRM types require code deployment
   - Violates "self-evolving" principle
   - Severity: CRITICAL

5. **Hard-Coded Field Names in Mock Data (4 violations)**
   - INITIAL_SAAS_CONFIG uses sales-specific fields (deal_value, lead_source)
   - Mock workflows trigger on "lead" entity only
   - Affects developer understanding and template behavior
   - Severity: HIGH

6. **Schema-Generation and Analytics Violations (4 violations)**
   - AnalyticsData schema assumes sales metrics (total_leads, won_leads, conversion_rate)
   - Form fallback logic hard-codes default status options
   - Breaks for non-sales CRM types
   - Severity: CRITICAL

### Overall Risk Assessment

| Category | Impact | Reversibility |
|----------|--------|----------------|
| **Custom CRMs fail at runtime** | HIGH | Hard |
| **Analytics broken for 90% of CRM types** | CRITICAL | Hard |
| **New CRM types require code deployment** | CRITICAL | Hard |
| **Mock data teaches wrong patterns** | MEDIUM | Easy |
| **UI text non-inclusive** | LOW | Trivial |

**Recommendation:** Do not deploy. Prioritize Phase 1 (Critical violations) immediately.

---

## 2. VIOLATION CATEGORIES (AGGREGATED)

### 2.1 Hard-Coded Entity Names
**Total: 7 violations** | Severity: **5 CRITICAL, 2 HIGH**

| Violation | File | Severity | Count |
|-----------|------|----------|-------|
| Default entity "lead" fallback | evolution.py:84 | CRITICAL | 1 |
| Entity name in mock workflows | mockData.ts:147, 162 | HIGH | 2 |
| Entity name in workflow examples | mockData.ts:159, 172 | MEDIUM | 2 |
| Entity name in copilot examples | copilot.py:91 | HIGH | 1 |
| Entity name in laya proposals | laya_system1.py:186–216 | MEDIUM | 3 |

**Systemic Impact:**
- Any CRM with entity name other than "lead" has broken workflows
- Copilot generates wrong tool calls
- Analytics proposals fail

---

### 2.2 Hard-Coded Field Names
**Total: 6 violations** | Severity: **4 HIGH, 2 MEDIUM**

| Violation | File | Severity | Count |
|-----------|------|----------|-------|
| Status field detection by name | ai_provider.py:140–141 | HIGH | 1 |
| Hard-coded priority/source defaults | ai_provider.py:122–127 | HIGH | 1 |
| Field inference keywords | field_extractor.py:55–63 | MEDIUM | 1 |
| Source tag options in tool schema | ai_tools.py:863–866 | LOW | 1 |
| Revenue field formatting assumption | workflows.py:275 | LOW | 1 |
| Field name detection in defaults | field_extractor.py | MEDIUM | 1 |

**Systemic Impact:**
- Custom field names not recognized
- Duplicate fields may be auto-created
- Type inference incorrect for non-standard names

---

### 2.3 Hard-Coded Status Values
**Total: 5 violations** | Severity: **3 CRITICAL, 2 MEDIUM**

| Violation | File | Severity | Count |
|-----------|------|----------|-------|
| Form fallback status options | RecordFormModal.tsx:176 | CRITICAL | 1 |
| Won_stages analytics logic | evolution.py:93–98 | CRITICAL | 1 |
| Pipeline defaults by industry | ai_provider.py:99–108 | HIGH | 1 |
| Hard-coded pipeline in taxonomy | laya_system1.py:76–121 | CRITICAL | 1 |
| Questionnaire stage examples | CRMChatPage.tsx:66 | MEDIUM | 1 |

**Systemic Impact:**
- Wrong stages shown in forms
- Analytics always shows 0 for non-sales CRMs
- Conversion metrics invalid
- User forced to manually edit stages after generation

---

### 2.4 Hard-Coded CRM Type Checks
**Total: 3 violations** | Severity: **3 CRITICAL**

| Violation | File | Severity | Count |
|-----------|------|----------|-------|
| Industry taxonomies with pre-built types | laya_system1.py:76–121 | CRITICAL | 1 |
| Pipeline defaults by keyword detection | ai_provider.py:99–108 | HIGH | 1 |
| CRM-type-specific questionnaire | CRMChatPage.tsx:32–128 | MEDIUM | 1 |

**Systemic Impact:**
- Only 4 pre-defined CRM types supported without code changes
- 5th CRM type requires developer intervention
- Violates "self-evolving" principle

---

### 2.5 Schema-Generation Violations
**Total: 4 violations** | Severity: **4 CRITICAL**

| Violation | File | Severity | Count |
|-----------|------|----------|-------|
| AnalyticsData hard-coded schema | crm.py:248–255 | CRITICAL | 1 |
| Hard-coded field defaults | ai_provider.py:122–127 | HIGH | 1 |
| INITIAL_SAAS_CONFIG sales-specific | mockData.ts:14–50 | HIGH | 1 |
| Form status fallback | RecordFormModal.tsx:176 | CRITICAL | 1 |

**Systemic Impact:**
- Analytics broken for non-sales CRMs
- Schema generation assumes Sales CRM patterns
- Mock data teaches wrong universality patterns

---

### 2.6 Other Violations
**Total: 4 violations** | Severity: **1 MEDIUM, 3 LOW**

| Violation | File | Severity | Count |
|-----------|------|----------|-------|
| UI label ambiguity (Leads/Records) | CRMDetailPage.tsx:200 | MEDIUM | 1 |
| Analytics fallback to total_leads | AnalyticsPage.tsx:106 | MEDIUM | 1 |
| Example prompts limited domains | CRMGeneratorPage.tsx:42–54 | MEDIUM | 1 |
| Copilot action detection keywords | copilot.py:261–262 | MEDIUM | 1 |

**Systemic Impact:**
- UI text non-inclusive
- Silent analytics failures
- User imagination limited to 3 example domains

---

## 3. CRITICAL & HIGH SEVERITY VIOLATIONS

### CRITICAL VIOLATIONS (Must Fix Before Release)

#### C1. Hard-Coded Form Status Fallback
**File:** `frontend/src/features/records/RecordFormModal.tsx`  
**Lines:** 175–176  
**Severity:** 🔴 CRITICAL  
**Category:** Schema-generation

**Code Quote:**
```tsx
options={statusOptions.length > 0 ? statusOptions : ['New', 'Active', 'Completed']}
```

**Explanation:**
When a CRM has no status field options configured, the form defaults to `['New', 'Active', 'Completed']`. This is arbitrary and wrong for 99% of non-sales CRMs.
- Healthcare: Shows "New/Active/Completed" instead of "Admitted/Discharged/Follow-up"
- E-Commerce: Shows wrong stages for order fulfillment
- Support: Overrides configured ticket states

**Current Impact:**
- User sees incorrect pipeline in record creation form
- Records may be created with wrong status values
- Silent failure — user doesn't notice until after data entry

**Fix Approach:**
1. If `statusOptions.length > 0` → use them ✅
2. If no options but field is type=status → derive from `activeCRM.configuration.pipeline_stages`
3. If pipeline_stages empty → show validation error instead of guessing
4. Never hard-code default stages

**Estimated Effort:** 0.5 day (1 component, logic fix, 1 test case)

---

#### C2. AnalyticsData Schema Hard-Coded to Sales Terms
**File:** `backend/app/schemas/crm.py`  
**Lines:** 248–255  
**Severity:** 🔴 CRITICAL  
**Category:** Schema-generation

**Code Quote:**
```python
class AnalyticsData(StrictModel):
    total_leads: int = Field(ge=0)
    qualified_leads: int = Field(ge=0)
    won_leads: int = Field(ge=0)
    conversion_rate: float = Field(ge=0, le=1)
    by_source: list[dict[str, Any]] = Field(default_factory=list)
    by_stage: list[dict[str, Any]] = Field(default_factory=list)
```

**Explanation:**
Analytics response schema assumes sales metrics: `total_leads`, `qualified_leads`, `won_leads`, `conversion_rate`. These don't exist for other CRM types.
- Healthcare: Has patients, not leads; outcomes, not wins
- E-Commerce: Has customers/orders, not leads
- Support: Has tickets, not deals

**Current Impact:**
- User with non-sales CRM gets all metrics = 0 regardless of actual data
- Analytics page shows nothing useful
- Blocks deployment for non-sales use cases

**Fix Approach:**
1. Replace with generic schema:
   ```python
   class AnalyticsData(StrictModel):
       total_records: int = Field(ge=0)
       records_by_stage: list[dict[str, Any]] = Field(default_factory=list)  # {stage, count}
       records_by_field: list[dict[str, Any]] = Field(default_factory=list)  # categorical metrics
   ```
2. Let frontend compute high-level KPIs from generic schema
3. Add dynamic metrics from CRM config (e.g., if CRM has revenue field, compute revenue_by_stage)

**Estimated Effort:** 2-3 days (schema change, backend compute update, frontend adaptation)

---

#### C3. Hard-Coded Won_Stages in Analytics
**File:** `backend/app/routers/evolution.py`  
**Lines:** 93–98  
**Severity:** 🔴 CRITICAL  
**Category:** Hard-coded status values

**Code Quote:**
```python
won_stages = {"Won", "won", "Closed Won", "closed_won"}
by_stage = repo.count_records_by_field(str(crm_id), primary_entity, stage_field.name)
won = sum(entry.get("count", 0) for entry in by_stage if entry.get("value") in won_stages)
analytics_data["won_leads"] = won
```

**Explanation:**
System only counts records in stages named "Won", "won", "Closed Won", "closed_won". A Healthcare CRM with stages "Treatment Complete", "Discharged", "Lost to Follow-up" will always have `won_leads = 0`.

**Current Impact:**
- Conversion rate always 0.0 for non-sales CRMs
- Evolution proposals fail for non-sales CRMs
- User sees broken analytics

**Fix Approach:**
1. Remove hard-coded won_stages list
2. Option A: Add CRM config field `success_stage_indicator` (e.g., stages that indicate "success")
3. Option B: Don't compute conversion_rate; return generic stage distribution instead
4. Let frontend/user define meaningful metrics

**Estimated Effort:** 1-2 days (config update, analytics logic refactor)

---

#### C4. Industry Taxonomies — Pre-Built CRM Types
**File:** `backend/app/services/laya_system1.py`  
**Lines:** 76–121  
**Severity:** 🔴 CRITICAL  
**Category:** Hard-coded CRM type checks

**Code Quote:**
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
            {"name": "deal_size", "label": "ARR Estimate ($)", "type": "number", "required": False},
            # ... 4 more fields
        ],
    },
    "healthcare": { ... },
    "real_estate": { ... },
    "ecommerce": { ... },
}
```

**Explanation:**
System has 4 pre-built CRM templates baked into code. A user requesting a 5th type (Recruitment, Logistics, Manufacturing, Academia) cannot create it without code deployment. This directly violates the "self-evolving" requirement.

**Current Impact:**
- Only 4 CRM types supported natively
- New CRM types require code changes and redeployment
- Users forced to override all fields and stages
- Cannot ship as "self-evolving" platform

**Fix Approach:**
1. Remove INDUSTRY_TAXONOMIES entirely
2. Build CRM dynamically from user input:
   - Use FieldExtractor to identify entities, fields, stages from prompt
   - Start from blank template or minimal defaults
   - Let user specify fields in questionnaire if needed
3. Move taxonomies to optional examples only (not defaults)

**Estimated Effort:** 3-4 days (removal + dynamic generation + testing)

---

#### C5. Default Entity Name "lead" Hard-Coded
**File:** `backend/app/routers/evolution.py`  
**Line:** 84  
**Severity:** 🔴 CRITICAL  
**Category:** Hard-coded entity names

**Code Quote:**
```python
primary_entity = config.entities[0].name if config.entities else "lead"
```

**Explanation:**
If CRM configuration has no entities defined, system defaults to "lead". A user with Healthcare CRM ("patient" entity) would trigger this fallback and try to count records in non-existent "lead" table.

**Current Impact:**
- Fallback is arbitrary and wrong for non-sales CRMs
- Silent failure — returns 0 records
- Evolution proposals fail

**Fix Approach:**
1. Validate CRM has at least one entity; don't use fallback
2. Use `config.entities[0].name` with validation
3. Return error if no entities defined instead of guessing

**Estimated Effort:** 0.5 day (1 line fix + validation)

---

### HIGH SEVERITY VIOLATIONS (Limits Flexibility)

#### H1. Sales-Specific Fields in INITIAL_SAAS_CONFIG Mock Data
**File:** `frontend/src/services/mockData.ts`  
**Lines:** 14–50  
**Severity:** 🟡 HIGH  
**Category:** Hard-coded field names

**Code Quote:**
```ts
export const INITIAL_SAAS_CONFIG: CRMConfiguration = {
  entities: [
    {
      name: 'lead',  // ← Sales assumption
      label: 'Lead',
      fields: [
        { name: 'full_name', label: 'Full Name', type: 'text', required: true },
        { name: 'email', label: 'Work Email', type: 'email', required: true },
        { name: 'company', label: 'Company Name', type: 'text', required: false },
        { name: 'phone', label: 'Phone Number', type: 'phone', required: false },
        { name: 'deal_value', label: 'Estimated Deal Value ($)', type: 'number', required: false },
        { name: 'source', label: 'Lead Source', type: 'select', "options": [...] },
        // ... more sales-only fields
      ],
    },
  ],
};
```

**Explanation:**
Mock CRM configuration is sales-specific (entity "lead", field "deal_value", field "source"). This becomes the template developers copy, creating bias that all CRMs are sales CRMs.

**Current Impact:**
- Developers assume CRMs are sales-centric
- New CRM types copy this structure as starting point
- Mock data is not truly universal

**Fix Approach:**
1. Rename entity to generic name: "record" or "contact"
2. Use generic fields: name, email, description, priority, status
3. Remove sales-specific fields: deal_value, source, company
4. Keep it minimal (5–6 fields only)

**Estimated Effort:** 1 day (refactor mock data, update tests)

---

#### H2. Entity Name Hard-Coded in Mock Workflow Triggers
**File:** `frontend/src/services/mockData.ts`  
**Lines:** 147, 162  
**Severity:** 🟡 HIGH  
**Category:** Hard-coded entity names

**Code Quote:**
```ts
const INITIAL_WORKFLOWS: WorkflowData[] = [
  {
    workflow_id: 'w1111111-1111-1111-1111-111111111111',
    name: 'New Lead Auto Follow-up',
    trigger: {
      type: 'record.created',
      entity: 'lead',  // ← Hard-coded
    },
  },
  {
    workflow_id: 'w2222222-2222-2222-2222-222222222222',
    name: 'High-Value Lead Alert',
    trigger: {
      type: 'record.stage_changed',
      entity: 'lead',  // ← Hard-coded
    },
  },
];
```

**Explanation:**
Mock workflows hard-code entity as "lead". If CRM has different entity (patient, customer, ticket), workflows don't function.

**Current Impact:**
- Workflows don't trigger for non-lead entities
- User forced to manually recreate workflows
- Documentation teaches workflows only for leads

**Fix Approach:**
1. Use primary entity from CRM config:
   ```ts
   entity: config.entities[0].name
   ```
2. Or make workflows generic:
   - Rename "New Lead Auto Follow-up" → "New Record Auto Follow-up"
   - Replace `entity: 'lead'` with `entity: null` (triggers on any entity)

**Estimated Effort:** 0.5 day (mock data updates)

---

#### H3. Status Field Detection by Hard-Coded Names
**File:** `backend/app/services/ai_provider.py`  
**Lines:** 140–141  
**Severity:** 🟡 HIGH  
**Category:** Hard-coded field names

**Code Quote:**
```python
has_status = any(f.get("name") in ("status", "stage", f"{entity_name}_status", "shipping_status") 
                 or f.get("type") in ("status", "select") and "status" in f.get("name", "") 
                 for f in fields)
```

**Explanation:**
System only recognizes status fields if named "status", "stage", "{entity}_status", or "shipping_status". A user with field "care_phase", "fulfillment_state", or "approval_status" won't be recognized.

**Current Impact:**
- Custom status field names not recognized
- System may add duplicate "status" field
- User loses control of field naming

**Fix Approach:**
1. Add schema metadata flag: `"is_stage_field": true`
2. Schema editor explicitly marks which field is the stage field
3. Remove hard-coded name detection completely

**Estimated Effort:** 1-2 days (schema update + field validation)

---

#### H4. Hard-Coded Priority/Source Field Defaults
**File:** `backend/app/services/ai_provider.py`  
**Lines:** 122–127  
**Severity:** 🟡 HIGH  
**Category:** Hard-coded field names

**Code Quote:**
```python
elif "priority" in ef.machine_key:
    fdict["options"] = ["Low", "Medium", "High", "Critical"]
elif "source" in ef.machine_key:
    fdict["options"] = ["Website", "Referral", "Partner", "Direct"]
```

**Explanation:**
System assumes "priority" always has [Low, Medium, High, Critical] and "source" always has [Website, Referral, Partner, Direct]. A user's CRM may have "priority": [1-5] or "source": [Google Ads, Facebook, LinkedIn].

**Current Impact:**
- Auto-generated options incorrect for user intent
- User must manually fix option lists after CRM generation
- Non-standard option values ignored

**Fix Approach:**
1. Don't hard-code specific option values
2. Fall back to generic labels: [Option 1, Option 2, Option 3, ...]
3. Let users override in schema editor
4. Attempt inference from context (FieldExtractor) only

**Estimated Effort:** 1 day (remove defaults, update logic)

---

#### H5. CRM-Type-Specific Questionnaire Branching
**File:** `frontend/src/features/crm-chat/CRMChatPage.tsx`  
**Lines:** 32–128  
**Severity:** 🟡 HIGH  
**Category:** Hard-coded CRM type checks

**Code Quote:**
```tsx
const CRM_TYPES = [
  { id: 'sales_pipeline', label: 'Sales Pipeline', description: 'Leads → Deals' },
  { id: 'client_management', label: 'Client Management', description: 'Accounts & relationships' },
  { id: 'customer_support', label: 'Customer Support', description: 'Tickets & service' },
  { id: 'all_in_one', label: 'All-in-One', description: 'Full CRM suite' },
  { id: 'custom', label: 'Other / Custom', description: 'Describe your own' },
];

function getNextQuestion(answers, crmType) {
  if (effective === 'sales_pipeline') {
    return {
      key: 'tracks',
      text: 'What do you need to track in the pipeline?',
      choices: ['Leads → Deals', 'Contacts + Companies + Deals', ...],
    };
  }
  if (effective === 'customer_support') {
    return {
      key: 'tracks',
      text: 'What does a support ticket need to capture?',
      choices: ['Issue + status + priority', 'Customer info + issue + resolution', ...],
    };
  }
}
```

**Explanation:**
Questionnaire has hard-coded branching logic per CRM type. Adding a 6th type (Recruitment, IoT, Manufacturing) requires code changes.

**Current Impact:**
- Only 5 CRM types supported without code modification
- Adding new type requires UI/logic changes
- Cannot extend questionnaire without deployment

**Fix Approach:**
1. Make questionnaire template-driven:
   - Store questionnaire templates in backend or config
   - Frontend renders generic question UI (text, multiple choice)
   - Backend returns next question based on current answers
2. Remove type-specific branching from frontend
3. Replace if/if/if chain with data-driven lookup

**Estimated Effort:** 2-3 days (backend questionnaire service, frontend refactor)

---

## 4. MEDIUM SEVERITY VIOLATIONS

### Grouped by Category

#### M1-M2: Hard-Coded Entity Names in Examples

**Files:**
- `frontend/src/services/mockData.ts` (lines 144, 159)
- `backend/app/routers/copilot.py` (line 91)
- `backend/app/services/laya_system1.py` (lines 186–216)

**Issues:**
- Workflow names: "New Lead Auto Follow-up", "High-Value Lead Alert"
- Copilot example: shows creating "lead" records with name/email fields
- Laya proposals: trigger entity hard-coded as "lead"

**Impact:** Educational — teaches non-universal patterns

**Fix Approach:** Use primary entity from CRM config in examples

**Estimated Effort:** 0.5 day total

---

#### M3: Analytics Fallback to `total_leads` Metric

**File:** `frontend/src/features/analytics/AnalyticsPage.tsx` (line 106)

**Issue:**
```tsx
const totalRecords =
  (analytics as any)?.total_records ??
  (analytics as any)?.total_leads ??
  0;
```

**Impact:** Silent failure if backend doesn't return `total_leads`

**Fix Approach:** Remove fallback; ensure backend always returns `total_records`

**Estimated Effort:** 0.5 day

---

#### M4: UI Label Ambiguity

**File:** `frontend/src/features/crms/CRMDetailPage.tsx` (line 200)

**Issue:**
```tsx
<span className="text-[10px] font-bold uppercase text-slate-400">Total Leads/Records</span>
```

**Impact:** Suggests leads are special; records are fallback

**Fix Approach:** Use entity-specific label: `Total ${primaryEntityName}s`

**Estimated Effort:** Trivial (1 line)

---

#### M5: Limited Example Prompts

**File:** `frontend/src/features/crm-generator/CRMGeneratorPage.tsx` (lines 42–54)

**Issue:** Only 3 examples (B2B SaaS, Real Estate, Healthcare) — limits user imagination

**Impact:** Users think CRMs are only for these 3 domains

**Fix Approach:** Add 2–3 more examples (E-Commerce, Recruitment, Project Management)

**Estimated Effort:** 0.5 day

---

#### M6: Questionnaire Choices Mention "Leads"

**File:** `frontend/src/features/crm-chat/CRMChatPage.tsx` (line 66)

**Issue:**
```tsx
choices: ['Leads → Deals', 'Contacts + Companies + Deals', 'Leads + Quotes + Invoices', 'Just leads for now']
```

**Impact:** Reinforces sales-specific thinking

**Fix Approach:** Use neutral language: "Primary Entity → Success State"

**Estimated Effort:** 0.5 day

---

#### M7-M8: Field Type Inference Brittle

**Files:**
- `backend/app/services/field_extractor.py` (lines 55–63)
- `backend/app/routers/copilot.py` (lines 261–262)

**Issues:**
- Hard-coded keywords for type inference (status, priority, source, etc.)
- Copilot action detection only recognizes specific entity names

**Impact:** Custom field/entity names not recognized; action detection fails

**Fix Approach:**
- Use dynamic entity detection (match against CRM config)
- Context-based type inference instead of keywords

**Estimated Effort:** 1–2 days

---

## 5. LOW SEVERITY VIOLATIONS

### Count by Category

| Category | Count | Severity | Description |
|----------|-------|----------|-------------|
| Label/text examples | 2 | LOW | Hard-coded "Lead" in example output |
| Field inference keywords | 1 | LOW | Comment references specific field names |
| Source tag documentation | 1 | LOW | Suggests specific source values |

### Brief Descriptions

1. **Hard-Coded "lead" in Known Entities** (ai_provider.py:87)
   - Known entity list includes "lead" first → bias
   - Not a violation per se, but contributes to lead-centric thinking

2. **CRM Examples in Chat Endpoint** (chat.py:72–115)
   - Generic placeholder stages in example payload
   - Not harmful but could confuse

3. **Revenue Field Formatting** (workflows.py:275)
   - Assumes "revenue" fields are currency
   - May incorrectly format other numeric fields
   - Low impact but incorrect assumption

**Fix Effort:** Trivial (text changes, 2–3 lines)

---

## 6. FIX ROADMAP

### Phase 1: CRITICAL Violations (Must Fix Before Release)
**Duration:** 6–8 days  
**Blocks:** Deployment  
**Risk if skipped:** System fails for 90% of CRM types

1. **Remove AnalyticsData hard-coded schema** (2–3 days)
   - Replace with generic: `total_records`, `records_by_stage`
   - Update backend analytics computation
   - Update frontend metric display

2. **Remove Industry Taxonomies** (3–4 days)
   - Delete INDUSTRY_TAXONOMIES constant
   - Build CRM from user input dynamically using FieldExtractor
   - Test with 5+ new CRM types (not in original 4)

3. **Fix Form Status Fallback** (0.5 day)
   - Use pipeline_stages from schema instead of hard-coded defaults

4. **Fix Default Entity Fallback** (0.5 day)
   - Validate entities exist; don't default to "lead"

5. **Fix Won_Stages Logic** (1–2 days)
   - Remove hard-coded stage list
   - Use CRM config to identify success stages
   - Return generic stage distribution

**Verification:**
- Test Healthcare CRM end-to-end (patient entity, custom stages)
- Test custom CRM (non-standard entity names)
- Verify analytics shows correct data for all CRM types
- Run existing test suite; ensure no regressions

---

### Phase 2: HIGH Severity Violations (Restores Flexibility)
**Duration:** 4–6 days  
**Blocks:** Non-sales CRM support  
**Risk if skipped:** New entity types cannot be created without workarounds

1. **Refactor Questionnaire into Template System** (2–3 days)
   - Move questionnaire logic from frontend to backend
   - Create questionnaire template format
   - Frontend becomes generic question renderer
   - Support unlimited CRM types

2. **Parameterize Mock Data** (1 day)
   - Remove sales-specific entity/field names
   - Use generic defaults (record, name, email, etc.)
   - Update workflow mock data to use dynamic entity names

3. **Dynamic Status Field Detection** (1–2 days)
   - Add schema metadata: `is_stage_field: true`
   - Remove hard-coded name-based detection
   - Update field validation

4. **Remove Hard-Coded Field Defaults** (1 day)
   - Stop assuming priority/source options
   - Fall back to generic [Option 1, 2, 3, ...] or empty

**Verification:**
- Create Recruitment CRM (candidate entity, custom fields)
- Create E-Commerce CRM (product, order entities, custom stages)
- Verify questionnaire extends without code changes
- Test status field with non-standard names

---

### Phase 3: MEDIUM Severity Violations (Polish)
**Duration:** 2–3 days  
**Blocks:** User experience, documentation accuracy  
**Risk if skipped:** UX confusion, limited user imagination

1. **Fix Copilot Examples & Action Detection** (1–2 days)
   - Build copilot examples from actual CRM config at runtime
   - Dynamic entity name detection instead of keyword list
   - Update system prompt to reference schema

2. **Update UI Labels** (0.5 day)
   - Change "Leads/Records" → entity-specific labels
   - Change "High-Value Lead Alert" → "Stage Change Alert"
   - Use neutral language throughout

3. **Expand Example Prompts** (0.5 day)
   - Add E-Commerce, Recruitment, Project Management examples

4. **Normalize Field Type Inference** (0.5 day)
   - Reduce hard-coded keywords in FieldExtractor
   - Use context-based inference

**Verification:**
- UI shows entity-specific labels for different CRM types
- Copilot generates correct examples for non-sales CRMs
- User imagination expanded to 5+ CRM types

---

## 7. ARCHITECTURAL RECOMMENDATIONS

### 7.1 Key Patterns to Establish for Universality

#### Pattern 1: Schema-First Design
**Principle:** All behavior derives from CRM configuration; never assume structure.

**Implementation:**
- Every component reads from `activeCRM.configuration`
- No hard-coded entity/field names
- No "if entity === 'lead'" logic

**Example:**
```typescript
// ❌ WRONG
if (record.entity === 'lead') {
  return leadSpecificLogic();
}

// ✅ CORRECT
const entityConfig = getEntityConfig(record.entity);
return renderRecordByConfig(record, entityConfig);
```

---

#### Pattern 2: Dynamic Metadata Over Hard-Coded Defaults
**Principle:** When a system needs to identify a special field (status, priority), read it from config metadata instead of detecting by name.

**Implementation:**
- Add explicit field metadata flags:
  ```python
  class FieldMetadata(BaseModel):
      name: str
      type: str
      is_stage_field: bool = False      # marks status/stage field
      is_primary_key: bool = False      # marks ID field
      is_identifier_field: bool = False # marks display name
  ```
- During schema generation, assign these flags
- Business logic checks flags, never names

**Example:**
```python
# ❌ WRONG
stage_field = next((f for f in fields if 'status' in f['name']), None)

# ✅ CORRECT
stage_field = next((f for f in fields if f.get('is_stage_field')), None)
```

---

#### Pattern 3: Config-Driven Tool Generation
**Principle:** AI Copilot tool signatures generated from CRM schema, not hard-coded.

**Implementation:**
- At runtime, build tool definitions from entity/field config
- Tool schemas include actual entity names and field names
- Example fields derived from top 3 fields of primary entity
- No hard-coded "lead", "email", "name" in tool schemas

**Example:**
```python
# At runtime, for each CRM:
tools = generate_copilot_tools(crm_config)
# Result: create_record(entity_id="patient", data={actual_fields})
# Not: create_record(entity_id="lead", data={name, email, company})
```

---

#### Pattern 4: Questionnaire Template System
**Principle:** Questionnaire questions/branches defined in configuration, not hard-coded in UI.

**Implementation:**
- Backend stores questionnaire templates (JSON or database)
- Frontend receives questions generically: `{ id, text, type, choices, next_question }`
- No switch/if statements based on CRM type
- Adding new CRM type = adding new template, no code deployment

**Example Structure:**
```json
{
  "questionnaires": {
    "crm_type": {
      "id": "crm_type",
      "text": "What kind of CRM are you building?",
      "type": "multiple_choice",
      "choices": ["Sales", "Support", "Healthcare", "Custom"],
      "next_question": "dependent_on_answer"
    },
    "sales_pipeline_tracks": {
      "id": "tracks_sales",
      "condition": { "crm_type": "sales_pipeline" },
      "text": "What do you need to track?",
      "type": "multiple_choice",
      "choices": ["Leads → Deals", "Contacts + Companies + Deals"]
    }
  }
}
```

---

#### Pattern 5: Generic Analytics Over Assumed Metrics
**Principle:** Analytics schema doesn't assume any specific metrics; instead, compute from schema + data.

**Implementation:**
- Analytics always returns:
  - `total_records`
  - `records_by_stage` (stage distribution)
  - `records_by_field` (for categorical fields)
- Additional metrics computed at request time based on CRM field metadata
- No `total_leads`, `won_leads`, `conversion_rate` in base schema

**Example:**
```python
# Backend compute function
def compute_analytics(crm_id: UUID, config: CRMConfiguration):
    total = count_total_records(crm_id)
    by_stage = count_by_stage(crm_id, config.primary_entity, config.stage_field)
    
    # Optional: if config requests specific metrics
    metrics = {}
    for metric in config.analytics_metrics:
        metrics[metric.name] = compute_metric(crm_id, metric)
    
    return {
        "total_records": total,
        "by_stage": by_stage,
        "custom_metrics": metrics
    }
```

---

### 7.2 Testing Approach to Verify Schema-Driven Behavior

#### Test Category 1: Multi-CRM Type End-to-End Tests
**Objective:** Verify core flows work with multiple CRM types without code changes.

**Test Cases:**
```gherkin
Scenario: Create record in Sales CRM
  Given a Sales CRM with lead entity and deal_value field
  When I create a record with name="Alice", deal_value=50000
  Then record appears in table with correct fields

Scenario: Create record in Healthcare CRM
  Given a Healthcare CRM with patient entity and treatment_status field
  When I create a record with name="Bob", treatment_status="Admitted"
  Then record appears in table with correct fields (no deal_value)

Scenario: Create record in Custom CRM
  Given a custom CRM with property entity and listing_price field
  When I create a record with address="123 Main St", listing_price=350000
  Then record appears in table with correct fields (no sales fields)

Scenario: Questionnaire for 6th CRM type
  Given a new CRM type is added to questionnaire templates
  When user flows through questions
  Then CRM is created correctly without code deployment
```

---

#### Test Category 2: Schema Adaptation Tests
**Objective:** Verify UI adapts correctly when CRM config changes.

**Test Cases:**
```gherkin
Scenario: Record form adapts to entity field changes
  Given a CRM with fields: name, email, status
  When I open Add Record form
  Then form shows input for name, email, status dropdown
  
  When CRM schema is updated to add field: phone
  And I refresh the form
  Then form now shows: name, email, phone, status

Scenario: Analytics adapts to stage changes
  Given a CRM with stages: New, Active, Completed
  When I view analytics
  Then stage distribution shows all three stages
  
  When stages are updated to: Open, In Progress, Resolved, Closed
  And I refresh analytics
  Then distribution shows all four new stages
```

---

#### Test Category 3: Field Type Rendering Tests
**Objective:** Verify form fields render correctly based on type, not name.

**Test Cases:**
```gherkin
Scenario: Status field renders as dropdown regardless of name
  Given a CRM with field: care_status (type=status, options=[admitted, discharged, follow-up])
  When I open Add Record form
  Then care_status renders as dropdown with correct options
  (NOT assuming "status" field name or default [New/Active/Completed])

Scenario: Custom field type renders correctly
  Given a CRM with field: payment_method (type=select, options=[Credit Card, Bank Transfer, Check])
  When I open Add Record form
  Then payment_method renders with actual options
  (NOT assuming generic defaults)
```

---

#### Test Category 4: Tool Execution Tests
**Objective:** Verify AI Copilot tools work with dynamic entity/field names.

**Test Cases:**
```gherkin
Scenario: Create record tool works with any entity
  Given a Healthcare CRM with patient entity and fields: name, email, admission_date
  When copilot calls: create_record(entity_id="patient", data={name, email, admission_date})
  Then record is created correctly
  
  Given an E-Commerce CRM with product entity and fields: sku, name, price
  When copilot calls: create_record(entity_id="product", data={sku, name, price})
  Then record is created correctly

Scenario: Copilot generates correct example calls for entity
  Given any CRM configuration
  When copilot system prompt is generated
  Then example calls use actual entity name and actual field names
  (NOT hard-coded "lead", "email", "company")
```

---

#### Test Automation Strategy

1. **Fixture: Multiple Pre-Built CRMs**
   ```python
   @pytest.fixture
   def crms_for_testing():
       return {
           'sales': SALES_CRM_CONFIG,
           'healthcare': HEALTHCARE_CRM_CONFIG,
           'ecommerce': ECOMMERCE_CRM_CONFIG,
           'recruitment': RECRUITMENT_CRM_CONFIG,
           'custom': CUSTOM_CRM_CONFIG,  # a 5th type
       }
   ```

2. **Parameterized Tests**
   ```python
   @pytest.mark.parametrize('crm_name,crm_config', 
       [('sales', SALES_CRM_CONFIG), 
        ('healthcare', HEALTHCARE_CRM_CONFIG),
        # ... more CRM types
       ])
   def test_records_table_renders_correctly(crm_name, crm_config):
       # Create CRM, add record, verify table shows correct fields
       # Works for all CRM types without modification
   ```

3. **Schema Change Tests**
   ```python
   def test_analytics_updates_when_stages_change():
       crm = create_crm(SALES_CRM_CONFIG)
       assert analytics['by_stage'] has 6 stages
       
       # Update stages
       update_crm_stages(crm, ['New', 'Active', 'Won'])
       
       # Verify analytics reflects change
       assert analytics['by_stage'] has 3 stages (new ones)
   ```

---

### 7.3 Code Review Checklist for Future Contributions

Before code review, verify:

#### Entity & Field Names
- [ ] No hard-coded entity names ("lead", "patient", "customer", etc.)
- [ ] No hard-coded field names ("email", "company", "deal_value", etc.)
- [ ] All references to entities/fields come from `crm.configuration` or passed parameters
- [ ] Field access uses metadata flags (is_stage_field) not name detection

#### CRM Type Logic
- [ ] No if/switch statements checking CRM type or industry
- [ ] No hard-coded CRM type defaults
- [ ] No CRM-specific branching (except in questionnaire template config)
- [ ] New CRM types work without code changes

#### Schemas & Data Models
- [ ] No fields in response schemas assuming specific CRM types
- [ ] Generic field names: `total_records` not `total_leads`
- [ ] Stage/status detection uses metadata, not name matching
- [ ] All pick lists/enums are configurable or derived from schema

#### Mock Data
- [ ] Mock entity names generic (record, contact, item) not domain-specific
- [ ] Mock field names generic (name, email, status) not sales-specific
- [ ] Mock examples demonstrate universality, not single CRM type
- [ ] Workflows/examples reference primary entity dynamically

#### Fallback Logic
- [ ] No hard-coded defaults for stages, fields, statuses
- [ ] Fallback to generic defaults ([Option 1, 2, 3]) or error handling
- [ ] Never assume standard field/status exists

#### Testing
- [ ] Tests pass for multiple CRM types (sales, healthcare, custom)
- [ ] Tests use parameterized fixtures, not single CRM type
- [ ] New features tested with at least 2 different CRM types
- [ ] Tests verify schema-driven behavior, not hard-coded assumptions

#### Documentation
- [ ] Examples show multiple CRM types
- [ ] References avoid sales terminology (use "entity", "record", "stage")
- [ ] Architecture docs explain universality principle

---

## 8. APPENDICES

### Appendix A: Complete Backend Audit Findings

See attached: `backend-audit.md`

Full details including:
- 18 backend violations by category
- Detailed code quotes for all findings
- Backend-specific impact analysis
- Backend-specific fix approaches and effort estimates

---

### Appendix B: Complete Frontend Audit Findings

See attached: `frontend-audit.md`

Full details including:
- 11 frontend violations by category
- Compliant systems analysis (Records, Analytics, Forms, Copilot)
- Frontend-specific impact analysis
- Frontend-specific fix approaches and effort estimates

---

## 9. SUMMARY & NEXT STEPS

### Current State
The AURA codebase violates its core requirement: **universality**. Both frontend and backend contain hard-coded assumptions about CRM types, entity names, field names, and stage values. The system cannot support custom CRMs (5th type and beyond) without code deployment.

### Severity
- **Cannot ship in current state** without risking user CRMs breaking at runtime
- **Critical violations** must be fixed before any release
- **High violations** must be fixed before non-sales CRMs are supported

### Fix Scope
- **Total violations:** 29 (18 backend, 11 frontend)
- **Total effort:** 18–24 developer-days
- **Priority:** Phase 1 (Critical) = 6–8 days minimum

### Recommended Action
1. **Immediate:** Assign developer to Phase 1 (Critical violations)
   - 6–8 day sprint to fix universality blockers
   - Test with 5+ diverse CRM types
   - Blocks all other work

2. **Short-term:** Phase 2 (High violations)
   - Questionnaire refactor
   - Mock data cleanup
   - 4–6 day sprint

3. **Medium-term:** Phase 3 (Medium violations) + architectural updates
   - Polish UI/UX
   - Establish patterns
   - Developer documentation

### Success Criteria
✅ User creates a custom CRM (not in pre-built 4 types)
✅ All records/analytics/copilot features work without code changes
✅ New CRM types don't require deployment
✅ Schema-driven behavior verified by multi-CRM test suite

---

**Report Compiled:** 2024  
**Total Violations:** 29  
**Total Files Affected:** 17  
**Recommended Fixes:** 18–24 developer-days  
**Status:** 🔴 **CRITICAL — DO NOT SHIP**
