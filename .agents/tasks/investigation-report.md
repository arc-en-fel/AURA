# AURA Application Architecture Investigation Report

**Date:** 2025-01-12  
**Scope:** Complete tool-calling pipeline, sidebar navigation, analytics implementation  
**Investigator:** Planning Agent

---

## EXECUTIVE SUMMARY

The AURA CRM application has **three critical areas that require fixes**:

1. **AI Copilot Tool Calling:** Currently **DISABLED** — the copilot has tools defined but does not call them. The LLM receives no tool schemas, making it impossible for the copilot to programmatically execute CRM actions.

2. **Sidebar Navigation:** Contains four items that must be removed (Settings, Workflows, Evolution Center). One item ("My CRMs" vs. "CRMs") needs review.

3. **Analytics Implementation:** Heavily **hard-coded** for a single CRM type with fixed concepts (Total Leads, Qualified, Won Deals, Conversion Rate, Acquisition Source). Must be fully dynamic based on actual CRM schema.

---

## PART 1 — COPILOT TOOL CALLING PIPELINE: COMPLETE TRACE

### 1.1 Current User-Facing Behavior

**User Request:**
```
"Add a lead to the CRM"
```

**Current Copilot Response (Wrong):**
```
"Records in Analytical_E_Commerce_CRM are stored dynamically... [Open Records button]"
```

**Expected Response (Correct):**
```
"Sure, I can add a lead to Analytical_E_Commerce_CRM. Please provide: Customer Name, Customer Segment, Total Revenue, Purchase Frequency, and Customer Value."
```

**Root Cause:** The copilot never initiates action flows. It only answers informational questions.

---

### 1.2 Complete Tool-Calling Pipeline — Component by Component

#### **A. Frontend Chat Input**
- **File:** `d:\AURA - Copy\frontend\src\features\ai-assistant\AIAssistantDrawer.tsx`
- **Lines:** 79-81 (handleSend function)
- **What happens:**
  1. User types a message in the input box
  2. `handleSend()` is called on Enter or Send button click
  3. Message is added to local state (`messages` array)
  4. Input is cleared
  5. `api.copilotChat(payload, crmId)` is called

**Code snippet:**
```typescript
const res = await api.copilotChat(payload, crmId);
```

**Finding:** The frontend successfully sends messages and receives a `reply` + optional `nav_route`. However, there is **NO TOOL EXECUTION IN THIS FLOW**. The chat is read-only informational.

---

#### **B. Frontend API Call**
- **File:** `d:\AURA - Copy\frontend\src\services\api.ts`
- **Lines:** 775-810 (copilotChat method)
- **What happens:**
  1. Frontend constructs a POST request to `/copilot/chat`
  2. Sends `messages` array (role/content pairs) and optional `crm_id`
  3. Receives response with `reply`, `nav_route`, `nav_label`, `fallback` flag

**Request payload:**
```json
{
  "messages": [
    {"role": "user", "content": "Add a lead"},
    {"role": "assistant", "content": "Sure..."},
    {"role": "user", "content": "John, Premium, 25000, 4, High"}
  ],
  "crm_id": "uuid-of-active-crm"
}
```

**Finding:** The API call does NOT include any tool schemas or tool definitions. The backend is not told what tools the copilot can call.

---

#### **C. Copilot Endpoint (Backend Entry Point)**
- **File:** `d:\AURA - Copy\backend\app\routers\copilot.py`
- **Route:** `POST /api/v1/copilot/chat` (lines 240–283)
- **What happens:**
  1. Validates the request with `CopilotRequest` schema
  2. Fetches the active CRM configuration (if crm_id provided)
  3. Builds a system prompt with CRM context
  4. Calls Ollama with the system prompt + messages
  5. Parses [NAV: ...] marker from reply
  6. Returns `success_response` with reply text

**Code snippet (line 278):**
```python
raw_reply = _call_ollama_copilot(messages_dicts, system)
```

**Finding:** The backend calls Ollama **but does not pass any tool definitions**. The LLM has NO KNOWLEDGE that tools exist.

---

#### **D. System Prompt Builder**
- **File:** `d:\AURA - Copy\backend\app\routers\copilot.py`
- **Function:** `_build_system_prompt(crm_context)` (lines 68–135)
- **What it includes:**
  - General AURA Copilot instructions
  - List of AURA_ROUTES for navigation
  - CRM context (entities, fields, pipeline stages, workflows)
  - **What it EXCLUDES:** No tool schemas, no function calling instructions, no "available tools" section

**Code snippet (lines 69–82):**
```python
base = (
    "You are AURA Copilot, an expert assistant for the AURA Self-Evolving CRM platform.\n\n"
    "Your capabilities:\n"
    "1. Answer questions about the user's CRM configuration (entities, fields, pipeline stages).\n"
    "2. Explain how workflows work in AURA.\n"
    "3. Guide users to the correct AURA screen using the real routes listed below.\n"
    "4. Suggest CRM improvements, but NEVER apply them — always tell the user to use the "
    "Evolution Center for changes.\n\n"
    "Rules:\n"
    "- Keep replies under 120 words. Be direct and helpful.\n"
    "- If you mention a navigation action, append it at the end as: "
    "[NAV: route_key | Button Label]\n"
    "..."
)
```

**Finding:** The system prompt explicitly tells the LLM NOT to apply changes ("NEVER apply them"). There is no mention of tools or function calling.

---

#### **E. LLM Call (Ollama)**
- **File:** `d:\AURA - Copy\backend\app\routers\copilot.py`
- **Function:** `_call_ollama_copilot(messages, system, timeout=60.0)` (lines 137–168)
- **What happens:**
  1. Constructs a prompt string with system instructions + message history
  2. Makes an HTTP POST to `http://localhost:11434/api/generate`
  3. Uses model `qwen3:4b` with `temperature=0.3`
  4. Passes the full prompt as a single concatenated string
  5. Returns the raw response text

**Code snippet (lines 150–157):**
```python
payload: dict[str, Any] = {
    "model": "qwen3:4b",
    "prompt": prompt,
    "stream": False,
    "think": False,
    "options": {"temperature": 0.3, "top_p": 0.9},
}
```

**Finding:** The Ollama request does NOT use function calling or tool calling protocols. It's a pure text generation request. Ollama's qwen3:4b model is not being instructed on tools or how to call them.

---

#### **F. Available Tools (Defined but Never Passed)**
- **File:** `d:\AURA - Copy\backend\app\services\ai_tools.py` (complete class at lines 1–350+)
- **Tools available in backend:**
  1. `add_crm_field` — Add a field to a CRM entity
  2. `update_crm_field` — Update field properties
  3. `delete_crm_field` — Delete a field
  4. `add_crm_stage` — Add a pipeline stage
  5. `delete_crm_stage` — Delete a pipeline stage
  6. `reorder_crm_fields` — Reorder fields
  7. `reorder_crm_stages` — Reorder stages

- **Tools are defined:** ✓ Yes (class CRMSchemaTools with static methods)
- **Tools are registered with LLM:** ✗ **NO** — LLM never receives schemas

**Code location (copilot.py):**
```python
from app.services.ai_tools import CRMSchemaTools
# ...
# BUT: CRMSchemaTools is never instantiated or passed to Ollama
```

**Finding:** Tools exist in Python code but are **never communicated to the LLM**.

---

#### **G. Tool Executor Endpoint**
- **File:** `d:\AURA - Copy\backend\app\routers\copilot.py`
- **Route:** `POST /api/v1/copilot/tool-call` (lines 285–381)
- **What it does:**
  1. Receives tool name, crm_id, and arguments
  2. Maps tool name to handler function from `CRMSchemaTools`
  3. Executes the tool with authorization checks
  4. Returns result (success/error)

**Code snippet (lines 316–329):**
```python
tool_handlers = {
    "add_crm_field": CRMSchemaTools.add_crm_field,
    "update_crm_field": CRMSchemaTools.update_crm_field,
    "delete_crm_field": CRMSchemaTools.delete_crm_field,
    "add_crm_stage": CRMSchemaTools.add_crm_stage,
    "delete_crm_stage": CRMSchemaTools.delete_crm_stage,
    "reorder_crm_fields": CRMSchemaTools.reorder_crm_fields,
    "reorder_crm_stages": CRMSchemaTools.reorder_crm_stages,
}
```

**Finding:** The tool executor is ready. However, it is **never called** because:
1. The LLM doesn't know about tools
2. The LLM cannot generate tool calls
3. The frontend has no code to detect or dispatch tool calls

---

#### **H. Deterministic Fallback**
- **File:** `d:\AURA - Copy\backend\app\routers\copilot.py`
- **Function:** `_deterministic_reply(question, crm_context)` (lines 170–220)
- **Purpose:** When Ollama is unavailable, return hardcoded navigation hints

**Finding:** This fallback is used when Ollama returns `None`. It helps the UI remain functional but does not enable tool calling.

---

### 1.3 Why Tool Calling Doesn't Work — Root Cause Analysis

| Component | Status | Issue |
|-----------|--------|-------|
| **Frontend sends request** | ✓ Working | Sends messages correctly |
| **Backend receives request** | ✓ Working | Parses CopilotRequest correctly |
| **CRM context loaded** | ✓ Working | Fetches configuration and workflows |
| **System prompt built** | ✓ Working | Includes CRM schema info |
| **LLM receives system prompt** | ✓ Working | Ollama is called with system instruction |
| **LLM receives tool schemas** | ✗ **BROKEN** | No tool schemas sent to LLM |
| **LLM is told to call tools** | ✗ **BROKEN** | System prompt says "NEVER apply them" |
| **LLM knows tool calling format** | ✗ **BROKEN** | No instructions on JSON tool format |
| **LLM generates tool call** | ✗ **BROKEN** | Cannot generate what it was not told about |
| **Frontend parses tool call** | ✗ **BROKEN** | No parsing logic in frontend |
| **Frontend dispatches tool call** | ✗ **BROKEN** | No dispatch logic in frontend |
| **Backend executes tool call** | ✓ Ready | Endpoint exists but never receives requests |
| **Frontend refreshes after tool** | ✗ **BROKEN** | No refresh logic |

**Critical Missing Pieces:**
1. LLM has no tool schemas in system prompt
2. LLM has no instructions on tool calling format (JSON)
3. Frontend has no tool call parsing logic
4. Frontend has no tool call dispatch logic
5. Frontend has no data refresh after tool execution

---

### 1.4 Tool Definitions (Backend)

The backend has these tools ready to be called. Here are the signatures and what they do:

#### Tool 1: add_crm_field
- **Location:** `app/services/ai_tools.py`, lines 34–122
- **Signature:**
  ```python
  add_crm_field(
    crm_id: str,
    owner_id: str,
    field_name: str,
    field_type: FieldType = "text",
    label: str | None = None,
    required: bool = False,
    options: list[str] | None = None,
  ) -> dict[str, Any]
  ```
- **Returns:** Success/error dict with updated configuration

#### Tool 2: update_crm_field
- **Location:** `app/services/ai_tools.py`, lines 125–200
- **Signature:**
  ```python
  update_crm_field(
    crm_id: str,
    owner_id: str,
    field_name: str,
    label: str | None = None,
    field_type: FieldType | None = None,
    required: bool | None = None,
    options: list[str] | None = None,
  ) -> dict[str, Any]
  ```

#### Tool 3: delete_crm_field
- **Location:** `app/services/ai_tools.py`, lines 203–280
- **Signature:**
  ```python
  delete_crm_field(
    crm_id: str,
    owner_id: str,
    field_name: str,
  ) -> dict[str, Any]
  ```

#### Tool 4: add_crm_stage
- **Location:** `app/services/ai_tools.py`, lines 283–370
- **Signature:**
  ```python
  add_crm_stage(
    crm_id: str,
    owner_id: str,
    stage_name: str,
    position: int | None = None,
  ) -> dict[str, Any]
  ```

#### Tool 5: delete_crm_stage
- **Location:** `app/services/ai_tools.py`, lines 373–440
- **Signature:**
  ```python
  delete_crm_stage(
    crm_id: str,
    owner_id: str,
    stage_name: str,
  ) -> dict[str, Any]
  ```

#### Tool 6: reorder_crm_fields
- **Location:** `app/services/ai_tools.py`, lines 443–520
- **Signature:**
  ```python
  reorder_crm_fields(
    crm_id: str,
    owner_id: str,
    field_names: list[str],
  ) -> dict[str, Any]
  ```

#### Tool 7: reorder_crm_stages
- **Location:** `app/services/ai_tools.py`, lines 523–600
- **Signature:**
  ```python
  reorder_crm_stages(
    crm_id: str,
    owner_id: str,
    stage_names: list[str],
  ) -> dict[str, Any]
  ```

**Note:** These tools exist for **CRM schema mutation** (field/stage modifications). For **record mutations** (create_record, update_record, delete_record), the backend has REST endpoints (documented in API_CONTRACTS.md, section 5.6–5.9).

---

### 1.5 Active CRM Determination (Server-Side)

**Current Implementation:**

1. **Frontend passes crm_id:** The frontend sends `crm_id` in the copilot request
   - **Location:** `AIAssistantDrawer.tsx`, lines 32, 77
   - **Source:** `activeCRM.crm_id` from CRM context
   - **Type:** String UUID

2. **Backend validates ownership:**
   - **Location:** `copilot.py`, lines 250–265
   - **Code:**
     ```python
     if body.crm_id:
         repo = CRMRepository()
         crm = repo.get_crm(body.crm_id, user_id)  # ownership enforced
     ```
   - **Safety:** CRM is fetched with `user_id` — never trusts arbitrary CRM ID

3. **Never executed AI-generated CRM IDs:** The system always validates against authenticated user

**Finding:** Active CRM determination is **safe and server-side**. ✓

---

### 1.6 Record Mutation Endpoints (Backend)

The backend has **REST endpoints for record mutations** (not tool calls):

#### Endpoint 1: Create Record
- **Route:** `POST /api/v1/crm/{crm_id}/records/{entity_name}`
- **File:** `backend/app/routers/records.py`, lines 48–77
- **Payload:**
  ```json
  {
    "data": { "field1": "value1", "field2": "value2" },
    "source": "Website"
  }
  ```
- **Returns:** Created record with ID, timestamps

#### Endpoint 2: Update Record
- **Route:** `PATCH /api/v1/crm/{crm_id}/records/{entity_name}/{record_id}`
- **File:** `backend/app/routers/records.py`, lines 129–161
- **Payload:**
  ```json
  {
    "data": { "status": "Qualified" }
  }
  ```

#### Endpoint 3: Delete Record
- **Route:** `DELETE /api/v1/crm/{crm_id}/records/{entity_name}/{record_id}`
- **File:** `backend/app/routers/records.py`, lines 164–189
- **Returns:** `{ "deleted": true }`

#### Endpoint 4: List Records
- **Route:** `GET /api/v1/crm/{crm_id}/records/{entity_name}?limit=20&offset=0`
- **File:** `backend/app/routers/records.py`, lines 92–127

#### Endpoint 5: Import CSV Records
- **Route:** `POST /api/v1/crm/{crm_id}/records/{entity_name}/import`
- **File:** `backend/app/routers/records.py`, lines 192–250

**Finding:** Record mutation endpoints are **fully implemented** and accessible via REST API. They are not tool calls but are designed for standard CRUD operations.

---

### 1.7 Field/Stage Mutation Endpoints (Backend)

These endpoints are in the **CRM router** (`backend/app/routers/crm.py`):

#### Endpoint 1: Add Field
- **Route:** `POST /api/v1/crm/{crm_id}/fields`
- **File:** `backend/app/routers/crm.py`, lines 216–352
- **Payload:**
  ```json
  {
    "field_name": "country",
    "label": "Country",
    "field_type": "text",
    "required": false,
    "options": null
  }
  ```
- **Returns:** Updated CRM configuration

#### Endpoint 2: Update Field
- **Route:** `PATCH /api/v1/crm/{crm_id}/fields/{field_name}`
- **File:** `backend/app/routers/crm.py`, lines 355–489
- **Payload:**
  ```json
  {
    "label": "New Label",
    "field_type": "email",
    "required": true
  }
  ```

#### Endpoint 3: Delete Field
- **Route:** `DELETE /api/v1/crm/{crm_id}/fields/{field_name}?confirm=true`
- **File:** `backend/app/routers/crm.py`, lines 492–628

#### Endpoint 4: Reorder Fields
- **Route:** `PATCH /api/v1/crm/{crm_id}/fields/reorder`
- **File:** `backend/app/routers/crm.py`, lines 631–701
- **Payload:**
  ```json
  {
    "field_names": ["name", "email", "company"]
  }
  ```

#### Endpoint 5: Add Stage
- **Route:** `POST /api/v1/crm/{crm_id}/stages`
- **File:** `backend/app/routers/crm.py`, lines 704–819
- **Payload:**
  ```json
  {
    "stage_name": "Negotiation",
    "position": 2
  }
  ```

#### Endpoint 6: Delete Stage
- **Route:** `DELETE /api/v1/crm/{crm_id}/stages/{stage_name}?confirm=true`
- **File:** `backend/app/routers/crm.py`, lines 822–950

#### Endpoint 7: Reorder Stages
- **Route:** `PATCH /api/v1/crm/{crm_id}/stages/reorder`
- **File:** `backend/app/routers/crm.py`, lines 953–1023
- **Payload:**
  ```json
  {
    "stage_names": ["New", "Qualified", "Negotiation", "Won", "Lost"]
  }
  ```

**Finding:** Field and stage mutation endpoints are **fully implemented and working**. ✓

---

## PART 2 — SIDEBAR NAVIGATION STRUCTURE

### 2.1 Current Sidebar Configuration

**File:** `d:\AURA - Copy\frontend\src\components\layout\Sidebar.tsx`
**Lines:** 26–42

Current nav items:
```typescript
const navItems = [
  { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
  { name: 'My CRMs', path: '/crms', icon: FolderKanban },
  { name: 'Build a CRM', path: '/chat-crm', icon: MessageCircle, highlight: true },
  { name: 'Records', path: '/records', icon: Database },
  { name: 'Workflows', path: '/workflows', icon: GitBranch },           // ← DELETE
  { name: 'Analytics', path: '/analytics', icon: BarChart3 },
  { name: 'Evolution Center', path: '/evolution', icon: Dna, badge: 'Core' },  // ← DELETE
  { name: 'Settings', path: '/settings', icon: Settings },               // ← DELETE
];
```

### 2.2 Items to Remove

| Item | Route | Reason | Status |
|------|-------|--------|--------|
| **Settings** | `/settings` | User-facing removal requested | REMOVE |
| **Workflows** | `/workflows` | User-facing removal requested | REMOVE |
| **Evolution Center** | `/evolution` | User-facing removal requested | REMOVE |

### 2.3 Items to Keep

| Item | Route | Icon | Notes |
|------|-------|------|-------|
| **Dashboard** | `/dashboard` | LayoutDashboard | Keep |
| **My CRMs** | `/crms` | FolderKanban | Keep (verify label) |
| **Build a CRM** | `/chat-crm` | MessageCircle | Keep (highlighted) |
| **Records** | `/records` | Database | Keep |
| **Analytics** | `/analytics` | BarChart3 | Keep |

### 2.4 Additional Sidebar Elements

#### AI Copilot Button
- **Location:** `Sidebar.tsx`, lines 142–169 (sidebar button) and lines 171–180 (floating button)
- **Status:** ✓ Present and functional
- **Trigger:** Opens `AIAssistantDrawer`

#### Active CRM Context Pill
- **Location:** `Sidebar.tsx`, lines 64–73
- **Status:** ✓ Present and shows active CRM name + version
- **Display:**
  ```
  Active CRM
  Analytical_E_Commerce_CRM
  v5
  ```

### 2.5 Backend Implications

**Important:** The task specifies:
> "Do NOT automatically delete backend workflow/evolution functionality."

**Current Status:**
- Workflows API (`/api/v1/crm/{crm_id}/workflows`, etc.) — **KEEP in backend**
- Evolution API (`/api/v1/crm/{crm_id}/evolution/...`) — **KEEP in backend**
- These services are used internally by the AI Copilot and may be needed for future features

**Action:** Remove sidebar navigation **ONLY**. Do not delete backend endpoints or services.

---

## PART 3 — ANALYTICS IMPLEMENTATION: HARD-CODED VS. DYNAMIC

### 3.1 Current Analytics Page (Hard-Coded)

**File:** `d:\AURA - Copy\frontend\src\features\analytics\AnalyticsPage.tsx`

#### Hard-Coded KPI Cards (Lines 114–161)
```typescript
<Card className="p-5">
  <span className="text-[10px] font-bold uppercase tracking-wider">
    Total Leads/Records          {/* ← Hard-coded label */}
  </span>
  <p className="text-2xl font-extrabold text-aura-navy">
    {analytics?.total_leads ?? 0}  {/* ← Hard-coded key */}
  </p>
</Card>

<Card className="p-5">
  <span className="text-[10px] font-bold uppercase tracking-wider">
    Qualified                     {/* ← Hard-coded label */}
  </span>
  <p className="text-2xl font-extrabold text-aura-navy">
    {analytics?.qualified_leads ?? 0}  {/* ← Hard-coded key */}
  </p>
</Card>

<Card className="p-5">
  <span className="text-[10px] font-bold uppercase tracking-wider">
    Won Deals                     {/* ← Hard-coded label */}
  </span>
  <p className="text-2xl font-extrabold text-emerald-600">
    {analytics?.won_leads ?? 0}   {/* ← Hard-coded key */}
  </p>
</Card>

<Card className="p-5">
  <span className="text-[10px] font-bold uppercase tracking-wider">
    Conversion Rate               {/* ← Hard-coded label */}
  </span>
  <p className="text-2xl font-extrabold text-amber-600">
    {analytics ? `${(analytics.conversion_rate * 100).toFixed(1)}%` : '0%'}
  </p>
</Card>
```

#### Hard-Coded Chart Titles (Lines 172, 191)
```typescript
<h3 className="text-sm font-bold text-aura-navy flex items-center gap-2">
  <BarChart3 className="w-4 h-4 text-aura-cyan" />
  Records by Pipeline Stage           {/* ← Hard-coded */}
</h3>

<h3 className="text-sm font-bold text-aura-navy flex items-center gap-2">
  <PieIcon className="w-4 h-4 text-aura-deep" />
  Lead Volume by Acquisition Source   {/* ← Hard-coded */}
</h3>
```

### 3.2 Backend Analytics Endpoint (Also Hard-Coded)

**File:** `d:\AURA - Copy\backend\app\routers\workflows.py`
**Lines:** 100–167

#### Hard-Coded Logic (Lines 109–134)
```python
# Find lead entity (first entity, or one named 'lead')
lead_entity = find_entity(config, "lead")
if not lead_entity:
    lead_entity = config.entities[0] if config.entities else None

# Assumes entity has 'lead' name
entity_name = lead_entity.name

# Find stage/status field
stage_field = None
source_field = None
for f in lead_entity.fields:
    if f.name in ("status", "stage") and f.type == "select":
        stage_field = f
    if f.name == "source" and f.type == "select":  # ← Hard-coded field name
        source_field = f
```

#### Hard-Coded Metrics (Lines 145–150)
```python
qualified_stages = {"Qualified", "qualified"}      # ← Hard-coded stage names
won_stages = {"Won", "won", "Closed Won", "closed_won"}  # ← Hard-coded stage names

for entry in by_stage:
    val = entry.get("value", "")
    if val in qualified_stages:
        qualified = entry.get("count", 0)
    if val in won_stages:
        won = entry.get("count", 0)
```

#### Response Structure (Lines 153–164)
```python
return success_response({
    "total_leads": total_leads,           # ← Total records (hard-coded key name)
    "qualified_leads": qualified,         # ← Hard-coded metric
    "won_leads": won,                      # ← Hard-coded metric
    "conversion_rate": round(conversion_rate, 4),  # ← Hard-coded metric
    "by_source": by_source,
    "by_stage": by_stage,
})
```

**Analysis:** The backend searches for a "source" field (hard-coded name) and hard-codes stage names like "Qualified" and "Won". This approach **does not work for custom CRMs** with different stages or fields.

### 3.3 What a Fully Dynamic Analytics System Would Need

#### Backend Changes
1. **Remove hard-coded stage names** — Read the actual stages from `configuration.pipeline_stages`
2. **Remove hard-coded "source" field assumption** — Make source field optional or configurable
3. **Return stage metadata** — Include stage labels and order so frontend can display them correctly
4. **Support any entity** — Don't assume "lead" entity; allow user to pick which entity to analyze (or use the first one)
5. **Compute metrics dynamically** — Instead of looking for "Qualified" and "Won" stages, analyze which stages represent "positive" outcomes or use user-defined business logic

#### Frontend Changes
1. **Fetch CRM schema along with analytics** — Need entity names, stage names, field types
2. **Generate KPI cards dynamically** — Instead of hard-coding "Total Leads", "Qualified", "Won Deals", generate cards from the CRM's actual structure
3. **Support variable stage lists** — A sales CRM might have 6 stages; a support CRM might have 4. The frontend must handle this
4. **Use CRM-defined stage names** — Display the user's actual stages, not hard-coded ones
5. **Make stage order match CRM configuration** — `pipeline_stages` array defines the order; respect it

### 3.4 Examples of What Should Be Dynamic

#### Example 1: Sales CRM
**Configured Stages:** `["New", "Contacted", "Qualified", "Proposal", "Negotiation", "Won", "Lost"]`

**Analytics should display:**
```
Records by Pipeline Stage:
  New — 35 (29.2%)
  Contacted — 28 (23.3%)
  Qualified — 22 (18.3%)
  Proposal — 15 (12.5%)
  Negotiation — 12 (10%)
  Won — 6 (5%)
  Lost — 2 (1.7%)
```

#### Example 2: Customer Support CRM
**Configured Stages:** `["Open", "Assigned", "In Progress", "Waiting for Customer", "Resolved", "Closed"]`

**Analytics should display:**
```
Records by Pipeline Stage:
  Open — 45 (25%)
  Assigned — 32 (17.8%)
  In Progress — 28 (15.6%)
  Waiting for Customer — 38 (21.1%)
  Resolved — 32 (17.8%)
  Closed — 5 (2.8%)
```

#### Example 3: Recruitment CRM
**Configured Stages:** `["Applied", "Screening", "Interview Round 1", "Interview Round 2", "Selected", "Hired", "Rejected"]`

**Analytics should display:**
```
Records by Pipeline Stage:
  Applied — 120 (45%)
  Screening — 60 (22.6%)
  Interview Round 1 — 35 (13.2%)
  Interview Round 2 — 25 (9.4%)
  Selected — 10 (3.8%)
  Hired — 8 (3%)
  Rejected — 4 (1.5%)
```

**Finding:** All of these need the **same backend and frontend logic**. The only difference is the **CRM schema**. The analytics system must be entirely driven by the schema.

---

## PART 4 — DATA SOURCES AND SCHEMA ACCESS

### 4.1 How Frontend Gets CRM Schema

**File:** `frontend/src/context/CRMContext.tsx` (inferred from usage)
**Source:** When user selects a CRM, the frontend stores `activeCRM` in context:
```typescript
const { activeCRM } = useCRM();
```

**What activeCRM contains:**
- `crm_id`: UUID
- `name`: String (e.g., "Analytical_E_Commerce_CRM")
- `configuration`: Full CRMConfiguration object (entities, fields, pipeline_stages)
- `configuration_version`: Number

### 4.2 How Backend Gets Analytics Data

**Endpoint:** `GET /api/v1/crm/{crm_id}/analytics`
**File:** `backend/app/routers/workflows.py`, lines 100–167
**Process:**
1. Fetch CRM from database using `crm_id` and `user_id`
2. Parse `configuration` JSONB column to get entity definitions
3. Find the "lead" entity (or first entity)
4. Query database for record counts by stage using `repo.count_records_by_field()`
5. Return aggregated counts

### 4.3 CRM Schema Structure

**Location in Database:** `crms.configuration` JSONB column
**Structure:**
```json
{
  "schema_version": "1.0",
  "name": "SaaS CRM",
  "industry": "saas",
  "entities": [
    {
      "name": "lead",
      "label": "Lead",
      "fields": [
        {
          "name": "full_name",
          "label": "Full Name",
          "type": "text",
          "required": true
        },
        {
          "name": "status",
          "label": "Lead Status",
          "type": "select",
          "required": true,
          "options": ["New", "Qualified", "Demo", "Proposal", "Won", "Lost"]
        }
      ]
    }
  ],
  "pipeline_stages": ["New", "Qualified", "Demo", "Proposal", "Won", "Lost"]
}
```

### 4.4 Key Observation: pipeline_stages Array

**Location:** `configuration.pipeline_stages`
**Type:** Array of strings
**Contains:** The **complete list of all user-defined stages** in the correct order

**Current Bug:** The backend ignores `pipeline_stages` and instead hard-codes stage names. This is the root cause of the analytics being non-universal.

**Fix:** When fetching analytics:
1. Read `configuration.pipeline_stages` (the user's actual stages)
2. Query database for record count per stage
3. Return all stages in the order they appear in the array
4. Compute percentages based on total record count

---

## PART 5 — BLOCKERS AND DEPENDENCIES

### 5.1 Copilot Tool Calling Blockers

| Blocker | Severity | Dependency | Solution |
|---------|----------|-----------|----------|
| LLM doesn't receive tool schemas | **CRITICAL** | None | Add tool schema JSON to system prompt |
| LLM doesn't know tool calling format | **CRITICAL** | None | Add tool calling instructions to system prompt |
| Frontend can't parse tool calls | **CRITICAL** | Tool schemas defined | Implement JSON parser in frontend |
| Frontend can't dispatch tool calls | **CRITICAL** | Tool parser working | Implement HTTP client to call backend tool executor |
| Frontend can't refresh data after tool | **CRITICAL** | Tools working | Invalidate/refetch affected data (records, CRM config, etc.) |
| No approval workflow for tool calls | **HIGH** | Tool calling working | Implement approval UI if needed (may not be for simple field adds) |

### 5.2 Sidebar Removal Blockers

| Item | Blocker | Dependency |
|------|---------|-----------|
| Remove "Settings" | None | Simple UI change |
| Remove "Workflows" | Frontend-only change | No dependencies |
| Remove "Evolution Center" | Frontend-only change | Backend unchanged |
| Label verification ("My CRMs") | None | Simple text review |

**Dependency:** None. Sidebar can be updated independently.

### 5.3 Analytics Dynamization Blockers

| Blocker | Severity | Dependency | Solution |
|---------|----------|-----------|----------|
| Backend hard-codes stage names | **CRITICAL** | None | Read from `pipeline_stages` array |
| Backend hard-codes "source" field | **HIGH** | Analytics query | Make optional or user-configurable |
| Backend hard-codes entity selection | **CRITICAL** | None | Use first entity or user selection |
| Frontend hard-codes KPI labels | **CRITICAL** | Backend working | Generate KPI cards dynamically from schema |
| Frontend doesn't fetch schema | **CRITICAL** | None | Already available in context |
| Frontend doesn't handle variable stage count | **HIGH** | Backend working | Use grid layout or dynamic card system |

**Dependencies:**
1. Backend must return stages in correct order
2. Frontend must have access to CRM schema (already does)
3. Frontend must compute percentages and generate UI dynamically

---

## PART 6 — RECOMMENDED FIX SEQUENCE AND APPROACH

### Phase 1: Copilot Tool Calling (Most Complex, Highest Impact)

**Goal:** Enable LLM to call tools for CRM modifications.

**Steps:**
1. Generate tool schemas JSON from `CRMSchemaTools` class methods
2. Add tool schemas to system prompt sent to Ollama
3. Add tool calling instructions to system prompt ("When user asks to add field, generate tool call in this format: ...")
4. Implement frontend parser to extract tool calls from LLM response
5. Implement frontend dispatcher to call `/copilot/tool-call` endpoint
6. Implement frontend data refresh after tool execution
7. Add record creation/update/deletion via REST API (NOT tools) when user requests it

**Complexity:** High (multiple systems: LLM, frontend parsing, API integration)
**Impact:** Enables all action-oriented copilot requests
**Timeline:** 2–3 days

### Phase 2: Sidebar Cleanup (Simplest)

**Goal:** Remove navigation items.

**Steps:**
1. Remove "Settings", "Workflows", "Evolution Center" from `navItems` array
2. Verify no dead links remain
3. Test sidebar rendering

**Complexity:** Very low (1 file, 3 lines removed)
**Impact:** Immediate UX improvement
**Timeline:** 30 minutes

### Phase 3: Analytics Dynamization (Medium Complexity)

**Goal:** Generate analytics UI and metrics based on CRM schema.

**Steps:**
1. Modify backend `/api/v1/crm/{crm_id}/analytics` to:
   - Read `pipeline_stages` from configuration (not hard-coded)
   - Return all stages in order with record counts
   - Return stage labels alongside counts
   - Make "source" field optional
2. Modify frontend `AnalyticsPage.tsx` to:
   - Fetch CRM schema (already available in context)
   - Generate KPI cards dynamically for each stage
   - Compute percentages dynamically
   - Handle variable stage count
   - Use stage labels from schema
3. Update analytics data types in `frontend/src/types/crm.ts`

**Complexity:** Medium (schema understanding required)
**Impact:** Makes analytics work for all CRM types
**Timeline:** 1–1.5 days

### Execution Order

**Recommended:** Phase 2 → Phase 1 → Phase 3

**Rationale:**
- Phase 2 is fast and safe; do it first to build momentum
- Phase 1 is complex but enables major feature; tackle after quick win
- Phase 3 depends on nothing in Phases 1–2; can happen in parallel or after

---

## PART 7 — RECORD MUTATION WORKFLOWS (Not Tool Calls)

### 7.1 How Record Mutations Should Work

The copilot should support **record CRUD** separately from **schema CRUD**:

#### Record Creation Example
```
User: "Add a lead named John, email john@example.com, status New"

Copilot should:
1. Identify "create_record" action
2. Map entity (lead) and fields (full_name → John, email → john@example.com, status → New)
3. Call REST endpoint: POST /api/v1/crm/{crm_id}/records/lead
4. Get back record ID
5. Confirm: "✓ Created lead #abc-123 (John, john@example.com, New)"
```

#### Record Update Example
```
User: "Update John's status to Qualified"

Copilot should:
1. Identify "update_record" action
2. Ask for clarification if multiple Johns exist
3. Call REST endpoint: PATCH /api/v1/crm/{crm_id}/records/lead/{record_id}
4. Confirm: "✓ Updated John's status to Qualified"
```

### 7.2 Implementation Approach

**Record mutations** are different from **schema mutations**:

- **Schema mutations** → Use `CRMSchemaTools` (tool calls via `/copilot/tool-call`)
- **Record mutations** → Use REST API directly (POST/PATCH/DELETE `/crm/{crm_id}/records/...`)

**Why?**
- Record mutations are simpler and don't need approval
- Schema mutations are rare and have side effects
- Schema tools are pre-built and awaiting tool calling implementation

---

## PART 8 — CURRENT ANALYTICS RESPONSE STRUCTURE

When frontend calls `api.getAnalytics(crm_id)`, backend returns:

```json
{
  "total_leads": 120,
  "qualified_leads": 40,
  "won_leads": 12,
  "conversion_rate": 0.10,
  "by_source": [
    {"value": "Website", "count": 65},
    {"value": "Referral", "count": 35},
    {"value": "Direct", "count": 20}
  ],
  "by_stage": [
    {"value": "New", "count": 30},
    {"value": "Qualified", "count": 40},
    {"value": "Won", "count": 12},
    {"value": "Lost", "count": 38}
  ]
}
```

**Problems with this structure:**
1. Hard-codes metric names (`total_leads`, `qualified_leads`, `won_leads`)
2. No stage labels (only values like "New", "Qualified")
3. No stage order hint (should match `pipeline_stages`)
4. No information about which CRM entity this represents

**What it should return instead:**
```json
{
  "entity_name": "lead",
  "entity_label": "Lead",
  "total_records": 120,
  "by_stage": [
    {"stage_name": "New", "stage_label": "New", "count": 30, "percentage": 25.0, "position": 0},
    {"stage_name": "Qualified", "stage_label": "Qualified", "count": 40, "percentage": 33.3, "position": 1},
    ...
  ],
  "by_source": [
    {"source": "Website", "count": 65, "percentage": 54.2},
    ...
  ]
}
```

---

## SUMMARY TABLE: Current vs. Required Implementation

| Subsystem | Current Status | Required Status | Effort | Priority |
|-----------|--------|--------|--------|----------|
| **Copilot Tool Calling** | Disabled (tools exist, LLM not told about them) | Tools working end-to-end | High | **CRITICAL** |
| **Sidebar Navigation** | Contains 3 items to remove | Clean 5-item sidebar | Very Low | **HIGH** |
| **Analytics Backend** | Hard-coded for "lead" entity, stage names | Dynamic based on schema | Medium | **CRITICAL** |
| **Analytics Frontend** | Hard-coded KPI cards | Dynamic KPI generation | Medium | **CRITICAL** |
| **CRM Schema Access** | Available in context | ✓ Already available | — | — |
| **Active CRM Safety** | Safe (server-side validation) | ✓ No changes needed | — | — |
| **Record CRUD API** | Fully implemented | ✓ Ready to use | — | — |
| **Field/Stage CRUD API** | Fully implemented | ✓ Ready to use | — | — |

---

## CONCLUSION

### What Works ✓
- Backend REST API for CRUD operations (records, fields, stages)
- Frontend chat UI and message history
- CRM context fetching and display
- Active CRM determination (server-side safe)
- Field/stage tools are defined and ready

### What's Broken ✗
- **Copilot does NOT call tools** — LLM has no tool schemas or calling instructions
- **Sidebar has navigation cruft** — Settings, Workflows, Evolution Center should be hidden
- **Analytics are hard-coded** — Fails for any CRM not exactly matching the assumed schema

### Recommended Action
1. **Implement tool calling pipeline** (LLM → frontend → backend execution)
2. **Clean up sidebar** (remove 3 items)
3. **Dynamize analytics** (read schema, generate UI)

This report provides the foundation for the implementation plan.

---

**END OF INVESTIGATION REPORT**
