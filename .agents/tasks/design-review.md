# Design Review: Universal CRM Generator Fix and Post-Generation Editing

**Reviewer:** Design Review Agent  
**Date:** 2025-01-15  
**Status:** CHANGES_REQUESTED  
**Severity:** 2 HIGH, 3 MEDIUM findings

---

## Verified Assumptions

✅ **Field extraction mechanism exists and is functional**
- `FieldExtractor.extract_fields_from_prompt()` in `backend/app/services/field_extractor.py` handles bullet points, newlines, commas, type annotations
- Deduplication by machine key is implemented
- Type inference from keywords works

✅ **Schema preservation service exists and is functional**
- `SchemaPreservation.validate_and_repair_schema()` compares extracted fields to generated fields
- Missing fields are detected and can be added
- Field count validation logic is present

✅ **Canonical field representation is well-defined**
- Both Python (`CRMField` in pydantic) and TypeScript (`CanonicalField` interface) are specified
- Structure matches: name, label, type, required, options

✅ **Supabase RLS architecture is in place**
- `crms` table has owner_id column and index on owner_id
- `records` table has crm_id foreign key
- Configuration_version column exists for optimistic locking
- RLS policies documented in API_CONTRACTS.md

✅ **Database schema supports JSONB field storage**
- `configuration` JSONB column can store entity definitions with any number of fields
- `records.data` JSONB column can store arbitrary field values
- No schema migration needed for adding/deleting fields

✅ **No hardcoded field names or CRM-specific logic required**
- Design explicitly avoids CRM-type-specific editors
- FieldExtractor works generically for any field list
- SchemaPreservation applies to any entity

---

## Unverified/Wrong Assumptions

❌ **ASSUMPTION: FieldExtractor is called in the main `/generate` endpoint**

**Status:** WRONG — The investigation explicitly states this is NOT happening.

**Evidence from investigation.md:**
> The current router file (line 36) shows only basic provider call and validation, **without SchemaPreservation or FieldExtractor**. The endpoint **only calls `provider.generate_crm_config(body.prompt)` and validates with Pydantic**, **without SchemaPreservation or FieldExtractor**.

**Impact:** The root cause is unresolved in the design. The design acknowledges SchemaPreservation exists but doesn't emphasize that the router must be updated to call it.

---

## HIGH Findings

### H1: Root Cause Not Fully Addressed in Design

**Severity:** HIGH  
**Location:** Design section 2.3 and the overall architecture flow  
**Problem:**

The investigation identifies three root causes:
1. FieldExtractor not called in router
2. SchemaPreservation not called in router
3. LLM prompt doesn't instruct Qwen to preserve fields

The design correctly specifies the LLM prompt fix (section 3) but **does not emphasize the integration of SchemaPreservation into the router** as a critical, immediate fix.

The design states (section 2.2):
> **Status:** Service exists in `backend/app/services/schema_preservation.py`  
> **No changes needed** — already validates and repairs schema correctly.

This is **misleading**. While the service is correct, the **router does not call it**, which is the actual problem. The design should explicitly state:

- Current state: Router calls only `provider.generate_crm_config()` and Pydantic validation
- Required change: Router must call `SchemaPreservation.validate_and_repair_schema()` after provider generation

**CONCRETE FIX:**

Update section 2.2 to clarify:

```markdown
### 2.2 Schema Preservation & Repair (SchemaPreservation)

**Status:** Service exists and is correct, but IS NOT CALLED in the main endpoint.

**Root cause:** `backend/app/routers/crm.py` line 44 calls only `provider.generate_crm_config()` 
and skips the repair pipeline. This must be fixed immediately.

**Required integration into router:**

The endpoint at `POST /api/v1/crm/generate` must:
1. Call `provider.generate_crm_config(body.prompt)` (already done)
2. **NEW:** Call `SchemaPreservation.validate_and_repair_schema()` to extract and validate fields
3. **NEW:** Call `FieldExtractor.extract_fields_from_prompt()` to count user requests
4. **NEW:** Call `SchemaPreservation.compare_field_counts()` to verify preservation
5. Return repaired config with field_analysis metadata

This is the critical fix for the field loss issue.
```

**Why it's HIGH:** Without this explicit direction, the implementation may skip the integration step or misunderstand its criticality.

---

### H2: Post-Generation Editing Endpoints Incomplete — Missing Endpoint for Updating CRM Configuration After Generation

**Severity:** HIGH  
**Location:** Section 4 (Post-Generation Editing Backend API) and integration with section 9.1 (Data Flow)

**Problem:**

The design specifies field/stage CRUD endpoints:
- POST /crm/{crm_id}/fields (add field)
- PATCH /crm/{crm_id}/fields/{field_name} (update field)
- DELETE /crm/{crm_id}/fields/{field_name} (delete field)
- etc.

But it **does not specify an endpoint for saving the entire updated CRM configuration**. 

The data flow (section 9.1) shows:
```
HTTP PATCH /api/v1/crm/{crm_id}/fields/{field_name}
  Body: { "label": "New Label", ... }
    ↓
Backend receives request
    ↓
... validate, update, save to DB
    ↓
HTTP 200 response with updated CRMConfiguration
```

**Problem:** The individual field endpoints (PATCH field) increment configuration_version and save. But what if the frontend wants to batch multiple changes (add 3 fields, delete 1, reorder)? Should the frontend call the endpoint 4 times, or should there be a batch endpoint?

**Current API_CONTRACTS.md** already has `PATCH /api/v1/crm/{crm_id}/configuration` (section 5.5), but:
- It says "Changes that alter the active CRM are applied only through an approved proposal" — which is not the intent for post-generation editing
- It's described as updating "safe descriptive metadata only" — contradicting the schema editing use case

**CONCRETE FIX:**

Either:

**Option A (Recommended):** Clarify that individual field endpoints are the primary path:
```markdown
Each field operation (add, update, delete, reorder) is a separate HTTP request. 
The backend validates each operation independently and increments configuration_version.
The frontend may batch multiple field operations if desired (multiple sequential calls).
For large batches, consider implementing a bulk endpoint in a future phase.
```

**Option B:** Add a batch endpoint:
```markdown
POST /api/v1/crm/{crm_id}/configuration/apply-edits

Request:
{
  "operations": [
    {"op": "add_field", "label": "Agent", "type": "select", ...},
    {"op": "delete_field", "field_name": "old_field"},
    {"op": "reorder_fields", "field_order": [...]}
  ],
  "expected_version": 1
}

Response:
{
  "data": {
    "configuration": CRMConfiguration,
    "configuration_version": 2,
    "operations_applied": 3
  }
}
```

**Why it's HIGH:** Without clarity, the implementation may choose incompatible approaches (batch vs. individual), causing rework.

---

## MEDIUM Findings

### M1: Field Renaming Not Implemented; Design Recommends Disallowing It

**Severity:** MEDIUM  
**Location:** Section 6.3 (Renaming a Field)

**Problem:**

Section 6.3 states:
> **Recommendation:** For MVP, disallow renaming if records exist. Rename is lower priority.

But:
1. No PATCH endpoint is defined for renaming (`PATCH /crm/{crm_id}/fields/{field_name}/rename`?)
2. No error handling defined for rename attempts
3. The UpdateFieldRequest schema (section 14.1) doesn't include a `name` field for renaming

This is actually a good MVP choice (avoid renaming complexity), but **it's not explicitly specified as an unsupported operation in the API contract**. 

**Impact:** Implementation may:
- Try to support renaming and introduce bugs
- Build rename UI that doesn't work
- Spend time on something explicitly out of scope

**CONCRETE FIX:**

Add to section 4.3 (Validation Rules):

```markdown
**Renaming fields (MVP constraint):**
- Field names cannot be changed after the CRM is created
- If a user wants a different name, the workflow is: delete the field, add a new field with desired name
- This avoids complex data migration logic in the MVP
- Future versions may support renaming with proper record migration
```

Also, update UpdateFieldRequest in section 14.1:

```markdown
**UpdateFieldRequest:**
class UpdateFieldRequest(StrictModel):
    label: str | None = None
    type: FieldType | None = None  # Note: MVP restricts type changes to safe conversions only
    required: bool | None = None
    options: list[str] | None = None
    description: str | None = None
    
    # Note: Field name (machine identifier) is immutable after creation.
    # Cannot rename fields; use delete + add instead.
```

**Why it's MEDIUM:** This clarification prevents scope creep and wasted implementation effort, but the feature isn't critical to the core fix.

---

### M2: Field Type Changes Are Restricted but Restrictions Not Fully Defined

**Severity:** MEDIUM  
**Location:** Section 6.4 (Changing Field Type)

**Problem:**

Section 6.4 lists "safe" and "unsafe" type changes:

Safe:
- text → textarea
- text → email
- number → text

Unsafe:
- select → number
- date → number
- email → boolean

But:
1. The list is **not comprehensive** (what about textarea → text? textarea → email?)
2. No explicit validation logic is defined for the backend to check type changes
3. No error response format defined for unsafe type changes

**Impact:** 
- Implementation may allow unsafe conversions
- Edge cases (textarea → text) are ambiguous
- Testing may miss some conversions

**CONCRETE FIX:**

Add a comprehensive type-change matrix in a new section:

```markdown
### 6.4a Type Conversion Matrix

When updating a field's type, only these conversions are allowed:

SAFE CONVERSIONS (no data loss, client can display):
  text          → textarea, email, phone, url
  textarea      → text, email (if content is single-line), phone, url
  email         → text, url
  phone         → text
  url           → text
  number        → text
  date          → text (format: YYYY-MM-DD)
  datetime      → text (format: ISO 8601), date (if time is 00:00)
  boolean       → select (options: ["true", "false"])
  select        → (none; select is end-of-conversion chain)
  multi_select  → (none; multi_select is end-of-conversion chain)

UNSAFE CONVERSIONS (rejected with 409 CONFLICT):
  All other conversions (e.g., select → number, date → boolean)

When an unsafe conversion is requested, return 409 with message:
  "Cannot convert field type select → number with existing records. 
   To change the type, delete the field and add a new one."
```

**Why it's MEDIUM:** The design works without this, but the omission risks unsafe conversions slipping into the codebase.

---

### M3: Post-Generation Editor Integration Point Unclear — When Should User Edit?

**Severity:** MEDIUM  
**Location:** Section 9 (Data Flow) and CRM lifecycle

**Problem:**

The design describes two workflows:

**Workflow A (Section 9):**
- User requests CRM generation
- GET /api/v1/crm/generate → returns draft configuration
- User clicks [Edit CRM]
- **Editor opens with draft config**
- User saves → PATCH /api/v1/crm/{crm_id}/configuration

**Workflow B (Inferred from section 5.2):**
- User requests CRM generation → POST /api/v1/crm/generate → returns draft
- **Frontend may auto-save draft or user must explicitly POST /api/v1/crm to save**
- Then user can click [Edit CRM]

**Ambiguity:** Does the [Edit CRM] button appear for:
1. Draft CRMs (not yet saved to DB)?
2. Active CRMs (already saved)?
3. Both?

**Current API_CONTRACTS.md** section 5.2 says "The configuration is a draft and is not saved/activated by this endpoint." But section 5.3 (Save CRM) is separate, suggesting a two-step flow:
1. Generate (draft in memory)
2. Save (persisted to DB)

The design shows both, but it's unclear **when the [Edit CRM] button appears and what state the CRM is in**.

**CONCRETE FIX:**

Clarify the full lifecycle in section 9:

```markdown
### 9.0 CRM Lifecycle and When Editing is Available

1. **GENERATION PHASE**
   - User submits natural language prompt
   - POST /api/v1/crm/generate returns draft configuration (not saved)
   - Frontend displays preview: "Generated CRM with X fields"
   - User can:
     a. [Save CRM] → POST /api/v1/crm (saves to DB, crm_id assigned)
     b. [Edit Before Saving] → Opens editor with draft config (local only)
     c. [Start Over] → Discard and regenerate

2. **AFTER SAVE PHASE** (CRM now has crm_id and is in DB)
   - CRM detail page displays current configuration
   - User can:
     a. [Edit CRM] → Opens editor with persisted config
     b. [Add Records] → Create/view records
     c. [Set Up Workflow] → Later feature
   
3. **EDITOR SESSION** (both draft and saved CRMs)
   - User makes changes (add/edit/delete fields)
   - Changes are local to editor state (no DB writes)
   - User clicks [Save Changes]
     - Frontend validation
     - PATCH /api/v1/crm/{crm_id}/fields/{field_name} (or batch)
     - Backend validates and persists
     - CRM configuration_version increments
     - Editor closes
   - Or [Cancel] → Discard unsaved changes

### 9.1 Complete Flow Diagram (Updated)
[... existing diagram ...]
```

**Why it's MEDIUM:** Without this clarity, frontend implementation may build the wrong UI flow or miss the "edit before save" case.

---

### M4: No Guidance on How LLM is Invoked — Multiple Providers (Ollama, Grok, Hugging Face)

**Severity:** MEDIUM  
**Location:** Design lacks provider selection logic; implementation contract unclear

**Problem:**

The design specifies updating the Ollama system prompt (section 3.1):
```python
# File: backend/app/services/ollama_provider.py
```

But AGENTS.md and the codebase support multiple providers:
- Ollama (local)
- Grok API
- Hugging Face

**Questions:**
1. Should the "FIELD PRESERVATION REQUIREMENT" be added to **all providers' prompts**, or just Ollama?
2. If just Ollama, what about users with other providers configured?
3. How does the system select which provider to use? (Settings? User choice? Fallback?)

**Current investigation.md** only mentions Ollama:
> **Location:** `backend/app/services/ollama_provider.py`, `_get_system_prompt()`, lines 59–86

**Impact:** The field preservation fix may work for Ollama but fail for Grok or Hugging Face, creating inconsistent behavior.

**CONCRETE FIX:**

Add a provider selection section to the design:

```markdown
### 3.3 Provider-Agnostic Field Preservation

The FIELD PRESERVATION REQUIREMENT must be added to **all LLM providers' system prompts**:

Files to update:
- backend/app/services/ollama_provider.py → _get_system_prompt()
- backend/app/services/grok_provider.py → _get_system_prompt() (if exists)
- backend/app/services/huggingface_provider.py → _get_system_prompt() (if exists)

The requirement text is identical across all providers:
  "FIELD PRESERVATION REQUIREMENT (DO NOT SKIP): ..."

The settings.llm_provider (from environment/config) determines which provider is used.
Every provider must enforce field preservation.
```

**Why it's MEDIUM:** Field preservation may silently fail for non-Ollama providers, causing inconsistent UX and debugging difficulty.

---

## NIT Findings

### N1: Drag-to-Reorder UX Not Specified (Nice to Have)

**Severity:** NIT  
**Location:** Sections 5.2 and 5.4 (Fields and Stages editors)

The design mentions:
```typescript
<div className="drag-handle">⋮⋮</div>
```

But doesn't specify:
- Which library (react-beautiful-dnd, dnd-kit, Sortable.js)?
- Accessibility requirements (keyboard support, ARIA labels)?
- Touch device support?

**Impact:** Implementation can choose any robust drag-drop library. Not blocking.

**Recommendation:** Add a note:
```markdown
Drag-to-reorder should support:
- Mouse drag
- Touch drag (mobile)
- Keyboard (arrow keys to move, Enter to confirm)
- Screen reader announcements (ARIA live region on reorder)
```

---

### N2: Component Split Not Optimized for Code Reuse

**Severity:** NIT  
**Location:** Section 5.2 (Fields Editor Sub-Component)

The `CRMSchemaEditor` component includes three tab panels for Fields, Stages, Metadata. Each is a separate React component. No mention of shared utilities for:
- Field validation logic
- Type selector component (reused across multiple forms)
- Option list editor (for select fields)

**Impact:** Minimal; these are small components. Optimization can happen in PR review.

---

## Summary of Findings

| Severity | Count | Findings |
|----------|-------|----------|
| HIGH | 2 | H1: Root cause not fully emphasized; H2: Batch configuration endpoint unclear |
| MEDIUM | 4 | M1: Field renaming not specified as unsupported; M2: Type change matrix incomplete; M3: Lifecycle unclear; M4: Multi-provider prompt updates missing |
| NIT | 2 | N1: Drag-to-reorder library choice; N2: Component optimization |

---

## Verdict

**CHANGES_REQUESTED**

The design has solid fundamentals but requires clarification on:
1. Integration of SchemaPreservation into the router (root cause emphasis)
2. Batch vs. individual field operation semantics
3. Field renaming constraints
4. Type conversion rules
5. CRM lifecycle and when editing is available
6. Multi-provider prompt updates

These are resolvable with addenda to the design document. **Do not proceed to implementation without resolving H1 and H2.**

---

## Recommended Next Steps

1. **Update design.md with clarifications:**
   - H1: Emphasize router integration as the critical fix
   - H2: Choose batch or individual field operations
   - M1: Add field renaming MVP constraint
   - M2: Add type conversion matrix
   - M3: Add full CRM lifecycle diagram
   - M4: Add multi-provider prompt requirement

2. **After design revisions, update API_CONTRACTS.md:**
   - Clarify when [Edit CRM] is available (draft vs. saved)
   - Add new request/response schemas for field operations
   - Specify field renaming as unsupported (MVP)
   - Document type conversion restrictions

3. **Implementation order:**
   - Phase 1: Fix field preservation (router + prompt)
   - Phase 2: Implement backend field CRUD endpoints
   - Phase 3: Build frontend schema editor
   - Phase 4 (optional): Copilot integration

---

## Design Quality Assessment

**Strengths:**
- Comprehensive generic component architecture
- Clear record safety considerations
- Strong authorization and AGENTS.md alignment
- Good decision rationale (section 10)
- Canonical field representation well-defined
- Testing strategy included

**Weaknesses:**
- Root cause not emphasized as critical integration
- Ambiguities in endpoint semantics (batch vs. individual)
- Lifecycle flow unclear
- Multi-provider support not addressed
- Some implementation details underspecified (M1, M2, M3, M4)

**Overall:** Design is 80% ready; clarifications will make it implementation-ready.
