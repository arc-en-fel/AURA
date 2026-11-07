# Implementation Plan: Universal CRM Generator Fix and Post-Generation Editing

**Status:** Complete  
**Date:** 2025-01-15  
**Scope:** Fix field loss in CRM generation pipeline globally, implement post-generation schema editing, create reusable editor component, connect AI tooling.  
**Approach:** Six independent features (FEAT-001 through FEAT-006) executed sequentially, verified and integrated. This plan is grounded in the approved design (design.md) and resolves all design review findings (design-review.md).

---

## Executive Summary

The CRM generator currently loses user-requested fields silently during generation. The root cause: the `/api/v1/crm/generate` endpoint calls `provider.generate_crm_config()` but does NOT call `SchemaPreservation.validate_and_repair_schema()` afterward. The fix requires:

1. **Integrate field preservation validation into the generation endpoint** (FEAT-001)
2. **Add backend API for post-generation schema editing** (FEAT-002)
3. **Build a generic, reusable React schema editor component** (FEAT-003)
4. **Connect AURA Copilot to schema modification tools** (FEAT-004)
5. **Update API contract documentation** (FEAT-005)
6. **Comprehensive end-to-end testing** (FEAT-006)

All work follows AGENTS.md strictly. No hardcoded CRM-specific logic. All endpoints enforce ownership via Supabase RLS + application-level authorization. Every schema change increments `configuration_version` for optimistic locking.

---

## FEAT-001: Fix Field Preservation Root Cause (CRITICAL)

**Complexity:** Low  
**Duration:** 1-2 hours  
**Blocks:** All other FEATs

### What
Integrate `SchemaPreservation.validate_and_repair_schema()` into the `/api/v1/crm/generate` endpoint. Enhance LLM prompts across all providers to instruct the model to preserve all user-requested fields.

### Root Cause Findings
- **Current state:** `backend/app/routers/crm.py` line 36-50 calls only `provider.generate_crm_config()` and Pydantic validation, without SchemaPreservation.
- **Expected state:** After provider generation, call SchemaPreservation to extract, validate, and repair any missing fields.
- **Why it's broken:** FieldExtractor and SchemaPreservation services are correct and already exist. The endpoint just doesn't use them.

### Steps

- [ ] 1. Enhance LLM prompts in all providers to include FIELD PRESERVATION REQUIREMENT
  - **File:** `backend/app/services/ollama_provider.py` → `_get_system_prompt()`
  - **Change:** Add section: "FIELD PRESERVATION REQUIREMENT (DO NOT SKIP): If the user's request lists specific fields, you MUST include EVERY ONE of those fields in the generated 'fields' array..."
  - **Verify:** Grep for "FIELD PRESERVATION" in the prompt string

- [ ] 2. Apply same prompt enhancement to other LLM providers
  - **Files:** Check for `backend/app/services/grok_provider.py`, `huggingface_provider.py`, etc.
  - **Change:** Add identical FIELD PRESERVATION REQUIREMENT section to each provider's `_get_system_prompt()`
  - **Verify:** Grep for "FIELD PRESERVATION" in all provider files

- [ ] 3. Integrate SchemaPreservation into POST /api/v1/crm/generate endpoint
  - **File:** `backend/app/routers/crm.py` → `generate_crm()` function
  - **Current flow:** 
    ```python
    config_dict = provider.generate_crm_config(body.prompt)
    config = CRMConfiguration(**config_dict)  # Pydantic validation only
    return success_response({"configuration": config.model_dump()})
    ```
  - **New flow:**
    ```python
    config_dict = provider.generate_crm_config(body.prompt)
    # NEW: Validate and repair schema
    config_dict = SchemaPreservation.validate_and_repair_schema(config_dict, body.prompt)
    # NEW: Analyze field coverage
    extracted_fields = FieldExtractor.extract_fields_from_prompt(body.prompt)
    coverage = SchemaPreservation.compare_field_counts(config_dict, len(extracted_fields))
    # Validate with Pydantic
    config = CRMConfiguration(**config_dict)
    # Include analysis in response
    return success_response({
        "configuration": config.model_dump(),
        "warnings": list(getattr(provider, "last_warnings", [])),
        "field_analysis": coverage
    })
    ```
  - **Verify:** Code review, tests pass

- [ ] 4. Add or update tests for field count preservation
  - **File:** `backend/tests/test_custom_crm_bug_fix.py` (create if needed) or extend `backend/tests/test_universal_crm_generation.py`
  - **Tests:**
    ```python
    def test_generate_crm_preserves_5_fields():
        prompt = "Create CRM with: Customer Name, Email, Phone, Status, Priority"
        response = generate_crm(prompt)
        assert len(response.entities[0].fields) == 5

    def test_generate_crm_preserves_10_fields():
        prompt = "Fields: " + ", ".join([f"Field{i}" for i in range(10)])
        response = generate_crm(prompt)
        assert len(response.entities[0].fields) == 10

    def test_generate_crm_preserves_15_fields():
        prompt = "Fields: " + ", ".join([f"Field{i}" for i in range(15)])
        response = generate_crm(prompt)
        assert len(response.entities[0].fields) == 15
    ```
  - **Verify:** `cd backend && python -m pytest backend/tests/test_custom_crm_bug_fix.py -v` — all pass

- [ ] 5. Verify no regressions in existing generation tests
  - **Verify:** `cd backend && python -m pytest backend/tests/test_universal_crm_generation.py -v` — all pass
  - **Verify:** `cd backend && python -m pytest backend/tests/test_regression_422_and_custom_crm.py -v` — all pass

### Verification
```bash
# Run new field count tests
cd backend && python -m pytest backend/tests/test_custom_crm_bug_fix.py::test_generate_crm_preserves_5_fields -v
cd backend && python -m pytest backend/tests/test_custom_crm_bug_fix.py::test_generate_crm_preserves_10_fields -v
cd backend && python -m pytest backend/tests/test_custom_crm_bug_fix.py::test_generate_crm_preserves_15_fields -v

# Verify no regressions
cd backend && python -m pytest backend/tests/ -v

# Manual test
curl -X POST http://localhost:8000/api/v1/crm/generate \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"prompt": "Create CRM with Customer Name, Email, Phone, Status, Priority"}'
# Response should have exactly 5 fields in configuration.entities[0].fields
```

---

## FEAT-002: Backend API for Post-Generation Schema Editing

**Complexity:** Medium  
**Duration:** 4-6 hours  
**Depends on:** FEAT-001 (field preservation must work first)  
**Blocks:** FEAT-003, FEAT-004

### What
Implement 8 REST endpoints for field and stage CRUD operations: POST/PATCH/DELETE fields, POST/PATCH/DELETE stages, reorder fields/stages. All endpoints enforce authorization (ownership), validate inputs, handle record safety, increment configuration_version.

### Steps

- [ ] 1. Add request/response schemas to `backend/app/schemas/crm.py`
  - **New classes:**
    ```python
    class AddFieldRequest(StrictModel):
        label: str = Field(min_length=1, max_length=100)
        type: FieldType
        required: bool = False
        options: list[str] | None = None
        description: str = ""

    class UpdateFieldRequest(StrictModel):
        label: str | None = None
        type: FieldType | None = None  # Only safe conversions allowed
        required: bool | None = None
        options: list[str] | None = None
        description: str | None = None

    class DeleteFieldRequest(StrictModel):
        # Empty for now; deletion confirmation via 409 warning
        force: bool = False  # Skip "records affected" warning

    class ReorderFieldsRequest(StrictModel):
        field_order: list[str] = Field(min_length=1)  # Machine keys in new order

    # Similar for stages
    class AddStageRequest(StrictModel):
        name: str = Field(min_length=1, max_length=100)
        position: int | None = None

    class FieldOperationResponse(StrictModel):
        configuration: CRMConfiguration
        field_added: CRMField | None = None
        field_updated: CRMField | None = None
        field_deleted: str | None = None  # Field name
        configuration_version: int
        records_affected: int = 0
    ```
  - **Verify:** Pydantic validation works, no TypeErrors

- [ ] 2. Implement POST /api/v1/crm/{crm_id}/fields — Add field
  - **File:** `backend/app/routers/crm.py`
  - **Logic:**
    1. Extract user_id from JWT
    2. Query crm where id = crm_id and owner_id = user_id; if not found, return 404
    3. Validate request body (Pydantic)
    4. Generate machine_key from label: `label.lower().replace(" ", "_")`
    5. Check if field_name already exists in entity.fields; if yes, return 409
    6. Create new CRMField, append to entity.fields
    7. Increment configuration_version
    8. Save to DB (Supabase)
    9. Return 200 (or 201) with updated CRMConfiguration
  - **Error codes:** 401 (not authenticated), 403 (not authorized), 404 (CRM not found), 409 (field exists), 422 (invalid input)
  - **Verify:** Endpoint works, field is added, version increments

- [ ] 3. Implement PATCH /api/v1/crm/{crm_id}/fields/{field_name} — Update field
  - **File:** `backend/app/routers/crm.py`
  - **Logic:** Similar to POST but updates existing field. Validate type conversions against safe conversion matrix (see FEAT-005).
  - **Safe conversions:** text→email, email→text, text→phone, phone→text, number→text, text→number, date→text, textarea→text, boolean→select
  - **Unsafe conversions:** select→number, date→number, email→boolean, etc. → return 409
  - **Error codes:** 400 (invalid conversion), 403, 404, 409 (unsafe change)
  - **Verify:** Update works, unsafe changes rejected

- [ ] 4. Implement DELETE /api/v1/crm/{crm_id}/fields/{field_name} — Delete field
  - **File:** `backend/app/routers/crm.py`
  - **Logic:**
    1. Verify CRM ownership
    2. Find field in entity.fields
    3. Query records table: `SELECT COUNT(*) FROM records WHERE crm_id = ? AND (data->>'{field_name}')::text IS NOT NULL`
    4. If count > 0, return 409 with message: "Field '{field_name}' has values in {count} existing records. Delete them first or confirm deletion (data will be lost)."
    5. If confirmed (or force=true), remove field from entity.fields
    6. Increment version, save, return 200
  - **Error codes:** 403, 404, 409 (records with values)
  - **Verify:** Deletion works, 409 warning issued for fields with records

- [ ] 5. Implement PATCH /api/v1/crm/{crm_id}/fields/reorder — Reorder fields
  - **File:** `backend/app/routers/crm.py`
  - **Logic:**
    1. Verify CRM ownership
    2. Validate field_order: must contain exactly the same fields as current entity.fields (same set, different order)
    3. Reorder entity.fields array per field_order
    4. Increment version, save, return 200
  - **Error codes:** 403, 404, 422 (field list mismatch)
  - **Verify:** Reorder works, field order persists

- [ ] 6. Implement POST /api/v1/crm/{crm_id}/stages — Add stage
  - **File:** `backend/app/routers/crm.py`
  - **Logic:** Similar to add field, but for pipeline_stages (simple string list). Validate stage name uniqueness.
  - **Verify:** Stage added, version increments

- [ ] 7. Implement PATCH /api/v1/crm/{crm_id}/stages/{stage_name} — Update stage (rename)
  - **File:** `backend/app/routers/crm.py`
  - **Note:** MVP constraint: renaming is NOT supported if records have that stage value. Recommend delete + add workflow instead.
  - **Alternative:** Allow rename but update records (complex). Skip for MVP.
  - **Verify:** Returns 409 with message about record safety

- [ ] 8. Implement DELETE /api/v1/crm/{crm_id}/stages/{stage_name} — Delete stage
  - **File:** `backend/app/routers/crm.py`
  - **Logic:** Similar to delete field. Check if any records have this stage value.
  - **Verify:** Deletion works, 409 warning issued

- [ ] 9. Implement PATCH /api/v1/crm/{crm_id}/stages/reorder — Reorder stages
  - **File:** `backend/app/routers/crm.py`
  - **Verify:** Reorder works

- [ ] 10. Add authorization tests: user A cannot edit/delete user B's CRM
  - **File:** `backend/tests/test_crm_endpoints_authorization.py` (new file)
  - **Tests:**
    ```python
    def test_user_a_cannot_add_field_to_user_b_crm():
        # Create CRM owned by user B
        # Try to add field as user A
        # Expect 403 or 404

    def test_user_a_cannot_delete_field_from_user_b_crm():
        # Similar

    # ... one per endpoint
    ```
  - **Verify:** All auth tests pass

- [ ] 11. Add functional tests for field operations
  - **File:** `backend/tests/test_crm_field_operations.py` (new file)
  - **Tests:**
    ```python
    def test_add_field_success():
        # POST /crm/{crm_id}/fields → 200, field added

    def test_add_duplicate_field_fails():
        # POST with same label → 409

    def test_delete_field_with_records_warns():
        # DELETE field used in records → 409 with message

    def test_reorder_fields_success():
        # PATCH /crm/{crm_id}/fields/reorder → 200, order persisted

    def test_update_field_type_safe_conversion():
        # PATCH /crm/{crm_id}/fields/{name} with type text→email → 200

    def test_update_field_type_unsafe_conversion_fails():
        # PATCH with select→number → 409
    ```
  - **Verify:** All tests pass

- [ ] 12. Update docs/API_CONTRACTS.md
  - **Add section 1.5:** "Field and Stage Modification Endpoints"
  - **Document:** All 8 endpoints, request/response schemas, error codes
  - **Verify:** No broken references, examples match actual behavior

### Verification
```bash
cd backend

# Test authorization
python -m pytest backend/tests/test_crm_endpoints_authorization.py -v

# Test field operations
python -m pytest backend/tests/test_crm_field_operations.py -v

# Manual tests
curl -X POST http://localhost:8000/api/v1/crm/{crm_id}/fields \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"label": "New Field", "type": "text"}'
# Expect 200, field added

curl -X PATCH http://localhost:8000/api/v1/crm/{crm_id}/fields/{field_name} \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"type": "select"}'  # Unsafe if field had records
# Expect 409 or 200 depending on record state
```

---

## FEAT-003: Frontend Generic Schema Editor Component

**Complexity:** Medium  
**Duration:** 4-6 hours  
**Depends on:** FEAT-002 (backend endpoints must exist)  
**Blocks:** None (can integrate with CRM detail page once complete)

### What
Create a reusable React component `CRMSchemaEditor.tsx` that works for ANY CRM type without hardcoded logic. Component allows user to add/edit/delete/reorder fields and stages, validate locally, and save via backend API.

### Steps

- [ ] 1. Create `frontend/src/components/CRMSchemaEditor/CRMSchemaEditor.tsx`
  - **Props:**
    ```typescript
    interface CRMSchemaEditorProps {
      crm: CRMConfiguration;
      onSave: (updatedConfig: CRMConfiguration) => Promise<void>;
      onCancel: () => void;
      isLoading?: boolean;
    }
    ```
  - **State:** editingConfig (local copy), activeTab, validationErrors, isSaving
  - **Tabs:** Fields, Stages, Metadata
  - **Buttons:** [Cancel] [Save Changes]
  - **Behavior:** No DB writes on keystroke. Only on explicit save.
  - **Verify:** Component renders, tabs switch, state updates

- [ ] 2. Create `frontend/src/components/CRMSchemaEditor/FieldsEditor.tsx`
  - **Shows:** List of current fields with edit/delete buttons
  - **Features:** Drag-to-reorder, [+ Add Field] button
  - **Calls:** onUpdate() to update parent state (not DB)
  - **Verify:** Fields display, add/delete/reorder UI works

- [ ] 3. Create `frontend/src/components/CRMSchemaEditor/AddFieldForm.tsx`
  - **Inputs:** Label (text), Type (dropdown: text/textarea/email/number/date/boolean/select/phone/url), Required (checkbox), Options (textarea for select types)
  - **Validation:** Label not empty, type valid, select options non-empty
  - **Auto-generate:** Machine key from label (e.g., "Customer Name" → "customer_name")
  - **Verify:** Form validates, key auto-generates correctly

- [ ] 4. Create `frontend/src/components/CRMSchemaEditor/FieldEditModal.tsx`
  - **Similar to AddFieldForm** but edits existing field
  - **Constraint:** Cannot rename (machine key immutable) — show this to user
  - **Verify:** Modal opens, updates work

- [ ] 5. Create `frontend/src/components/CRMSchemaEditor/StagesEditor.tsx`
  - **Shows:** List of pipeline_stages with add/delete/reorder UI
  - **Verify:** Stages display, operations work

- [ ] 6. Create `frontend/src/components/CRMSchemaEditor/AddStageForm.tsx`
  - **Input:** Stage name
  - **Validation:** Not empty, not duplicate
  - **Verify:** Form works

- [ ] 7. Create `frontend/src/components/CRMSchemaEditor/MetadataEditor.tsx`
  - **Inputs:** CRM name, industry
  - **Verify:** Editable, updates parent state

- [ ] 8. Implement drag-to-reorder for fields and stages
  - **Library choice:** `@dnd-kit/core` (good accessibility) or `react-beautiful-dnd`
  - **Features:** Mouse drag, touch drag, keyboard support
  - **Verify:** Drag works, order persists in local state

- [ ] 9. Create frontend validation utilities in `frontend/src/utils/crmValidation.ts`
  - **Functions:**
    ```typescript
    validateCRMConfiguration(config: CRMConfiguration): string[]
    validateField(field: CanonicalField): string[]
    validateSelectOptions(options: string[] | undefined): string[]
    normalizeLabelToKey(label: string): string
    ```
  - **Verify:** Validation catches errors (empty options for select, invalid field type, etc.)

- [ ] 10. Create TypeScript types in `frontend/src/types/crm.ts`
  - **Interfaces:** CanonicalField, CRMConfiguration (ensure alignment with backend Pydantic models)
  - **Verify:** No type mismatches, both frontend and backend use same structure

- [ ] 11. Integrate into CRMDetailPage
  - **File:** `frontend/src/features/crms/CRMDetailPage.tsx` (or similar)
  - **Add:** [Edit CRM] button
  - **On click:** Set isEditing = true, open editor modal
  - **On save:** Call backend endpoints (POST/PATCH/DELETE), refresh CRM, close modal
  - **On error:** Show error message, keep modal open
  - **Verify:** Integration works, saves to backend

- [ ] 12. Add tests in `frontend/src/components/__tests__/CRMSchemaEditor.test.tsx`
  - **Tests:**
    ```typescript
    test('renders Fields, Stages, Metadata tabs')
    test('add field button opens form')
    test('field validation prevents invalid input')
    test('drag reorder updates field order')
    test('save button calls onSave callback')
    test('cancel button closes without saving')
    test('error from API shown to user')
    ```
  - **Verify:** All tests pass, no TypeScript errors

### Verification
```bash
cd frontend

# Type check
npm run type-check  # or tsc --noEmit

# Tests (if configured)
npm test

# Manual test
# 1. Start dev server: ./start-dev.bat
# 2. Generate a CRM
# 3. Navigate to CRM detail page
# 4. Click [Edit CRM]
# 5. Add a field, verify it appears
# 6. Reorder fields, verify order changes
# 7. Click Save, verify backend called, success message shown
# 8. Click Edit again, verify new field persists
```

---

## FEAT-004: AI Tooling for Schema Modifications

**Complexity:** Low  
**Duration:** 2-3 hours  
**Depends on:** FEAT-002 (backend endpoints)

### What
Enable AURA Copilot to call schema modification tools (add_field, delete_field, add_stage, etc.). All tool calls are validated server-side before execution.

### Steps

- [ ] 1. Create `backend/app/services/ai_tools.py`
  - **Class:** CRMSchemaTools with static methods
    ```python
    class CRMSchemaTools:
        @staticmethod
        async def add_crm_field(crm_id: str, label: str, field_type: FieldType, 
                                required: bool = False, options: list[str] | None = None):
            # Call POST /api/v1/crm/{crm_id}/fields internally
            # Return updated CRMConfiguration or error

        @staticmethod
        async def update_crm_field(crm_id: str, field_name: str, label: str | None = None, ...):
            # Call PATCH endpoint

        @staticmethod
        async def delete_crm_field(crm_id: str, field_name: str, force: bool = False):
            # Call DELETE endpoint

        @staticmethod
        async def add_crm_stage(crm_id: str, stage_name: str):
            # Call POST endpoint

        # ... etc for update/delete stages
    ```
  - **Verify:** Methods defined, callable

- [ ] 2. Create tool schemas in OpenAI function-calling format
  - **File:** `backend/app/services/ai_tools.py` → `COPILOT_TOOLS` constant
  - **Example:**
    ```python
    COPILOT_TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "add_crm_field",
                "description": "Add a new field to a CRM schema",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "crm_id": {"type": "string", "description": "CRM ID"},
                        "label": {"type": "string", "description": "Field label"},
                        "field_type": {
                            "type": "string",
                            "enum": ["text", "email", "phone", ..., "select"],
                            "description": "Field type"
                        },
                        "required": {"type": "boolean", "default": False},
                        "options": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["crm_id", "label", "field_type"]
                }
            }
        },
        # ... more tools
    ]
    ```
  - **Verify:** Tool schemas are valid JSON, all required fields present

- [ ] 3. Create tool execution endpoint in `backend/app/routers/copilot.py`
  - **Endpoint:** POST /api/v1/copilot/tool-call (or similar)
  - **Logic:**
    1. Extract user_id from JWT
    2. Validate tool_name, parameters
    3. Call CRMSchemaTools.{tool_name}()
    4. Return result or error
  - **Error handling:** 400 (invalid tool), 401 (not authenticated), 403 (not authorized), 422 (invalid parameters)
  - **Verify:** Endpoint works, tools execute

- [ ] 4. Add authorization checks
  - **Verify:** Tool calls check CRM ownership
  - **Verify:** User A cannot call tool to modify User B's CRM

- [ ] 5. Add tests in `backend/tests/test_copilot_tools.py`
  - **Tests:**
    ```python
    def test_add_field_via_tool():
        # Call tool → field added

    def test_unauthorized_user_cannot_call_tool():
        # User A cannot modify User B's CRM

    def test_invalid_parameters_rejected():
        # Missing required param → 422

    def test_tool_result_format():
        # Response has correct structure
    ```
  - **Verify:** All tests pass

- [ ] 6. Update Copilot system prompt
  - **File:** `backend/app/services/ollama_provider.py` → `_get_system_prompt()`
  - **Add:** Include COPILOT_TOOLS in system prompt
  - **Instruct:** "You have access to CRM schema modification tools. Use them when user requests schema changes."
  - **Verify:** Copilot sees tools in prompt

- [ ] 7. Document tools in `docs/API_CONTRACTS.md`
  - **Add section:** "Copilot Schema Modification Tools"
  - **List:** All tool names, parameters, descriptions
  - **Verify:** Documentation complete

### Verification
```bash
cd backend

# Test tools
python -m pytest backend/tests/test_copilot_tools.py -v

# Manual test
curl -X POST http://localhost:8000/api/v1/copilot/tool-call \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "add_crm_field",
    "parameters": {
      "crm_id": "...",
      "label": "Escalation Level",
      "field_type": "select",
      "options": ["Low", "Medium", "High"]
    }
  }'
# Expect 200, field added

# Copilot integration test
# Prompt Copilot: "Add an 'Escalation' field to my CRM"
# Verify: Copilot calls add_crm_field tool, field appears
```

---

## FEAT-005: Documentation Updates

**Complexity:** Low  
**Duration:** 2-3 hours  
**Depends on:** FEAT-001–FEAT-004 (documentation follows implementation)

### What
Update API contract documentation and add design clarifications from design review findings.

### Steps

- [ ] 1. Update `docs/API_CONTRACTS.md` section 1.5
  - **Add:** Complete documentation of all 8 field/stage endpoints
  - **Include:** Request/response schemas, status codes, error responses
  - **Example:**
    ```
    ### POST /api/v1/crm/{crm_id}/fields

    Add a new field to the CRM's main entity.

    **Request:**
    {
      "label": "Escalation Level",
      "type": "select",
      "required": false,
      "options": ["Low", "Medium", "High"]
    }

    **Response (200):**
    {
      "data": {
        "configuration": CRMConfiguration,
        "field_added": {
          "name": "escalation_level",
          "label": "Escalation Level",
          ...
        },
        "configuration_version": 2
      }
    }

    **Error (409):**
    {
      "error": {
        "code": "CONFLICT",
        "message": "Field 'escalation_level' already exists"
      }
    }
    ```
  - **Verify:** All 8 endpoints documented with examples

- [ ] 2. Add "Lifecycle and When Editing is Available" section
  - **Explain:**
    1. **Generation Phase:** User submits prompt → draft config in memory
    2. **Save Phase:** User clicks "Save CRM" → POST to DB, gets crm_id
    3. **Active Phase:** CRM stored, user can [Edit CRM]
  - **Clarify:** [Edit CRM] button appears after save (or user can edit draft before saving)
  - **Verify:** Lifecycle clear

- [ ] 3. Add "Field Operation Semantics" section
  - **Clarify:** Operations are applied individually (not batched in MVP)
  - **Each:** PATCH/POST/DELETE is separate HTTP request, increments version
  - **Frontend:** May batch calls sequentially if desired
  - **Verify:** Clear

- [ ] 4. Add "Field Renaming (MVP Constraint)" section
  - **Document:** Machine identifiers (names) are immutable
  - **Workflow:** Delete old field, add new field
  - **Rationale:** Avoids complex record migration
  - **Verify:** Clear

- [ ] 5. Add "Type Conversion Matrix" section
  - **Table:** Safe and unsafe conversions
  - **Safe:** text↔email, text↔phone, number↔text, etc.
  - **Unsafe:** select↔number, date↔boolean, etc.
  - **Behavior:** Unsafe returns 409 CONFLICT
  - **Verify:** Table complete

- [ ] 6. Add "Multi-Provider Field Preservation" section
  - **Document:** All LLM providers enforce field preservation
  - **Providers:** Ollama, Grok, Hugging Face, etc.
  - **Verify:** Clear

- [ ] 7. Create `docs/SCHEMA_EDITING.md`
  - **Content:** Developer guide for schema editing
  - **Topics:** When to use each endpoint, field vs. stage operations, type conversions, record safety, authorization
  - **Examples:** Add field, delete field with records, reorder, etc.
  - **Verify:** Comprehensive, clear

- [ ] 8. Update `AGENTS.md`
  - **Add:** Reference to schema editing in Architecture section
  - **Example:** "Post-generation editing: See docs/API_CONTRACTS.md section 1.5 for field/stage endpoints"
  - **Verify:** Added

- [ ] 9. Verify documentation completeness
  - **Check:** No "TODO", no placeholder text
  - **Check:** All links valid
  - **Check:** Examples match actual API behavior
  - **Verify:** Grep finds no TODOs

### Verification
```bash
# Verify documentation exists and is readable
grep -n "POST /api/v1/crm/{crm_id}/fields" docs/API_CONTRACTS.md
grep -n "Type Conversion" docs/API_CONTRACTS.md
grep -n "Field Renaming" docs/API_CONTRACTS.md
ls docs/SCHEMA_EDITING.md  # File exists

# Verify no broken TODOs
grep -r "TODO\|FIXME" docs/ # Should return nothing (or only expected items)
```

---

## FEAT-006: Comprehensive End-to-End Testing

**Complexity:** Medium  
**Duration:** 3-4 hours  
**Depends on:** FEAT-001–FEAT-005 (all features complete)

### What
Comprehensive integration and end-to-end tests covering all phases: field preservation, backend API, frontend editor, AI tools. Test happy paths and edge cases. Verify no regressions.

### Steps

- [ ] 1. Create `backend/tests/test_e2e_crm_generation_and_editing.py`
  - **Scenarios:**
    1. Generate CRM with 5 fields → verify all 5 in schema
    2. Add field via API → verify count increments
    3. Delete field with records → verify 409 warning
    4. Delete field without records → verify successful deletion
    5. Reorder fields → verify order preserved
    6. Update field type (safe) → verify type changed
    7. Attempt unsafe type conversion → verify 409
    8. Add/delete/reorder stages → verify all work
  - **Verify:** All scenarios pass

- [ ] 2. Add cross-tenant isolation tests
  - **Tests:** User A cannot read/edit User B's CRM
  - **Files:** All field/stage endpoints tested with wrong user
  - **Verify:** All auth tests pass

- [ ] 3. Add edge case tests
  - **Cases:**
    - Field with special chars → normalized to valid key
    - Duplicate field names → rejected 409
    - Field name collision with reserved names → rejected 409
    - Select field without options → rejected 422
    - Reorder with missing field → rejected 422
    - Delete non-existent field → 404
    - Update non-existent field → 404
  - **Verify:** All edge cases handled

- [ ] 4. Add record safety tests
  - **Cases:**
    - Add field to entity with records → works (new records support field)
    - Delete field with records → 409 warning
    - Type change (safe) with records → works
    - Type change (unsafe) with records → consider safety (may need migration or prevention)
  - **Verify:** All cases pass

- [ ] 5. Create frontend integration tests (if test infrastructure exists)
  - **File:** `frontend/src/__tests__/e2e/crm-editing.spec.tsx` (or similar)
  - **Tests:**
    - Generate CRM → display in UI
    - Click [Edit CRM] → editor opens
    - Add field → field appears
    - Save changes → API called, success message
    - Cancel → modal closes, changes discarded
    - API error → error displayed
  - **Verify:** Tests pass (if infrastructure supports them)

- [ ] 6. Add performance tests
  - **Tests:** Edit CRM with 50+ fields, 30+ stages → operations complete in < 1 second
  - **Verify:** Performance acceptable

- [ ] 7. Add backward compatibility tests
  - **Tests:** Old CRM configs (created before schema editing) can be edited
  - **Verify:** No migration errors, existing schemas still work

- [ ] 8. Run full regression test suite
  - **Verify:** `python -m pytest backend/tests/ -v` — ALL tests pass
  - **Verify:** No broken functionality

- [ ] 9. Create test utilities in `backend/tests/conftest.py`
  - **Helpers:**
    ```python
    @pytest.fixture
    def crm_with_n_fields(n: int) -> CRMConfiguration:
        # Generate CRM with n fields
        pass

    @pytest.fixture
    def crm_with_records(crm: CRMConfiguration, count: int) -> tuple[CRMConfiguration, list[UUID]]:
        # Create CRM and N records
        pass

    @pytest.fixture
    def authenticated_user_a() -> dict:
        # Auth context for user A
        pass

    @pytest.fixture
    def authenticated_user_b() -> dict:
        # Auth context for user B
        pass
    ```
  - **Verify:** Helpers work

- [ ] 10. Create test documentation
  - **File:** `backend/tests/README.md`
  - **Content:** Test structure, how to run suites, how to add tests
  - **Examples:** Authorization tests, schema operation tests
  - **Verify:** Documentation clear and runnable

### Verification
```bash
cd backend

# Run end-to-end tests
python -m pytest backend/tests/test_e2e_crm_generation_and_editing.py -v

# Run auth tests
python -m pytest backend/tests/ -k 'authorization' -v

# Run record safety tests
python -m pytest backend/tests/ -k 'record' -v

# Full test suite (should all pass)
python -m pytest backend/tests/ -v

# Coverage check
python -m pytest backend/tests/ --cov=app.routers --cov=app.services --cov-report=term-missing
# Target: > 90% coverage

# Manual end-to-end flow
# 1. Generate CRM with custom fields
# 2. Save CRM
# 3. Edit: Add field, reorder, save
# 4. Edit: Delete field, save
# 5. Verify all changes persisted
# 6. Create record with new field schema
# 7. Verify record validation works
```

---

## Integration Verification

After all FEATs complete, verify:

1. **Full system test:**
   ```bash
   cd backend && python -m pytest backend/tests/ -v
   cd frontend && npm test  # if applicable
   ```

2. **Manual end-to-end workflow:**
   - Start dev servers: `./start-dev.bat`
   - Generate a CRM (SalesCRM, ServiceCRM, RecruitmentCRM)
   - Verify all user-requested fields are in schema
   - Click [Edit CRM]
   - Add 3 fields, reorder 2, delete 1
   - Save changes
   - Verify persistence
   - Create a record with new schema
   - Verify no errors

3. **Cross-CRM validation:**
   - Repeat workflow with different CRM types
   - Verify editor works identically for all (no hardcoded logic)

4. **Authorization validation:**
   - Test with 2 different users
   - Verify User A cannot edit User B's CRM
   - Verify 403/404 responses appropriate

---

## Implementation Order and Dependencies

```
FEAT-001: Field Preservation Fix
    ↓
FEAT-002: Backend Schema Editing API
    ├─→ FEAT-003: Frontend Editor Component
    ├─→ FEAT-004: AI Tooling
    └─→ FEAT-005: Documentation
         ↓
    FEAT-006: Comprehensive Testing
         ↓
    Integration Verification & Deployment
```

**Strict order:** FEAT-001 → FEAT-002 → {FEAT-003, FEAT-004, FEAT-005} → FEAT-006

FEATs 003, 004, 005 can run in parallel once FEAT-002 completes.

---

## Success Criteria

- ✅ User requests N fields → generated schema has N fields (no silent drops)
- ✅ All 8 field/stage endpoints implemented, tested, authorized
- ✅ Frontend editor works for all CRM types (generic, no hardcoding)
- ✅ Copilot can call schema tools
- ✅ Documentation complete and accurate
- ✅ All tests pass; >90% code coverage
- ✅ No regressions in existing functionality
- ✅ Backward compatible with existing CRM configs

---

## Notes

- **Verification:** Each FEAT has explicit verification steps. Run them before claiming FEAT complete.
- **Database:** No migrations needed. JSONB configuration_version tracking already in place.
- **Authorization:** RLS policies + application-level checks enforce ownership. Never trust client-provided user_id.
- **Secrets:** .env files are never committed. Use environment variables.
- **Testing:** All new code must have tests. Run full test suite before submitting.

