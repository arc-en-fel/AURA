# AURA Phase 1: Implementation Plan

**Date:** 2024  
**Scope:** Fix critical violations C1–C5  
**Duration:** Estimated 18–24 developer-days  
**Branch:** `phase-1-critical-fixes`  

---

## PLAN STRUCTURE

This plan sequences the five critical violations (C1–C5) in dependency order. Each item leaves the codebase in a buildable, testable state. Verification uses the project's actual build and test commands.

---

## IMPLEMENTATION PLAN

### 1. **Fix C4: Remove Hard-Coded "lead" Entity Fallback**

**What:** Eliminate the fallback to "lead" entity name when `config.entities` is empty. Add explicit validation.

**Rationale:** C4 is the smallest fix with zero downstream dependencies. Fixing it first removes silent failures from analytics and evolution proposals.

**Files to Modify:**
- `backend/app/routers/evolution.py` (line 84)

**Detailed Changes:**

**File: `backend/app/routers/evolution.py`**
- **Location:** Line 84 in `create_proposal()` function
- **Current:**
  ```python
  primary_entity = config.entities[0].name if config.entities else "lead"
  ```
- **Changed to:**
  ```python
  if not config.entities:
      return error_response(422, "VALIDATION_ERROR", "CRM configuration has no entities defined.")
  primary_entity = config.entities[0].name
  ```

**Tests to Write:**
- Test that proposal creation fails with clear error if CRM has no entities
- Test that proposal creation succeeds when CRM has one entity (any name)
- Test that proposal creation uses first entity regardless of name

**Verification:**
```bash
cd backend
python -m pytest tests/test_evolution_proposals.py -v -k "entity" --tb=short
# Expected: all entity-related tests pass
```

**Estimated Effort:** 0.5 day (1 line fix + 1 test)

---

### 2. **Fix C1: Remove Hard-Coded Form Status Defaults**

**What:** Replace the arbitrary `['New', 'Active', 'Completed']` fallback with dynamic logic that reads from CRM configuration.

**Rationale:** C1 affects every record creation form. Fix next to ensure form renders correctly for all CRM types.

**Files to Modify:**
- `frontend/src/features/records/RecordFormModal.tsx` (lines 170–180)

**Detailed Changes:**

**File: `frontend/src/features/records/RecordFormModal.tsx`**
- **Location:** `renderFieldInput()` function, `case 'status'` block
- **Current:**
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
          //                            ↑↑↑ PROBLEM: Arbitrary fallback
          value={String(val ?? statusOptions[0] ?? '')}
          onChange={(e) => handleChange(field.name, e.target.value)}
          error={errorMsg}
        />
      </div>
    );
  }
  ```

- **Changed to:**
  ```tsx
  case 'status': {
    const stages = activeCRM?.configuration?.pipeline_stages || [];
    const statusOptions = field.options && field.options.length > 0 ? field.options : stages;
    
    // NEW: If both field options and pipeline stages are empty, show validation error
    if (statusOptions.length === 0) {
      return (
        <div key={field.name}>
          <label className="block text-xs font-semibold text-slate-700 mb-1.5 uppercase tracking-wider">
            {field.label} {field.required && <span className="text-rose-500">*</span>}
          </label>
          <div className="border border-rose-400 rounded-lg p-3 bg-rose-50/20 text-xs text-rose-600 font-medium">
            Status field has no options configured in CRM schema. Please contact your administrator to add status options to the pipeline.
          </div>
        </div>
      );
    }
    
    return (
      <div key={field.name}>
        <Select
          label={field.label}
          required={field.required}
          options={statusOptions}
          value={String(val ?? statusOptions[0] ?? '')}
          onChange={(e) => handleChange(field.name, e.target.value)}
          error={errorMsg}
        />
      </div>
    );
  }
  ```

**Tests to Write:**
- Test that status field renders with field.options when available
- Test that status field renders with pipeline_stages when field.options empty but pipeline_stages exist
- Test that status field shows error message when both field.options and pipeline_stages are empty
- Test that status field value persists correctly across re-renders

**Verification:**
```bash
cd frontend
npm run test -- RecordFormModal.tsx --watch=false
# Expected: all status field tests pass
```

**Estimated Effort:** 1 day (1 component, logic + error handling, 4 test cases)

---

### 3. **Fix C3: Remove Hard-Coded Won_Stages Detection**

**What:** Replace the fixed set of won-stage names with dynamic logic that derives meaningful completion metrics from CRM configuration.

**Rationale:** C3 breaks analytics calculations for non-sales CRMs. Must fix before C2 (analytics schema).

**Files to Modify:**
- `backend/app/routers/evolution.py` (lines 93–98)
- `backend/app/routers/workflows.py` (lines 135–160) — related code that also needs updating
- `backend/app/schemas/crm.py` — optional: add config fields for outcome metrics

**Approach:**

Instead of hard-coded won_stages, implement a strategy:
1. If CRM configuration explicitly defines `outcome_stages`, use those
2. Otherwise, compute generic completion rates:
   - For healthcare: count patients in "last stage" or "discharged"
   - For e-commerce: count orders in "completed" or "fulfilled"
   - For support: count tickets in "resolved" or "closed"
3. Return `completion_rate` (generic term) instead of `conversion_rate` (sales-specific)

**Files: `backend/app/routers/evolution.py`**
- **Location:** Lines 93–98 in `create_proposal()` function
- **Current:**
  ```python
  if stage_field and total > 0:
      won_stages = {"Won", "won", "Closed Won", "closed_won"}
      by_stage = repo.count_records_by_field(str(crm_id), primary_entity, stage_field.name)
      won = sum(entry.get("count", 0) for entry in by_stage if entry.get("value") in won_stages)
      analytics_data["won_leads"] = won
      analytics_data["conversion_rate"] = round(won / total, 4)
  ```

- **Changed to:**
  ```python
  if stage_field and total > 0 and config.pipeline_stages:
      # Derive outcome stages from CRM configuration
      # Strategy: Last stage(s) represent completion/success
      outcome_stages_config = getattr(config, 'outcome_stages', None)
      if outcome_stages_config:
          # Explicit configuration (future enhancement)
          outcome_stages = set(outcome_stages_config)
      else:
          # Default: Last stage in pipeline represents success
          outcome_stages = {config.pipeline_stages[-1]} if config.pipeline_stages else set()
      
      by_stage = repo.count_records_by_field(str(crm_id), primary_entity, stage_field.name)
      completed = sum(
          entry.get("count", 0) 
          for entry in by_stage 
          if entry.get("value") in outcome_stages
      )
      analytics_data["completion_rate"] = round(completed / total, 4) if total > 0 else 0.0
      analytics_data["completed_records"] = completed
  ```

**Schema Update (Optional for Phase 1, but recommended):**

**File: `backend/app/schemas/crm.py`**
- Add optional field to CRMConfiguration:
  ```python
  class CRMConfiguration(StrictModel):
      # ... existing fields ...
      outcome_stages: list[str] | None = Field(default=None, max_length=30)
      # Explicit stages representing successful outcomes (e.g., "Won", "Resolved", "Completed")
      # If not set, last pipeline stage is used as default
  ```

**Tests to Write:**
- Test that completion_rate is 0.0 when no records in outcome stage
- Test that completion_rate is 1.0 when all records in outcome stage
- Test that completion_rate uses last stage by default
- Test that completion_rate uses explicit outcome_stages if configured
- Test across 3+ CRM types (sales, support, e-commerce)

**Verification:**
```bash
cd backend
python -m pytest tests/test_evolution_proposals.py::TestAnalyticsComputation -v --tb=short
# Expected: completion_rate tests pass across all CRM types
```

**Estimated Effort:** 2 days (logic refactor + optional schema update + 5 test cases)

---

### 4. **Fix C2: Replace Hard-Coded Analytics Schema**

**What:** Replace sales-specific `AnalyticsData` schema with a generic, dynamic schema that adapts to CRM configuration.

**Rationale:** C2 is complex because it affects three layers: schema (backend contract), backend computation, and frontend rendering. It's also the most critical for universal CRM support.

**Files to Modify:**
- `backend/app/schemas/crm.py` (lines 248–255)
- `backend/app/routers/workflows.py` (lines 30–160) — `get_analytics()` function
- `frontend/src/features/analytics/AnalyticsPage.tsx` (lines 35–165) — analytics rendering
- `backend/app/routers/responses.py` — optional: update success_response() if needed

**Approach:**

**Step 1: Update Schema to Be Generic**

**File: `backend/app/schemas/crm.py`**
- **Location:** Lines 248–255
- **Current (Sales-Only):**
  ```python
  class AnalyticsData(StrictModel):
      total_leads: int = Field(ge=0)
      qualified_leads: int = Field(ge=0)
      won_leads: int = Field(ge=0)
      conversion_rate: float = Field(ge=0, le=1)
      by_source: list[dict[str, Any]] = Field(default_factory=list)
      by_stage: list[dict[str, Any]] = Field(default_factory=list)
  ```

- **Changed to (Generic):**
  ```python
  class AnalyticsData(StrictModel):
      total_records: int = Field(ge=0)
      entity_name: str = Field(min_length=1, max_length=64)
      entity_label: str = Field(min_length=1, max_length=100)
      by_stage: list[dict[str, Any]] = Field(default_factory=list)
      by_source: list[dict[str, Any]] = Field(default_factory=list)
      numeric_metrics: list[dict[str, Any]] = Field(default_factory=list)
      categorical_metrics: list[dict[str, Any]] = Field(default_factory=list)
      kpi_cards: list[dict[str, Any]] = Field(default_factory=list)
      schema_info: dict[str, Any] = Field(default_factory=dict)
      # Backward compatibility: deprecated fields (for tests that still expect them)
      total_leads: int = Field(default=0, ge=0)
      qualified_leads: int = Field(default=0, ge=0)
      won_leads: int = Field(default=0, ge=0)
      conversion_rate: float = Field(default=0.0, ge=0, le=1)
  ```

**Step 2: Refactor Backend Analytics Computation**

**File: `backend/app/routers/workflows.py`**
- **Location:** Lines 30–160 in `get_analytics()` function
- The current code already computes `by_stage`, `by_source`, `numeric_metrics`, `categorical_metrics` correctly
- Ensure response includes all fields:
  ```python
  return success_response({
      "total_records": total_records,
      "entity_name": entity_name,
      "entity_label": entity_label,
      "by_stage": by_stage,
      "by_source": by_source,
      "numeric_metrics": numeric_metrics,
      "categorical_metrics": categorical_metrics,
      "kpi_cards": kpi_cards,
      "schema_info": {
          "primary_entity_name": entity_name,
          "pipeline_stages": pipeline_stages,
          "stage_field_name": stage_field_name,
          "source_field_name": source_field_name,
          "categorical_fields": [...],
          "numeric_fields": [...]
      },
      # Backward compatibility
      "total_leads": total_records,
      "qualified_leads": 0,  # or compute from config if config.outcome_stages defined
      "won_leads": 0,
      "conversion_rate": 0.0
  })
  ```

**Step 3: Update Frontend to Use Generic Fields**

**File: `frontend/src/features/analytics/AnalyticsPage.tsx`**
- **Location:** Lines 35–165 (entire analytics rendering logic)
- Use `total_records` instead of `total_leads`
- Use `entity_label` from response to dynamically label cards
- Render `kpi_cards` if available
- Render `categorical_metrics` and `numeric_metrics` generically

**Tests to Write:**
- Test AnalyticsData schema validation with generic fields
- Test analytics response includes all required fields
- Test backward compatibility: old code expecting total_leads still works
- Test across 5 CRM types: Sales, Healthcare, Support, E-Commerce, Custom
- Test with zero records
- Test with mixed data (some fields empty, some populated)

**Verification:**
```bash
cd backend
python -m pytest tests/test_schema_editing_api.py tests/test_universal_crm_generation.py -v -k "analytics" --tb=short
cd frontend
npm run test -- AnalyticsPage.tsx --watch=false
# Expected: all analytics tests pass for all CRM types
```

**Estimated Effort:** 3–4 days (schema change, backend refactor, frontend adaptation, 6+ test cases)

---

### 5. **Fix C5: Remove Hard-Coded Industry Taxonomies**

**What:** Remove the pre-built `INDUSTRY_TAXONOMIES` dictionary and implement dynamic CRM generation from user input.

**Rationale:** C5 is the most complex because it requires redesigning the CRM generation logic. It's last because fixing C1–C4 first makes testing and validation easier.

**Files to Modify:**
- `backend/app/services/laya_system1.py` (lines 76–121) — remove INDUSTRY_TAXONOMIES
- `backend/app/services/laya_system1.py` (lines 180–320) — refactor `repair_crm_configuration()` and `generate_scaffold_config()`
- `backend/app/services/ai_provider.py` (lines 99–150) — refactor MockAIProvider.generate_crm_config()
- `backend/app/services/field_extractor.py` — enhance field/entity/stage extraction

**Approach:**

**Step 1: Enhance Field Extraction**

Create/enhance `field_extractor.py` to extract:
- Entity names (e.g., "customer", "patient", "ticket", "shipment")
- Field descriptions (e.g., "customer email", "ticket priority")
- Pipeline stages (e.g., "New → In Progress → Done")

**Step 2: Remove INDUSTRY_TAXONOMIES**

**File: `backend/app/services/laya_system1.py`**
- **Delete:** Lines 76–121 (entire INDUSTRY_TAXONOMIES dictionary)
- This function becomes a fallback only:
  ```python
  @classmethod
  def detect_industry(cls, prompt: str) -> str:
      """Fast rule-based industry hint (for observability only, not for defaults)."""
      # Just returns a label, doesn't drive schema generation
      p = prompt.lower()
      if any(w in p for w in ["health", "clinic", "patient", "medical"]):
          return "healthcare_hint"
      # ... etc ...
      return "general"
  ```

**Step 3: Refactor CRM Generation**

**File: `backend/app/services/laya_system1.py`**
- **Refactor:** `repair_crm_configuration()` and `generate_scaffold_config()` to:
  1. Extract entities, fields, stages from prompt using FieldExtractor
  2. Validate extracted structure
  3. Build minimal CRM with extracted components
  4. No hard-coded defaults per industry

**Example:**
```python
@classmethod
def generate_scaffold_config(cls, prompt: str) -> dict[str, Any]:
    """Generate CRM config dynamically from prompt without taxonomies."""
    cls.validate_prompt_safety(prompt)
    
    # Extract structured info from prompt
    entities = FieldExtractor.extract_entities(prompt)
    fields_by_entity = FieldExtractor.extract_fields(prompt)
    stages = FieldExtractor.extract_pipeline_stages(prompt)
    
    # Determine primary entity
    primary_entity_name = entities[0] if entities else "record"
    
    # Build configuration from extracted components
    config = {
        "schema_version": "1.0",
        "name": cls._infer_crm_name(prompt),
        "industry": cls.detect_industry(prompt),  # Hint only
        "entities": [
            {
                "name": primary_entity_name,
                "label": primary_entity_name.replace("_", " ").title(),
                "fields": fields_by_entity.get(primary_entity_name, [
                    {"name": "name", "label": "Name", "type": "text", "required": True},
                    {"name": "status", "label": "Status", "type": "select", "required": True, "options": stages or ["Active", "Inactive"]},
                ])
            }
        ],
        "pipeline_stages": stages or ["New", "In Progress", "Done"],
    }
    
    CRMConfiguration(**config)
    return config
```

**Step 4: Update MockAIProvider**

**File: `backend/app/services/ai_provider.py`**
- Refactor `generate_crm_config()` to use FieldExtractor instead of keyword matching
- Remove hard-coded option values (Low/Medium/High, Website/Referral/etc.)
- Use generic defaults only

**Step 5: Remove Mock Workflow Hard-Coding**

**File: `frontend/src/services/mockData.ts`**
- Update `INITIAL_WORKFLOWS` to use primary entity from CRM config instead of hard-coded "lead"
- Make workflow entity configurable

**Tests to Write:**
- Test CRM generation for 5+ industry types without code changes
- Test field extraction from prompts
- Test entity name inference
- Test stage extraction from prompts
- Test fallback behavior when extraction fails
- Test dynamic workflows with different entity types
- Test mock data no longer hard-codes "lead"

**Verification:**
```bash
cd backend
python -m pytest tests/test_universal_crm_generation.py -v --tb=short
python -m pytest tests/test_ai_brain.py::TestLayaSystem1 -v --tb=short
# Expected: generation tests pass for arbitrary prompts, not just pre-defined types
```

**Estimated Effort:** 4–5 days (large refactor + FieldExtractor enhancements + 7+ test cases)

---

## REGRESSION TEST SUITE

After completing all fixes, add dedicated regression tests to prevent re-introduction of violations:

**File: `backend/tests/test_phase1_critical_violations.py`** (new)

```python
"""Regression tests for Phase 1 critical violations (C1–C5)."""
import pytest
from app.schemas.crm import CRMConfiguration, CRMEntity, CRMField

class TestC1FormStatusDefaults:
    """C1: Hard-coded form status defaults removed."""
    
    def test_form_renders_field_options_when_available(self):
        # Status field with options should render options
        field = CRMField(name="status", label="Status", type="select", 
                        required=True, options=["Active", "Inactive", "Pending"])
        assert field.options == ["Active", "Inactive", "Pending"]
    
    def test_form_renders_pipeline_stages_when_field_options_empty(self):
        # Status field without options should fallback to pipeline_stages
        # (tested in frontend)
        pass
    
    def test_form_shows_error_when_no_options_and_no_stages(self):
        # If both field.options and pipeline_stages empty, show error
        # (tested in frontend)
        pass

class TestC2AnalyticsSchema:
    """C2: Hard-coded Analytics schema replaced with generic schema."""
    
    def test_analytics_schema_generic_fields(self):
        from app.schemas.crm import AnalyticsData
        # Schema should have generic fields
        assert hasattr(AnalyticsData, 'total_records')
        assert hasattr(AnalyticsData, 'entity_name')
        assert hasattr(AnalyticsData, 'by_stage')
        assert hasattr(AnalyticsData, 'numeric_metrics')
    
    def test_analytics_for_sales_crm(self):
        # Sales CRM analytics should compute correctly
        pass
    
    def test_analytics_for_healthcare_crm(self):
        # Healthcare CRM analytics should compute correctly
        pass
    
    def test_analytics_for_ecommerce_crm(self):
        # E-Commerce CRM analytics should compute correctly
        pass

class TestC3WonStagesHardCoded:
    """C3: Hard-coded won_stages detection removed."""
    
    def test_completion_rate_uses_last_stage_by_default(self):
        # If no explicit outcome_stages config, use last stage
        pass
    
    def test_completion_rate_uses_outcome_stages_config(self):
        # If CRM config has outcome_stages, use those
        pass
    
    def test_completion_rate_across_crm_types(self):
        # Test completion_rate for Sales, Healthcare, Support, E-Commerce
        pass

class TestC4EntityFallback:
    """C4: Hard-coded 'lead' entity fallback removed."""
    
    def test_proposal_fails_if_no_entities(self):
        # If CRM has no entities, return clear error
        pass
    
    def test_proposal_uses_first_entity_name(self):
        # Proposal should use config.entities[0].name
        pass

class TestC5IndustryTaxonomies:
    """C5: Hard-coded industry taxonomies removed."""
    
    def test_crm_generation_for_arbitrary_prompt(self):
        # Generation should work for any prompt, not just pre-defined types
        pass
    
    def test_crm_generation_detects_custom_entities(self):
        # Prompt with custom entity names should extract them
        pass
    
    def test_crm_generation_detects_custom_fields(self):
        # Prompt with custom field descriptions should extract them
        pass
    
    def test_crm_generation_detects_custom_stages(self):
        # Prompt with custom pipeline stages should extract them
        pass
    
    def test_crm_generation_no_sales_bias(self):
        # Healthcare/Support/E-Commerce prompts shouldn't get sales fields
        pass
```

**File: `backend/tests/test_universal_crm_validation.py`** (new)

```python
"""Validation tests for 5 diverse CRM configurations."""
import pytest
from app.schemas.crm import CRMConfiguration

class TestMultiCRMTypeValidation:
    """Validate all CRM types work end-to-end."""
    
    CONFIGS = {
        "sales": {...},      # Traditional SaaS sales CRM
        "healthcare": {...}, # Patient management
        "support": {...},    # Customer support tickets
        "ecommerce": {...},  # Customer + order management
        "custom": {...},     # Completely custom schema
    }
    
    @pytest.mark.parametrize("crm_type", CONFIGS.keys())
    def test_crm_config_valid(self, crm_type):
        config_data = self.CONFIGS[crm_type]
        config = CRMConfiguration(**config_data)
        assert config.entities
        assert config.name
    
    @pytest.mark.parametrize("crm_type", CONFIGS.keys())
    def test_analytics_computation(self, crm_type):
        # Compute analytics for each CRM type
        pass
    
    @pytest.mark.parametrize("crm_type", CONFIGS.keys())
    def test_record_form_rendering(self, crm_type):
        # Frontend should render forms without errors
        pass
    
    @pytest.mark.parametrize("crm_type", CONFIGS.keys())
    def test_evolution_proposals(self, crm_type):
        # Evolution proposals should work for each type
        pass
```

---

## BUILD & TEST COMMANDS

### Backend Build & Test
```bash
cd backend

# Lint
python -m flake8 app/ --max-line-length=120 --ignore=E501,W503

# Type check
python -m mypy app/ --ignore-missing-imports

# Test (specific C# tests)
python -m pytest tests/test_phase1_critical_violations.py -v --tb=short

# Test (universal validation)
python -m pytest tests/test_universal_crm_validation.py -v --tb=short

# Test (all, full regression)
python -m pytest tests/ -v --tb=short

# Coverage report
python -m pytest tests/ --cov=app --cov-report=html
```

### Frontend Build & Test
```bash
cd frontend

# Lint
npm run lint

# Type check
npm run type-check

# Test
npm run test -- --watch=false

# Build
npm run build

# Verify build output
ls -la dist/
```

---

## VERIFICATION CHECKLIST

After implementing all five fixes, verify:

- [ ] C1 fixed: Form doesn't default to ['New', 'Active', 'Completed']
- [ ] C2 fixed: Analytics uses generic schema; all CRM types have meaningful metrics
- [ ] C3 fixed: Completion rate works for non-sales CRMs
- [ ] C4 fixed: Entity fallback removed; clear error if no entities
- [ ] C5 fixed: CRM generation works for arbitrary prompts without code changes

**Cross-CRM Testing:**
- [ ] Sales CRM: Lead → Deal flow works
- [ ] Healthcare CRM: Patient → Treatment → Discharge flow works
- [ ] Support CRM: Ticket → Assigned → Resolved flow works
- [ ] E-Commerce CRM: Customer → Order → Fulfillment flow works
- [ ] Custom CRM: Entirely custom entities/fields/stages work

**Regression Testing:**
- [ ] All existing tests pass (423+ tests)
- [ ] New regression tests pass (10+ C1–C5 specific tests)
- [ ] No breaking changes to public API contracts
- [ ] Database schema compatible (no migrations required)

---

## TIMELINE

Assuming two developers, full-time:

| Phase | Duration | Items |
|-------|----------|-------|
| **Setup** | 0.5 day | Create branch, environment setup |
| **C4 (Entity Fallback)** | 0.5 day | 1-line fix + validation |
| **C1 (Form Status)** | 1 day | 1 component, error handling |
| **C3 (Completion Rate)** | 2 days | Logic refactor, config update |
| **C2 (Analytics)** | 3–4 days | Schema + backend + frontend |
| **C5 (Taxonomies)** | 4–5 days | Large refactor + field extraction |
| **Regression Tests** | 2 days | Write + run test suite |
| **Integration & Review** | 1–2 days | Cross-CRM validation, PR review |
| **Buffer** | 2 days | Fixes for unexpected issues |
| **TOTAL** | **18–24 days** | Two developers, full-time |

---

## NOTES FOR IMPLEMENTATION TEAM

1. **Dependency Order Matters:** Fix C4 → C1 → C3 → C2 → C5 (smallest to largest, dependencies-first)
2. **Database Migrations:** None required — all changes are in application logic
3. **Backward Compatibility:** Maintain old field names in AnalyticsData for tests that depend on them
4. **Test-Driven:** Add tests before fixing code where possible
5. **Use Real CRM Configs:** Don't use mock data; test with generated configs
6. **Review with Architects:** Complex changes (C2, C5) should be reviewed before implementation

---

**Plan Status:** Ready for implementation  
**Next Step:** Create feature branch and begin with C4
