# AURA Frontend Codebase Audit: CRM-Specific Hard-Coding Violations

**Audit Date:** 2024
**Scope:** d:\AURA - Copy\frontend/src (49 TypeScript/TSX files)
**Status:** IDENTIFIED VIOLATIONS REQUIRING IMMEDIATE REMEDIATION

---

## Executive Summary

The AURA frontend codebase demonstrates strong adherence to universal CRM architecture principles in most areas. However, **3 CRITICAL violations** and **5 MEDIUM violations** were identified that directly contradict the requirement for zero CRM-specific hard-coding.

### Key Findings:
- **Records system:** ✅ COMPLIANT — Fully schema-driven table generation
- **Analytics system:** ✅ COMPLIANT — Dynamic KPI cards and metrics from schema
- **AI Assistant:** ✅ COMPLIANT — Tool execution without hard-coded entity names
- **Record form generation:** ✅ COMPLIANT — Field types drive input rendering
- **Mock data & examples:** ⚠️ **VIOLATIONS** — Hard-coded entity fields and example CRMs
- **CRM questionnaire flow:** ⚠️ **VIOLATIONS** — CRM-type-specific branching logic
- **Form fallback logic:** 🔴 **CRITICAL** — Hard-coded default status options

### Violation Distribution by Severity:
- **CRITICAL:** 1 violation (breaks universality)
- **HIGH:** 2 violations (limits flexibility)
- **MEDIUM:** 5 violations (poor practice, architectural debt)
- **LOW:** 3 violations (cosmetic, examples/labels)

---

## File-by-File Findings

### 🔴 CRITICAL VIOLATIONS

#### 1. Hard-Coded Status Fallback in Form Generation

**File:** `frontend/src/features/records/RecordFormModal.tsx`  
**Lines:** 175–176  
**Severity:** CRITICAL

**Problematic Code:**
```tsx
options={statusOptions.length > 0 ? statusOptions : ['New', 'Active', 'Completed']}
```

**Why It Violates Requirements:**
- If a CRM has no status field options defined, the form defaults to `['New', 'Active', 'Completed']`
- These hardcoded stages will appear for ANY CRM that lacks explicit status options
- Breaks Requirement #3 (Universal Entity System) and #6 (Universal Dynamic Record Form)
- Example: A Healthcare CRM with stages like `Admitted → Discharged → Follow-up` would show `New / Active / Completed` instead

**Impact:**
- User sees incorrect pipeline stages in the form
- Record submissions may use wrong status values
- Breaks the principle that schema determines behavior

**Fix Approach:** 
- Replace fallback with schema-driven defaults:
  - If field has options: use them
  - If field is type=status but no options: use `activeCRM.configuration.pipeline_stages`
  - If pipeline_stages is empty: show a validation error instead of guessing
- **Effort:** LOW (1 component, 1 conditional)

---

#### 2. Entity Name in Mock Trigger Logic

**File:** `frontend/src/services/mockData.ts`  
**Lines:** 143–147  
**Severity:** HIGH

**Problematic Code:**
```ts
const INITIAL_WORKFLOWS: WorkflowData[] = [
  {
    workflow_id: 'w1111111-1111-1111-1111-111111111111',
    name: 'New Lead Auto Follow-up',
    status: 'active',
    trigger: {
      type: 'record.created',
      entity: 'lead',  // ← Hard-coded entity name
    },
```

**Why It Violates Requirements:**
- Triggers are hard-coded to entity `'lead'`
- If initialized with a different CRM (e.g., Healthcare with `'patient'` entity), the workflow trigger doesn't match
- Breaks Requirement #3 (Universal Entity System) and #9 (Universal Copilot Intent Handling)

**Impact:**
- Workflows don't function correctly with non-sales CRMs
- Requires code changes to support new entity types

**Fix Approach:**
- Make trigger entity dynamic:
  - Derive from `activeCRM.configuration.entities[0].name`
  - Or parameterize the mock workflow initialization
- **Effort:** MEDIUM (refactor mock data generation to accept entity name parameter)

---

#### 3. Hard-Coded Field Names in Initial CRM Configuration

**File:** `frontend/src/services/mockData.ts`  
**Lines:** 14–50  
**Severity:** HIGH

**Problematic Code:**
```ts
export const INITIAL_SAAS_CONFIG: CRMConfiguration = {
  entities: [
    {
      name: 'lead',
      label: 'Lead',
      fields: [
        { name: 'full_name', label: 'Full Name', type: 'text', required: true },
        { name: 'email', label: 'Work Email', type: 'email', required: true },
        { name: 'company', label: 'Company Name', type: 'text', required: false },
        { name: 'phone', label: 'Phone Number', type: 'phone', required: false },
        // ... more sales-specific fields
        { name: 'deal_value', label: 'Estimated Deal Value ($)', type: 'number', required: false },
```

**Why It Violates Requirements:**
- Entity name is `'lead'` — assumes sales CRM
- Fields are sales-specific: `full_name`, `deal_value`, `source` (Lead Source)
- These fields would be copied as example schema when generating new CRMs
- Breaks Requirement #3 (Universal Entity System) — no assumption about entity names allowed

**Impact:**
- Mock data is not truly universal; it's a Sales CRM template
- New developers think "leads" are a fundamental concept
- Example becomes the de facto standard, creating cognitive bias

**Fix Approach:**
- Remove hard-coded INITIAL_SAAS_CONFIG or make it truly generic:
  - Rename `lead` entity to `record`
  - Use generic fields: `name`, `email`, `description`, `priority`, `status`
  - Remove sales-specific fields like `deal_value`, `source`
- **Effort:** MEDIUM (1 file, 15 line updates, plus test data refresh)

---

### 🟡 HIGH VIOLATIONS

#### 4. CRM-Type-Specific Questionnaire Branching

**File:** `frontend/src/features/crm-chat/CRMChatPage.tsx`  
**Lines:** 32–128  
**Severity:** MEDIUM (architectural debt)

**Problematic Code:**
```tsx
const CRM_TYPES = [
  { id: 'sales_pipeline' as CrmTypeId, label: 'Sales Pipeline', description: 'Leads → Deals' },
  { id: 'client_management' as CrmTypeId, label: 'Client Management', description: 'Accounts & relationships' },
  { id: 'customer_support' as CrmTypeId, label: 'Customer Support', description: 'Tickets & service' },
  { id: 'all_in_one' as CrmTypeId, label: 'All-in-One', description: 'Full CRM suite' },
  { id: 'custom' as CrmTypeId, label: 'Other / Custom', description: 'Describe your own' },
];

function getNextQuestion(answers, crmType) {
  if (effective === 'sales_pipeline') {
    return {
      key: 'tracks',
      text: 'What do you need to track in the pipeline?',
      choices: ['Leads → Deals', 'Contacts + Companies + Deals', 'Leads + Quotes + Invoices', 'Just leads for now'],
    };
  }
  if (effective === 'customer_support') {
    return {
      key: 'tracks',
      text: 'What does a support ticket need to capture?',
      choices: ['Issue + status + priority', 'Customer info + issue + resolution', 'Bug reports + severity + assignee', 'Custom fields'],
    };
  }
```

**Why It Violates Requirements:**
- System pre-defines 5 CRM types and branches logic differently for each
- Questions and answer choices are hard-coded per type
- A 6th CRM type (Recruitment, Healthcare, E-Commerce) requires code changes
- Breaks Requirement #6 (Universal Dynamic Record Form) — questionnaire is not universal

**Impact:**
- Adding a new CRM category requires frontend code modification
- Creates coupling between UI and business logic
- Users with exotic CRM types (IoT sensor tracking, volunteer management) must use "Custom"
- Hard to maintain questionnaire consistency

**Fix Approach:**
- Make questionnaire template-driven:
  - Store questionnaire templates in backend or configuration
  - Frontend just renders generic question UI (text, choices)
  - Replace type-specific branching with data-driven lookup
  - Example structure:
    ```json
    {
      "questionnaires": {
        "crm_type": {
          "key": "crm_type",
          "text": "What kind of CRM are you building?",
          "choices": [...]
        },
        "tracks": {
          "sales_pipeline": { "text": "...", "choices": [...] },
          "customer_support": { "text": "...", "choices": [...] }
        }
      }
    }
    ```
- **Effort:** HIGH (requires backend template support, refactor questionnaire logic)

---

#### 5. Hard-Coded Example Prompts in CRM Generator

**File:** `frontend/src/features/crm-generator/CRMGeneratorPage.tsx`  
**Lines:** 42–54  
**Severity:** MEDIUM (examples only, but influences thinking)

**Problematic Code:**
```tsx
const examplePrompts = [
  {
    title: 'B2B SaaS Sales CRM',
    prompt:
      'Create a B2B SaaS CRM to track enterprise leads, deals, lead sources, demo follow-up dates, deal values, and subscription tier stages.',
  },
  {
    title: 'Real Estate Brokerage CRM',
    prompt:
      'Create a luxury real estate CRM to manage property buyer leads, listings, site visits, budgets, location preferences, and escrow stages.',
  },
  {
    title: 'Healthcare & Patient Clinic',
    prompt:
      'Create a healthcare clinic CRM to track patients, appointments, primary phone, blood groups, triage status, and consultation stages.',
  },
];
```

**Why It Violates Requirements:**
- These examples teach users that CRMs are only for Sales, Real Estate, or Healthcare
- All examples use domain-specific language (leads, deals, patients, appointments)
- No examples for other domains: E-Commerce, Recruitment, Project Management, Manufacturing, etc.
- Creates cognitive bias that CRMs fit specific patterns

**Impact:**
- Users may not recognize AURA can build CRMs for unusual domains
- Limits user imagination about CRM applications

**Fix Approach:**
- Expand examples to demonstrate true universality:
  - Include E-Commerce (products, orders, shipments, returns)
  - Recruitment (candidates, applications, interview stages)
  - Project Management (tasks, sprints, blocked/in-progress/done)
  - Educational (courses, students, enrollment stages)
  - Event Planning (events, vendors, bookings)
- Keep total to 3–5 examples (rotate or randomize)
- **Effort:** LOW (add 2–3 more prompts, ~10 lines)

---

### 🟠 MEDIUM VIOLATIONS

#### 6. Hard-Coded Entity Name in Workflow Examples

**File:** `frontend/src/services/mockData.ts`  
**Lines:** 143–172  
**Severity:** MEDIUM

**Problematic Code:**
```ts
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
```

**Why It Violates Requirements:**
- Workflow names and triggers assume entity is `'lead'`
- Cannot be reused for other CRM types
- Breaks Requirement #3 (Universal Entity System)

**Impact:**
- Documentation teaches workflows only work with "leads"
- Template workflows must be manually customized for other entities

**Fix Approach:**
- Create generic workflow templates:
  - Rename to "Auto Follow-up on New Record" and "Alert on Stage Change"
  - Replace `entity: 'lead'` with `entity: null` or use primary entity from CRM config
- **Effort:** LOW (text replacements, 5 lines)

---

#### 7. Hard-Coded Analytics Label with Lead/Record Ambiguity

**File:** `frontend/src/features/crms/CRMDetailPage.tsx`  
**Line:** 200  
**Severity:** MEDIUM

**Problematic Code:**
```tsx
<span className="text-[10px] font-bold uppercase text-slate-400">Total Leads/Records</span>
```

**Why It Violates Requirements:**
- Label says "Leads/Records" — suggests leads are special, records are fallback
- Not inclusive of all entity types (patients, customers, tickets, candidates, etc.)

**Impact:**
- Cosmetic, but teaches non-universal thinking
- Inconsistent with universal principles

**Fix Approach:**
- Change to: `Total {primaryEntityName}s` (derived from schema)
- Or generically: "Total Records"
- **Effort:** TRIVIAL (1 line change)

---

#### 8. Fallback Metric Label in Analytics

**File:** `frontend/src/features/analytics/AnalyticsPage.tsx`  
**Lines:** 105–108  
**Severity:** MEDIUM

**Problematic Code:**
```tsx
const totalRecords =
  (analytics as any)?.total_records ??
  (analytics as any)?.total_leads ??
  0;
```

**Why It Violates Requirements:**
- Falls back to `total_leads` if `total_records` not present
- Embeds assumption that leads are a standard metric
- Non-inclusive for other CRM types

**Impact:**
- Analytics may show zero for non-sales CRMs if backend doesn't return `total_leads`
- Creates silent failures

**Fix Approach:**
- Remove `total_leads` fallback:
  ```tsx
  const totalRecords = (analytics as any)?.total_records ?? 0;
  ```
- Ensure backend always returns `total_records` (not `total_leads`)
- **Effort:** LOW (1 line change + backend alignment)

---

#### 9. Hard-Coded "Lead" in CRM Questionnaire Choice Labels

**File:** `frontend/src/features/crm-chat/CRMChatPage.tsx`  
**Line:** 66  
**Severity:** MEDIUM

**Problematic Code:**
```tsx
choices: ['Leads → Deals', 'Contacts + Companies + Deals', 'Leads + Quotes + Invoices', 'Just leads for now'],
```

**Why It Violates Requirements:**
- Shows "Leads" as a fundamental concept in all questionnaires
- Educates users that leads are primary

**Impact:**
- Reinforces sales-specific thinking

**Fix Approach:**
- Use neutral language:
  ```tsx
  choices: [
    'Primary Entity → Deal',  // generic
    'Contacts + Companies + Deals',  // domain-specific but flexible
    'Primary Entity + Quotes + Invoices',
    'Just the main entity type for now'
  ]
  ```
- **Effort:** LOW (text changes only)

---

### ✅ COMPLIANT AREAS

**The following systems demonstrate excellent universal architecture:**

1. **Records Table (RecordsPage.tsx):**
   - Fully schema-driven column generation
   - Dynamic entity tabs from `activeCRM.configuration.entities`
   - Field types drive cell rendering (no hard-coded assumptions)
   - ✅ Compliant with Requirements #4 & #5

2. **Analytics System (AnalyticsPage.tsx):**
   - KPI cards derived from schema: `primaryEntityName`, `pipeline_stages`, `kpi_cards`
   - Stage distribution bar chart uses actual configured stages
   - Categorical metrics dynamically generated from field metadata
   - ✅ Compliant with Requirements #14 & #15

3. **Record Form Generation (RecordFormModal.tsx):**
   - Field inputs determined by `field.type` (text, email, phone, select, status, boolean, date, etc.)
   - No hard-coded field names
   - Validation rules derived from field metadata
   - ✅ Compliant with Requirement #6

4. **AI Copilot (AIAssistantDrawer.tsx):**
   - Tool execution doesn't hard-code entity names
   - Tools: `create_record`, `update_record`, `delete_record` accept dynamic field data
   - No assumption about CRM type
   - ✅ Compliant with Requirements #9, #10, #11

5. **CRM Context (CRMContext.tsx):**
   - Dynamically reads active entity from schema
   - No hard-coded entity selection
   - ✅ Compliant with Requirement #1

---

## Violation Summary Table

| File | Issue | Severity | Lines | Category | Impact |
|------|-------|----------|-------|----------|--------|
| RecordFormModal.tsx | Hard-coded status fallback `['New', 'Active', 'Completed']` | CRITICAL | 176 | Fallback Logic | Form shows wrong stages |
| mockData.ts | Entity name hard-coded to `'lead'` in workflow triggers | HIGH | 147, 162 | Mock Data | Workflows fail for other entities |
| mockData.ts | Sales-specific field names in INITIAL_SAAS_CONFIG | HIGH | 14–50 | Mock Data | Template teaches sales-only thinking |
| CRMChatPage.tsx | CRM-type-specific questionnaire branching | MEDIUM | 32–128 | Questionnaire | Code changes needed for new CRM types |
| CRMGeneratorPage.tsx | Hard-coded example prompts (3 domains only) | MEDIUM | 42–54 | Examples | Limits user imagination |
| mockData.ts | "New Lead Auto Follow-up" workflow names | MEDIUM | 144, 159 | Mock Data | Documentation teaches lead-centric patterns |
| CRMDetailPage.tsx | Label: "Total Leads/Records" | MEDIUM | 200 | Labels | Non-inclusive language |
| AnalyticsPage.tsx | Fallback to `total_leads` metric | MEDIUM | 106 | Fallback Logic | Silent failures if metric missing |
| CRMChatPage.tsx | Questionnaire choices mention "Leads" | MEDIUM | 66 | UI Text | Reinforces sales-specific thinking |

---

## Recommendations by Category

### 1. IMMEDIATE ACTION (Week 1)
- [ ] Fix Critical: Remove hard-coded status fallback in RecordFormModal.tsx
- [ ] Fix High: Parameterize mock workflows to use dynamic entity names
- [ ] Fix High: Refactor INITIAL_SAAS_CONFIG to use generic entity/field names

### 2. SHORT-TERM (Week 2)
- [ ] Update analytics fallback logic (total_leads → total_records only)
- [ ] Fix UI labels (leads → records or entity name)
- [ ] Add more example prompts covering diverse CRM types

### 3. MEDIUM-TERM (Week 3–4)
- [ ] Refactor questionnaire into template-driven system
- [ ] Remove CRM-type-specific branching from frontend
- [ ] Update UI text to use neutral language ("entity" not "lead")

### 4. LONG-TERM (Week 5+)
- [ ] Build questionnaire template editor in admin panel
- [ ] Create CRM-type taxonomy and validation rules
- [ ] Document universal architecture patterns for new developers

---

## Effort Estimates

| Priority | Count | Total Effort |
|----------|-------|--------------|
| CRITICAL | 1 | 0.5 day |
| HIGH | 2 | 1 day |
| MEDIUM | 5 | 2 days |
| LOW (examples) | 3 | 0.5 day |
| **Total** | **11** | **4 days** |

---

## Testing Recommendations

After fixes:

1. **Records Page:** Test with multiple CRM types (Sales, Healthcare, E-Commerce)
   - Verify correct fields and entity tabs appear
   - Verify status fields show configured stages, not defaults

2. **Record Form:** Create records for multiple CRM types
   - Verify form fields match schema
   - Verify status dropdowns show correct options

3. **Analytics:** Test with multiple CRM types
   - Verify correct entity name displayed
   - Verify correct stage distribution shown

4. **Workflows:** Create workflows for non-sales entities
   - Verify triggers work regardless of entity type

5. **Mock Data:** Verify mock data doesn't leak CRM-specific assumptions
   - Search for entity.name assumptions
   - Verify all data is generic/parameterized

---

## Conclusion

The AURA frontend demonstrates strong commitment to universal CRM architecture. The violations identified are **localized and fixable** without architectural changes. Most core systems (records, analytics, forms, AI assistant) already implement the universal pattern correctly.

**Primary issue:** Mock data and UI examples inadvertently teach sales-specific thinking, which contradicts the universal principle. Fixing these violations will ensure the codebase reinforces rather than contradicts the requirement for true CRM universality.

**Recommendation:** Schedule the fixes sequentially, prioritizing the CRITICAL fallback logic (highest impact on production behavior) before addressing the MEDIUM violations (which currently only affect UI text and questionnaire branching).
