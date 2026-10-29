# AURA Copilot Universal Record Creation — Design Document

**Status:** Design for Implementation  
**Author:** AURA Design Review  
**Date:** 2025  
**Root Causes Addressed:** RC-001 through RC-008  
**Test Scenarios:** 14 mapped test cases  

---

## Overview

The AURA Copilot record creation pipeline currently suffers from eight critical defects that prevent it from operating universally on any CRM schema. The issues span entity resolution (silent fallback), hardcoded examples, missing validation, and incomplete parsing. This design specifies a complete fix addressing all root causes with concrete schemas, algorithms, and code paths.

The fix operates within the existing AURA architecture: schema-driven CRM definitions, Supabase PostgreSQL backend, FastAPI routes, and React/Vite frontend. No new dependencies or major architectural changes are needed. All fixes reuse existing API contracts, authentication flows, and tool infrastructure.

---

## Root Causes Analysis

| RC | File | Line | Issue | Impact |
|----|------|------|-------|--------|
| RC-001 | `ai_tools.py` | 54 | `_resolve_entity()` returns `entities[0]` instead of `None` when no match found | Silently creates records in wrong entity |
| RC-002 | `copilot.py` | 48–63 | System prompt contains hardcoded entity names ("Lead", "Machine Identifier") | LLM biased toward non-existent entities |
| RC-003 | `copilot.py` | 71–93 | Minimal entity context in CRM section of prompt | LLM lacks rich schema info to match user intent |
| RC-004 | `copilot.py` | 680–750 | No validation of tool arguments before backend dispatch | Malformed requests reach backend |
| RC-005 | `AIAssistantDrawer.tsx` | 36–55 | Incomplete regex for tool-call parsing (no handling for deeply nested JSON or edge cases) | Tool calls silently fail to parse |
| RC-006 | `copilot.py` | 195–220 | LLM-generated arguments never validated against field schemas | Invalid field values persisted |
| RC-007 | No explicit code | — | Multi-turn context for required fields not preserved; no workflow to collect them | Users cannot provide missing fields in follow-up messages |
| RC-008 | `AIAssistantDrawer.tsx` | 217–235 | Raw `TOOL_CALL` payload displayed when parsing fails | User sees `TOOL_CALL: {...}` in chat instead of friendly error |

---

## 1. Entity Resolution Algorithm

### 1.1 Input and Purpose

**Input:**
- `config: dict` — The CRM's configuration containing `entities` list
- `entity_identifier: str | None` — User-supplied entity name, label, or alias (case-insensitive, space/hyphen tolerant)
- `user_context: str | None` — The user's message, for semantic hints (optional, future NLP enhancement)

**Purpose:**
Deterministically match a user's entity request to the actual CRM entity without silent fallback. Return exactly one entity or `None` for ambiguous/missing matches.

### 1.2 Algorithm (Priority-Ordered Matching)

```
Function resolve_entity(config, entity_identifier, user_context=None):
  
  entities = config.get("entities", [])
  
  if not entity_identifier:
    # No identifier provided — no fallback to first entity
    return None
  
  # Normalize input for comparison
  norm_id = normalize(entity_identifier)  // lowercase, trim, replace spaces/hyphens with _
  
  // PRIORITY 1: Exact name match
  for entity in entities:
    if normalize(entity["name"]) == norm_id:
      return entity
  
  // PRIORITY 2: Exact label match
  for entity in entities:
    if normalize(entity["label"]) == norm_id:
      return entity
  
  // PRIORITY 3: Case-insensitive substring match (name or label)
  matches = []
  for entity in entities:
    e_name = entity["name"].lower()
    e_label = entity["label"].lower()
    if norm_id in e_name or norm_id in e_label:
      matches.append(entity)
  
  if len(matches) == 1:
    return matches[0]
  elif len(matches) > 1:
    // Ambiguous — return None, let caller ask user for clarification
    return None
  
  // PRIORITY 4: Fuzzy match on aliases (if entity has "aliases" field)
  for entity in entities:
    aliases = entity.get("aliases", [])
    for alias in aliases:
      if normalize(alias) == norm_id:
        return entity
  
  // No match found
  return None

Function normalize(text: str) -> str:
  return text.lower().strip().replace(" ", "_").replace("-", "_")
```

### 1.3 Behavior

- **Match found (unique):** Return the entity dict
- **No match found:** Return `None`; caller asks user for clarification and lists available entities
- **Multiple matches:** Return `None`; caller asks user to disambiguate
- **No entity_identifier provided:** Return `None`; do not fallback

### 1.4 Caller Responsibility

When `resolve_entity()` returns `None`, the Copilot must:

1. List all available entities with their labels and primary fields
2. Ask user which one they meant (e.g., "Which entity? I found: Lead, Contact, Machine Identifier")
3. Preserve the user's original intent (e.g., "add a lead") in the conversation context for the next turn

---

## 2. Dynamic System Prompt Template

### 2.1 Prompt Structure

The system prompt is built dynamically using a template that avoids hardcoded entity names and instead injects the **actual CRM schema** into three sections:

```
Section A: Capabilities & Intent Recognition
Section B: Tool Calling Format & Rules
Section C: Active CRM Context (dynamic)
Section D: Available AURA Routes
```

### 2.2 Template

```
You are AURA Copilot, an expert assistant for the AURA Self-Evolving CRM platform.

# YOUR CAPABILITIES
1. Answer questions about the user's active CRM configuration, records, workflows.
2. Guide users to AURA features.
3. Execute CRM actions using available tools.

# DISTINGUISHING COMMANDS vs. QUESTIONS
Recognize the user's intent:

COMMANDS (generate tool calls):
- "Add a lead", "Create a new contact", "Delete this record"
- "I want to add...", "I need to create...", "Change field X to Y"
→ Generate TOOL_CALL JSON

QUESTIONS (answer with information):
- "What fields does my CRM have?", "How do workflows work?"
- "Show me...", "Explain...", "How do I..."
→ Answer with schema information; do NOT generate tool call

# TOOL CALLING FORMAT
When executing an action, generate exactly one JSON tool call:
TOOL_CALL: {"name": "tool_name", "arguments": {...}}

Examples:
- Create: TOOL_CALL: {"name": "create_record", "arguments": {"entity_name": "lead", "data": {"full_name": "John Doe", "email": "john@example.com"}}}
- Update: TOOL_CALL: {"name": "update_record", "arguments": {"entity_name": "lead", "record_id": "uuid", "data": {"status": "Won"}}}
- Delete: TOOL_CALL: {"name": "delete_record", "arguments": {"entity_name": "lead", "record_id": "uuid"}}
- Add field: TOOL_CALL: {"name": "add_crm_field", "arguments": {"field_name": "priority", "label": "Priority", "field_type": "select", "options": ["High", "Medium", "Low"]}}
- Add stage: TOOL_CALL: {"name": "add_crm_stage", "arguments": {"stage_name": "Negotiation"}}

# RULES
- Base all actions on the ACTIVE CRM CONTEXT below. Never invent entities, fields, or statuses.
- If the user does not specify which entity to use, ask for clarification. Do NOT assume.
- If required fields are missing, ask the user for them. Preserve the context for multi-turn input.
- Keep replies under 120 words.
- Never execute code or SQL.
- For dangerous operations (delete, remove field/stage), always generate a TOOL_CALL — frontend will request user confirmation.

# AVAILABLE TOOLS

Record Actions:
- create_record(entity_name, data, source?): Create a new record in the specified entity
- update_record(entity_name, record_id, data): Update a record
- delete_record(entity_name, record_id): Delete a record (dangerous)

Field Actions:
- add_crm_field(field_name, label, field_type, required?, options?): Add a field
- update_crm_field(field_name, label?, field_type?, required?, options?): Update field
- delete_crm_field(field_name): Delete field (dangerous)

Stage Actions:
- add_crm_stage(stage_name, position?): Add pipeline stage
- delete_crm_stage(stage_name): Delete stage (dangerous)
- reorder_crm_stages(stage_order): Reorder stages
- reorder_crm_fields(field_order): Reorder fields

=== ACTIVE CRM CONTEXT ===

Name: {crm_name}
Industry: {industry}
Configuration Version: {config_version}

Entities ({entity_count}):
{entity_list}

Pipeline Stages: {stage_list}

Workflows ({workflow_count}):
{workflow_list}

=== END CONTEXT ===

Available AURA routes:
- dashboard: /dashboard
- crms: /crms
- records: /records
- analytics: /analytics
- workflows: /workflows
- settings: /settings
```

### 2.3 Dynamic Context Injection

**Entity List Formatting:**
```
- Lead (name: lead): fields = full_name (text, required), email (email), status (select, options: New/Qualified/Won/Lost)
- Contact (name: contact): fields = name (text, required), phone (phone), company (text)
- Machine Identifier (name: machine_identifier): fields = serial (text, required), model (text)
```

**Stage List Formatting:**
```
New → Qualified → Demo → Proposal → Won → Lost
```

**Workflow List Formatting (first 5):**
```
- Auto-qualify High-Value Leads (trigger: record_created, status: active)
- Send Welcome Email (trigger: entity:lead:created, status: active)
```

### 2.4 Implementation

**Location:** `backend/app/routers/copilot.py` — function `_build_system_prompt()`

```python
def _build_system_prompt(crm_context: dict[str, Any] | None) -> str:
  """
  Build dynamic system prompt injecting actual CRM schema.
  No hardcoded entity names.
  """
  
  base_template = """
  [Base capabilities, rules, tool format...]
  """
  
  if not crm_context:
    return base_template
  
  config = crm_context.get("configuration", {})
  crm_name = config.get("name", "your CRM")
  industry = config.get("industry", "unknown")
  config_version = crm_context.get("configuration_version", 1)
  entities = config.get("entities", [])
  stages = config.get("pipeline_stages", [])
  workflows = crm_context.get("workflows", [])
  
  # Format entity list
  entity_lines = []
  for e in entities[:10]:  # cap at 10 to control token usage
    fields_summary = ", ".join(
      f"{f['label']} ({f['type']}"
      + (f", required" if f.get("required") else "")
      + (f", options: {'/'.join(f['options'][:3])}" if f.get("type") == "select" and f.get("options") else "")
      + ")"
      for f in e.get("fields", [])[:5]
    )
    entity_lines.append(f"- {e['label']} (name: {e['name']}): {fields_summary}")
  
  # Format pipeline stages
  stage_text = " → ".join(stages) if stages else "(no stages configured)"
  
  # Format workflows
  workflow_lines = []
  for w in workflows[:5]:
    trigger_type = w.get("trigger", {}).get("type", "unknown")
    status = w.get("status", "unknown")
    workflow_lines.append(f"- {w.get('name', 'Unnamed')} (trigger: {trigger_type}, {status})")
  
  # Inject into template
  context_block = f"""
=== ACTIVE CRM CONTEXT ===
Name: {crm_name}
Industry: {industry}
Configuration Version: {config_version}

Entities ({len(entities)}):
{chr(10).join(entity_lines)}

Pipeline Stages: {stage_text}

Workflows ({len(workflows)}):
{chr(10).join(workflow_lines) if workflow_lines else "(no workflows)"}

=== END CONTEXT ===
  """
  
  return base_template + context_block
```

---

## 3. Required-Field Workflow (Multi-Turn Collection)

### 3.1 Overview

When the user requests record creation and required fields are missing, the Copilot must:

1. **Collect missing required fields** via multi-turn conversation
2. **Preserve pending record state** (entity, partially filled fields) across turns
3. **Validate supplied values** against field schemas
4. **Create the record only when sufficient data is available**

### 3.2 State Machine

```
State 1: USER_REQUEST_RECEIVED
  ↓
  Copilot parses user message for entity and fields
  ↓
  Determines which entity was requested (or asks for clarification)
  ↓
  
State 2: COLLECT_REQUIRED_FIELDS
  ↓
  Identifies missing required fields
  ↓
  If all required fields present → State 4 (CREATE)
  If some missing → Copilot asks for them, enters State 3
  ↓
  
State 3: AWAITING_USER_INPUT
  ↓
  User provides values for missing fields
  ↓
  Copilot validates input against field type/options
  ↓
  If valid and all required fields now present → State 4 (CREATE)
  If still missing → loop back to ask for more
  ↓
  
State 4: CREATE_RECORD
  ↓
  Generate TOOL_CALL with complete, validated data
  ↓
  Frontend executes, backend confirms
```

### 3.3 Pending Record Context

The backend maintains a **conversation-scoped pending record** in the chat history. The Copilot tracks:

```python
{
  "pending_entity_name": "lead",
  "pending_entity_label": "Lead",
  "collected_data": {
    "full_name": "John Doe",
    "email": "john@example.com",
    // other fields provided by user
  },
  "missing_required_fields": ["status"],  // updated after each turn
  "all_entity_fields": [...]  // for validation
}
```

**Storage:** This state is embedded in the system message or passed in the message history when calling the LLM. It is **not persisted** to the database (only conversation-scoped).

### 3.4 Prompt Extension for Multi-Turn Mode

When in pending-record state, the system prompt includes:

```
# PENDING RECORD CREATION

You are collecting information for a new {entity_label} record.

Already collected:
- full_name: "John Doe"
- email: "john@example.com"

Still needed (required):
- status: (select: New, Qualified, Won, Lost)

Ask the user for the missing field value, and validate it when provided.
If all required fields are now complete, generate TOOL_CALL to create the record.
```

### 3.5 Validation Rules During Collection

For each field value supplied by the user:

1. **Type validation:** Ensure the value matches the field type (text, number, date, email, phone, select, etc.)
2. **Required validation:** If field is required, value must not be null/empty
3. **Enum validation:** If field is `select`, value must be in the `options` list
4. **Format validation:** For email/phone, apply regex checks
5. **Reject/Clarify:** If invalid, ask user for correction; do not silently accept

Example:
```
User: "status: invalid_value"
Copilot: "I didn't recognize that status. The options are: New, Qualified, Won, Lost. Which one did you mean?"
```

### 3.6 Implementation Points

**Backend (copilot.py):**
- Enhance system prompt builder to include pending record context
- In `_universal_action_reply()`, detect "provide missing fields" scenario
- Validate field values using entity schema before generating TOOL_CALL

**Frontend (AIAssistantDrawer.tsx):**
- When parsing tool call fails, show friendly error, not raw JSON
- Preserve conversation history for multi-turn context

---

## 4. Frontend Tool-Call Parser (Improved Regex & Error Handling)

### 4.1 Parsing Algorithm

**Goal:** Extract `TOOL_CALL: {...}` from LLM reply with robust JSON handling.

**Input:** LLM response text (may contain multiple tool calls, mixed with natural language)

**Output:** `ToolCall[]` where `ToolCall = {name: string, arguments: Record<string, any>}`

### 4.2 Algorithm

```
Function parseToolCalls(text: string): ToolCall[]:
  
  toolCalls = []
  
  // Find all TOOL_CALL: markers
  index = 0
  while (index < text.length):
    marker_index = text.indexOf("TOOL_CALL:", index)
    if marker_index == -1:
      break
    
    // Start of JSON is after "TOOL_CALL:"
    json_start = marker_index + "TOOL_CALL:".length
    
    // Skip whitespace
    while json_start < text.length and text[json_start] in [' ', '\n', '\t']:
      json_start += 1
    
    if json_start >= text.length or text[json_start] != '{':
      index = json_start
      continue  // Not a valid JSON start
    
    // Find matching closing brace using a bracket counter
    brace_count = 0
    in_string = false
    escape_next = false
    json_end = json_start
    
    for char_idx in range(json_start, text.length):
      char = text[char_idx]
      
      if escape_next:
        escape_next = false
        continue
      
      if char == '\\':
        escape_next = true
        continue
      
      if char == '"' and not escape_next:
        in_string = not in_string
        continue
      
      if not in_string:
        if char == '{':
          brace_count += 1
        elif char == '}':
          brace_count -= 1
          if brace_count == 0:
            json_end = char_idx + 1
            break
    
    if brace_count != 0:
      index = json_start + 1
      continue  // Unmatched braces
    
    // Extract and parse JSON
    json_string = text[json_start:json_end]
    try:
      tool_call = JSON.parse(json_string)
      if tool_call.name and tool_call.arguments:
        toolCalls.append(tool_call)
    catch error:
      logger.warn("Failed to parse tool call:", json_string, error)
      // Continue, do not fail
    
    index = json_end
  
  return toolCalls
```

### 4.3 Error Handling

If parsing fails:

1. **Incomplete JSON:** Log warning, continue scanning for more calls
2. **No TOOL_CALL marker:** Treat entire reply as conversational text (not an error)
3. **Malformed tool structure (missing `name` or `arguments`):** Skip that call, continue
4. **Invalid JSON:** Log and skip

**Never:**
- Throw exception and crash
- Return raw `TOOL_CALL: {...}` in displayed text
- Silently ignore parsing errors in logs

**Always:**
- Remove all `TOOL_CALL: {...}` markers from display text before showing to user
- Log parsing issues at `debug` level (informational, not error)

### 4.4 Implementation

**Location:** `frontend/src/features/ai-assistant/AIAssistantDrawer.tsx`

```typescript
interface ToolCall {
  name: string;
  arguments: Record<string, any>;
}

function parseToolCalls(text: string): ToolCall[] {
  const toolCalls: ToolCall[] = [];
  let index = 0;

  while (index < text.length) {
    const markerIndex = text.indexOf("TOOL_CALL:", index);
    if (markerIndex === -1) break;

    const jsonStart = markerIndex + "TOOL_CALL:".length;
    let wsIdx = jsonStart;
    while (wsIdx < text.length && /\s/.test(text[wsIdx])) {
      wsIdx++;
    }

    if (wsIdx >= text.length || text[wsIdx] !== "{") {
      index = wsIdx;
      continue;
    }

    let braceCount = 0;
    let inString = false;
    let escapeNext = false;
    let jsonEnd = wsIdx;

    for (let i = wsIdx; i < text.length; i++) {
      const char = text[i];

      if (escapeNext) {
        escapeNext = false;
        continue;
      }

      if (char === "\\") {
        escapeNext = true;
        continue;
      }

      if (char === '"' && !escapeNext) {
        inString = !inString;
        continue;
      }

      if (!inString) {
        if (char === "{") braceCount++;
        else if (char === "}") {
          braceCount--;
          if (braceCount === 0) {
            jsonEnd = i + 1;
            break;
          }
        }
      }
    }

    if (braceCount !== 0) {
      index = wsIdx + 1;
      continue;
    }

    const jsonString = text.substring(wsIdx, jsonEnd);
    try {
      const toolCall = JSON.parse(jsonString) as ToolCall;
      if (toolCall.name && toolCall.arguments) {
        toolCalls.push(toolCall);
      }
    } catch (e) {
      console.debug("Failed to parse tool call:", jsonString, e);
    }

    index = jsonEnd;
  }

  return toolCalls;
}

function cleanToolCallMarkers(text: string): string {
  // Remove all TOOL_CALL: {...} markers (greedy or non-greedy, handles nesting)
  return text
    .replace(/TOOL_CALL:\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}/g, "")
    .trim();
}
```

### 4.5 Frontend Display Logic

After parsing tool calls:

```typescript
const displayText = cleanToolCallMarkers(res.reply);

if (toolCalls.length > 0) {
  // Execute tool calls (with confirmation for dangerous operations)
  for (const toolCall of toolCalls) {
    if (["delete_record", "delete_crm_field", "delete_crm_stage"].includes(toolCall.name)) {
      // Show confirmation dialog
      await showToolConfirmationDialog(toolCall);
    } else {
      // Execute immediately
      await executeToolCall(toolCall);
    }
  }
} else if (/TOOL_CALL:/i.test(res.reply)) {
  // Marker found but failed to parse — show friendly error
  const errorMsg: Message = {
    sender: "ai",
    text: "I tried to execute an action, but there was a formatting issue. Please try again or rephrase your request.",
    time: now,
  };
  setMessages((prev) => [...prev, errorMsg]);
} else {
  // No tool call — display reply as-is
}

// Display the cleaned reply (without tool-call markers)
const aiMsg: Message = {
  sender: "ai",
  text: displayText,
  time: now,
};
setMessages((prev) => [...prev, aiMsg]);
```

---

## 5. Backend Validation Schema

### 5.1 Tool Argument Validation Rules

Every tool receives arguments. The backend must validate each before execution.

**Validation Layers:**

1. **Tool-level schema validation** (Pydantic, OpenAPI spec)
2. **Business logic validation** (CRM ownership, entity exists, etc.)
3. **Data validation** (field types, required fields, enum values)

### 5.2 Validation Rules by Tool

#### create_record

**Required arguments:**
- `entity_name` (str): Must match an entity in the CRM configuration
- `data` (dict): Field values

**Validation:**
1. `entity_name` → Resolve using `_resolve_entity()`. If `None`, return 400 with entity list.
2. `data` → Validate each field:
   - Reject unknown fields not in entity schema
   - Check required fields are present
   - Type-check each value
   - For select fields, ensure value is in options

**Response on validation failure:**
```json
{
  "success": false,
  "error_code": "VALIDATION_ERROR",
  "error_message": "Missing required field: email. Valid fields: [list]",
  "details": {
    "entity": "lead",
    "missing_required": ["email"],
    "schema": {...}
  }
}
```

#### update_record

**Required arguments:**
- `entity_name` (str)
- `record_id` (str or UUID)
- `data` (dict)

**Validation:**
1. Resolve entity using `_resolve_entity()`. If `None`, return 400.
2. Verify record exists in database.
3. Validate `data` the same way as create_record (but allow partial updates).

#### delete_record

**Required arguments:**
- `entity_name` (str)
- `record_id` (str or UUID)

**Validation:**
1. Resolve entity. If `None`, return 400.
2. Verify record exists.
3. Check for referential constraints (optional; document if skipped).

#### add_crm_field

**Required arguments:**
- `field_name` (str): Pattern `^[a-z][a-z0-9_]{0,62}$`
- `label` (str): min 1, max 100
- `field_type` (enum): text, textarea, email, number, date, boolean, select, phone

**Optional arguments:**
- `required` (bool): default False
- `options` (list): for select fields

**Validation:**
1. Verify `field_name` matches pattern
2. If `field_type` is "select", ensure `options` is non-empty
3. Verify field does not already exist in entity
4. Validate with Pydantic schema

#### add_crm_stage

**Required arguments:**
- `stage_name` (str): min 1, max 50

**Optional arguments:**
- `position` (int): 0-based index

**Validation:**
1. Verify stage does not already exist
2. If position provided, ensure it's within bounds

### 5.3 Pydantic Schema

**Location:** `backend/app/schemas/copilot.py` (new file)

```python
from pydantic import BaseModel, Field, field_validator
from typing import Any, Optional, Literal

class ToolArgumentsSchema(BaseModel):
  """Base schema for tool arguments."""
  pass

class CreateRecordArguments(ToolArgumentsSchema):
  entity_name: str = Field(
    ...,
    min_length=1,
    max_length=100,
    description="Machine name of the entity"
  )
  data: dict[str, Any] = Field(
    default_factory=dict,
    description="Record field values"
  )
  source: Optional[str] = Field(
    default="AI Copilot",
    max_length=100
  )

class UpdateRecordArguments(ToolArgumentsSchema):
  entity_name: str = Field(...)
  record_id: str = Field(...)
  data: dict[str, Any] = Field(...)

class DeleteRecordArguments(ToolArgumentsSchema):
  entity_name: str = Field(...)
  record_id: str = Field(...)

class AddCRMFieldArguments(ToolArgumentsSchema):
  field_name: str = Field(
    ...,
    pattern="^[a-z][a-z0-9_]{0,62}$",
    description="Lowercase, alphanumeric, underscores"
  )
  label: str = Field(..., min_length=1, max_length=100)
  field_type: Literal[
    "text", "textarea", "email", "number", "date",
    "boolean", "select", "phone"
  ] = "text"
  required: bool = False
  options: Optional[list[str]] = None

class AddCRMStageArguments(ToolArgumentsSchema):
  stage_name: str = Field(..., min_length=1, max_length=50)
  position: Optional[int] = Field(None, ge=0)

# Map tool names to argument schemas
TOOL_ARGUMENT_SCHEMAS = {
  "create_record": CreateRecordArguments,
  "update_record": UpdateRecordArguments,
  "delete_record": DeleteRecordArguments,
  "add_crm_field": AddCRMFieldArguments,
  "add_crm_stage": AddCRMStageArguments,
  # ...
}
```

### 5.4 Validation at Tool Execution

**Location:** `backend/app/routers/copilot.py` — function `execute_tool_call()`

```python
@router.post("/tool-call")
async def execute_tool_call(
  body: ToolCallRequest,
  user_id: CurrentUser,
):
  """
  Execute a tool call with full validation.
  """
  tool_name = body.tool_name.strip().lower()
  
  # 1. Validate tool exists
  if tool_name not in TOOL_HANDLERS:
    return error_response(400, "INVALID_TOOL", f"Unknown tool: {tool_name}")
  
  # 2. Validate arguments schema
  schema_class = TOOL_ARGUMENT_SCHEMAS.get(tool_name)
  if schema_class:
    try:
      validated_args = schema_class(**body.arguments)
      # Use validated_args.dict() for tool call
    except ValidationError as e:
      return error_response(422, "ARGUMENT_VALIDATION_ERROR", str(e))
  
  # 3. Execute tool with owner_id for authorization
  handler = TOOL_HANDLERS[tool_name]
  try:
    result = handler(
      crm_id=body.crm_id,
      owner_id=str(user_id),
      **validated_args.dict()
    )
  except Exception as e:
    logger.exception("Tool execution failed")
    return error_response(500, "TOOL_EXECUTION_ERROR", str(e))
  
  # 4. Return result
  if result.get("success"):
    return success_response(result)
  else:
    # Tool returned a structured error
    return error_response(
      400,
      result.get("error_code", "UNKNOWN_ERROR"),
      result.get("error_message", "Tool execution failed")
    )
```

---

## 6. API Contracts & Response Formats

### 6.1 POST /api/v1/copilot/chat

**Request:**
```json
{
  "messages": [
    {"role": "user", "content": "I want to add a lead"},
    {"role": "assistant", "content": "Which entity? I found: Lead, Contact, Machine Identifier"}
  ],
  "crm_id": "uuid-of-crm"
}
```

**Response (Success):**
```json
{
  "success": true,
  "data": {
    "reply": "I've prepared a new Lead record for creation.",
    "nav_route": null,
    "nav_label": null,
    "fallback": false
  }
}
```

**Response (Entity Ambiguity):**
```json
{
  "success": true,
  "data": {
    "reply": "I found multiple entities matching your request:\n- Lead\n- Contact\nWhich one did you mean?",
    "nav_route": null,
    "nav_label": null,
    "fallback": false
  }
}
```

### 6.2 POST /api/v1/copilot/tool-call

**Request:**
```json
{
  "tool_name": "create_record",
  "crm_id": "uuid",
  "arguments": {
    "entity_name": "lead",
    "data": {
      "full_name": "John Doe",
      "email": "john@example.com",
      "status": "New"
    }
  }
}
```

**Response (Success):**
```json
{
  "success": true,
  "data": {
    "success": true,
    "crm_id": "uuid",
    "entity_name": "lead",
    "data": {
      "id": "record-uuid",
      "full_name": "John Doe",
      "email": "john@example.com",
      "status": "New",
      "created_at": "2025-01-15T10:30:00Z"
    }
  }
}
```

**Response (Validation Error):**
```json
{
  "success": false,
  "error_code": "VALIDATION_ERROR",
  "error_message": "Missing required field: email",
  "details": {
    "entity": "lead",
    "required_fields": ["full_name", "email", "status"],
    "missing": ["email"],
    "provided": {"full_name": "John Doe"}
  }
}
```

---

## 7. Test Scenarios & Code Path Mapping

### Test Mapping Matrix

| # | Scenario | Component | Test Focus | Expected Outcome |
|---|----------|-----------|------------|------------------|
| 1 | CRM has Lead entity; user says "add a lead" | copilot.py + ai_tools.py | Entity matching (Priority 1: exact name) | Resolves to Lead entity, collects required fields |
| 2 | CRM has Contact entity but no Lead; user says "add a lead" | copilot.py | Entity resolution fails (no match) | Copilot asks user which entity they meant, lists alternatives |
| 3 | CRM has Lead, Contact, Customer entities; user says "add a lead" | copilot.py | Entity matching (Priority 2: label match) | Resolves to Lead unambiguously |
| 4 | CRM has only Machine Identifier; user says "add a lead" | copilot.py | No match scenario | Copilot explains available entities, does NOT silently create Machine Identifier |
| 5 | Record creation missing required fields | copilot.py → _universal_action_reply() | Multi-turn workflow initiation | Copilot asks for missing fields, enters collection state |
| 6 | User provides missing field values in follow-up | copilot.py → chat endpoint | Multi-turn context preservation | Copilot validates, recognizes all required fields now present, generates TOOL_CALL |
| 7 | Groq/LLM provider returns native tool_calls format | copilot.py → _call_groq_copilot() | Native tool-call handling | Backend transforms to TOOL_CALL: {...} format |
| 8 | Local Ollama model returns textual TOOL_CALL | copilot.py → _call_ollama_copilot() | Textual tool-call parsing | Backend extracts JSON, generates valid tool call |
| 9 | Frontend receives malformed TOOL_CALL JSON | AIAssistantDrawer.tsx → parseToolCalls() | Parser error recovery | Parser logs warning, continues, displays friendly error message (not raw JSON) |
| 10 | Record creation fails at backend (DB error, validation) | ai_tools.py → create_record() | Failure handling | Backend returns structured error (error_code, error_message, details) |
| 11 | Record creation succeeds | ai_tools.py + AIAssistantDrawer.tsx | Success confirmation | UI shows success message, refreshes records table, clears pending state |
| 12 | Request attempts to access another tenant's CRM | copilot.py (auth via user_id) | Authorization check | Backend returns 403, request rejected at CRMRepository level |
| 13 | Repeated identical requests within short time window | Frontend + Backend | Idempotency / deduplication | Backend recognizes duplicate via record ID or request hash, prevents double-creation |
| 14 | CRM schema changes mid-conversation (config_version bumps) | copilot.py → system prompt builder | Schema versioning | Copilot re-fetches schema on next turn, uses updated entity/field definitions |

### Test Implementation Locations

#### Test 1: Entity Matching (Exact Name)
**File:** `tests/test_ai_tools.py`
```python
def test_resolve_entity_exact_name_match():
  config = {
    "entities": [
      {"name": "lead", "label": "Lead", "fields": [...]},
      {"name": "contact", "label": "Contact", "fields": [...]}
    ]
  }
  entity = CRMSchemaTools._resolve_entity(config, "lead")
  assert entity["name"] == "lead"
```

#### Test 2: No Match (List Alternatives)
**File:** `tests/test_copilot_routes.py`
```python
def test_copilot_no_matching_entity():
  crm_context = {
    "configuration": {
      "entities": [
        {"name": "machine_identifier", "label": "Machine Identifier", ...}
      ]
    }
  }
  question = "I want to add a lead"
  result = _universal_action_reply(question, crm_context)
  assert "available" in result["reply"].lower()
  assert "Machine Identifier" in result["reply"]
  assert result["fallback"] is False
```

#### Test 3: Multi-Turn Collection
**File:** `tests/test_copilot_routes.py`
```python
def test_copilot_multi_turn_required_field_collection():
  # Turn 1: User requests lead creation without email
  messages_turn1 = [{"role": "user", "content": "Add a lead named John"}]
  result1 = copilot_chat(messages_turn1, crm_id, user_id)
  assert "email" in result1["reply"]  # Ask for email
  
  # Turn 2: User provides email
  messages_turn2 = [
    {"role": "user", "content": "Add a lead named John"},
    {"role": "assistant", "content": result1["reply"]},
    {"role": "user", "content": "email: john@example.com"}
  ]
  result2 = copilot_chat(messages_turn2, crm_id, user_id)
  assert "TOOL_CALL" in result2["reply"]  # Now we generate the call
  tool_calls = parseToolCalls(result2["reply"])
  assert len(tool_calls) == 1
  assert tool_calls[0]["name"] == "create_record"
```

#### Test 4: Frontend Parser Robustness
**File:** `tests/test_frontend_parser.js`
```javascript
test("parseToolCalls handles nested JSON", () => {
  const text = `Here's the action:
TOOL_CALL: {"name": "create_record", "arguments": {"entity_name": "lead", "data": {"name": "John", "metadata": {"source": "API"}}}}
Thank you!`;
  
  const calls = parseToolCalls(text);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].arguments.data.metadata.source, "API");
});

test("parseToolCalls recovers from malformed JSON", () => {
  const text = `Action:
TOOL_CALL: {"name": "create_record", "arguments": {invalid json}
Let me try again:
TOOL_CALL: {"name": "create_record", "arguments": {"entity_name": "lead", "data": {}}}`;
  
  const calls = parseToolCalls(text);
  assert.equal(calls.length, 1);  // Only the valid one
  assert.equal(calls[0].name, "create_record");
});
```

#### Test 5: Authorization Check
**File:** `tests/test_copilot_auth.py`
```python
def test_copilot_rejects_unauthorized_crm_access():
  # User A's CRM
  crm_a = create_test_crm(owner_id="user_a_id")
  
  # User B tries to access User A's CRM
  with pytest.raises(Unauthorized):
    result = copilot_chat(
      messages=[{"role": "user", "content": "Add a lead"}],
      crm_id=crm_a["id"],
      user_id="user_b_id"
    )
```

#### Test 6: Tool Argument Validation
**File:** `tests/test_tool_validation.py`
```python
def test_tool_call_validation_rejects_invalid_entity():
  result = execute_tool_call(
    tool_name="create_record",
    crm_id="crm_id",
    arguments={"entity_name": "nonexistent", "data": {}},
    user_id="user_id"
  )
  assert result["success"] is False
  assert result["error_code"] == "VALIDATION_ERROR"
  assert "entity" in result["error_message"].lower()
```

---

## 8. Fixes to Root Causes

### RC-001: Silent Fallback in `_resolve_entity()`

**File:** `backend/app/services/ai_tools.py`, line 54

**Before:**
```python
def _resolve_entity(config, entity_identifier):
  entities = config.get("entities", [])
  if not entities:
    return None
  if not entity_identifier:
    return entities[0]  # ❌ WRONG: silent fallback
  # ... matching logic ...
  return entities[0]  # ❌ WRONG: silent fallback on no match
```

**After:**
```python
def _resolve_entity(config, entity_identifier):
  entities = config.get("entities", [])
  if not entities:
    return None
  if not entity_identifier:
    return None  # ✅ CORRECT: no fallback
  # ... Priority 1-4 matching logic per section 1.2 ...
  return None  # ✅ CORRECT: return None if no match (not entities[0])
```

---

### RC-002: Hardcoded Entity Names in System Prompt

**File:** `backend/app/routers/copilot.py`, lines 48–63

**Before:**
```python
base = (
  # ...
  "Examples:\n"
  "- Create record: TOOL_CALL: {...\"entity_name\": \"lead\"...}\n"  # ❌ Hardcoded
  "- Update record: TOOL_CALL: {...\"entity_name\": \"lead\"...}\n"  # ❌ Hardcoded
  # ...
)
```

**After:**
```python
# Use dynamic template with placeholders
base = (
  # ... (generic, no hardcoded entities)
  "Examples:\n"
  "- Create record: TOOL_CALL: {\"name\": \"create_record\", \"arguments\": {...}}\n"
  "  (substitute actual entity names from ACTIVE CRM CONTEXT)\n"
  # ...
)

# Inject actual entities later in context section
if crm_context:
  # ... (section 2.3: entity list formatting)
```

---

### RC-003: Minimal Entity Context in Prompt

**File:** `backend/app/routers/copilot.py`, lines 71–93

**Before:**
```python
crm_block = (
  f"ACTIVE CRM CONTEXT:\n"
  f"Entities: [abbreviated list]\n"  # ❌ Minimal context
)
```

**After:**
```python
# Per section 2.3: detailed entity formatting
entity_lines = []
for e in entities[:10]:
  fields_summary = ", ".join(
    f"{f['label']} ({f['type']}"
    + (", required" if f.get("required") else "")
    + ")"
    for f in e.get("fields", [])[:5]
  )
  entity_lines.append(f"- {e['label']} ({e['name']}): {fields_summary}")
```

---

### RC-004: No Entity Validation Before Tool Execution

**File:** `backend/app/routers/copilot.py`, lines 680–750

**Before:**
```python
@router.post("/tool-call")
async def execute_tool_call(body, user_id):
  handler = TOOL_HANDLERS[body.tool_name]  # ❌ No validation of arguments
  result = handler(**body.arguments)  # ❌ Directly pass unvalidated args
```

**After:**
```python
@router.post("/tool-call")
async def execute_tool_call(body, user_id):
  # 1. Validate tool exists
  if tool_name not in TOOL_HANDLERS:
    return error_response(400, "INVALID_TOOL", ...)
  
  # 2. Validate arguments against schema
  schema_class = TOOL_ARGUMENT_SCHEMAS.get(tool_name)
  if schema_class:
    try:
      validated_args = schema_class(**body.arguments)  # ✅ Pydantic validation
    except ValidationError as e:
      return error_response(422, "ARGUMENT_VALIDATION_ERROR", str(e))
  
  # 3. Execute handler with validated args
  result = handler(crm_id=body.crm_id, owner_id=str(user_id), **validated_args.dict())
```

---

### RC-005: Incomplete Regex in Frontend Tool Parser

**File:** `frontend/src/features/ai-assistant/AIAssistantDrawer.tsx`, lines 36–55

**Before:**
```typescript
const regex = /TOOL_CALL:\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})/g;  // ❌ Limited nesting
```

**After:**
```typescript
// Use proper brace-counting algorithm (section 4.2)
function parseToolCalls(text: string): ToolCall[] {
  // ✅ Handles arbitrary nesting via escape-aware bracket counting
  // ✅ Errors are logged, not thrown
  // ✅ Partial matches skipped gracefully
}
```

---

### RC-006: No Pre-Validation of LLM Arguments

**File:** `backend/app/routers/copilot.py`, lines 195–220

**Before:**
```python
# LLM generates TOOL_CALL, frontend sends to backend
# Backend immediately calls handler without validating field values
```

**After:**
```python
# Per section 5.2-5.4: Full validation schema
# Every field value is type-checked, required fields verified, enum options validated
# Backend returns structured error if validation fails, not generic 500
```

---

### RC-007: Missing Multi-Turn Required-Field Workflow

**No explicit code location** — This is a missing feature.

**After (Implementation):**
```python
# Per section 3: Multi-turn context preserved in conversation history
# Copilot tracks pending_entity_name, collected_data, missing_required_fields
# Each turn validates new input against entity schema
# Tool call generated only when all required fields present and valid
```

---

### RC-008: Raw Tool-Call Display on Parse Failure

**File:** `frontend/src/features/ai-assistant/AIAssistantDrawer.tsx`, lines 217–235

**Before:**
```typescript
// If parsing fails or incomplete, display raw TOOL_CALL in chat
const displayText = res.reply;  // ❌ Includes TOOL_CALL: {...}
```

**After:**
```typescript
// Per section 4.4: Always remove TOOL_CALL markers from display
const displayText = cleanToolCallMarkers(res.reply);  // ✅ Removes markers

// If parsing fails, show friendly error
if (/TOOL_CALL:/i.test(res.reply) && toolCalls.length === 0) {
  showFriendlyError("I tried to execute an action, but there was an issue. Please try again.");
}
```

---

## 9. Security & Auth Considerations

### 9.1 Tenant Isolation

- Every CRM operation checks `owner_id` via authenticated user_id (from JWT)
- Backend uses Supabase RLS policies or application-level checks
- Test suite includes cross-tenant attack scenarios

### 9.2 Input Validation

- All LLM-generated arguments validated against Pydantic schemas before execution
- User-supplied field values type-checked and enum-validated
- No code/SQL execution from model output

### 9.3 Error Messages

- Backend never returns raw database errors or stack traces to client
- All errors have stable `error_code` for frontend handling
- `error_message` is user-friendly and does not leak implementation details

---

## 10. Testability & Coverage

### 10.1 Unit Tests

- `test_resolve_entity_*`: 6 tests (exact match, label match, substring, fuzzy, no match, ambiguous)
- `test_copilot_intent_*`: 5 tests (command vs. question, create, update, delete, schema query)
- `test_tool_validation_*`: 4 tests (invalid entity, missing required field, type mismatch, enum validation)

### 10.2 Integration Tests

- `test_copilot_chat_e2e_*`: 4 tests (single-turn record creation, multi-turn field collection, tool execution, error recovery)
- `test_auth_isolation_*`: 3 tests (read, write, delete isolation across tenants)
- `test_tool_call_execution_*`: 3 tests (success, backend validation error, authorization error)

### 10.3 Frontend Tests

- `test_parseToolCalls_*`: 5 tests (simple JSON, nested objects, malformed JSON, multiple calls, empty input)
- `test_cleanToolCallMarkers_*`: 2 tests (single marker, multiple markers)
- `test_AIAssistantDrawer_*`: 3 tests (tool execution flow, confirmation dialog, error display)

### 10.4 Test Framework & Coverage

- **Backend:** pytest (existing), target 85%+ coverage on copilot.py and ai_tools.py
- **Frontend:** Jest or Vitest, target 80%+ coverage on AIAssistantDrawer.tsx

---

## 11. Implementation Timeline & Dependencies

### Phase 1: Backend Core (2-3 days)

1. Fix RC-001: Update `_resolve_entity()` to return `None` on no match
2. Enhance RC-003: Build dynamic system prompt with rich entity context
3. Implement multi-turn workflow (RC-007): Context preservation in conversation history
4. Add validation schema (RC-006): Pydantic models for tool arguments
5. Write backend unit + integration tests for Phases 1-3

### Phase 2: Tool Call Validation (1-2 days)

1. Implement tool-call validation endpoint (`/api/v1/copilot/tool-call`)
2. Add argument schema validation before handler dispatch
3. Update CRMSchemaTools handlers to return structured errors
4. Write tests for validation errors and edge cases

### Phase 3: Frontend Parser (1-2 days)

1. Replace regex with brace-counting parser (RC-005)
2. Implement `cleanToolCallMarkers()` (RC-008)
3. Add error handling for parse failures
4. Write frontend unit tests for parser

### Phase 4: Integration & E2E Tests (1-2 days)

1. Write 14 test scenarios per section 7
2. Test cross-tenant isolation
3. Test schema version bump handling
4. E2E tests covering full conversation flows

### Phase 5: Documentation & Rollout (1 day)

1. Update API_CONTRACTS.md with tool-call validation details
2. Document multi-turn workflow in user guide
3. Add internal ADR (Architecture Decision Record) for entity resolution

**Total Effort:** ~7-10 days

### Dependencies

- Supabase RLS or application auth framework must be operational
- Groq API key and Ollama local model available for testing both paths
- Existing CRMRepository and database schema in place

---

## 12. Responses to Design Review Findings

*(To be filled in after design review)*

---

## Appendix: Example Conversation Flow

### Scenario: Multi-Turn Lead Creation

**CRM Schema:**
```json
{
  "entities": [
    {
      "name": "lead",
      "label": "Lead",
      "fields": [
        {"name": "full_name", "label": "Full Name", "type": "text", "required": true},
        {"name": "email", "label": "Email", "type": "email", "required": true},
        {"name": "status", "label": "Status", "type": "select", "required": true, "options": ["New", "Qualified"]}
      ]
    }
  ],
  "pipeline_stages": ["New", "Qualified"]
}
```

**Turn 1: User Request**
```
User: "I want to add a lead named John"

Copilot (backend):
  1. Parse intent: create_record for entity "lead"
  2. Resolve entity using _resolve_entity("lead") → matches exactly
  3. Extract partial data: {full_name: "John"}
  4. Identify missing required fields: [email, status]
  5. Generate multi-turn context:
     {
       "pending_entity": "lead",
       "collected": {full_name: "John"},
       "missing": ["email", "status"]
     }
  6. Compose reply with prompt for missing fields

Copilot (reply):
  "I've started a new Lead record with name 'John'.
   
   To complete it, I need:
   - Email address (required)
   - Status (choose from: New, Qualified)
   
   What's the email?"
```

**Turn 2: User Provides Email**
```
User: "email: john@example.com"

Copilot (backend):
  1. Retrieve pending context from conversation history
  2. Extract new input: {email: "john@example.com"}
  3. Validate email format → valid
  4. Merge with collected: {full_name: "John", email: "john@example.com"}
  5. Still missing: [status]
  6. Ask for status

Copilot (reply):
  "Great! I have:
   - Full Name: John
   - Email: john@example.com
   
   Now, what status should this lead have? (New or Qualified)"
```

**Turn 3: User Provides Status**
```
User: "New"

Copilot (backend):
  1. Retrieve pending context
  2. Extract input: {status: "New"}
  3. Validate against enum: ["New", "Qualified"] → valid
  4. Merge: {full_name: "John", email: "john@example.com", status: "New"}
  5. All required fields present
  6. Generate TOOL_CALL

Copilot (reply):
  "Perfect! Creating your Lead record:
   - Full Name: John
   - Email: john@example.com
   - Status: New
   
   TOOL_CALL: {"name": "create_record", "arguments": {"entity_name": "lead", "data": {"full_name": "John", "email": "john@example.com", "status": "New"}}}
   
   [After frontend executes tool]
   ✓ Lead record created successfully. ID: abc-123-def. You can view it in the Records section."
```

---

**End of Design Document**
