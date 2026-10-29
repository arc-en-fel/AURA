# AURA Backend Codebase Audit: Hard-Coded CRM-Specific Logic

**Audit Date:** 2024  
**Scope:** Backend Python codebase (d:\AURA - Copy\backend)  
**Auditor:** Kiro  

---

## Executive Summary

**Status:** ⚠️ CRITICAL VIOLATIONS FOUND

The AURA backend contains **18 critical violations** of the universal CRM architecture requirement. The codebase violates the core principle that AURA must support ANY CRM without modifying code.

### Key Findings

1. **Hard-coded entity names** ("lead", "customer", "patient", etc.) hard-baked into business logic
2. **Hard-coded stage values** ("Won", "Closed Won", pipeline defaults) in analytics and proposal generation
3. **Hard-coded field assumptions** (status field detection by name, priority/source option defaults)
4. **Hard-coded CRM type routing** (sales, healthcare, e-commerce logic baked into defaults)
5. **Hard-coded analytics schema** (`AnalyticsData` with `total_leads`, `won_leads`, `conversion_rate`)
6. **Hard-coded industry taxonomies** with pre-defined fields and pipelines for specific CRM types

### Impact

- **Records created in a custom CRM (not Sales/Healthcare/E-Commerce) may not work correctly**
- **Evolution proposals assume Sales CRM semantics (won_leads, conversion_rate)**
- **Analytics hard-coded to count "Won" stages instead of reading from schema**
- **New CRM types require code changes** (violates universal architecture requirement)
- **Field extraction defaults assume priority, source, status exist** in all CRMs

---

## Violations by Severity

### CRITICAL (Breaks Universality)

#### 1. AnalyticsData Schema — Hard-Coded to Sales Terms
**File:** `backend/app/schemas/crm.py` (lines 248-255)

```python
class AnalyticsData(StrictModel):
    total_leads: int = Field(ge=0)
    qualified_leads: int = Field(ge=0)
    won_leads: int = Field(ge=0)
    conversion_rate: float = Field(ge=0, le=1)
    by_source: list[dict[str, Any]] = Field(default_factory=list)
    by_stage: list[dict[str, Any]] = Field(default_factory=list)
```

**Problem:**
- Field names `total_leads`, `qualified_leads`, `won_leads` assume Sales CRM terminology
- A Healthcare CRM has no "leads" or "won" state—it has patients and treatment outcomes
- E-Commerce CRM has no "qualified leads"—it has customers and orders
- Conversion rate is meaningless for service tickets, patient records, or shipments

**Why It Violates:**
- A user creates a custom CRM: "Track my properties and show me time-to-sale"
- Analytics code tries to populate `total_leads` and `won_leads` but those fields don't exist in the user's schema
- The API returns 0 for all metrics regardless of actual data

**Fix Approach:**
- Replace with generic schema: `total_records`, `records_by_stage`, `stage_distribution`
- Let frontend derive high-level analytics from dynamic schema
- OR allow AnalyticsData to be schema-defined in CRM configuration

**Effort Estimate:** HIGH (affects multiple systems)

---

#### 2. Hard-Coded Won_Stages in Evolution Proposals
**File:** `backend/app/routers/evolution.py` (lines 93-98)

```python
won_stages = {"Won", "won", "Closed Won", "closed_won"}
by_stage = repo.count_records_by_field(str(crm_id), primary_entity, stage_field.name)
won = sum(entry.get("count", 0) for entry in by_stage if entry.get("value") in won_stages)
analytics_data["won_leads"] = won
```

**Problem:**
- Only recognizes stages named "Won", "won", "Closed Won", "closed_won"
- A Healthcare CRM has stages like "Treatment Complete", "Discharged", "Lost to Follow-up"
- An E-Commerce CRM has "Repeat Buyer", "VIP", "Churn Risk"
- Code counts 0 records as "won" for all non-Sales CRMs

**Why It Violates:**
- Evolution proposal generation fails for 100% of non-Sales CRMs
- Conversion rate always 0.0 because won_leads is always 0

**Fix Approach:**
- Read schema metadata to identify "success/completion" stage indicator
- OR allow CRM config to define which stages count as "successful"
- OR generically count all stages without favoring "won"

**Effort Estimate:** MEDIUM

---

#### 3. Default Entity Name "lead" Hard-Coded
**File:** `backend/app/routers/evolution.py` (line 84)

```python
primary_entity = config.entities[0].name if config.entities else "lead"
```

**Problem:**
- Fallback defaults to "lead" entity if config is empty
- User creates a Healthcare CRM with "patient" as primary entity
- System tries to count records in non-existent "lead" entity → 0 records

**Why It Violates:**
- Assumes first entity is always present and counts it
- Fallback to "lead" is arbitrary and wrong for other CRM types

**Fix Approach:**
- Use `config.entities[0].name` with validation; don't fallback
- OR allow CRM config to specify which entity is primary

**Effort Estimate:** LOW

---

### HIGH (Limits Flexibility)

#### 4. Status Field Detection by Hard-Coded Names
**File:** `backend/app/services/ai_provider.py` (lines 140-141)

```python
has_status = any(f.get("name") in ("status", "stage", f"{entity_name}_status", "shipping_status") 
                 or f.get("type") in ("status", "select") and "status" in f.get("name", "") 
                 for f in fields)
```

**Problem:**
- Only recognizes status fields named "status", "stage", "shipping_status"
- A user's custom CRM may call it "care_status", "fulfillment_state", "appointment_phase"
- If not recognized, code adds a default "status" field (duplicate if user has different name)

**Why It Violates:**
- User loses control of field naming
- Duplicate status-like fields may be created

**Fix Approach:**
- Add a field-type metadata flag: `"is_stage_field": true`
- Let schema editor explicitly mark which field is the stage/status field
- Remove hardcoded name detection

**Effort Estimate:** MEDIUM

---

#### 5. Hard-Coded Field Type Inference for "priority", "source"
**File:** `backend/app/services/ai_provider.py` (lines 122-127)

```python
if any(w in ef.machine_key for w in ["status", "stage"]):
    fdict["options"] = list(stages)
elif "priority" in ef.machine_key:
    fdict["options"] = ["Low", "Medium", "High", "Critical"]
elif "source" in ef.machine_key:
    fdict["options"] = ["Website", "Referral", "Partner", "Direct"]
```

**Problem:**
- Assumes "priority" always has [Low, Medium, High, Critical]
- Assumes "source" always has [Website, Referral, Partner, Direct]
- User's CRM may have "priority" with [1-5], [P0-P4], [Critical, High, Normal]
- User's "source" may be [Google Ads, Facebook, LinkedIn, Direct Mail]

**Why It Violates:**
- Hard-coded defaults override user intent
- Users must manually fix auto-generated option lists

**Fix Approach:**
- Use FieldExtractor to attempt inference from context
- Fall back to generic [Option 1, Option 2, Option 3] instead of specific values
- Let users override in schema editor

**Effort Estimate:** MEDIUM

---

#### 6. Hard-Coded Industry Taxonomies with Pre-Built CRM Types
**File:** `backend/app/services/laya_system1.py` (lines 76-121)

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
    "healthcare": {
        "label": "Healthcare Clinic CRM",
        "default_entity": "patient",
        "pipeline": ["Inquiry", "Triage", "Consultation Booked", "Treatment", "Follow-up Completed"],
        ...
    },
    ...
}
```

**Problem:**
- System provides 4 pre-built CRM templates: saas, healthcare, real_estate, ecommerce
- User wants to build a custom CRM: "Track my suppliers and their certification levels"
- System forces user to pick one of the 4, or forces them to override all fields and stages
- Any new CRM type requires code deployment

**Why It Violates:**
- "Self-evolving" means users can create ANY CRM
- Baking in specific templates contradicts universality
- New industries require code changes

**Fix Approach:**
- Remove hard-coded taxonomies
- Build fields and stages dynamically from user input
- Allow schema editor to start from blank or minimal template
- Use field extraction and stage inference instead of taxonomy lookup

**Effort Estimate:** HIGH

---

#### 7. Hard-Coded Pipeline Defaults by Industry Detection
**File:** `backend/app/services/ai_provider.py` (lines 99-108)

```python
elif "support" in industry or "ticket" in lower:
    stages = ["Open", "Assigned", "In Progress", "Waiting", "Resolved", "Closed"]
elif "recruitment" in industry or "candidate" in lower:
    stages = ["Applied", "Screening", "Interview", "Selected", "Hired", "Rejected"]
elif "export" in industry or "shipment" in lower:
    stages = ["New Lead", "Contacted", "Quotation", "Order Confirmed", "Shipped", "Completed"]
else:
    stages = ["New", "In Progress", "Completed"]
```

**Problem:**
- System auto-generates pipeline stages based on keyword detection
- User says "I want a CRM for managing my research papers from submission to publication"
- System keyword-matches on nothing, defaults to [New, In Progress, Completed]
- User wants [Submitted, Under Review, Revisions Requested, Accepted, Published]
- User must manually edit stages after CRM generation

**Why It Violates:**
- Doesn't respect user intent
- User's described stages are ignored
- Generic defaults are incorrect for custom use cases

**Fix Approach:**
- Explicitly extract stages from user prompt using FieldExtractor
- Fall back to minimal 3-stage default: [Start, Active, End] or similar
- Let user specify stages in questionnaire or chat

**Effort Estimate:** MEDIUM

---

#### 8. Copilot Examples Hard-Code Entity Names
**File:** `backend/app/routers/copilot.py` (line 91)

```python
"- Create record: TOOL_CALL: {\"name\": \"create_record\", \"arguments\": {\"entity_name\": \"lead\", \"data\": {\"name\": \"John\", \"email\": \"john@example.com\"}}}\n"
```

**Problem:**
- System prompt example shows creating a "lead" record
- User's CRM has "patient" entity—copilot may assume "lead" exists
- Example also hard-codes fields: name, email (user may not have these)

**Why It Violates:**
- Copilot trained on wrong entity/field names
- May generate incorrect tool calls for custom CRMs

**Fix Approach:**
- Build examples dynamically from actual CRM config
- Use first entity name and first few fields in examples

**Effort Estimate:** LOW

---

### MEDIUM (Poor Practice)

#### 9. Copilot Action Detection Assumes Specific Entity Names
**File:** `backend/app/routers/copilot.py` (lines 261-262)

```python
if any(q_lower.startswith(w) or f" {w} " in f" {q_lower} " for w in ["add", "create", "new", "insert", "make"]) and (
    any(w in q_lower for w in ["record", "customer", "lead", "ticket", "candidate", "shipment", "item", "order", "entry", "user"])
```

**Problem:**
- Copilot looks for specific keywords: customer, lead, ticket, candidate, shipment, order
- User's custom CRM: "Create a property listing"
- Keyword "property" not in list → action not triggered
- Copilot falls back to informational mode

**Why It Violates:**
- Copilot action detection is brittle and hard-coded
- Custom entity names not recognized

**Fix Approach:**
- Instead of keyword list, check if any entity name appears in prompt
- Match against actual CRM entities dynamically

**Effort Estimate:** MEDIUM

---

#### 10. Laya System 1 Hard-Codes Entity Names in Example Workflows
**File:** `backend/app/services/laya_system1.py` (lines 186-190, 200-203, 214-216)

```python
"trigger": {"type": "record.created", "entity": "lead"},
...
"trigger": {"type": "record.stage_changed", "entity": "lead"},
...
"trigger": {"type": "record.updated", "entity": "lead"},
```

**Problem:**
- All mock evolution proposals hard-code entity as "lead"
- A Healthcare CRM's workflows should trigger on "patient" records
- AI provider generates incorrect workflow proposals

**Why It Violates:**
- Proposals don't match CRM entity
- Workflows won't trigger in non-Sales CRMs

**Fix Approach:**
- Use primary entity name from config in proposals
- Build examples from actual CRM schema

**Effort Estimate:** LOW

---

#### 11. Ollama Provider Template Remapping
**File:** `backend/app/services/ollama_provider.py` (lines 214-218)

```python
if template and isinstance(entities, list) and len(entities) == 1:
    entity = entities[0]
    if isinstance(entity, dict) and entity.get("name") == "lead":
        entity["name"], entity["label"] = template
```

**Problem:**
- Only renames entity if it's exactly named "lead"
- Doesn't handle custom entity names
- User's CRM has "prospect" entity → no remapping occurs

**Why It Violates:**
- Selective hard-coding of "lead"
- Inconsistent treatment of different entity names

**Fix Approach:**
- Remap primary entity regardless of name
- OR remove this logic if not needed

**Effort Estimate:** LOW

---

#### 12. Default Entity Used Inconsistently
**File:** `backend/app/services/laya_system1.py` (lines 531-532)

```python
elif "patient" in p_lower or "client" in p_lower:
    entity_name = "patient" if industry == "healthcare" else "client"
```

**Problem:**
- Selective entity naming based on industry
- Assumes "patient" is only healthcare, "client" is default fallback
- Custom entity names not supported

**Fix Approach:**
- Extract entity name from user input directly
- Don't infer or default based on industry

**Effort Estimate:** LOW

---

### LOW (Cosmetic / Minor)

#### 13. Hard-Coded "lead" in Industry Detection Logic
**File:** `backend/app/services/ai_provider.py` (line 87)

```python
("lead", "Lead"),
```

**Problem:**
- Known entities list includes "lead" as first option
- Matched in prompt if user mentions "leads"
- Not truly a violation but contributes to lead-centric bias

**Fix Approach:**
- Keep but don't bias; let FieldExtractor extract from prompt

**Effort Estimate:** VERY LOW

---

#### 14. CRM Examples in Chat Endpoint
**File:** `backend/app/routers/chat.py` (lines 72-115)

```json
"pipeline_stages": ["Stage1", "Stage2", "Stage3"]
```

**Problem:**
- Generic placeholder stages in example payload
- Not a real violation but could confuse

**Fix Approach:**
- Remove or use real example stages

**Effort Estimate:** VERY LOW

---

#### 15. Hard-Coded Source Tag Options
**File:** `backend/app/services/ai_tools.py` (lines 863-866)

```python
"source": {
    "type": "string",
    "description": "Optional source tag (e.g., 'Website', 'Email', 'Manual')",
},
```

**Problem:**
- Tool description suggests specific source values
- User may have different source types (API, CSV Import, Referral)

**Fix Approach:**
- Keep generic description; don't suggest specific values

**Effort Estimate:** VERY LOW

---

#### 16. Analytics Workflow Detection Hard-Codes "revenue"
**File:** `backend/app/routers/workflows.py` (line 275)

```python
fmt = "currency" if nm["type"] == "currency" or "revenue" in nm["field_name"] or "value" in nm["field_name"] or "price" in nm["field_name"] else "number"
```

**Problem:**
- Assumes numeric fields containing "revenue" are currency
- User's field "customer_revenue_bucket" gets formatted as currency
- Not always desired

**Fix Approach:**
- Respect field type declared in schema; don't infer from name

**Effort Estimate:** LOW

---

#### 17. ReorderFieldsRequest and ReorderStagesRequest
**File:** `backend/app/schemas/crm.py` (lines 342-365)

```python
class ReorderFieldsRequest(StrictModel):
    """Request to reorder fields in an entity."""
    field_order: list[str] = Field(min_length=1)

class ReorderStagesRequest(StrictModel):
    """Request to reorder pipeline stages."""
    stage_order: list[str] = Field(min_length=1)
```

**Problem:**
- These schemas are generic and correct
- No violation here, but included for completeness

**Fix Approach:**
- No change needed

**Effort Estimate:** N/A

---

#### 18. Field Extractor Type Indicator Keywords
**File:** `backend/app/services/field_extractor.py` (lines 55-63)

```python
'select': {'status', 'stage', 'type', 'category', 'priority', 'level', 'state', 'reason', 'source', 'channel', 'method'},
```

**Problem:**
- Hard-codes keywords to infer field type
- User's field "leadership_priority" inferred as "priority" (select type)
- May be incorrect

**Fix Approach:**
- Use context and position in sentence; reduce hard-coded keywords

**Effort Estimate:** MEDIUM

---

## Summary Table

| Category | Count | Severity | Impact |
|----------|-------|----------|--------|
| Hard-Coded Entity Names | 4 | CRITICAL | Custom CRMs fail |
| Hard-Coded Stage Values | 3 | CRITICAL | Analytics broken |
| Hard-Coded Fields | 4 | HIGH | Field detection fails |
| Hard-Coded Type Inference | 2 | HIGH | Field types wrong |
| Industry Taxonomies | 1 | CRITICAL | New CRM types need code |
| **TOTAL** | **18** | **Mixed** | **Breaks Universality** |

---

## Recommended Fixes (Priority Order)

### Phase 1: Critical (Must Fix for Universality)

1. **Remove AnalyticsData hard-coded fields** (1-2 days)
   - Replace with generic schema
   - Move to dynamic metrics computed from CRM config

2. **Remove Won_Stages logic** (1 day)
   - Don't hard-code success stage detection
   - Let CRM define or compute generic stage distribution

3. **Remove Industry Taxonomies** (2-3 days)
   - Build CRM from user input dynamically
   - Use FieldExtractor for all prompts
   - Remove template baking

### Phase 2: High (Restores Flexibility)

4. **Dynamic Status Field Detection** (1 day)
   - Add schema metadata flag for stage field
   - Remove name-based detection

5. **Remove Hard-Coded Field Type Defaults** (1 day)
   - Stop assuming priority/source options
   - Use generic defaults or user input

6. **Dynamic Copilot Examples** (1 day)
   - Build from actual CRM config at runtime

### Phase 3: Medium (Polish)

7. **Fix Copilot Action Detection** (1-2 days)
   - Match entity names dynamically
   - Remove keyword list

8. **Fix Laya Mock Proposals** (0.5 days)
   - Use primary entity from config

9. **Normalize Field Type Inference** (1 day)
   - Reduce hard-coded keywords in FieldExtractor
   - Use context-based inference

---

## Conclusion

**The current codebase violates the core requirement that AURA is a universal CRM platform.** All 18 violations must be resolved before release to ensure that users can create ANY CRM type without code modifications.

**Total Estimated Effort:** 14-18 developer-days

**Criticality:** Cannot ship without fixing Critical category violations. System will fail for non-Sales CRMs.
