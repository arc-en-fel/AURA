# AURA Copilot Tool-Calling Pipeline: Investigation Report

**Date**: 2025-10-29  
**Scope**: Complete analysis of hard-coded entity names, raw tool-call display, and tool-calling mechanism  
**Status**: Investigation complete — root causes identified and documented

---

## Executive Summary

The AURA Copilot is exhibiting two critical behaviors:

1. **Hard-coded entity selection**: When a user asks to "add a lead," the Copilot generates tool calls with entity names that don't exist in the CRM (e.g., `machine_identifier`) and silently falls back to the first entity in the CRM, creating records in unintended entities.

2. **Raw tool-call display**: Tool-call JSON markers sometimes appear in the UI as plain text instead of being hidden or converted to natural-language confirmations.

Both issues stem from fundamental architectural gaps in entity resolution, system prompt construction, and tool-call message handling. The fixes require changes across the frontend UI layer, backend system prompt generation, entity resolution logic, and the tool-call execution pipeline.

---

## Root Causes Identified

### 1. Silent Entity Fallback in `ai_tools.py:_resolve_entity()`

**File**: `backend/app/services/ai_tools.py`, lines 40-55  
**Issue**: When the LLM generates an entity name that doesn't match any entity in the CRM, the function silently returns the first entity instead of indicating a resolution failure.

```python
@staticmethod
def _resolve_entity(config: dict[str, Any], entity_identifier: str | None) -> dict[str, Any] | None:
    """Resolve an entity from configuration by name, id, or label, or fallback to first entity."""
    entities = config.get("entities", [])
    if not entities:
        return None
    if not entity_identifier:
        return entities[0]
    norm = str(entity_identifier).lower().strip().replace(" ", "_").replace("-", "_")
    for e in entities:
        name = str(e.get("name", "")).lower().strip().replace(" ", "_").replace("-", "_")
        label = str(e.get("label", "")).lower().strip().replace(" ", "_").replace("-", "_")
        if name == norm or label == norm:
            return e
    # ← PROBLEM: Returns entities[0] instead of None when no match found (line 54)
    return entities[0]
```

**Impact**: If a CRM has only a `Machine Identifier` entity (name: `machine_identifier`) but no `Lead` entity, and the LLM generates `entity_name="machine_identifier"` (a hardcoded guess), the code silently creates a record in the machine identifier entity instead of informing the user that no lead entity exists.

---

### 2. Hardcoded Example Entity Names in System Prompt

**File**: `backend/app/routers/copilot.py`, lines 48-63  
**Issue**: The system prompt includes hardcoded example tool calls using example entity names (`lead`, `customer`, `contact`) without reflecting the actual CRM's entities.

```python
"# TOOL CALLING FORMAT\n"
"When you need to execute an action, generate a JSON tool call in this format:\n"
"TOOL_CALL: {\"name\": \"tool_name\", \"arguments\": {arg1: value1, arg2: value2}}\n\n"
"Examples:\n"
"- Create record: TOOL_CALL: {\"name\": \"create_record\", \"arguments\": {\"entity_name\": \"lead\", ...}}\n"
"- Update record: TOOL_CALL: {\"name\": \"update_record\", \"arguments\": {\"entity_name\": \"lead\", ...}}\n"
"- Delete record: TOOL_CALL: {\"name\": \"delete_record\", \"arguments\": {\"entity_name\": \"lead\", ...}}\n"
```

**Impact**: The LLM learns that valid entity names are `lead`, `customer`, and `contact` from these examples. Even if the active CRM has no such entities, the LLM may hallucinate these names or fall back to guessing based on examples it has seen in training. When the system prompt provides no actual list of valid CRM entities, the LLM generates invalid entity names.

---

### 3. Missing Entity Context in LLM System Prompt

**File**: `backend/app/routers/copilot.py`, lines 71-93  
**Issue**: The "ACTIVE CRM CONTEXT" section includes entity labels and fields but doesn't create an explicit, easily parseable list of valid entity names.

```python
crm_block = (
    f"\nACTIVE CRM CONTEXT:\n"
    f"Name: {config.get('name', 'Unknown')}\n"
    f"Industry: {config.get('industry', 'Unknown')}\n"
    ...
    f"Entities:\n" + ("\n".join(entity_summary) if entity_summary else "  None") + "\n"
)
```

The entity summary includes field names but not a clear machine-identifier list. When the LLM processes this, it has to infer valid entity names from a semi-structured text rather than from an explicit list.

---

### 4. No Tool-Name Validation Before Execution

**File**: `backend/app/routers/copilot.py`, lines 680-750  
**Issue**: The `execute_tool_call` endpoint accepts `entity_name` from the tool call without validating that the entity exists in the CRM.

```python
@router.post("/tool-call")
async def execute_tool_call(
    body: ToolCallRequest,
    user_id: CurrentUser,
):
    """
    Execute a CRM schema tool call from an AI assistant.
    ...
    """
    tool_handlers = { ... }
    
    tool_name = body.tool_name.strip().lower()
    if tool_name not in tool_handlers:
        return error_response(...)
    
    handler = tool_handlers[tool_name]
    
    # ← PROBLEM: entity_name validation happens inside the handler
    # If the handler silently falls back (see #1), the request succeeds with wrong entity
    result = handler(crm_id=body.crm_id, owner_id=str(user_id), **body.arguments)
```

**Impact**: The handler receives untrusted `entity_name` from the LLM. If the handler has a fallback mechanism (see #1), the tool call silently succeeds with the wrong entity.

---

### 5. Incomplete Tool-Call Regex in Frontend Parser

**File**: `frontend/src/features/ai-assistant/AIAssistantDrawer.tsx`, lines 36-55 and 62-64  
**Issue**: The regex pattern for parsing `TOOL_CALL: {...}` markers is designed for simple, non-nested JSON but fails on moderately complex tool-call arguments.

```typescript
function parseToolCalls(text: string): ToolCall[] {
  const toolCalls: ToolCall[] = [];
  
  // Match TOOL_CALL: {...} pattern (regex handles nested JSON up to ~2 levels)
  const regex = /TOOL_CALL:\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})/g;
  let match;
  
  while ((match = regex.exec(text)) !== null) {
    try {
      const call_json = match[1];
      const call_obj = JSON.parse(call_json) as ToolCall;
      if (call_obj.name && call_obj.arguments) {
        toolCalls.push(call_obj);
      }
    } catch (e) {
      console.warn('Failed to parse tool call:', match[1], e);
    }
  }
  
  return toolCalls;
}

function cleanToolCallMarkers(text: string): string {
  return text.replace(/TOOL_CALL:\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}/g, '').trim();
}
```

**Impact**: If the LLM generates a tool call with nested data structures (e.g., `data: {crm_status: "New", nested_field: {value: 123}}`), the regex may fail to match the complete JSON. When the regex fails, `cleanToolCallMarkers()` doesn't remove the marker, and the raw `TOOL_CALL: {...}` string appears in the UI.

---

### 6. No Validation of LLM-Generated Entity Names

**File**: `backend/app/routers/copilot.py`, lines 195-220  
**Issue**: The `_universal_action_reply()` function generates tool calls with entity names based on fuzzy matching against the user's input, but doesn't validate that the selected entity actually exists.

```python
# Find which entity the user might be referring to
target_entity = primary_entity
for ent in entities:
    if ent["name"].lower() in q_lower or ent["label"].lower() in q_lower:
        target_entity = ent
        break

target_entity_name = target_entity["name"] if target_entity else primary_entity_name
```

If no entity matches the user's input AND `primary_entity` is None, the code falls back to `primary_entity_name`. If this field was never set, it defaults to the first entity's name. This is inconsistent with the entity resolution logic.

---

### 7. Missing Required-Field Collection Workflow

**File**: `backend/app/routers/copilot.py` and `backend/app/services/ai_tools.py`  
**Issue**: When the Copilot creates a record, it doesn't collect all required fields before calling the backend. It generates a tool call with whatever data it can extract from the user message, and the backend's validation either succeeds (data is sufficient) or fails (validation error returned to user).

**Impact**: If a CRM requires fields like `email` and `phone_number` and the user only says "add a lead named John," the Copilot generates a tool call with only `name: "John"`. The backend validation fails, returning a generic error. The user must then correct the request, but there's no way to preserve context across multiple messages or to ask specifically which fields are missing.

---

### 8. Raw Tool-Call Text in User Messages

**File**: `frontend/src/features/ai-assistant/AIAssistantDrawer.tsx`, lines 217-235  
**Issue**: If the LLM's reply contains unparseable tool-call markers or if `cleanToolCallMarkers()` fails to remove them, the raw text is displayed to the user as part of the AI's message.

```typescript
const displayText = cleanToolCallMarkers(res.reply);
...
const aiMsg: Message = {
  sender: 'ai',
  text: displayText,  // ← If cleaning failed, displayText contains TOOL_CALL markers
  time: replyTime,
  action: ...,
};
```

**Impact**: Users see JSON fragments like `TOOL_CALL: {"name":"create_record","arguments":{"entity_name":"machine_identifier"...}}` in the conversation, which is confusing and breaks the natural-language conversation flow.

---

## Data Flow Analysis

### Current Flow (Problematic)

```
1. User: "Add a lead"
   ↓
2. Frontend sends message to /api/v1/copilot/chat
   ↓
3. Backend retrieves CRM context (e.g., entities: ["machine_identifier", "product"])
   ↓
4. Backend builds system prompt with HARDCODED examples:
      "entity_name": "lead"  ← User's CRM has no "lead" entity
   ↓
5. LLM sees examples using "lead" and templates its response:
      TOOL_CALL: {"name":"create_record","arguments":{"entity_name":"lead",...}}
   ↓
6. Frontend regex FAILS to parse (nested JSON issue) or succeeds
   ↓
7. Frontend calls /api/v1/copilot/tool-call with entity_name="lead"
   ↓
8. Backend's _resolve_entity() is called:
      - Looks for entity named "lead" → NOT FOUND
      - Returns entities[0] (first entity) → "machine_identifier"
   ↓
9. Record is created in WRONG entity (machine_identifier)
   ↓
10. Frontend displays raw TOOL_CALL marker if regex parsing failed:
       "I've prepared a new Lead record... TOOL_CALL: {..."
```

### Required Flow (After Fix)

```
1. User: "Add a lead"
   ↓
2. Frontend sends message to /api/v1/copilot/chat
   ↓
3. Backend retrieves CRM context (entities: ["machine_identifier", "product"])
   ↓
4. Backend builds system prompt with ACTUAL CRM ENTITIES:
      "VALID ENTITY NAMES: machine_identifier, product"
      Examples use valid entity names from the actual CRM
   ↓
5. LLM evaluates user input:
      - User says "lead" but valid entities are "machine_identifier" and "product"
      - No clear match → LLM asks for clarification or suggests available entities
   ↓
6. Frontend parses response (improved regex or fallback)
      - If Copilot asks a question, display it naturally
      - If Copilot provides a tool call, validate entity name before execution
   ↓
7. If user clarifies: "I meant product", continue
   OR Frontend prevents invalid tool calls
   ↓
8. Backend validates entity_name exists before tool execution
      - If entity not found, return error with available entities
   ↓
9. Record is created in CORRECT entity (product)
   ↓
10. Frontend displays clean confirmation:
       "✓ Successfully created product 'My Item'"
```

---

## Impact Analysis

| Component | Severity | Impact |
|-----------|----------|--------|
| **Entity Resolution** | Critical | Records created in wrong entities; data corruption |
| **System Prompt** | Critical | LLM hallucinates invalid entity names |
| **Tool Validation** | High | No defense against invalid tool calls |
| **Regex Parsing** | High | Raw JSON displayed to users |
| **Required Field Collection** | High | Poor UX; backend validation errors reported to user |
| **Error Handling** | Medium | Unclear error messages when entity not found |

---

## Files Affected

### Backend

1. **`backend/app/routers/copilot.py`**
   - `_build_system_prompt()` — generates system prompt with hardcoded examples
   - `_universal_action_reply()` — generates tool calls without entity validation
   - `execute_tool_call()` — executes tool calls without pre-validation

2. **`backend/app/services/ai_tools.py`**
   - `CRMSchemaTools._resolve_entity()` — silently falls back to first entity
   - `CRMSchemaTools.create_record()` — calls `_resolve_entity()` which may return wrong entity

### Frontend

1. **`frontend/src/features/ai-assistant/AIAssistantDrawer.tsx`**
   - `parseToolCalls()` — regex too restrictive for complex JSON
   - `cleanToolCallMarkers()` — fails to remove markers on parsing failure
   - `executeToolCall()` — no pre-validation of arguments

### Documentation

1. **`docs/API_CONTRACTS.md`**
   - May need updates to specify entity-name contract requirements

---

## Recommended Fixes (Architecture)

### Phase 1: System Prompt & Entity Context (Highest Priority)

**Objective**: Ensure LLM always uses valid entity names from the actual CRM.

1. **Dynamic entity list in system prompt** (`backend/app/routers/copilot.py`):
   - Replace hardcoded examples ("lead", "customer", "contact") with examples using actual CRM entities
   - Add explicit section listing all valid entity machine names
   - Add instruction: *"Always use entity names from the VALID ENTITY NAMES list. Never invent entity names."*

2. **Entity matching with clarification** (`backend/app/services/ai_tools.py`):
   - Change `_resolve_entity()` to return `None` (not `entities[0]`) when no match found
   - In `create_record()`, when entity resolution fails, return a special response indicating the need for clarification
   - Generate a tool call that asks the user to select from available entities

### Phase 2: Tool-Call Validation & Execution (High Priority)

**Objective**: Prevent invalid tool calls from reaching the database.

1. **Pre-execution validation** (`backend/app/routers/copilot.py::execute_tool_call()`):
   - Before calling the handler, fetch the CRM and validate that `entity_name` exists
   - Return a clear error if entity not found: *"Entity 'lead' not found in this CRM. Available entities: machine_identifier, product"*

2. **Improved error handling** (`backend/app/services/ai_tools.py`):
   - Return structured error responses with available entity names
   - Log all entity resolution failures for debugging

### Phase 3: Frontend Tool-Call Parsing & Display (High Priority)

**Objective**: Ensure tool calls are never displayed as raw JSON.

1. **Improved regex** (`frontend/src/features/ai-assistant/AIAssistantDrawer.tsx`):
   - Use a more robust JSON parser instead of regex (e.g., iterate through the text looking for `TOOL_CALL:` and parse the JSON that follows)
   - Fallback: If parsing fails, remove the marker and log a warning

2. **Tool-call display policy**:
   - Never display unparseable tool calls to users
   - If a tool call execution fails, show a friendly error message, not the raw JSON

### Phase 4: Required Field Collection (Medium Priority)

**Objective**: Collect missing required information before creating records.

1. **Required field analysis**:
   - In `create_record()`, analyze which fields are required but missing from the provided data
   - If missing, generate a response asking the user for those fields

2. **Multi-turn context**:
   - Preserve pending record-creation context across messages
   - Track which fields the user has provided and which are still needed

### Phase 5: Comprehensive Testing (All Priority Levels)

**Objective**: Ensure all scenarios work correctly.

Create tests for:
- CRM with `Lead` entity → user says "add a lead" → correct entity selected
- CRM with no `Lead` entity → user says "add a lead" → clarification requested
- CRM with multiple entities → user says "add" → asks which entity
- Required fields missing → user prompted for missing info
- LLM returns hardcoded entity name → backend rejects with suggestions
- Raw tool-call markers never displayed in UI
- Repeated requests don't create duplicates

---

## Success Criteria

When these fixes are complete:

1. ✓ User says "add a lead" → Copilot uses the actual `lead` entity (if it exists) or asks for clarification (if not)
2. ✓ Copilot never generates tool calls with invalid entity names
3. ✓ Backend validates entity names before tool execution
4. ✓ Raw `TOOL_CALL: {...}` JSON never appears in user conversations
5. ✓ Missing required fields are collected via natural conversation, not validation errors
6. ✓ All 14 test scenarios pass
7. ✓ No regression in existing functionality

---

## Next Steps

1. **Design Phase** (separate document):
   - Detailed API contract changes
   - Entity resolution algorithm
   - System prompt template changes
   - Required field collection workflow
   - Error handling and user messaging

2. **Implementation** (follows design):
   - Update backend system prompt generation
   - Implement entity validation in execute_tool_call
   - Improve frontend regex parsing
   - Add comprehensive tests

3. **Review & Testing**:
   - Integration testing with multiple CRM types
   - Regression testing of existing Copilot functionality
   - User acceptance testing

---

**Report prepared by**: Investigation Agent  
**Date**: 2025-10-29  
**Status**: Investigation complete — ready for design phase
