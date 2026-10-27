# Integration Examples — How to Use the Normalization Layer

## Example 1: Update Chat Endpoint to Skip Clarifications

**File:** `backend/app/routers/chat.py`

Before (has loops):
```python
@router.post("")
async def chat(body: ChatRequest, user_id: CurrentUser, settings: Annotated[Settings, Depends(get_settings)]):
    # Always ask "What fields?"
    latest_user_msg = body.messages[-1].content
    reply = "What fields do you need in your CRM?"  # ← Re-ask even if already answered
    return success_response({"reply": reply, "ready_to_generate": False})
```

After (skips loops):
```python
from app.services.crm_builder_integration import (
    process_user_crm_input,
    eliminate_clarification_loop,
)

@router.post("")
async def chat(body: ChatRequest, user_id: CurrentUser, settings: Annotated[Settings, Depends(get_settings)]):
    messages_dicts = [{"role": m.role, "content": m.content} for m in body.messages]
    latest_user_msg = body.messages[-1].content if body.messages else ""
    
    # Extract mentioned custom columns (simple regex example)
    import re
    mentioned = re.findall(r'\b(?:field|column)s?:\s*([^,.]+)', latest_user_msg, re.I)
    mentioned_columns = [col.strip() for col in mentioned] if mentioned else None
    
    # Check if ready to generate
    if eliminate_clarification_loop(
        [{"role": m.role, "content": m.content} for m in body.messages],
        user_provided_columns=mentioned_columns,
    ):
        # Generate immediately with normalized schema
        result = process_user_crm_input(
            user_message=latest_user_msg,
            mentioned_columns=mentioned_columns,
        )
        
        # Use normalized schema for generation
        provider = get_ai_provider(settings.llm_provider)
        config_dict = provider.generate_crm_config(result["generation_prompt"])
        
        return _chat_reply_response({
            "configuration": config_dict,
            "ready_to_generate": True,
        }, "llm")
    
    # Otherwise, continue conversation (no change)
    reply = _fallback_reply(body.messages)[0]
    return _chat_reply_response({"reply": reply, "ready_to_generate": False}, "fallback")
```

---

## Example 2: Update Ollama Provider to Inject Normalized Schema

**File:** `backend/app/services/ollama_provider.py`

Before (no schema constraints):
```python
def _get_system_prompt(self, decision: GenerationDecision | None = None) -> str:
    return (
        "You are an expert CRM architect system. Generate a complete CRM configuration JSON..."
        # No mention of normalized schema or which keys to use
    )
```

After (schema-aware):
```python
from app.services.schema_binding import SchemaBinding
from app.services.laya_system1 import LayaSystem1

def _get_system_prompt_with_schema(
    self, 
    decision: GenerationDecision | None = None,
    custom_columns: list[str] | None = None,
    custom_statuses: list[str] | None = None,
) -> str:
    # Normalize custom input
    normalized = None
    if custom_columns or custom_statuses:
        normalized = LayaSystem1.normalize_custom_schema(
            custom_columns=custom_columns,
            custom_statuses=custom_statuses,
        )
    
    # Inject normalized schema into prompt
    base_prompt = (
        "You are an expert CRM architect system. Generate a complete CRM configuration JSON..."
    )
    
    system_prompt = SchemaBinding.build_qwen_system_prompt(
        normalized_schema=normalized,
        base_prompt=base_prompt,
    )
    
    if decision:
        system_prompt += (
            f"\nVerified System 1 decision (use as planning context): "
            f"industry={decision.industry}; strategy={decision.strategy}."
        )
    
    return system_prompt

def generate_crm_config(
    self, 
    prompt: str,
    custom_columns: list[str] | None = None,
    custom_statuses: list[str] | None = None,
) -> dict[str, Any]:
    """Generate with optional normalized schema."""
    LayaSystem1.validate_prompt_safety(prompt)
    decision = self.decision_engine.decide_generation(prompt) if self.decision_engine else None
    
    # Use schema-aware system prompt
    system_prompt = self._get_system_prompt_with_schema(
        decision, 
        custom_columns=custom_columns,
        custom_statuses=custom_statuses,
    )
    
    decision_prompt = f"{prompt}\nSystem 1 classified industry: {decision.industry}." if decision else prompt
    raw_response = self._call_ollama_generate(system_prompt, decision_prompt)

    if raw_response:
        for _ in range(MAX_REPAIR_ATTEMPTS):
            try:
                parsed_json = LayaSystem1.extract_json_payload(raw_response)
                
                # Normalize custom schema info
                if custom_columns or custom_statuses:
                    normalized = LayaSystem1.normalize_custom_schema(
                        custom_columns=custom_columns,
                        custom_statuses=custom_statuses,
                    )
                    parsed_json["custom_columns"] = custom_columns
                    parsed_json["custom_statuses"] = custom_statuses
                
                repaired = self._apply_generation_decision(
                    LayaSystem1.repair_crm_configuration(parsed_json, prompt), decision
                )
                CRMConfiguration(**repaired)
                self.last_warnings = []
                return repaired
            except Exception as exc:
                logger.warning("Failed to parse or repair Ollama output: %s", exc)

    raise ValueError("Qwen CRM generation is currently unavailable. Please check your Ollama connection and try again.")
```

---

## Example 3: Integrate with Laya for Routing

**File:** `backend/app/services/laya_runtime.py` (or integration layer)

Before (raw strings cause ambiguity):
```python
questions = {
    "primary_field": {
        "type": "choice",
        "instructions": "Pick the most important field.",
        "criteria": {
            "Budget Size!": "field for budget information",
            "Priority (Level)": "field for priority level",
            "Deal @Stage": "field for deal stage",
        }
    }
}
```

After (normalized schema):
```python
from app.services.schema_binding import SchemaBinding
from app.services.laya_system1 import LayaSystem1

def build_laya_routing(custom_columns: list[str] | None = None):
    # Normalize custom input
    normalized = LayaSystem1.normalize_custom_schema(
        custom_columns=custom_columns,
    )
    
    # Build Laya choice with normalized keys
    primary_field_choice = SchemaBinding.build_laya_choice_primitive(
        question_key="primary_field",
        instructions="Pick the most important field for this CRM.",
        normalized_schema=normalized,
        choice_type="column",
    )
    
    questions = {
        "primary_field": primary_field_choice,
        "industry": {
            "type": "choice",
            "instructions": "Classify the requested CRM business domain.",
            "criteria": {
                "saas": "software subscriptions, B2B products, demos, ARR",
                "healthcare": "clinics, patients, doctors, appointments",
                "real_estate": "property listings, buyers, viewings, sales",
                "ecommerce": "stores, orders, customers, retail purchases",
                "general": "a business not covered by the other categories",
            }
        },
    }
    
    # Laya now receives deterministic, structured input
    return questions

# Use in decision engine
laya_questions = build_laya_routing(
    custom_columns=["Budget!", "Priority (Level)"]
)
result = laya_engine.predict(state, laya_questions)
# Result: {"answers": {"primary_field": {"choice": "budget"}}} ← Deterministic!
```

---

## Example 4: Validate Qwen Output Before Persistence

**File:** `backend/app/routers/records.py` (or similar)

Before (accepts anything Qwen returns):
```python
@router.post("/generate-draft")
async def generate_record_draft(request: RecordDraftRequest):
    # Qwen generates JSON
    raw_output = await llm.generate(prompt)
    
    # Use it directly (risk of mismatched keys)
    record = Record(**raw_output)  # May fail validation
    return success_response(record)
```

After (validates against normalized schema):
```python
from app.services.schema_binding import SchemaBinding

@router.post("/generate-draft")
async def generate_record_draft(request: RecordDraftRequest):
    # Get normalized schema for the CRM
    crm = db.get_crm(request.crm_id)
    custom_columns = extract_columns_from_crm(crm)
    normalized = LayaSystem1.normalize_custom_schema(
        custom_columns=custom_columns,
    )
    
    # Qwen generates JSON
    raw_output = await llm.generate(prompt)
    
    # Validate against normalized schema
    is_valid, cleaned, errors = SchemaBinding.validate_qwen_output(
        raw_output, normalized_schema=normalized
    )
    
    if not is_valid:
        logger.warning(f"Validation failed: {errors}")
        return error_response(400, "VALIDATION_ERROR", f"Generated record has issues: {errors}")
    
    # Use cleaned output
    record = Record(**cleaned)
    return success_response(record)
```

---

## Example 5: Display Normalized Fields to User

**File:** `frontend/src/features/crm-chat/CRMChatPage.tsx`

```typescript
import { process_user_crm_input } from 'api/normalization';

function CRMChatPage() {
  const [fieldMapping, setFieldMapping] = useState<Record<string, string>>({});
  
  const handleUserInput = async (message: string) => {
    // Extract custom columns from user message
    const customColumns = extractColumns(message);
    
    if (customColumns.length > 0) {
      // Get normalized schema from backend
      const result = await processUserInput({
        user_message: message,
        mentioned_columns: customColumns,
      });
      
      // Display normalized field mapping to user
      setFieldMapping(result.field_mapping);
      
      // Show user what was normalized
      console.log('Normalized fields:', result.field_mapping);
      // Output: { "budget": "Budget", "priority": "Priority" }
      
      // Trigger immediate generation
      const config = await generateCRM(result.generation_prompt);
      setGeneratedConfig(config);
    }
  };
  
  return (
    <div>
      <ChatInput onSubmit={handleUserInput} />
      {Object.entries(fieldMapping).map(([key, label]) => (
        <NormalizedFieldBadge key={key} machineKey={key} humanLabel={label} />
      ))}
      {generatedConfig && <CRMPreview config={generatedConfig} />}
    </div>
  );
}
```

---

## Example 6: End-to-End User Story

**Scenario:** User wants to build a custom CRM with "Client Budget!" and "Deal Priority (Level)" fields.

### Step 1: User Input
```
User: "I need a sales CRM. Key fields are Client Budget! and Deal Priority (Level). Status should be Active, On-Hold, or Won."
```

### Step 2: Backend Normalization
```python
result = process_user_crm_input(
    user_message="I need a sales CRM. Key fields are Client Budget! and Deal Priority (Level). Status should be Active, On-Hold, or Won.",
    mentioned_columns=["Client Budget!", "Deal Priority (Level)"],
    mentioned_statuses=["Active", "On-Hold", "Won"],
)

# Result:
{
    "normalized_schema": NormalizedSchema(...),
    "field_mapping": {
        "client_budget": "Client Budget",
        "deal_priority": "Deal Priority",
    },
    "status_mapping": {
        "active": "Active",
        "on_hold": "On Hold",
        "won": "Won",
    },
    "laya_choice_primitive": {...},
    "qwen_system_prompt": "You are an expert CRM architect...\n\nNormalized Schema:\n- `client_budget` (Client Budget)\n- `deal_priority` (Deal Priority)\n...",
    "generation_prompt": "I need a sales CRM...",
}
```

### Step 3: Laya Routing (System 1)
```python
laya_choice = result["laya_choice_primitive"]
# Laya receives: {"client_budget": "Client Budget", "deal_priority": "Deal Priority"}
# Laya decides: "Which field is most important?" → "client_budget"
# No ambiguity, no re-ask!
```

### Step 4: Qwen Generation (System 2)
```python
qwen_response = await qwen.generate(
    prompt=result["generation_prompt"],
    system_prompt=result["qwen_system_prompt"],
)

# Qwen knows exactly which keys to use:
# {
#   "schema_version": "1.0",
#   "name": "Sales CRM",
#   "entities": [
#     {
#       "name": "lead",
#       "fields": [
#         {"name": "client_budget", "label": "Client Budget", ...},
#         {"name": "deal_priority", "label": "Deal Priority", ...},
#         {"name": "status", "label": "Status", "options": ["active", "on_hold", "won"]}
#       ]
#     }
#   ]
# }
```

### Step 5: Validation & Persistence
```python
is_valid, cleaned, errors = SchemaBinding.validate_qwen_output(
    qwen_response, normalized_schema=result["normalized_schema"]
)

if is_valid:
    config = CRMConfiguration(**cleaned)
    db.save_crm(config)
    return success_response(config)
```

### Result: ✅ Zero loops, deterministic output, schema-valid!

---

## Testing the Integration

```python
# In your test file
from app.services.crm_builder_integration import process_user_crm_input
from app.services.schema_binding import SchemaBinding

def test_e2e_custom_columns():
    # Setup
    user_message = "Build a CRM with Budget and Priority fields"
    
    # Process input
    result = process_user_crm_input(
        user_message=user_message,
        mentioned_columns=["Budget!", "Priority (Level)"],
    )
    
    # Verify normalization
    assert "budget" in result["field_mapping"]
    assert "priority_level" in result["field_mapping"]
    
    # Verify Laya binding
    assert result["laya_choice_primitive"] is not None
    assert "budget" in result["laya_choice_primitive"]["criteria"]
    
    # Verify Qwen binding
    assert "budget" in result["qwen_system_prompt"].lower()
    assert "priority_level" in result["qwen_system_prompt"].lower()
    
    # Simulate Qwen response
    qwen_output = {
        "budget": "50000",
        "priority_level": "high",
        "assigned_status": "active",
        "draft_response": "Created sales CRM",
    }
    
    # Validate output
    is_valid, cleaned, errors = SchemaBinding.validate_qwen_output(
        qwen_output, normalized_schema=result["normalized_schema"]
    )
    
    assert is_valid
    assert len(errors) == 0
    assert "budget" in cleaned
```

---

## Debugging

### Check what got normalized:
```python
normalized = LayaSystem1.normalize_custom_schema(
    custom_columns=["Budget!", "Priority (Level)"],
)

for key, ni in normalized.column_mapping.items():
    print(f"Machine: {key}")
    print(f"  Human: {ni.human_label}")
    print(f"  Original: {ni.original_raw}")

# Output:
# Machine: budget
#   Human: Budget
#   Original: Budget!
# Machine: priority_level
#   Human: Priority Level
#   Original: Priority (Level)
```

### Check Laya criteria:
```python
print(normalized.laya_choice_criteria)
# Output: {"budget": "Budget", "priority_level": "Priority Level"}
```

### Check if Qwen prompt includes schema:
```python
prompt = SchemaBinding.build_qwen_system_prompt(
    normalized_schema=normalized,
)
print(prompt)
# Verify it contains: "budget", "priority_level", "assigned_status", etc.
```

---

## Migration Checklist

- [ ] Add `SchemaBinding` to Ollama provider's `_get_system_prompt()`
- [ ] Update chat endpoint to use `process_user_crm_input()`
- [ ] Add `eliminate_clarification_loop()` to skip unnecessary questions
- [ ] Add `validate_qwen_output()` before persistence
- [ ] Extract custom columns from user messages (regex or NLP)
- [ ] Test end-to-end with custom columns
- [ ] Update API contracts documentation
- [ ] Add frontend display of normalized fields
- [ ] Monitor logs for normalization patterns
- [ ] Train support team on normalized schema behavior
