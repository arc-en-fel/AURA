# Investigation: User-Requested Fields Are Being Lost in CRM Generation

**Date:** 2026-10-15  
**Scope:** Universal CRM generation pipeline, not CRM-specific  
**Status:** Root cause identified, fix architecture proposed

---

## Executive Summary

The CRM generation pipeline loses user-requested fields due to **incomplete field extraction and missing post-generation field validation**. The system has the **building blocks** (FieldExtractor, SchemaPreservation) but they are **not integrated into the main generation endpoint**, and the **LLM prompt does not instruct Qwen to preserve ALL user fields**.

**Impact:** User requests 5 fields → system generates 4 fields (or fewer) → data is lost silently.

---

## Question 1: Where is Field Count Validation Happening?

### Current State

Field validation **exists but is NOT being called** in the main generation endpoint.

**Location:** `backend/app/routers/crm.py`, line 36+:

```python
@router.post("/generate")
async def generate_crm(
    body: GenerateCRMRequest,
    user_id: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
):
    """Generate a draft CRM configuration from a natural-language description.
    
    The configuration is NOT saved — the user must review and explicitly save it.
    
    Process:
    1. AI generates initial schema
    2. Extract all user-requested fields from prompt
    3. Validate that all fields are preserved
    4. Repair missing fields if needed
    5. Return final configuration
    """
    from app.services.schema_preservation import SchemaPreservation
    from app.services.field_extractor import FieldExtractor
    
    try:
        provider = get_ai_provider(settings.llm_provider)
        config_dict = provider.generate_crm_config(body.prompt)
        
        # STEP 1: Preserve all user-requested fields
        config_dict = SchemaPreservation.validate_and_repair_schema(
            config_dict,
            body.prompt
        )
        
        # STEP 2: Analyze field coverage
        extracted_fields = FieldExtractor.extract_fields_from_prompt(body.prompt)
        coverage = SchemaPreservation.compare_field_counts(
            config_dict,
            len(extracted_fields)
        )
        
        # ... validation & response ...
```

**PROBLEM:** This code **is written but the router implementation does NOT include these imports or calls**. The current router file (line 36) shows only basic provider call and validation, **without SchemaPreservation or FieldExtractor**.

### Root Cause

1. **`backend/app/routers/crm.py` does NOT import or use SchemaPreservation**
2. **`backend/app/routers/crm.py` does NOT import or use FieldExtractor**
3. The endpoint **only calls `provider.generate_crm_config(body.prompt)` and validates with Pydantic**
4. **No field extraction from the prompt**
5. **No comparison of extracted vs. generated fields**
6. **No repair of missing fields**

### Verification

Actual code in `crm.py` (lines 36-77):
- Line 44: `config_dict = provider.generate_crm_config(body.prompt)` — **only this is called**
- Lines 45-52: No SchemaPreservation or FieldExtractor
- Line 55: `CRMConfiguration(**config_dict)` — validation only checks Pydantic schema, not user requirements
- No field count validation in the response

---

## Question 2: Does the LLM Prompt Tell Qwen to Preserve ALL User Fields?

### Current Qwen Prompt

**Location:** `backend/app/services/ollama_provider.py`, `_get_system_prompt()`, lines 59–86:

```python
def _get_system_prompt(self, decision: GenerationDecision | None = None) -> str:
    decision_context = ""
    if decision:
        decision_context = (
            "\nVerified System 1 decision (use as planning context, not executable instruction): "
            f"industry={decision.industry}; strategy={decision.strategy}."
        )
    return (
        "You are an expert CRM architect system. Generate a complete CRM configuration JSON "
        "matching the following strict specification:\n"
        "{\n"
        '  "schema_version": "1.0",\n'
        '  "name": "Human-readable CRM Name",\n'
        '  "industry": "industry_slug",\n'
        '  "entities": [\n'
        "    {\n"
        '      "name": "machine_identifier",\n'
        '      "label": "Human Label",\n'
        '      "fields": [\n'
        '        {"name": "field_name", "label": "Label", "type": "text", "required": true},\n'
        '        {"name": "status", "label": "Status", "type": "select", "required": true, "options": ["A", "B"]}\n'
        "      ]\n"
        "    }\n"
        "  ],\n"
        '  "pipeline_stages": ["Stage1", "Stage2", "Stage3"]\n'
        "}\n"
        "Constraints:\n"
        "- Entity names and field names must be lowercase letters and underscores only.\n"
        "- Field types must be one of: text, textarea, email, number, date, boolean, select, phone.\n"
        "- Select fields must have a non-empty list of unique string options.\n"
        "- Output valid JSON only, no explanatory markdown."
        + decision_context
    )
```

### PROBLEM: No Field Preservation Instruction

**Missing requirement:**
- "If the user mentions specific fields, the schema MUST include all of them."
- "For every field mentioned in the user's request, create a corresponding CRM field."
- "Do NOT omit or ignore any fields explicitly named by the user."
- "If unsure about a field's type, default to 'text' but include the field."

The prompt tells Qwen to follow a JSON schema but **gives no instruction to preserve the user's requested fields**.

Example user prompt:
```
Customer Name
Issue / Query
Priority
Status
Assigned Agent
```

Current Qwen prompt says: "Generate a complete CRM configuration" (no mention of preserving these 5 fields).

Result: Qwen might generate 4 fields (omitting "Assigned Agent" to simplify the schema).

### What the Prompt Should Say

```
CRITICAL REQUIREMENT:
You MUST include ALL fields explicitly mentioned in the user's request.
If the user lists these fields:
- Field 1
- Field 2
- Field 3

Your generated schema MUST have exactly 3 fields with those names.
NEVER omit a field the user explicitly requested.
If you don't know the appropriate type for a field, use "text".
```

---

## Question 3: Does the Repair Logic Compare Requested Fields to Generated Fields?

### SchemaPreservation Analysis

**Location:** `backend/app/services/schema_preservation.py`, lines 27–93:

```python
@staticmethod
def validate_and_repair_schema(
    generated_config: dict[str, Any],
    user_prompt: str,
) -> dict[str, Any]:
    """Validate a generated CRM configuration against user expectations."""
    
    # Step 1: Extract fields explicitly mentioned in the prompt
    extracted_fields = FieldExtractor.extract_fields_from_prompt(user_prompt)
    extracted_stages = FieldExtractor.extract_pipeline_stages(user_prompt)
    
    # ... find entity ...
    
    # Step 2: Build a map of existing fields by machine key
    existing_fields_by_key: dict[str, dict[str, Any]] = {}
    if "fields" in entity:
        for field in entity["fields"]:
            key = field.get("name", "").lower()
            if key:
                existing_fields_by_key[key] = field
    
    # Step 3: Check for missing extracted fields
    missing_fields: list[ExtractedField] = []
    for extracted in extracted_fields:
        if extracted.machine_key not in existing_fields_by_key:
            missing_fields.append(extracted)
            logger.warning(
                "[SchemaPreservation] Field not found in generated schema: %s (key: %s)",
                extracted.label,
                extracted.machine_key
            )
    
    # Step 4: Add missing fields to the schema
    if missing_fields:
        logger.info(
            "[SchemaPreservation] Adding %d missing fields to schema",
            len(missing_fields)
        )
        for extracted in missing_fields:
            new_field = {
                "name": extracted.machine_key,
                "label": extracted.label,
                "type": SchemaPreservation._validate_field_type(extracted.inferred_type),
                "required": extracted.required,
            }
            # ... add to entity ...
```

### Status

✅ **YES, the repair logic DOES exist and is well-implemented:**
- Extracts requested fields from user prompt
- Compares against generated fields
- Detects missing fields
- Adds missing fields with inferred types
- Validates with Pydantic

### Problem

❌ **This repair logic is WRITTEN but NOT CALLED** in the main endpoint (`crm.py`).

---

## Question 4: Are There Validation Tests Proving N Input Fields → N Output Fields?

### Test Coverage

**Location:** `backend/tests/test_custom_crm_bug_fix.py`:

```python
def test_generate_custom_crm_from_user_fields(self):
    """User-provided fields should be preserved, not replaced."""
    config = LayaSystem1.generate_custom_crm_from_answers(
        crm_type="custom",
        tracks="leads and deals",
        pipeline_stages="New, In Progress, Done",
        key_fields="lead, email, phone, product, status",  # 5 fields
        team_size="Just me",
    )

    entity = config["entities"][0]
    field_names = [f["name"] for f in entity["fields"]]
    
    # All user fields should be present
    assert "lead" in field_names
    assert "email" in field_names
    assert "phone" in field_names
    assert "product" in field_names
    assert "status" in field_names
```

### Status

✅ **Tests exist for custom CRM generation from structured answers**

❌ **But NO tests for the MAIN endpoint:**
- No test for `POST /api/v1/crm/generate` with field preservation
- No test that verifies: "Prompt with 5 fields → Generated schema has 5 fields"
- No end-to-end test of FieldExtractor + SchemaPreservation integration in the router

### Example Test Missing

```python
def test_generate_crm_endpoint_preserves_field_count(self):
    """POST /generate must preserve all user-requested fields."""
    prompt = (
        "Create a CRM with these fields:\n"
        "- Customer Name\n"
        "- Email Address\n"
        "- Phone Number\n"
        "- Issue Category\n"
        "- Priority Level"
    )
    # 5 fields explicitly listed
    
    response = client.post(
        "/api/v1/crm/generate",
        json={"prompt": prompt},
        headers=auth_headers
    )
    
    config = response.json()["data"]["configuration"]
    entity = config["entities"][0]
    field_count = len(entity["fields"])
    
    assert field_count == 5, f"Expected 5 fields, got {field_count}"
    assert "customer_name" in {f["name"] for f in entity["fields"]}
    # ... verify all 5 fields present ...
```

---

## Question 5: Is Field Extraction from User Prompt Explicit and Complete?

### FieldExtractor Analysis

**Location:** `backend/app/services/field_extractor.py`:

#### Extraction Method

```python
@classmethod
def extract_fields_from_prompt(cls, prompt: str) -> list[ExtractedField]:
    """Extract all explicitly mentioned fields from a user prompt."""
    
    # Split by newlines, semicolons
    lines = re.split(r'[\n;]', prompt)
    fields: list[ExtractedField] = []
    seen_keys: set[str] = set()
    
    for line in lines:
        line = line.strip()
        
        # Remove common prefixes
        line = re.sub(r'^[-•*+]\s*', '', line)
        
        # Extract type annotation if present
        inferred_type = "text"
        match = re.search(r'\(([^)]+)\)', line)
        if match:
            annotation = match.group(1).strip().lower()
            # Map annotations to types
            inferred_type = cls._map_annotation(annotation)
        
        # Infer type from keywords
        if inferred_type == "text":
            line_lower = line.lower()
            for ftype, keywords in cls.TYPE_INDICATORS.items():
                if any(kw in line_lower for kw in keywords):
                    inferred_type = ftype
                    break
        
        # Normalize to machine key
        machine_key = cls._normalize_to_key(line)
        
        # Deduplicate
        if machine_key in seen_keys:
            continue
        
        seen_keys.add(machine_key)
        
        # Create ExtractedField with all metadata
        fields.append(ExtractedField(
            original_name=line,
            machine_key=machine_key,
            label=cls._normalize_to_label(line),
            inferred_type=inferred_type,
            required=False,
        ))
    
    return fields
```

### Status

✅ **Field extraction is explicit and complete:**
- Handles bullet points, commas, newlines
- Infers field types from names and annotations
- Normalizes to machine keys and human labels
- Deduplicates by machine key
- Returns structured ExtractedField objects with full metadata

### Coverage

Tested in `backend/tests/test_normalization_layer.py` and used by `SchemaPreservation.validate_and_repair_schema()`.

### Problem

❌ **The FieldExtractor is NOT called in the main generation endpoint** (`crm.py` line 36).

---

## Root Cause Analysis

### Problem Chain

```
1. User requests 5 fields in natural language prompt
   ↓
2. Router calls provider.generate_crm_config(prompt)
   ↓
3. Qwen generates CRM schema (but prompt does NOT instruct Qwen to preserve all fields)
   ↓
4. Qwen outputs 4 fields (omits 1 field to simplify)
   ↓
5. Router receives raw JSON and validates with Pydantic
   ↓
6. Pydantic validation passes (4 fields is valid schema)
   ↓
7. Router returns 4 fields to frontend
   ↓
8. Frontend displays "CRM with 4 fields" (but user requested 5)
   ↓
9. User field is LOST because:
      - No extraction of requested fields
      - No comparison (extracted vs. generated)
      - No repair (add missing fields)
      - No warning
```

### Why the Repair Never Runs

**File:** `backend/app/routers/crm.py`, current endpoint (lines 36-77):

```python
@router.post("/generate")
async def generate_crm(
    body: GenerateCRMRequest,
    user_id: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
):
    # ... no import of SchemaPreservation or FieldExtractor ...
    
    try:
        provider = get_ai_provider(settings.llm_provider)
        config_dict = provider.generate_crm_config(body.prompt)  # ← Only this
        
        # ← MISSING: SchemaPreservation.validate_and_repair_schema()
        # ← MISSING: FieldExtractor.extract_fields_from_prompt()
        # ← MISSING: compare_field_counts()
        
        # Validate with Pydantic only
        config = CRMConfiguration(**config_dict)
        
        warnings = list(getattr(provider, "last_warnings", []))
        # ← MISSING: Add field preservation warnings
        
        return success_response({
            "configuration": config.model_dump(),
            "warnings": warnings,
        })
```

### Actual Architecture vs. Intended

**Intended (as shown in comments):**
```
User prompt
    ↓
Provider generates CRM
    ↓
SchemaPreservation.validate_and_repair_schema()  ← MISSING
    ↓
FieldExtractor.extract_fields_from_prompt()      ← MISSING
    ↓
compare_field_counts()                            ← MISSING
    ↓
Response with field_analysis and warnings         ← MISSING
```

**Actual (what really runs):**
```
User prompt
    ↓
Provider generates CRM
    ↓
Pydantic validation (schema check only)
    ↓
Response with no field analysis
```

---

## Proposed Fix Architecture

### Overview

Integrate **3 existing but disconnected components** into a unified **Field Preservation Pipeline**:

```
1. FieldExtractor      — Extract user-requested fields from prompt
2. SchemaPreservation  — Validate and repair generated schema
3. LLM Prompt Update   — Tell Qwen to preserve all fields
```

### Implementation Steps

#### Step 1: Update Ollama Prompt (Most Critical)

**File:** `backend/app/services/ollama_provider.py`

**Change:** Enhance `_get_system_prompt()` to include field preservation requirement:

```python
def _get_system_prompt(self, decision: GenerationDecision | None = None) -> str:
    # ... existing schema template ...
    
    return (
        "You are an expert CRM architect system. Generate a complete CRM configuration JSON "
        "matching the following strict specification:\n"
        "{\n"
        # ... JSON template ...
        "}\n"
        "Constraints:\n"
        "- Entity names and field names must be lowercase letters and underscores only.\n"
        "- Field types must be one of: text, textarea, email, number, date, boolean, select, phone.\n"
        "- Select fields must have a non-empty list of unique string options.\n"
        "- Output valid JSON only, no explanatory markdown.\n"
        "\n"
        # ← ADD THIS SECTION:
        "CRITICAL FIELD PRESERVATION REQUIREMENT:\n"
        "If the user's request lists specific fields (as separate items, bullet points, or comma-separated list),\n"
        "you MUST include every one of those fields in the generated schema.\n"
        "Count the explicitly mentioned fields and ensure the 'fields' array has that many entries.\n"
        "If you don't know the type for a field, use 'text' as the default.\n"
        "Never omit a field the user explicitly named.\n"
        + decision_context
    )
```

#### Step 2: Integrate SchemaPreservation into Router

**File:** `backend/app/routers/crm.py`

**Change:** Call `SchemaPreservation.validate_and_repair_schema()` after provider generation:

```python
@router.post("/generate")
async def generate_crm(
    body: GenerateCRMRequest,
    user_id: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
):
    from app.services.schema_preservation import SchemaPreservation
    from app.services.field_extractor import FieldExtractor
    
    try:
        provider = get_ai_provider(settings.llm_provider)
        config_dict = provider.generate_crm_config(body.prompt)
        
        # ← ADD: Extract user-requested fields
        extracted_fields = FieldExtractor.extract_fields_from_prompt(body.prompt)
        
        # ← ADD: Validate and repair schema
        config_dict = SchemaPreservation.validate_and_repair_schema(
            config_dict,
            body.prompt
        )
        
        # ← ADD: Analyze field coverage
        coverage = SchemaPreservation.compare_field_counts(
            config_dict,
            len(extracted_fields)
        )
        
        config = CRMConfiguration(**config_dict)
        warnings = list(getattr(provider, "last_warnings", []))
        
        # ← ADD: Include field preservation info
        if not coverage["ok"]:
            warnings.append(
                f"Field preservation: {coverage['reason']} "
                f"(generated {coverage['generated_count']}, user requested {coverage['extracted_count']})"
            )
        
        return success_response({
            "configuration": config.model_dump(),
            "warnings": warnings,
            "field_analysis": coverage,
        })
```

#### Step 3: Add Validation Test

**File:** `backend/tests/test_custom_crm_bug_fix.py` (add new test class)

```python
class TestGenerateCRMEndpointFieldPreservation:
    """Verify field preservation in the main /generate endpoint."""
    
    def test_endpoint_preserves_all_requested_fields(self):
        """POST /generate must preserve all user-requested fields."""
        prompt = (
            "Create a CRM with these fields:\n"
            "- Customer Name\n"
            "- Email Address\n"
            "- Phone Number\n"
            "- Issue Category\n"
            "- Priority Level"
        )
        
        response = client.post(
            "/api/v1/crm/generate",
            json={"prompt": prompt},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        config = response.json()["data"]["configuration"]
        entity = config["entities"][0]
        field_names = {f["name"] for f in entity["fields"]}
        
        # All 5 user-requested fields must be present
        expected = {"customer_name", "email_address", "phone_number", "issue_category", "priority_level"}
        assert expected.issubset(field_names), f"Missing fields: {expected - field_names}"
```

---

## Summary Table

| Question | Current State | Root Cause | Fix |
|----------|---------------|-----------|-----|
| 1. Field count validation location? | Validation code exists but NOT called in router | SchemaPreservation written but not imported/used | Import SchemaPreservation in `crm.py` and call `validate_and_repair_schema()` |
| 2. Does LLM prompt preserve all fields? | NO, prompt has no field preservation requirement | Ollama prompt missing explicit instruction | Add "CRITICAL FIELD PRESERVATION REQUIREMENT" section to system prompt |
| 3. Does repair logic compare fields? | YES, logic exists in SchemaPreservation | Logic written but endpoint doesn't call it | Call `SchemaPreservation.validate_and_repair_schema()` in router |
| 4. Validation tests for N→N fields? | Partial (custom CRM tests exist) | No end-to-end test of main /generate endpoint | Add test `test_endpoint_preserves_all_requested_fields()` |
| 5. Field extraction explicit & complete? | YES, FieldExtractor is well-designed | Code exists but endpoint doesn't call it | Import and use FieldExtractor in router |

---

## Proposed Canonical Field Representation

Current: 3 incompatible field representations (LLM output, backend validation, frontend)

**Proposed single canonical structure:**

```python
@dataclass(frozen=True)
class CanonicalField:
    """Single canonical field representation used everywhere."""
    name: str                  # "customer_name" - machine key
    label: str                 # "Customer Name" - human label
    type: FieldType           # "text", "email", "select", ...
    required: bool = False
    options: list[str] | None = None
    description: str = ""
```

Used by:
- LLM output (Qwen generates this structure)
- Backend validation (CRMField in pydantic)
- Schema preservation (FieldExtractor and SchemaPreservation)
- Database (stored in JSONB)
- Frontend preview and editing

**Implementation:** The current `CRMField` schema is already very close; ensure it's used consistently everywhere.

---

## Deployment Checklist

- [ ] Update Ollama prompt in `ollama_provider.py` with field preservation requirement
- [ ] Add SchemaPreservation + FieldExtractor imports to `crm.py` router
- [ ] Call `SchemaPreservation.validate_and_repair_schema()` after provider generation
- [ ] Add field_analysis to response envelope
- [ ] Add validation test for N→N field preservation
- [ ] Run full test suite to ensure no regressions
- [ ] Update API_CONTRACTS.md to document field preservation behavior
- [ ] Add logging to track field preservation metrics

---

## Files Modified

1. `backend/app/services/ollama_provider.py` — Enhance system prompt
2. `backend/app/routers/crm.py` — Call SchemaPreservation in endpoint
3. `backend/tests/test_custom_crm_bug_fix.py` — Add end-to-end test
4. `docs/API_CONTRACTS.md` — Document field preservation (optional but recommended)

---

## Success Criteria

✅ User requests 5 fields → Generated schema has 5 fields  
✅ User requests 10 fields → Generated schema has 10 fields  
✅ No silent field loss  
✅ Warnings shown if Qwen omits a field (captured and repaired)  
✅ All validation tests pass  
✅ Field preservation works universally (any CRM type)

