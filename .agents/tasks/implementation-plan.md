# AURA CRM — Implementation Plan

**Date:** 2025-01-12  
**Status:** Implementation Ready  
**Source:** design.md (Approved Design)  
**Scope:** Three Critical Fixes (Copilot Tool Calling, Sidebar Cleanup, Dynamic Analytics)

---

## EXECUTIVE SUMMARY

This plan decomposes the approved design into five sequential phases, each producing a verifiable, working state of the codebase. Phases are ordered by dependency: backend tools must exist before frontend can dispatch them; sidebar cleanup is independent; analytics backend changes before frontend display logic.

**Key Decision:** Implement in sequence (backend → frontend for each fix) rather than per-fix because phases 1 and 3 have interdependencies (both modify copilot.py and workflows.py system prompt generation).

**Critical Paths:**
1. **Phase 1 & 2 (Copilot):** Backend tool schemas and dispatcher → Frontend tool parsing and execution
2. **Phase 3 (Sidebar):** Frontend only, no dependencies
3. **Phase 4 & 5 (Analytics):** Backend dynamic metrics → Frontend schema-driven display

---

## PHASE BREAKDOWN & IMPLEMENTATION SEQUENCE

### PHASE 1: Backend Tool Definitions and Dispatcher (copilot.py)

**Scope:**  
Define tool schemas in system prompt, add tool execution endpoint, implement missing record CRUD tool methods, create tool dispatcher map.

**Rationale:**  
Frontend tool calling is impossible without backend tools available and executable. This phase establishes the backend foundation.

**Files to Modify:**

1. **`backend/app/routers/copilot.py`** — Main copilot router
   - Add `TOOL_HANDLERS` map (module level, around line 40)
   - Add `_generate_tools_section()` function (tool schema generation)
   - Replace `_build_system_prompt()` (lines 72–100) to include tools section and action detection instructions
   - Add `ToolCallRequest` Pydantic model (around line 65)
   - Add `execute_tool_call()` endpoint (POST /copilot/tool-call, after chat endpoint)
   - Update `/copilot/chat` response parsing to extract and return tool_calls in response

2. **`backend/app/services/ai_tools.py`** — AI tool implementations
   - Add `create_record()` method to CRMSchemaTools class
   - Add `update_record()` method to CRMSchemaTools class
   - Add `delete_record()` method to CRMSchemaTools class
   - (Note: Field/stage tools already exist: add_crm_field, update_crm_field, delete_crm_field, add_crm_stage, delete_crm_stage)

3. **`backend/app/routers/responses.py`** — Response helpers (if not present)
   - Verify `success_response()` and `error_response()` helper functions exist or add them

**Implementation Details:**

#### 1.1 Add Tool Execution Endpoint

Insert this after the `/copilot/chat` endpoint in copilot.py:

```python
@router.post("/tool-call")
async def execute_tool_call(
    body: ToolCallRequest,
    user_id: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
):
    """
    Execute a copilot tool call with ownership validation.
    
    Validates CRM ownership server-side before any tool execution.
    Tool handlers receive validated crm_id and owner_id, not user input.
    """
    # STEP 1: Validate CRM ownership
    repo = CRMRepository()
    crm = repo.get_crm(body.crm_id, user_id)
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found or access denied")
    
    # STEP 2: Validate tool name is whitelisted
    if body.tool_name not in TOOL_HANDLERS:
        return error_response(400, "INVALID_TOOL", f"Unknown tool: {body.tool_name}")
    
    # STEP 3: Get tool handler
    handler = TOOL_HANDLERS[body.tool_name]
    
    # STEP 4: Log tool call
    logger.info(
        f"Executing tool: {body.tool_name}",
        extra={
            "user_id": str(user_id),
            "crm_id": str(body.crm_id),
            "tool_name": body.tool_name,
        }
    )
    
    # STEP 5: Execute tool with validated parameters
    try:
        result = await handler(
            crm_id=body.crm_id,
            owner_id=user_id,
            **body.arguments
        )
        
        # STEP 6: Ensure standard response schema
        if "success" not in result:
            result["success"] = True
        
        return success_response(result)
    
    except Exception as e:
        logger.error(
            f"Tool execution failed: {body.tool_name}",
            extra={
                "user_id": str(user_id),
                "crm_id": str(body.crm_id),
                "error": str(e),
            }
        )
        return error_response(500, "EXECUTION_ERROR", "Tool execution failed")
```

#### 1.2 Add Tool Dispatcher Map

Add near the top of copilot.py (after AURA_ROUTES):

```python
# ── Tool execution dispatcher ──────────────────────────────────────

TOOL_HANDLERS = {
    # Information tools
    "get_active_crm": _get_active_crm,
    "get_crm_schema": _get_crm_schema,
    "list_records": _list_records,
    # Record actions
    "create_record": CRMSchemaTools.create_record,
    "update_record": CRMSchemaTools.update_record,
    "delete_record": CRMSchemaTools.delete_record,
    # Field actions
    "add_field": CRMSchemaTools.add_crm_field,
    "modify_field": CRMSchemaTools.update_crm_field,
    "remove_field": CRMSchemaTools.delete_crm_field,
    # Stage actions
    "add_stage": CRMSchemaTools.add_crm_stage,
    "modify_stage": CRMSchemaTools.update_crm_stage,
    "remove_stage": CRMSchemaTools.delete_crm_stage,
}
```

#### 1.3 Update System Prompt Builder

Replace the entire `_build_system_prompt()` function (lines 72–100) with the version from design.md section 1.3 that includes:
- Tool calling format instructions (TOOL_CALL: {...} format)
- Action vs. informational request detection
- Tool schema definitions
- When to use each tool

**Key changes:**
- Add explicit section "# DISTINGUISHING ACTION vs. INFORMATIONAL REQUESTS"
- Add "# TOOL CALLING FORMAT" with examples
- Add "# AVAILABLE TOOLS" listing all 13 tools with brief descriptions
- Add "# When to use each tool" decision tree

#### 1.4 Add Missing Record CRUD Tools to ai_tools.py

Add these methods to the CRMSchemaTools class:

```python
@staticmethod
async def create_record(
    crm_id: UUID,
    owner_id: UUID,
    entity_name: str,
    data: dict[str, Any],
    source: str | None = None,
) -> dict[str, Any]:
    """Create a new record in the CRM."""
    repo = CRMRepository()
    crm = repo.get_crm(crm_id, owner_id)
    if not crm:
        return {"success": False, "error_code": "NOT_FOUND", "error_message": "CRM not found"}
    
    # Validate entity exists
    config = crm.get("configuration", {})
    entities = config.get("entities", [])
    entity = next((e for e in entities if e["name"] == entity_name), None)
    
    if not entity:
        return {"success": False, "error_code": "INVALID_ENTITY", 
                "error_message": f"Entity '{entity_name}' not found"}
    
    # Validate required fields
    for field in entity.get("fields", []):
        if field.get("required") and field["name"] not in data:
            return {"success": False, "error_code": "MISSING_REQUIRED_FIELD",
                    "error_message": f"Required field '{field['name']}' is missing"}
    
    try:
        result = repo.create_record(crm_id, entity_name, data)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Failed to create record: {e}")
        return {"success": False, "error_code": "INTERNAL_ERROR", "error_message": str(e)}

@staticmethod
async def update_record(
    crm_id: UUID,
    owner_id: UUID,
    entity_name: str,
    record_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Update an existing record."""
    repo = CRMRepository()
    crm = repo.get_crm(crm_id, owner_id)
    if not crm:
        return {"success": False, "error_code": "NOT_FOUND", "error_message": "CRM not found"}
    
    try:
        result = repo.update_record(crm_id, entity_name, record_id, data)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Failed to update record: {e}")
        return {"success": False, "error_code": "INTERNAL_ERROR", "error_message": str(e)}

@staticmethod
async def delete_record(
    crm_id: UUID,
    owner_id: UUID,
    entity_name: str,
    record_id: str,
) -> dict[str, Any]:
    """Soft delete a record."""
    repo = CRMRepository()
    crm = repo.get_crm(crm_id, owner_id)
    if not crm:
        return {"success": False, "error_code": "NOT_FOUND", "error_message": "CRM not found"}
    
    try:
        repo.soft_delete_record(crm_id, entity_name, record_id)
        return {"success": True, "data": {"deleted": True}}
    except Exception as e:
        logger.error(f"Failed to delete record: {e}")
        return {"success": False, "error_code": "INTERNAL_ERROR", "error_message": str(e)}
```

#### 1.5 Update Chat Endpoint Response

Modify the `/copilot/chat` endpoint to parse tool calls and include them in response:

```python
# Inside the @router.post("/chat") handler, after calling Ollama:

if raw_reply:
    # Parse navigation hint
    clean_reply, nav_route, nav_label = _parse_nav(raw_reply)
    
    # Parse tool calls
    tool_calls = _parse_tool_calls(clean_reply)
    
    # Remove TOOL_CALL markers from display text
    for _ in tool_calls:
        clean_reply = re.sub(
            r'TOOL_CALL:\s*\{[^}]*\}',
            '',
            clean_reply
        ).strip()
    
    return success_response({
        "reply": clean_reply,
        "nav_route": nav_route,
        "nav_label": nav_label,
        "tool_calls": tool_calls if tool_calls else None,
        "fallback": False,
    })
```

#### 1.6 Add Tool Call Parser Function

Add this helper function to copilot.py:

```python
def _parse_tool_calls(reply: str) -> list[dict[str, Any]]:
    """
    Extract TOOL_CALL: {...} JSON objects from LLM reply.
    Returns list of {name, arguments} dicts.
    """
    import json
    
    tool_calls = []
    # Match TOOL_CALL: {...} pattern (regex handles nested JSON up to 2 levels)
    pattern = r'TOOL_CALL:\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})'
    
    for match in re.finditer(pattern, reply):
        try:
            call_json = match.group(1)
            call_obj = json.loads(call_json)
            if 'name' in call_obj and 'arguments' in call_obj:
                tool_calls.append(call_obj)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse tool call: {match.group(1)}")
    
    return tool_calls
```

#### 1.7 Add Tool Schema Generation Function

Add this function to copilot.py:

```python
def _generate_tools_section() -> str:
    """Generate tool definitions for system prompt."""
    return """# AVAILABLE TOOLS

## Information Tools (read-only, no backend call)
- get_active_crm: Returns active CRM ID, name, entities, stages
- get_crm_schema: Returns detailed schema (entities, fields, types)
- list_records: Lists records from an entity (paginated, limit: 100)

## Record Actions
- create_record(entity_name, data, source?): Create a new record
- update_record(entity_name, record_id, data): Update existing record
- delete_record(entity_name, record_id): Delete a record (soft delete)

## Field Actions
- add_field(field_name, label, field_type, required?, options?): Add field to entity
- modify_field(field_name, label?, field_type?, required?, options?): Update field
- remove_field(field_name, confirm?): Delete field

## Stage Actions
- add_stage(stage_name, position?): Add pipeline stage
- modify_stage(stage_name, new_name): Rename stage
- remove_stage(stage_name, confirm?): Delete stage (soft delete)

## When to use each tool

CREATE_RECORD: User says "Add a [entity_type]", "Create a [entity_type]", "I want to record..."
UPDATE_RECORD: User says "Change [field] for [record]", "Update [record]'s status"
DELETE_RECORD: User says "Delete [record]", "Remove [record]"
ADD_FIELD: User says "Add [field_name] field", "New column for..."
MODIFY_FIELD: User says "Change [field_name] type to...", "Make [field_name] required"
REMOVE_FIELD: User says "Delete [field_name]", "Remove [field_name] column"
ADD_STAGE: User says "Add [stage_name] stage", "New status called [stage_name]"
MODIFY_STAGE: User says "Rename [old] to [new]"
REMOVE_STAGE: User says "Delete [stage_name] stage", "Remove [stage_name] status"
"""
```

**How to Verify Phase 1:**

```bash
cd backend

# Type check
mypy app/routers/copilot.py --ignore-missing-imports

# Unit test: Tool execution endpoint
pytest tests/test_copilot.py::test_execute_tool_call_create_record -v

# Unit test: Ownership validation
pytest tests/test_copilot.py::test_execute_tool_call_wrong_crm_owner -v

# Unit test: Tool schema parsing
pytest tests/test_copilot.py::test_parse_tool_calls -v

# Integration test: System prompt includes tools
pytest tests/test_copilot.py::test_system_prompt_includes_tool_schemas -v
```

**Expected Outcome:**
- `/copilot/tool-call` endpoint exists and is callable
- Tool schemas appear in system prompt sent to LLM
- Tool call parser correctly extracts TOOL_CALL: {...} JSON from text
- Tool dispatcher map routes all tool names to correct handlers
- Ownership validation prevents tools from executing on other users' CRMs

---

### PHASE 2: Frontend Tool Calling Flow (AIAssistantDrawer.tsx)

**Scope:**  
Implement tool call parsing, execution, confirmation dialogs, and data refresh in the frontend AI assistant drawer.

**Rationale:**  
Now that backend tools exist, frontend must be able to parse LLM responses for tool calls, execute them, and refresh data.

**Files to Modify:**

1. **`frontend/src/features/ai-assistant/AIAssistantDrawer.tsx`** — Main AI drawer component
   - Add `parseToolCalls()` function
   - Add `executeToolCall()` function
   - Add `showToolConfirmationDialog()` function (callback-based)
   - Add `refreshDataAfterToolExecution()` function
   - Update `handleSend()` to detect and execute tool calls
   - Add confirmation modal state and render logic
   - Update Message interface to optionally include tool execution status

2. **`frontend/src/services/api.ts`** — API client
   - Add `executeToolCall()` method to api object
   - Signature: `executeToolCall(crm_id, {tool_name, arguments})` → returns result

3. **`frontend/src/components/ui/ConfirmationModal.tsx`** (new component)
   - Create reusable confirmation modal for dangerous operations
   - Props: title, message, onConfirm, onCancel
   - Styling: match AURA design system

**Implementation Details:**

#### 2.1 Update API Client (api.ts)

Add this method to the api object:

```typescript
export async function executeToolCall(
  crm_id: string,
  request: {
    tool_name: string;
    arguments: Record<string, any>;
  }
): Promise<any> {
  const response = await fetch(`${BASE_URL}/copilot/tool-call`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      tool_name: request.tool_name,
      crm_id: crm_id,
      arguments: request.arguments,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error_message || 'Tool execution failed');
  }

  return response.json();
}
```

#### 2.2 Add Tool Call Parser to AIAssistantDrawer.tsx

```typescript
function parseToolCalls(text: string): Array<{name: string; arguments: Record<string, any>}> {
  const toolCalls: Array<{name: string; arguments: Record<string, any>}> = [];
  
  // Match TOOL_CALL: {...} pattern (regex handles nested JSON)
  const regex = /TOOL_CALL:\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})/g;
  let match;
  
  while ((match = regex.exec(text)) !== null) {
    try {
      const parsed = JSON.parse(match[1]);
      if (parsed.name && parsed.arguments) {
        toolCalls.push(parsed);
      }
    } catch (e) {
      console.warn('Failed to parse tool call:', match[1], e);
    }
  }
  
  return toolCalls;
}
```

#### 2.3 Add Tool Execution Function

```typescript
async function executeToolCall(
  toolCall: { name: string; arguments: Record<string, any> },
): Promise<{success: boolean; result?: any; error?: string}> {
  if (!crmId) {
    return { success: false, error: 'No active CRM' };
  }

  try {
    const response = await api.executeToolCall(crmId, {
      tool_name: toolCall.name,
      arguments: toolCall.arguments,
    });

    // Show success message in chat
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const successMsg: Message = {
      sender: 'ai',
      text: `✓ Tool '${toolCall.name}' executed successfully.`,
      time: now,
    };
    setMessages((prev) => [...prev, successMsg]);

    return { success: true, result: response };

  } catch (err: unknown) {
    const errorText = err instanceof Error ? err.message : 'Tool execution failed';
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const errorMsg: Message = {
      sender: 'ai',
      text: `✗ Tool failed: ${errorText}`,
      time: now,
    };
    setMessages((prev) => [...prev, errorMsg]);

    return { success: false, error: errorText };
  }
}
```

#### 2.4 Add Confirmation Dialog Handler

```typescript
interface ConfirmationState {
  visible: boolean;
  title: string;
  message: string;
  onConfirm?: () => void;
  onCancel?: () => void;
}

const [showConfirmation, setShowConfirmation] = useState<ConfirmationState>({
  visible: false,
  title: '',
  message: '',
});

async function showToolConfirmationDialog(
  toolCall: { name: string; arguments: Record<string, any> },
): Promise<void> {
  return new Promise((resolve) => {
    const handleConfirm = async () => {
      setShowConfirmation({ visible: false, title: '', message: '' });
      await executeToolCall(toolCall);
      resolve();
    };

    const handleCancel = () => {
      setShowConfirmation({ visible: false, title: '', message: '' });
      const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      setMessages((prev) => [
        ...prev,
        {
          sender: 'ai',
          text: `⚠ Operation cancelled. No changes made.`,
          time: now,
        },
      ]);
      resolve();
    };

    // Set state with callbacks
    setShowConfirmation({
      visible: true,
      title: `Confirm ${toolCall.name}`,
      message: `This action cannot be undone. Are you sure?`,
      onConfirm: handleConfirm,
      onCancel: handleCancel,
    });
  });
}
```

#### 2.5 Update handleSend Function

Modify the handleSend function to detect and execute tool calls:

```typescript
const handleSend = async (textToSend?: string) => {
  const query = (textToSend || input).trim();
  if (!query || isThinking) return;

  const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const userMsg: Message = { sender: 'user', text: query, time: now };

  const updatedMessages = [...messages, userMsg];
  setMessages(updatedMessages);
  if (!textToSend) setInput('');
  setIsThinking(true);

  try {
    // Build payload: only send role/content pairs
    const payload = updatedMessages.map((m) => ({
      role: m.sender === 'ai' ? 'assistant' : 'user',
      content: m.text,
    })) as { role: 'user' | 'assistant'; content: string }[];

    const res = await api.copilotChat(payload, crmId);

    // Parse tool calls from the reply
    const toolCalls = parseToolCalls(res.reply);
    
    // Remove tool call markers from display text
    let displayText = res.reply;
    for (const _ of toolCalls) {
      displayText = displayText.replace(/TOOL_CALL:\s*\{[^}]+(?:\{[^}]*\}[^}]*)*\}/g, '').trim();
    }

    const replyTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    // If there are tool calls, execute them
    if (toolCalls.length > 0) {
      for (const toolCall of toolCalls) {
        // Check if tool requires confirmation
        const dangerousTools = ['delete_record', 'remove_field', 'remove_stage'];
        if (dangerousTools.includes(toolCall.name)) {
          // Show confirmation UI
          await showToolConfirmationDialog(toolCall);
        } else {
          // Execute immediately
          await executeToolCall(toolCall);
        }
      }
    }

    // Add AI response to chat
    const aiMsg: Message = {
      sender: 'ai',
      text: displayText,
      time: replyTime,
      action:
        res.nav_route && res.nav_label
          ? { label: res.nav_label, route: res.nav_route }
          : undefined,
    };
    setMessages((prev) => [...prev, aiMsg]);

    // Refresh relevant data after tool execution
    if (toolCalls.length > 0) {
      await refreshDataAfterToolExecution(toolCalls);
    }

  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Something went wrong.';
    const errTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    setMessages((prev) => [
      ...prev,
      {
        sender: 'ai',
        text: `I ran into an issue: ${msg}. Please try again.`,
        time: errTime,
      },
    ]);
  } finally {
    setIsThinking(false);
  }
};
```

#### 2.6 Add Data Refresh Function

```typescript
async function refreshDataAfterToolExecution(
  toolCalls: Array<{ name: string; arguments: Record<string, any> }>,
): Promise<void> {
  // Determine what data needs to be refreshed
  const needsRecordsRefresh = toolCalls.some(
    (t) => ['create_record', 'update_record', 'delete_record'].includes(t.name)
  );
  
  const needsConfigRefresh = toolCalls.some(
    (t) => ['add_field', 'modify_field', 'remove_field', 'add_stage', 'modify_stage', 'remove_stage'].includes(t.name)
  );

  // Dispatch custom events to trigger data refresh in other components
  if (needsRecordsRefresh) {
    window.dispatchEvent(new CustomEvent('records-changed'));
  }

  if (needsConfigRefresh) {
    window.dispatchEvent(new CustomEvent('crm-config-changed'));
  }
}
```

#### 2.7 Add Confirmation Modal Render

Add this to the JSX render (inside the slide-over panel, before or after the chat messages):

```typescript
{showConfirmation.visible && (
  <ConfirmationModal
    title={showConfirmation.title}
    message={showConfirmation.message}
    onConfirm={showConfirmation.onConfirm || (() => {})}
    onCancel={showConfirmation.onCancel || (() => {})}
  />
)}
```

#### 2.8 Create ConfirmationModal Component

Create new file `frontend/src/components/ui/ConfirmationModal.tsx`:

```typescript
import React from 'react';
import { AlertCircle, Check, X } from 'lucide-react';

interface ConfirmationModalProps {
  title: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  confirmText?: string;
  cancelText?: string;
}

export const ConfirmationModal: React.FC<ConfirmationModalProps> = ({
  title,
  message,
  onConfirm,
  onCancel,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
}) => {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm pointer-events-auto">
      <div className="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4 p-6 border border-slate-200 animate-fade-in">
        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
            <AlertCircle className="w-6 h-6 text-amber-600" />
          </div>
          <h2 className="text-lg font-bold text-aura-navy">{title}</h2>
        </div>

        {/* Message */}
        <p className="text-sm text-slate-600 mb-6">{message}</p>

        {/* Buttons */}
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-lg bg-slate-100 text-slate-700 font-medium text-sm hover:bg-slate-200 transition-colors flex items-center gap-2"
          >
            <X className="w-4 h-4" />
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 rounded-lg bg-aura-cyan text-aura-navy font-bold text-sm hover:bg-cyan-400 transition-colors flex items-center gap-2"
          >
            <Check className="w-4 h-4" />
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
};
```

**How to Verify Phase 2:**

```bash
cd frontend

# Type check
npx tsc --noEmit

# (If test framework exists)
npm test -- AIAssistantDrawer.test.tsx

# Manual test (run dev server):
# 1. User says "Add a lead"
# 2. Copilot generates tool call
# 3. Tool call parsed correctly (inspect Network tab in DevTools)
# 4. Tool executes, result appears in chat
# 5. For delete_record, confirmation modal appears
```

**Expected Outcome:**
- Tool calls parsed from LLM response and removed from display text
- `/copilot/tool-call` endpoint called with correct parameters
- Tool execution results displayed in chat
- Dangerous tools (delete_record, remove_field, remove_stage) require confirmation
- Data refresh events dispatched after tool execution

---

### PHASE 3: Sidebar Cleanup (Sidebar.tsx)

**Scope:**  
Remove Settings, Workflows, and Evolution Center from navigation menu. Clean up unused icon imports.

**Rationale:**  
Simple frontend-only change that has zero backend impact. Can be done independently.

**Files to Modify:**

1. **`frontend/src/components/layout/Sidebar.tsx`** — Navigation sidebar
   - Remove 3 nav items from `navItems` array (lines 26–42)
   - Remove 3 unused icon imports

**Implementation Details:**

#### 3.1 Update navItems Array

Find the `navItems` constant (around line 26) and replace with:

```typescript
const navItems = [
  { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
  { name: 'My CRMs', path: '/crms', icon: FolderKanban },
  { name: 'Build a CRM', path: '/chat-crm', icon: MessageCircle, highlight: true },
  { name: 'Records', path: '/records', icon: Database },
  { name: 'Analytics', path: '/analytics', icon: BarChart3 },
];
```

#### 3.2 Remove Unused Icon Imports

In the lucide-react import statement at the top (lines 4–17), remove these three:
- `GitBranch` (was used for Workflows)
- `Dna` (was used for Evolution Center)
- `Settings` (was used for Settings)

Updated import:

```typescript
import {
  LayoutDashboard,
  FolderKanban,
  Database,
  BarChart3,
  ChevronLeft,
  ChevronRight,
  Bot,
  Layers,
  MessageCircle,
  Sparkles,
} from 'lucide-react';
```

**How to Verify Phase 3:**

```bash
cd frontend

# Type check
npx tsc --noEmit

# Build check
npm run build

# Manual test:
# 1. Run dev server
# 2. Sidebar should show exactly 5 items
# 3. No console warnings about missing icons or dead routes
# 4. Click each remaining item to verify navigation works
```

**Expected Outcome:**
- Sidebar displays exactly 5 navigation items
- Settings, Workflows, Evolution Center removed
- No console errors or warnings
- Build succeeds with no errors
- All remaining nav items clickable and functional

---

### PHASE 4: Backend Analytics Endpoint (workflows.py)

**Scope:**  
Replace hard-coded analytics logic with fully dynamic, schema-driven analytics that derives metrics from the active CRM's configuration.

**Rationale:**  
Must be completed before frontend analytics changes so frontend has correct data to display.

**Files to Modify:**

1. **`backend/app/routers/workflows.py`** — Analytics endpoint
   - Replace the entire `get_analytics()` function (lines 100–167 approx.)
   - Add edge case handling for empty pipelines, missing stage field, orphaned stage values
   - Return schema_info for frontend to use

**Implementation Details:**

#### 4.1 Replace get_analytics() Function

Replace the existing `get_analytics()` function with:

```python
@router.get("/analytics")
async def get_analytics(crm_id: UUID, user_id: CurrentUser):
    """
    Get CRM analytics dynamically derived from the active CRM's schema.
    
    Handles edge cases:
    - Empty pipeline_stages: return empty by_stage array
    - No stage field: return empty by_stage array
    - Orphaned stage values (records with stage not in pipeline): include in "Other" bucket
    - No source field: return empty by_source array
    - Zero records: return 0 counts with 0% percentages
    
    Returns:
    {
        "total_records": int,
        "by_stage": [{"stage_name": str, "count": int, "percentage": float}, ...],
        "by_source": [{"source": str, "count": int, "percentage": float}, ...],
        "schema_info": {
            "primary_entity_name": str,
            "pipeline_stages": [str, ...],
            "stage_field_name": str | None,
            "source_field_name": str | None
        }
    }
    """
    repo = _get_repo()
    crm = repo.get_crm(crm_id, user_id)
    
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found or access denied")
    
    config = crm.get("configuration", {})
    
    # Determine primary entity (first entity in configuration)
    entities = config.get("entities", [])
    if not entities:
        return error_response(400, "INVALID_CRM", "CRM has no entities defined")
    
    primary_entity = entities[0]
    entity_name = primary_entity["name"]
    
    # Get pipeline stages from configuration (user-defined)
    pipeline_stages = config.get("pipeline_stages", [])
    
    # Find stage field (typically "status" or "stage" with type "select")
    stage_field_name = None
    for field in primary_entity.get("fields", []):
        if field.get("type") == "select" and field["name"] in ("status", "stage"):
            stage_field_name = field["name"]
            break
    
    # Find source field (typically "source" with type "select")
    source_field_name = None
    for field in primary_entity.get("fields", []):
        if field["name"] == "source":
            source_field_name = field["name"]
            break
    
    # Query: Total records
    total_records = repo.count_records(crm_id)
    
    # Query: Records by stage
    by_stage = []
    if pipeline_stages and stage_field_name:
        stage_counts = repo.count_records_by_field(crm_id, entity_name, stage_field_name)
        
        # stage_counts is [{"value": "stage_name", "count": 5}, ...]
        stage_map = {s["value"]: s["count"] for s in stage_counts if s.get("value")}
        
        # Add counts for each pipeline stage (in order)
        for stage_name in pipeline_stages:
            count = stage_map.pop(stage_name, 0)
            percentage = (count / total_records * 100) if total_records > 0 else 0.0
            by_stage.append({
                "stage_name": stage_name,
                "count": count,
                "percentage": round(percentage, 1),
            })
        
        # EDGE CASE: Orphaned stage values (records with stage not in pipeline_stages)
        if stage_map:  # Remaining items are orphaned
            orphaned_count = sum(stage_map.values())
            orphaned_percentage = (orphaned_count / total_records * 100) if total_records > 0 else 0.0
            by_stage.append({
                "stage_name": "Other",
                "count": orphaned_count,
                "percentage": round(orphaned_percentage, 1),
            })
    
    # Query: Records by source
    by_source = []
    if source_field_name:
        source_counts = repo.count_records_by_field(crm_id, entity_name, source_field_name)
        
        # source_counts is [{"value": "source_name", "count": 5}, ...]
        for s in source_counts:
            if s.get("value"):
                count = s["count"]
                percentage = (count / total_records * 100) if total_records > 0 else 0.0
                by_source.append({
                    "source": s["value"],
                    "count": count,
                    "percentage": round(percentage, 1),
                })
    
    return success_response({
        "total_records": total_records,
        "by_stage": by_stage,
        "by_source": by_source,
        "schema_info": {
            "primary_entity_name": entity_name,
            "pipeline_stages": pipeline_stages,
            "stage_field_name": stage_field_name,
            "source_field_name": source_field_name,
        }
    })
```

**Key Changes:**
1. Removed hard-coded `{"Qualified", "qualified"}` stage search
2. Removed hard-coded "source" field assumption (now dynamic)
3. Returns `by_stage` derived from user-defined pipeline_stages
4. Handles empty pipeline_stages (returns empty array)
5. Handles orphaned stage values (records with invalid stage values)
6. Calculates percentages dynamically for all stages
7. Returns schema_info for frontend to use in UI rendering

**How to Verify Phase 4:**

```bash
cd backend

# Type check
mypy app/routers/workflows.py --ignore-missing-imports

# Unit test: Empty pipeline_stages
pytest tests/test_analytics.py::test_get_analytics_empty_pipeline_stages -v

# Unit test: Missing stage field
pytest tests/test_analytics.py::test_get_analytics_missing_stage_field -v

# Unit test: Orphaned stage values
pytest tests/test_analytics.py::test_get_analytics_orphaned_stages -v

# Integration test: Actual CRM with records
pytest tests/test_analytics.py::test_get_analytics_e_commerce_crm -v

# Integration test: Multi-entity CRM (only first entity used)
pytest tests/test_analytics.py::test_get_analytics_multi_entity -v
```

**Expected Outcome:**
- GET /analytics returns dynamic metrics based on CRM configuration
- Stages come from pipeline_stages (not hard-coded)
- Percentages sum to 100% (or 0% if no records)
- Edge cases handled: empty pipelines, missing fields, orphaned values
- schema_info included so frontend can render dynamic titles

---

### PHASE 5: Frontend Analytics UI (AnalyticsPage.tsx)

**Scope:**  
Replace hard-coded KPI cards and chart titles with dynamic, schema-driven display logic.

**Rationale:**  
Now that backend returns dynamic metrics and schema_info, frontend can render UI that adapts to any CRM.

**Files to Modify:**

1. **`frontend/src/features/analytics/AnalyticsPage.tsx`** — Analytics page
   - Remove hard-coded card names ("Total Leads/Records", "Qualified", "Won Deals", "Conversion Rate")
   - Remove hard-coded chart titles ("Records by Pipeline Stage", "Lead Volume by Acquisition Source")
   - Add dynamic KPI card generation based on by_stage and total_records
   - Add dynamic chart title generation using schema_info
   - Preserve chart rendering logic (it's already generic)

**Implementation Details:**

#### 5.1 Replace Hard-Coded KPI Cards

Find the KPI Cards section (around line 82–115) and replace with:

```typescript
{/* Key Metric KPI Cards — Dynamically Generated */}
<div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
  {/* Card 1: Total Records */}
  <Card className="p-5">
    <div className="flex items-center justify-between text-slate-400 mb-2">
      <span className="text-[10px] font-bold uppercase tracking-wider">
        Total Records
      </span>
      <Users className="w-4 h-4 text-aura-deep" />
    </div>
    <p className="text-2xl font-extrabold text-aura-navy">
      {analytics?.total_records ?? 0}
    </p>
    <p className="text-[11px] text-slate-400 mt-1">
      Total {analytics?.schema_info?.primary_entity_name || 'records'}
    </p>
  </Card>

  {/* Cards 2+: Top 3 Stages (if available) */}
  {(analytics?.by_stage || []).slice(0, 3).map((stage, idx) => (
    <Card key={stage.stage_name} className="p-5">
      <div className="flex items-center justify-between text-slate-400 mb-2">
        <span className="text-[10px] font-bold uppercase tracking-wider">
          {stage.stage_name}
        </span>
        <TrendingUp className="w-4 h-4 text-blue-500" />
      </div>
      <p className="text-2xl font-extrabold text-aura-navy">
        {stage.count}
      </p>
      <p className="text-[11px] text-slate-400 mt-1">
        {stage.percentage}% of total
      </p>
    </Card>
  ))}
</div>
```

**Rationale:**
- Card 1 always shows total records (applies to all CRMs)
- Cards 2–4 show first 3 pipeline stages with their counts and percentages
- If CRM has fewer than 3 stages, shows fewer cards (responsive)
- Stage names come from by_stage array (user-defined)

#### 5.2 Update Chart Titles with schema_info

Find the chart header sections and update:

**Stage Distribution Chart (around line 127):**

```typescript
<div className="flex items-center justify-between">
  <h3 className="text-sm font-bold text-aura-navy flex items-center gap-2">
    <BarChart3 className="w-4 h-4 text-aura-cyan" />
    {analytics?.schema_info?.stage_field_name 
      ? `Records by ${analytics.schema_info.stage_field_name}` 
      : 'Records by Stage'}
  </h3>
  <span className="text-xs text-slate-400 font-mono">by_stage</span>
</div>
```

**Source Distribution Chart (around line 164):**

```typescript
<div className="flex items-center justify-between">
  <h3 className="text-sm font-bold text-aura-navy flex items-center gap-2">
    <PieIcon className="w-4 h-4 text-aura-deep" />
    {analytics?.schema_info?.source_field_name 
      ? `Records by ${analytics.schema_info.source_field_name}` 
      : 'Records by Source'}
  </h3>
  <span className="text-xs text-slate-400 font-mono">by_source</span>
</div>
```

#### 5.3 Update Chart Data Mapping

The chart data is already generic (maps to stage_name/count), no changes needed. Verify stageData and sourceData mapping:

```typescript
// These mappings already work for any CRM:
const stageData = (analytics?.by_stage || []).map((s) => ({
  name: s.stage_name || 'Unassigned',
  count: s.count,
}));

const sourceData = (analytics?.by_source || []).map((s) => ({
  name: s.source || 'Direct',
  count: s.count,
}));
```

#### 5.4 Add Empty State Handling

Update the empty state checks to be more informative:

```typescript
{stageData.length === 0 ? (
  <div className="h-64 flex items-center justify-center text-xs text-slate-400">
    <p>
      {analytics?.schema_info?.stage_field_name 
        ? `No records with ${analytics.schema_info.stage_field_name} assigned yet.`
        : 'No stage field configured in this CRM.'}
    </p>
  </div>
) : (
  // ... chart rendering
)}
```

**How to Verify Phase 5:**

```bash
cd frontend

# Type check
npx tsc --noEmit

# Build
npm run build

# Manual test with different CRMs:
# 1. Create Sales CRM (stages: New, Contacted, Qualified, Negotiation, Won, Lost)
#    → Analytics should show 6 stage cards + 1 total card
#    → Chart title: "Records by status"
#    → Each stage shows count and percentage

# 2. Create Healthcare CRM (stages: Registered, Triage, In-Consultation, Admitted, Discharged)
#    → Analytics should show 5 stage cards + 1 total card
#    → Chart title: "Records by status"
#    → Stage names match user configuration

# 3. Add records to different stages
#    → KPI cards update with correct counts and percentages
#    → Percentages sum to 100%
#    → Chart renders correctly

# 4. Create CRM with no stages
#    → Analytics page shows empty state gracefully
#    → No console errors
```

**Expected Outcome:**
- Analytics page displays dynamic KPI cards based on pipeline_stages
- Chart titles use actual field names from schema_info
- Card labels use user-defined stage names (not hard-coded "Qualified", "Won")
- Percentages calculated correctly for all CRM types
- Works for any CRM regardless of industry or stage configuration
- Empty states handled gracefully

---

## IMPLEMENTATION SEQUENCE & DEPENDENCIES

**Order:** Phases 1–5 sequential (each depends on previous output)

```
Phase 1 (Backend Tools)
    ↓ (enables tool calling)
Phase 2 (Frontend Tool Execution)
    ↓ (independent from 3, but 3 should run during 2)
Phase 3 (Sidebar Cleanup) — can run in parallel with 2
    ↓ (independent, no blockers)
Phase 4 (Backend Analytics)
    ↓ (enables dynamic frontend analytics)
Phase 5 (Frontend Analytics UI)
```

**Critical Path:**
1. Phase 1 must complete before Phase 2 (no tools to execute without backend)
2. Phase 4 must complete before Phase 5 (no dynamic data without backend)
3. Phase 3 is fully independent; can be done anytime

**Suggested Execution:**
- Day 1: Phase 1 + 3 (backend tools, sidebar cleanup)
- Day 2: Phase 2 (frontend tool calling)
- Day 3: Phase 4 + 5 (analytics backend, then frontend)

---

## VERIFICATION CHECKPOINTS

### Checkpoint 1: After Phase 1
```bash
# Backend tools exist and are callable
curl -X POST http://localhost:8000/api/v1/copilot/tool-call \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "crm_id": "...",
    "tool_name": "list_records",
    "arguments": {"entity_name": "lead"}
  }'

# Expected: 200 OK with records list

# System prompt includes tools
grep -i "TOOL_CALL" $(find backend/app/routers -name "copilot.py")

# Expected: TOOL_CALL format instructions present
```

### Checkpoint 2: After Phase 2
```
# In browser DevTools:
# 1. Send message: "Add a lead"
# 2. Check Network tab for POST to /copilot/tool-call
# 3. Verify tool call executed
# 4. Check chat displays success/error message
# 5. Verify records page refreshed (if create_record)
```

### Checkpoint 3: After Phase 3
```
# Sidebar rendered without errors
# Exactly 5 items visible: Dashboard, My CRMs, Build a CRM, Records, Analytics
# No console errors
npm run build succeeds
```

### Checkpoint 4: After Phase 4
```bash
# Analytics endpoint returns dynamic data
curl http://localhost:8000/api/v1/workflows/analytics?crm_id=<id>

# Expected response:
{
  "total_records": 120,
  "by_stage": [
    {"stage_name": "New", "count": 35, "percentage": 29.2},
    {"stage_name": "Contacted", "count": 28, "percentage": 23.3},
    ...
  ],
  "schema_info": {
    "primary_entity_name": "lead",
    "pipeline_stages": ["New", "Contacted", "Qualified", ...],
    "stage_field_name": "status",
    "source_field_name": "source"
  }
}
```

### Checkpoint 5: After Phase 5
```
# In browser:
# 1. Navigate to Analytics page
# 2. Verify KPI cards show dynamic stages (not "Qualified", "Won")
# 3. Verify chart title uses schema_info field names
# 4. Create different CRM type
# 5. Verify Analytics adapts to new CRM's stages
# 6. No console errors
```

---

## SUCCESS CRITERIA

After all phases complete:

- **Copilot Tool Calling:**
  - ✅ User says "Add a lead" → Copilot generates create_record tool call
  - ✅ Tool call executed on backend with proper ownership validation
  - ✅ Record appears in database and UI refreshes
  - ✅ Dangerous tools (delete) require explicit confirmation
  - ✅ Tool results displayed in chat

- **Sidebar Cleanup:**
  - ✅ Sidebar shows exactly 5 items: Dashboard, My CRMs, Build a CRM, Records, Analytics
  - ✅ Settings, Workflows, Evolution Center removed from UI
  - ✅ All remaining items clickable and functional
  - ✅ No console errors or warnings

- **Dynamic Analytics:**
  - ✅ Analytics page displays user-defined pipeline stages (not hard-coded)
  - ✅ Chart titles use actual CRM field names
  - ✅ KPI cards show stage-specific metrics with percentages
  - ✅ Works for any CRM type (Sales, Support, Recruitment, Custom)
  - ✅ Empty stages handled gracefully
  - ✅ Percentages sum to 100%

- **Technical:**
  - ✅ TypeScript compilation passes (`npx tsc --noEmit`)
  - ✅ Backend type checking passes (`mypy app/`)
  - ✅ Frontend build succeeds (`npm run build`)
  - ✅ No console errors in browser
  - ✅ All unit tests pass (if test suite present)
  - ✅ Integration tests verify end-to-end workflows

---

## EFFORT ESTIMATE

| Phase | Task | Estimated Hours | Cumulative |
|-------|------|-----------------|-----------|
| 1 | Backend tool definitions & dispatcher | 3–4 | 3–4 |
| 2 | Frontend tool calling & execution | 4–5 | 7–9 |
| 3 | Sidebar cleanup | 0.5–1 | 7.5–10 |
| 4 | Backend analytics | 2–3 | 9.5–13 |
| 5 | Frontend analytics UI | 2–3 | 11.5–16 |
| **Testing & Verification** | Unit + integration tests | 2–3 | 13.5–19 |
| **Total** | | | **13.5–19 hours** |

**Notes:**
- Time assumes developer familiar with FastAPI, React, TypeScript
- Unfamiliar with Supabase/database layer: +2–3 hours
- No existing test framework: +2–3 hours for setup
- Contingency for issues: +2–3 hours

---

## KNOWN RISKS & MITIGATIONS

| Risk | Impact | Mitigation |
|------|--------|-----------|
| LLM doesn't generate valid TOOL_CALL JSON | Phase 2 fails | Add robust error handling in parser; test with Ollama locally first |
| Tool handlers crash on edge cases | Phase 1 fails | Implement explicit null checks, validation, error logging |
| Confirmation modal race conditions | Phase 2 unpredictable | Use callback-based pattern (not promises + state) |
| Analytics endpoint times out on large record counts | Phase 4 fails | Add database indexes on (crm_id, status, source) before implementing |
| CRM with no stages breaks analytics | Phase 5 fails | Handle empty pipeline_stages in backend + frontend |
| Ownership validation not enforced | Security risk | Test cross-user CRM access; verify repo.get_crm() checks user_id |

---

## ROLLBACK POINTS

If a phase fails, rollback to the last successful state:

1. **Phase 1 fails:** Revert copilot.py and ai_tools.py to previous commit. Sidebar and analytics unaffected.
2. **Phase 2 fails:** Revert AIAssistantDrawer.tsx and api.ts. Users can still use copilot (without tool calling).
3. **Phase 3 fails:** Revert Sidebar.tsx. Cosmetic issue only; all features still work.
4. **Phase 4 fails:** Revert workflows.py get_analytics(). Analytics page shows error or mock data.
5. **Phase 5 fails:** Revert AnalyticsPage.tsx. Fall back to hard-coded cards (less flexible but stable).

---

## NEXT STEPS

1. **Code Review:** Have the approved design reviewed by the team before implementation.
2. **Test Setup:** Ensure backend test framework (pytest) and frontend test framework (vitest/jest) are configured.
3. **Database Readiness:** Verify CRMRepository methods exist: count_records(), count_records_by_field(), soft_delete_record().
4. **Environment:** Ensure Ollama (qwen3:4b) running on localhost:11434, or switch to mock provider for testing.
5. **Implementation:** Follow phases 1–5 in order; test at each checkpoint.

---

**Plan Complete**  
**Ready for Implementation Phase**
