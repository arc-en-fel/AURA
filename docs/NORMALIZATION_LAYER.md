# Normalization Layer & Schema Binding Documentation

## Overview

The normalization layer fixes natural language input loops and dynamic schema mapping in the Laya + Qwen CRM system. It provides:

1. **Deterministic Input Normalization**: Raw user strings → machine keys (e.g., "Client Budget Size!" → `client_budget_size`)
2. **Bidirectional Mapping**: Tracks both the human-readable label and the original raw input for audit trails
3. **Laya Integration**: Builds structured choice primitives with normalized keys so Laya never receives ambiguous strings
4. **Qwen Integration**: Injects normalized schema into system prompts so Qwen returns JSON with strictly-validated keys
5. **Loop Elimination**: Skips clarification questions when custom input is provided upfront

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ USER INPUT (Raw Natural Language)                               │
│ "Budget Size!", "Priority Level", "Contact Phone"               │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ NORMALIZATION LAYER (LayaSystem1)                               │
│ _normalize_user_input() + normalize_custom_schema()             │
│ Output: NormalizedSchema (bidirectional mapping)                │
└────────────────┬────────────────────────────────────────────────┘
                 │
        ┌────────┴────────┐
        │                 │
        ▼                 ▼
┌──────────────────┐  ┌──────────────────────────┐
│ LAYA (SYSTEM 1)  │  │ QWEN (SYSTEM 2)          │
│ Choice Primitive │  │ System Prompt Injection  │
│ with normalized  │  │ + JSON Schema Validation │
│ keys only        │  │                          │
└──────────────────┘  └──────────────────────────┘
        │                       │
        └───────────┬───────────┘
                    │
                    ▼
        ┌──────────────────────┐
        │ Schema-Valid Output  │
        │ No loops, no mismatches
        └──────────────────────┘
```

## Core Components

### 1. LayaSystem1 Normalization Methods

#### `_normalize_user_input()`
Converts raw strings into deterministic machine keys.

**Input:**
```python
raw_inputs = [
    "Client Budget Size!",
    "Priority (Level)",
    "Deal @Stage",
]
```

**Processing:**
1. Remove special characters → "Client Budget Size", "Priority Level", "Deal Stage"
2. Lowercase and replace spaces with underscores → "client_budget_size", "priority_level", "deal_stage"
3. Collapse multiple underscores → (no change here)
4. Validate identifier format (start with letter) → all valid
5. Truncate to 63 chars → (no change)
6. Check reserved fields → (no collisions)
7. Handle collisions → (append _1, _2, etc. if duplicates)

**Output:**
```python
{
    "client_budget_size": NormalizedInput(
        machine_key="client_budget_size",
        human_label="Client Budget Size",
        original_raw="Client Budget Size!"
    ),
    "priority_level": NormalizedInput(...),
    "deal_stage": NormalizedInput(...),
}
```

#### `normalize_custom_schema()`
Normalizes both columns and statuses into a unified schema.

**Input:**
```python
custom_columns = ["Budget!", "Priority"]
custom_statuses = ["Active", "On-Hold"]
```

**Output:**
```python
NormalizedSchema(
    column_mapping={
        "budget": NormalizedInput(...),
        "priority": NormalizedInput(...),
    },
    status_mapping={
        "active": NormalizedInput(...),
        "on_hold": NormalizedInput(...),
    },
    laya_choice_criteria={
        "budget": "Budget",
        "priority": "Priority",
    },
    laya_status_criteria={
        "active": "Active",
        "on_hold": "On Hold",
    },
)
```

### 2. SchemaBinding Utilities

#### `build_laya_choice_primitive()`
Creates a Laya choice dict with normalized criteria.

**Example:**
```python
normalized = LayaSystem1.normalize_custom_schema(
    custom_columns=["Budget!", "Priority"]
)

choice = SchemaBinding.build_laya_choice_primitive(
    question_key="primary_field",
    instructions="Pick the most critical field.",
    normalized_schema=normalized,
    choice_type="column",
)

# Result:
{
    "type": "choice",
    "instructions": "Pick the most critical field.",
    "criteria": {
        "budget": "Budget",
        "priority": "Priority",
    }
}
```

**Why this fixes the loop:** Laya now receives structured, lowercase keys instead of raw user text with special characters. No ambiguity, no re-asking.

#### `build_qwen_system_prompt()`
Injects normalized schema into Qwen's system prompt.

**Example:**
```python
prompt = SchemaBinding.build_qwen_system_prompt(
    normalized_schema=normalized,
    base_prompt="You are a CRM expert.",
)

# Snippet of output:
"""
You are a CRM expert.

## Normalized Schema Constraints

You MUST return a JSON object whose keys strictly match these identifiers:

**Custom Columns (use as JSON keys):**
  - `budget` (originally: 'Budget!')
  - `priority` (originally: 'Priority')

**Custom Statuses (for `assigned_status` field):**
  - `active` (originally: 'Active')

Your JSON output MUST use these exact machine keys...
"""
```

**Why this fixes schema mismatches:** Qwen knows exactly which JSON keys to use. No guessing, no invented fields.

#### `validate_qwen_output()`
Validates that Qwen's JSON matches the normalized schema.

**Example:**
```python
raw_output = {
    "budget": 50000,
    "assigned_status": "active",
    "draft_response": "Created draft CRM.",
}

is_valid, cleaned, errors = SchemaBinding.validate_qwen_output(
    raw_output, normalized_schema
)

# Result:
is_valid = True
cleaned = {
    "budget": 50000,
    "assigned_status": "active",
    "draft_response": "Created draft CRM.",
}
errors = []
```

### 3. CRM Builder Integration

#### `process_user_crm_input()`
High-level entry point for one-turn CRM generation with custom inputs.

**Example:**
```python
result = process_user_crm_input(
    user_message="Build me a CRM with Budget and Priority fields",
    mentioned_columns=["Budget!", "Priority"],
)

# Returns:
{
    "normalized_schema": NormalizedSchema(...),
    "laya_choice_primitive": {...},
    "qwen_system_prompt": "You are an expert...",
    "field_mapping": {
        "budget": "Budget",
        "priority": "Priority",
    },
    "generation_prompt": "Build me a CRM...",
}
```

#### `eliminate_clarification_loop()`
Determines if the system should skip clarifications and generate immediately.

**Triggers:**
1. User provided custom columns/statuses
2. User said "generate now"
3. Conversation depth ≥ 3 meaningful exchanges

**Example:**
```python
# Custom input provided → skip clarifications
ready = eliminate_clarification_loop(
    conversation_history,
    user_provided_columns=["Budget", "Priority"],
)
# Returns: True
```

## Usage Patterns

### Pattern 1: One-Turn Generation with Custom Input

User provides custom columns in a single message:

```python
# In chat endpoint
result = process_user_crm_input(
    user_message="Build a sales CRM with Budget and Priority fields",
    mentioned_columns=["Budget", "Priority"],
)

# Instant generation (no clarifications)
generation_prompt = result["generation_prompt"]
qwen_system_prompt = result["qwen_system_prompt"]
# Send to Qwen → get normalized JSON
```

### Pattern 2: Multi-Turn Conversation with Late Custom Input

User provides custom input after several exchanges:

```python
# Turn 1-3: Conversation, building context
# Turn 4: User says "I need Budget and Priority fields"

mentioned_columns = extract_columns_from_message(latest_user_msg)
if mentioned_columns:
    # Check if ready to generate
    if eliminate_clarification_loop(history, user_provided_columns=mentioned_columns):
        # Generate immediately
        result = process_user_crm_input(
            user_message="\n".join(user_messages),
            mentioned_columns=mentioned_columns,
        )
        config = await generate_with_normalized_schema(result)
```

### Pattern 3: Validate Qwen Output Against Schema

```python
# After Qwen generates
raw_qwen_output = parse_json_response(qwen_response)
is_valid, cleaned, errors = SchemaBinding.validate_qwen_output(
    raw_qwen_output, normalized_schema
)

if not is_valid:
    # Re-prompt Qwen with error details
    # Or use scaffold fallback
else:
    # Use cleaned output
    persist_crm_config(cleaned)
```

## Data Flow Diagram: Before & After

### Before (Problematic)

```
User Input:
"Budget!", "Priority (Level)", "Deal@Stage"
        ↓
        ├→ Laya: "Does this choice match 'Budget!'?" ← Ambiguous!
        │  (String comparison fails, re-ask loop)
        │
        ├→ Qwen: "Generate JSON with any field names"
        │  (Qwen invents: {"budget_size": ..., "priority": ...})
        │  (Schema mismatch: expected "budget", got "budget_size")
```

### After (Fixed)

```
User Input:
"Budget!", "Priority (Level)", "Deal@Stage"
        ↓
Normalize:
"budget", "priority_level", "deal_stage"
        ├→ Bidirectional mapping stored for audit
        │
        ├→ Laya: "Does this choice match 'budget'?" ← Deterministic!
        │  (String match succeeds, no re-ask)
        │
        ├→ Qwen: "Generate JSON with these exact keys: budget, priority_level, deal_stage"
        │  (Qwen returns: {"budget": ..., "priority_level": ..., "deal_stage": ...})
        │  (Validation passes: keys match normalized schema)
```

## Guarantees Provided

✅ **No Ambiguity in Laya Routing**
- Laya always receives lowercase, underscore-separated identifiers
- String comparisons always deterministic

✅ **Strict Schema Conformance in Qwen**
- JSON output keys exactly match normalized keys
- No invented or misspelled field names

✅ **No Repetitive Clarification Loops**
- If user provides custom input, system processes it instantly
- No "What fields do you need?" re-ask if already answered

✅ **Bidirectional Traceability**
- Human labels stored for UI display
- Original raw strings stored for audit logs
- Full mapping maintained throughout pipeline

✅ **Reserved Field Protection**
- Custom fields prefixed with "custom_" if they collide with reserved names
- (e.g., "id" → "custom_id")

## Integration with Existing Code

### In `chat.py` endpoint:

```python
from app.services.crm_builder_integration import (
    process_user_crm_input,
    eliminate_clarification_loop,
)

# When user provides custom columns in a message
if user_mentioned_columns:
    result = process_user_crm_input(
        user_message=body.messages[-1].content,
        mentioned_columns=extract_columns(body.messages[-1].content),
    )
    
    # Use normalized schema for generation
    config = await provider.generate_crm_config_with_normalized_schema(
        result["generation_prompt"],
        system_prompt=result["qwen_system_prompt"],
    )
```

### In `ollama_provider.py`:

```python
from app.services.schema_binding import SchemaBinding

# Before calling Qwen
system_prompt = SchemaBinding.build_qwen_system_prompt(
    normalized_schema=normalized,
    base_prompt=self._get_system_prompt(decision),
)

# After Qwen returns
is_valid, cleaned, errors = SchemaBinding.validate_qwen_output(
    raw_qwen_output, normalized_schema
)

if not is_valid:
    logger.warning("Qwen output validation failed: %s", errors)
    # Use scaffold fallback or re-prompt
```

## Testing

19 comprehensive tests verify:
- ✅ Basic normalization
- ✅ Special character removal
- ✅ Space/hyphen handling
- ✅ Collision detection
- ✅ Laya choice building
- ✅ Qwen prompt injection
- ✅ Output validation
- ✅ Loop elimination
- ✅ End-to-end integration

Run tests:
```bash
cd backend
python -m pytest tests/test_normalization_layer.py -v
```

## Performance

- **Normalization**: O(n) where n = number of input strings (typically 5-20)
- **Mapping storage**: O(n) memory for bidirectional mapping
- **Laya choice building**: O(n) to construct choice dict
- **Qwen validation**: O(k) where k = number of Qwen output keys

Total overhead: Negligible (< 1ms for typical inputs)

## Troubleshooting

### Issue: Laya still getting ambiguous choices

**Cause:** Not using `SchemaBinding.build_laya_choice_primitive()`

**Fix:** Always call `SchemaBinding` to build choices:
```python
choice = SchemaBinding.build_laya_choice_primitive(
    question_key="field",
    instructions="...",
    normalized_schema=normalized,  # ← Use normalized schema
)
```

### Issue: Qwen returning mismatched keys

**Cause:** Not injecting normalized schema into system prompt

**Fix:** Use `SchemaBinding.build_qwen_system_prompt()`:
```python
prompt = SchemaBinding.build_qwen_system_prompt(
    normalized_schema=normalized,  # ← Inject normalized schema
)
```

### Issue: Clarification loop still happening

**Cause:** Not calling `eliminate_clarification_loop()`

**Fix:** Check readiness before generating:
```python
if eliminate_clarification_loop(
    history,
    user_provided_columns=mentioned_columns,
):
    # Generate immediately
```

## Future Enhancements

1. **Multi-language support**: Normalize columns from non-English input
2. **Fuzzy matching**: Handle typos in status/column names
3. **Collision resolution UI**: Let users choose between collision candidates
4. **Telemetry**: Track which normalizations happen most often
5. **Custom normalization rules**: Let admins define org-specific rules
