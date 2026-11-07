# How AI Models Work in AURA: Deep Technical Explanation

**Purpose:** Understand how AURA uses AI models without exposing API keys or secrets.

---

## 1. Architecture Overview: Three-Tier AI System

AURA uses a **three-tier AI approach** to balance speed, accuracy, and cost:

```
┌─────────────────────────────────────────┐
│         User Request / Prompt           │
└────────────────────┬────────────────────┘
                     │
                     ▼
    ┌───────────────────────────────┐
    │  System 1: Laya Classifier    │ ← Fast, Rule-Based (0-10ms)
    │  (Deterministic Logic)        │
    │  - Classify intent            │
    │  - Resolve entity names       │
    │  - Repair schemas             │
    └──────────────┬────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
    ┌───▼────┐           ┌───▼──────┐
    │ Simple │           │ Complex  │
    │ Request│           │ Request  │
    │ (no    │           │ (needs   │
    │ LLM)   │           │ reasoning)
    │        │           │          │
    └────────┘           └────┬─────┘
                              │
                              ▼
                  ┌──────────────────────┐
                  │  System 2: LLM       │ ← Slow, Accurate (1-5s)
                  │  Provider Selection  │
                  └──────────┬───────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
         ┌──────▼──────┐        ┌────────▼────────┐
         │  Groq API   │        │ Ollama Fallback │
         │ (Production)│        │ (Dev/Fallback)  │
         │ llama-3.3-  │        │ qwen2.5:3b      │
         │ 70b model   │        │ (Local)         │
         └──────┬──────┘        └────────┬────────┘
                │                        │
                │                        │
         (External SaaS)         (Local Container)
                │                        │
                └────────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │  Response + Output   │
                  └──────────────────────┘
```

---

## 2. System 1: Laya (Deterministic Classifier)

**What it is:** A rule-based, deterministic classifier (NOT an LLM).

**Location:** `backend/app/services/laya_system1.py` (330+ lines of pure Python logic)

**No External API Calls:** Laya runs entirely locally in milliseconds; no network dependency.

### What Laya Does

#### A. Intent Classification
**Purpose:** Categorize user input without calling an expensive LLM

**Logic:**
```python
# Pseudo-code example
if "how many" in prompt and ("leads" in prompt or "deals" in prompt):
    return IntentCategory.ANALYTICS_QUERY
elif "add" in prompt or "create" in prompt:
    return IntentCategory.CREATE_RECORD
elif "what fields" in prompt or "show me" in prompt:
    return IntentCategory.HELP_REQUEST
else:
    return IntentCategory.RECORD_QUERY
```

**Examples:**
- User: "How many deals are in negotiation?" → Laya classifies as **ANALYTICS_QUERY**
- User: "Create a new lead" → Laya classifies as **CREATE_RECORD**
- User: "What fields does my CRM have?" → Laya classifies as **HELP_REQUEST**

**Benefit:** No LLM call needed for routine requests; response is instant.

#### B. Entity Resolution (Name Matching)
**Purpose:** Match user's entity reference to actual CRM entities

**Logic:**
- User says "lead" → Match against CRM entities: "lead" (exact match) ✓
- User says "leads" (plural) → Match to "lead" (singular, stemming) ✓
- User says "customer" → Match to closest entity in CRM by name similarity
- If multiple matches, ask user for clarification

**Example:**
```python
# Pseudo-code
user_input = "create a new lead"
crm_entities = [{"name": "lead", "label": "Lead"}, {"name": "deal", "label": "Deal"}]

resolved_entity = fuzzy_match(user_input, crm_entities)
# Returns: {"name": "lead", "label": "Lead"}
```

**Benefit:** Resolves ambiguity before passing to LLM, reducing token usage.

#### C. Schema Repair & Sanitization
**Purpose:** Fix common errors in AI-generated CRM schemas

**Logic:**
1. **Validate entity names:** Must be lowercase, underscores only, no spaces/special chars
   - "User Profile" → "user_profile" ✓
   - "Invalid-Name" → "invalid_name" ✓
2. **Validate field types:** Only allow known types (text, email, number, date, select, phone)
   - "string" → "text" ✓
   - "integer" → "number" ✓
   - "unknown_type" → "text" (safe default) ✓
3. **Deduplicate:** Remove duplicate field/stage names
4. **Fill defaults:** If missing required fields, add sensible defaults

**Example:**
```python
# Raw output from LLM (may have errors)
raw_schema = {
    "entities": [
        {"name": "User Profile", "fields": [...]},  # ❌ Invalid name
        {"name": "user_profile", "fields": [...]},  # ✓ Duplicate
    ]
}

# After Laya repair
repaired = {
    "entities": [
        {"name": "user_profile", "fields": [...]}  # ✓ Fixed
    ]
}
```

**Benefit:** Catches AI errors before they cause runtime issues; improves reliability.

#### D. Industry Detection
**Purpose:** Infer industry from prompt to provide context

**Logic:**
```python
if any(keyword in prompt_lower for keyword in ["sales", "leads", "deals", "pipeline"]):
    return "saas"
elif any(keyword in prompt_lower for keyword in ["patient", "doctor", "appointment"]):
    return "healthcare"
elif any(keyword in prompt_lower for keyword in ["candidate", "hire", "interview"]):
    return "recruitment"
else:
    return "custom"
```

**Benefit:** Helps downstream systems make better decisions without LLM call.

### When Laya is Used

| Scenario | Laya? | Why |
|----------|-------|-----|
| User asks "how many leads in negotiation?" | ✅ Yes | Intent is clear; can query directly |
| User says "I need a CRM for sales" (ambiguous) | ✅ Yes (initially) | Classify as CRM_GENERATION; escalate to LLM for detailed schema |
| User asks "add Alice Smith as a lead" | ✅ Yes | Resolve entity "lead", classify as CREATE_RECORD |
| User asks "what's the meaning of life?" | ✅ Yes | Classify as OUT_OF_SCOPE; return help message |

---

## 3. System 2: LLM Provider Selection

**When Laya isn't enough**, AURA escalates to an LLM. The backend uses a **provider factory** that selects between Groq and Ollama based on configuration.

### How Provider Selection Works

**Location:** `backend/app/services/ai_provider.py::get_ai_provider()`

**Configuration Mechanism:**
```python
# In backend/.env or environment variables
LLM_PROVIDER=groq  # or "local" or "mock" for testing

# Read from config
settings = get_settings()
provider_name = settings.llm_provider  # e.g., "groq"

# Factory returns appropriate provider
provider = get_ai_provider(provider_name)
# Returns: GroqProvider, OllamaProvider, or MockProvider
```

**No hardcoding:** The provider is determined entirely by environment configuration, not code.

### Data Flow: How Requests Reach the Model

```
User Request
    ↓
Backend Endpoint
(e.g., POST /api/v1/crm/chat)
    ↓
Service Layer (e.g., GroqProvider)
    ↓
Provider reads settings.groq_api_key
(from environment, NOT hardcoded)
    ↓
Provider initializes SDK:
from groq import Groq
client = Groq(api_key=settings.groq_api_key)
    ↓
Provider calls LLM API:
completion = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{...}],
    ...
)
    ↓
LLM Service (Groq SaaS or local Ollama)
    ↓
Model generates response
    ↓
Response returned to backend
    ↓
Response validated and sanitized
    ↓
Response sent to frontend
```

**Critical:** API key is never:
- Hardcoded in code
- Sent to frontend
- Logged in plain text
- Exposed in error messages

---

## 4. Groq: Production LLM Provider

**Model:** `llama-3.3-70b-versatile`  
**Provider:** Groq, Inc. (SaaS API)  
**Latency:** ~1–2 seconds per request  
**Cost:** Paid per token (shared key managed server-side)

### How Groq Works (High Level)

Groq is an **external SaaS API** that hosts large language models. AURA doesn't run the model locally; instead, it sends requests to Groq's infrastructure.

#### Step 1: Credential Initialization
```python
# In GroqProvider.__init__()
from groq import Groq

# Credentials loaded from environment, NOT hardcoded
api_key = settings.groq_api_key  # e.g., from backend/.env

# Initialize client
self.client = Groq(api_key=api_key)
```

**Security:** The API key is read from the environment at startup and never duplicated or logged.

#### Step 2: Building the Request
```python
# Example: CRM generation request

messages = [
    {"role": "system", "content": "You are a CRM architect..."},
    {"role": "user", "content": "I need a sales CRM with leads and deals"}
]

params = {
    "model": "llama-3.3-70b-versatile",
    "messages": messages,
    "temperature": 0.2,  # Low randomness for deterministic generation
    "max_tokens": 4096   # Max response length
}
```

**Note:** No API key in the request body; it's passed via the HTTP header (handled by Groq SDK).

#### Step 3: Sending to Groq's API
```python
# Groq SDK handles HTTPS connection
completion = self.client.chat.completions.create(**params)
```

**Behind the scenes:**
- SDK signs request with API key
- Sends over HTTPS to `https://api.groq.com/...` (encrypted)
- Groq service receives request
- Verifies API key is valid
- Routes to llama-3.3-70b model
- Model processes prompt
- Response returned

#### Step 4: Parsing Response
```python
# Response object
response = {
    "content": "Here's a CRM schema...",
    "tool_calls": [...],  # If function calling
    "provider": "groq",
    "model": "llama-3.3-70b-versatile",
    "used": True
}

# Extract JSON or text
content = response["content"]
parsed_json = json.loads(content)
```

#### Step 5: Validation & Sanitization
```python
# Laya repairs any errors
repaired = LayaSystem1.repair_crm_configuration(parsed_json, original_prompt)

# Validate against Pydantic schema
config = CRMConfiguration(**repaired)

# Return to frontend (no API key, no secrets)
return config.model_dump()
```

### Use Cases for Groq in AURA

| Use Case | Prompt | Model Task |
|----------|--------|-----------|
| **CRM Generation** | "I need a CRM for a recruitment agency" | Generate schema JSON with entities, fields, stages |
| **Copilot Chat** | "Create a lead named Alice" | Reason about intent, generate tool call JSON |
| **Evolution Proposals** | "Analyze usage and suggest improvements" | Review analytics, suggest schema changes |
| **Schema Repair** | Raw JSON from LLM has errors | Validate and sanitize structure |

### Temperature Parameter (Randomness Control)

Groq supports `temperature` to control response randomness:

- **temperature=0.2** (used in AURA): Very deterministic, repeatable responses (good for CRM generation)
- **temperature=0.7**: Moderate creativity (good for conversation)
- **temperature=1.0**: Maximum randomness (good for brainstorming)

AURA uses **0.2** for CRM generation because we want predictable, valid schemas—not creative variations.

---

## 5. Ollama: Local LLM Runtime (Your Current Setup)

**Model:** `qwen2.5:3b` (3 billion parameters)  
**Provider:** Local container running on `http://localhost:11434`  
**Latency:** ~2–5 seconds (slower than Groq, but no API key needed)  
**Cost:** $0 (runs locally on your machine)  
**Status:** ✅ **Currently active** (LLM_PROVIDER=local in your .env)

### What is Ollama?

Ollama is a **local LLM runtime** that runs language models directly on your machine, without needing cloud APIs or API keys.

**How it differs from Groq:**
```
GROQ:                              OLLAMA:
External SaaS API                  Local application
Requires API key                   No credentials needed
Remote servers                     Your machine
1-2 second response                3-5 second response
Pay per token                      Free (offline)
Latest 70B models                  Smaller 3B-13B models
Always available (if internet)     Works offline
```

### Setup & Installation (One-Time)

```bash
# 1. Install Ollama
# Visit https://ollama.ai and download for your OS

# 2. Download the model
ollama pull qwen2.5:3b

# 3. Start Ollama server (runs in background)
ollama serve

# 4. Verify it's running
curl http://localhost:11434/api/tags
# Response: {"models":[{"name":"qwen2.5:3b:latest",...}]}
```

### How AURA Uses Ollama

**Location:** `backend/app/services/ollama_provider.py`

#### Step 1: Initialize Provider

```python
class OllamaAIProvider:
    def __init__(self, base_url="http://localhost:11434", model="qwen2.5:3b"):
        self.base_url = base_url      # From settings.local_llm_base_url
        self.model = model            # From settings.local_llm_model
```

#### Step 2: Build Request

```python
def _call_ollama_generate(self, system_prompt: str, user_prompt: str) -> str | None:
    """Send request to local Ollama server."""
    
    # Build payload
    payload = {
        "model": self.model,  # "qwen2.5:3b"
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2,   # Low randomness for deterministic generation
        "stream": False       # Wait for complete response
    }
```

#### Step 3: Send to Local Ollama

```python
    # Make HTTP POST request to local server
    import requests
    
    response = requests.post(
        f"{self.base_url}/api/chat",  # http://localhost:11434/api/chat
        json=payload,
        timeout=30.0
    )
    
    # Parse response
    result = response.json()
    content = result["message"]["content"]
    return content
```

#### Step 4: No API Key Involved

```python
# ✅ Unlike Groq, NO API key authentication needed
# Ollama runs locally on localhost (localhost:11434)
# No HTTPS, no credentials, no external service
```

### Your Current Configuration

**From your `backend/.env`:**
```env
LLM_PROVIDER=local
```

**From `backend/app/config.py` defaults:**
```python
local_llm_base_url="http://localhost:11434"  # Where Ollama listens
local_llm_model="qwen2.5:3b"                 # Model being used
```

**Flow when backend starts:**
```
1. Load settings from .env
   → LLM_PROVIDER = "local"
   
2. Call: get_ai_provider("local")
   
3. Provider factory decides:
   if provider_name == "local":
       return OllamaAIProvider(
           base_url="http://localhost:11434",
           model="qwen2.5:3b"
       )
   
4. All AI requests now use OllamaAIProvider
```

### Use Cases for Ollama in AURA

| Feature | Ollama Works? | Latency | Use Case |
|---------|---|---|---|
| **CRM Generation** | ✅ Yes | 2–5s | User describes CRM → Ollama generates schema |
| **Copilot Chat** | ✅ Yes | 1–3s | Multi-turn conversation with AI assistant |
| **Tool Calling** | ✅ Yes | 1–2s | Generates JSON tool calls (create_record, etc.) |
| **Evolution Proposals** | ✅ Yes | 2–5s | Analyzes usage, suggests improvements |
| **CSV Processing** | ✅ Yes | 1–2s | Extract fields from CSV headers |

### Why Ollama is Perfect for Your Hackathon

**Advantages:**
- ✅ No API key needed (instant setup)
- ✅ Works offline (no internet dependency)
- ✅ Free (runs on your machine)
- ✅ All features work exactly the same
- ✅ Deterministic & reliable
- ✅ Shows AURA works end-to-end

**Tradeoff:**
- ⚠️ Slower than Groq (3–5s vs. 1–2s)
- ⚠️ Less accurate than 70B models (uses 3B qwen2.5)
- ⚠️ But still very good for demos

---

## 5b. Switching to Groq (If You Get API Key Later)

To use Groq instead of Ollama:

```env
# In backend/.env, change:
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...  # Your API key
GROQ_MODEL=llama-3.3-70b-versatile
```

Then restart the backend. Provider factory automatically switches to GroqAIProvider.

### Why Ollama is Used as Fallback

| Scenario | Provider | Why |
|----------|----------|-----|
| **Your setup (now)** | Ollama | Free, no key, instant demo |
| **Production** | Groq | Reliable, fast, latest models |
| **Development** | Ollama | Local testing, offline support |
| **Groq unreachable** | Ollama | Automatic fallback (if configured) |
| **Testing (CI/CD)** | Mock | Deterministic fixtures, no network |

### Provider Selection Logic

**Location:** `backend/app/services/ai_provider.py::get_ai_provider()`

```python
def get_ai_provider(provider_name: str = "groq") -> AIProvider:
    """Factory function: select provider based on config."""
    normalized = provider_name.lower().strip()
    
    # Decision tree
    if normalized == "mock":
        return MockAIProvider()  # Deterministic (testing)
    
    if normalized == "groq":
        return GroqAIProvider()  # SaaS API (production)
    
    if normalized in ("local", "ollama"):
        settings = get_settings()
        return OllamaAIProvider(
            base_url=settings.local_llm_base_url,      # localhost:11434
            model=settings.local_llm_model             # qwen2.5:3b
        )
    
    raise ValueError(f"Unsupported provider: {provider_name}")
```

**Your case:**
```
backend/.env: LLM_PROVIDER=local
    ↓
get_ai_provider("local")
    ↓
if normalized in ("local", "ollama"): ✓
    ↓
return OllamaAIProvider(...)
    ↓
All AURA requests use Ollama
```

---

## 6. How Secrets (API Keys) Are Protected

### Where Credentials Come From

```
┌──────────────────────┐
│  backend/.env file   │  ← NOT committed to git
│  (local machine)     │
│  LLM_PROVIDER=groq   │
│  GROQ_API_KEY=gsk_.. │
│  GROQ_MODEL=llama... │
└──────────┬───────────┘
           │
           │ (loaded at startup)
           ▼
┌──────────────────────────┐
│  Settings object         │
│  (in-memory only)        │
│  groq_api_key: str       │
│  groq_model: str         │
└──────────┬───────────────┘
           │
           │ (used to initialize provider)
           ▼
┌──────────────────────────┐
│  GroqProvider            │
│  self.client = Groq(...) │
│  (secret never exposed)  │
└──────────────────────────┘
```

### Credential Security Rules (Enforced by Code)

1. **Never in code:**
   ```python
   # ❌ BAD
   GROQ_API_KEY = "gsk_..."  # Never do this
   
   # ✅ GOOD
   groq_api_key = settings.groq_api_key  # From environment only
   ```

2. **Never sent to frontend:**
   ```python
   # ❌ BAD
   return {"api_key": settings.groq_api_key, "data": ...}
   
   # ✅ GOOD
   return {"data": ..., "provider": "groq"}  # No secrets
   ```

3. **Never logged in plain text:**
   ```python
   # ❌ BAD
   logger.info(f"Connecting to Groq with key {settings.groq_api_key}")
   
   # ✅ GOOD
   logger.info("Connecting to Groq API (provider configured)")
   ```

4. **Never in error messages:**
   ```python
   # ❌ BAD
   raise Exception(f"API key {api_key} is invalid")
   
   # ✅ GOOD
   raise GroqUnavailable("Groq API is not configured properly")
   ```

### How Secrets Are Read at Runtime

```python
# backend/app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    groq_api_key: str = Field(
        default="", 
        description="Groq API key (server-side only)"
    )
    
    model_config = {
        "env_file": (".env", "backend/.env"),
        "env_file_encoding": "utf-8"
    }

# Pydantic-settings automatically:
# 1. Reads .env file
# 2. Loads environment variables
# 3. Populates Settings object
# 4. Never exposes secrets in __repr__
```

---

## 7. API Request Flow (Detailed)

### Example: CRM Generation from Chat

```
1. USER SUBMITS PROMPT
   Frontend (React)
   ├─ User types: "I need a CRM for a sales team"
   └─ Clicks "Generate"

2. FRONTEND SENDS REQUEST
   POST /api/v1/crm/chat
   {
     "messages": [{...}],
     "generate_now": true
   }
   
   ├─ No API key in request
   └─ JWT token in Authorization header (for auth, not API)

3. BACKEND RECEIVES REQUEST
   FastAPI endpoint (chat.py::chat())
   ├─ Verifies JWT → auth.uid() = user123
   ├─ Loads settings → llm_provider = "groq"
   └─ Gets provider → GroqProvider

4. PROVIDER SENDS TO GROQ
   GroqProvider.generate_json()
   ├─ Reads settings.groq_api_key (from environment)
   ├─ Initializes Groq client
   ├─ Builds request:
   │  {
   │    "model": "llama-3.3-70b-versatile",
   │    "messages": [
   │      {"role": "system", "content": "You are a CRM architect..."},
   │      {"role": "user", "content": "I need a CRM for a sales team"}
   │    ],
   │    "temperature": 0.2,
   │    "max_tokens": 4096
   │  }
   └─ Sends HTTPS request (API key in header, not body)

5. GROQ PROCESSES REQUEST
   ├─ Groq API receives request
   ├─ Verifies API key
   ├─ Routes to llama-3.3-70b model
   ├─ Model generates response:
   │  {
   │    "schema_version": "1.0",
   │    "name": "Sales CRM",
   │    "entities": [...],
   │    "pipeline_stages": [...]
   │  }
   └─ Returns response

6. PROVIDER RECEIVES & VALIDATES
   ├─ Parses JSON response
   ├─ Extracts content (removes markdown if present)
   ├─ Validates as JSON
   └─ Returns dict

7. BACKEND REPAIRS SCHEMA
   ├─ Calls LayaSystem1.repair_crm_configuration()
   ├─ Fixes entity names, field types
   ├─ Validates against Pydantic CRMConfiguration
   └─ Returns repaired config

8. BACKEND SENDS RESPONSE
   200 OK
   {
     "data": {
       "configuration": {...},
       "ready": true
     },
     "meta": {"request_id": "req_123"}
   }
   
   ├─ No secrets exposed
   ├─ No API key in response
   └─ Frontend ready to display CRM draft

9. FRONTEND DISPLAYS RESULT
   ├─ Parses response
   ├─ Shows generated CRM schema
   └─ User can review and save
```

---

## 8. Error Handling & Fallback

### What If Groq is Unavailable?

```python
# backend/app/services/groq_provider.py

try:
    completion = self._client().chat.completions.create(**params)
    # Success ✓
except GroqUnavailable as exc:
    # Groq API error
    # Options:
    # 1. Fall back to Ollama if configured
    # 2. Return error to frontend
    raise

except Exception as exc:
    # Unexpected error (network, timeout, etc.)
    # Don't expose error details
    raise GroqUnavailable(
        f"Groq request failed ({type(exc).__name__})."
    ) from exc
```

### Fallback Strategy

```python
# Example in backend
try:
    provider = get_ai_provider(settings.llm_provider)  # "groq"
    result = provider.generate_crm_config(prompt)
except ProviderUnavailable:
    # Groq failed; try local?
    if settings.llm_provider != "local":
        try:
            local_provider = get_ai_provider("local")
            result = local_provider.generate_crm_config(prompt)
        except:
            return error_response(...)
    else:
        return error_response(...)
```

---

## 9. Performance Characteristics

### Latency by Provider

| Operation | Groq | Ollama | Laya |
|-----------|------|--------|------|
| Intent classification | — | — | 1–5 ms |
| Entity resolution | — | — | 5–10 ms |
| Schema repair | — | — | 10–20 ms |
| CRM generation | 1–2 s | 3–5 s | — |
| Copilot chat | 0.5–1 s | 2–3 s | — |
| Evolution proposal | 1–2 s | 3–5 s | — |

**Strategy:** Use Laya first (fast deterministic) → Only call LLM if needed (slower but accurate).

### Token Usage

Groq charges based on tokens (input + output):

- **CRM generation:** ~500–2000 tokens per request (depends on prompt length and CRM complexity)
- **Copilot chat:** ~100–500 tokens per message
- **Evolution proposal:** ~1000–3000 tokens

**Cost Optimization:**
- Use Laya for simple intents (no token cost)
- Limit max_tokens in requests
- Cache frequently-generated schemas
- Use low temperature (0.2) to reduce hallucination (fewer tokens needed to fix errors)

---

## 10. How Tool Calling Works (Bonus)

### What is Function Calling?

When the LLM needs to execute an action (not just generate text), it returns a **tool call** instead of plain text.

### Example: Copilot "Create Lead"

```python
# Backend sends function definitions to Groq
tools = [
    {
        "type": "function",
        "function": {
            "name": "create_record",
            "description": "Create a new record in the CRM",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_name": {"type": "string"},
                    "data": {"type": "object"}
                },
                "required": ["entity_name", "data"]
            }
        }
    },
    # ... more tools
]

# User message
messages = [
    {"role": "system", "content": "You are a CRM assistant..."},
    {"role": "user", "content": "Create a new lead named Alice Smith"}
]

# Request to Groq WITH tools
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=messages,
    tools=tools,  # ← Pass function definitions
    tool_choice="auto"  # ← Let model decide when to use tools
)
```

### Groq Responds with Tool Call

```python
# Instead of plain text, Groq returns:
response.choices[0].message.tool_calls = [
    {
        "id": "call_abc123",
        "type": "function",
        "function": {
            "name": "create_record",
            "arguments": '{"entity_name": "lead", "data": {"name": "Alice Smith"}}'
        }
    }
]
```

### Backend Executes Tool

```python
# Parse tool call
tool_call = response.choices[0].message.tool_calls[0]
tool_name = tool_call.function.name
arguments = json.loads(tool_call.function.arguments)

# Validate
if tool_name not in ALLOWED_TOOLS:
    return error_response("Tool not allowed")

# Execute
if tool_name == "create_record":
    result = CRMSchemaTools.create_record(
        entity_name=arguments["entity_name"],
        data=arguments["data"]
    )

# Return tool result
return {"success": True, "record": result}
```

---

## 11. Architecture Diagram: Data & Secrets Flow

```
┌──────────────────────────────────────────────────────────────┐
│                      Frontend (React)                        │
│                  (No secrets, no API keys)                   │
│                                                              │
│  User Input → API Request → Display Response                │
│  (No credentials sent)                                       │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           │ JWT Token
                           │ (for authentication)
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                    FastAPI Backend                           │
│          (Handles all secrets server-side)                   │
│                                                              │
│  ┌─────────────────────────────────────────────┐            │
│  │  Endpoint (e.g., chat())                    │            │
│  │  - Verify JWT                               │            │
│  │  - Get settings (includes groq_api_key)     │            │
│  │  - Create provider                          │            │
│  └────────────────┬─────────────────────────────┘            │
│                   │                                          │
│  ┌────────────────▼─────────────────────────────┐            │
│  │  GroqProvider (or OllamaProvider)            │            │
│  │  - Read settings.groq_api_key               │            │
│  │  - Initialize Groq SDK client               │            │
│  │  - Build request                            │            │
│  │  - Call LLM (API key in header)             │            │
│  │  - Parse response                           │            │
│  │  - Validate & sanitize                      │            │
│  │  - Return safe response                     │            │
│  └────────────┬──────────────────────────────────┘            │
│               │                                              │
│  ┌────────────▼────────────────────────────────┐            │
│  │  Laya System1 (if needed)                   │            │
│  │  - Repair schema                            │            │
│  │  - Validate structure                       │            │
│  │  - No API key involved                      │            │
│  └───────────┬─────────────────────────────────┘            │
│              │                                              │
│  ┌───────────▼──────────────────────────────────┐           │
│  │  Response Preparation                        │           │
│  │  - Remove secrets                            │           │
│  │  - Sanitize errors                           │           │
│  │  - Add metadata                              │           │
│  └───────────┬──────────────────────────────────┘           │
│              │                                              │
└──────────────┼──────────────────────────────────────────────┘
               │
               │ JSON response (no secrets)
               │
┌──────────────▼──────────────────────────────────────────────┐
│                    Frontend (React)                         │
│            Receives & displays response safely              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  External LLM Services                      │
│        (Only backend can communicate; frontend cannot)     │
│                                                             │
│  ┌──────────────────┐            ┌──────────────────────┐ │
│  │  Groq API        │            │  Ollama Local        │ │
│  │  https://...     │            │  http://localhost... │ │
│  │  (SaaS)          │            │  (Local Container)   │ │
│  └──────────────────┘            └──────────────────────┘ │
│                                                             │
│  Only backend has credentials to reach these               │
└─────────────────────────────────────────────────────────────┘
```

---

## Summary: How It All Fits Together

1. **User submits request** → Frontend sends to backend (with JWT, no API key)
2. **Backend receives request** → Loads secrets from environment (never hardcoded)
3. **Backend decides provider** → Check settings.llm_provider (groq, local, or mock)
4. **Provider initializes** → Creates client with API key (from environment)
5. **Provider builds request** → Laya (if simple) or LLM (if complex)
6. **Request sent to LLM** → Groq API (external) or Ollama (local)
7. **LLM responds** → Returns generated content (CRM schema, tool call, etc.)
8. **Response validated** → Laya repairs any errors, Pydantic validates
9. **Secrets removed** → No API keys, no raw errors in response
10. **Response sent to frontend** → Frontend displays safely

**Key Principle:** Secrets never leave the backend; frontend only knows about data and provider status, not credentials.

---

**End of AI Models Explanation**


---

## 6. Laya System 1: The Deterministic Classifier (Your Speed Secret)

**What it is:** NOT a machine learning model. A rule-based, deterministic classifier using regex patterns and logic.  
**Speed:** 1–50 milliseconds (100x faster than LLMs)  
**Cost:** $0 per request (no API calls)  
**Purpose:** Make fast decisions before escalating to Ollama/Groq  
**Status:** ✅ **Always active** (used by every Copilot request)

### What Laya Actually Is

Laya is a **fast, deterministic decision engine** that routes user requests:
- **Simple requests** → Handled locally by Laya (instant)
- **Complex requests** → Escalated to Ollama/Groq (1–5 seconds)

**Key difference from LLMs:**
```
OLLAMA/GROQ:                    LAYA:
Neural network inference        Rule-based logic
Random (probabilistic)          Deterministic (same input → same output)
Slow (1–5 seconds)             Fast (1–50 milliseconds)
Cost: ~$0.002 per request      Cost: $0
Black box (explain hard)        Transparent (see exact rules)
```

### The 8 Intent Categories Laya Recognizes

Laya classifies every user message into ONE of these categories:

```python
class IntentCategory(str, Enum):
    CREATE_RECORD                   # "Add a new lead"
    UPDATE_RECORD                   # "Mark as negotiating"
    DELETE_RECORD                   # "Remove this record"
    ANALYTICS_QUERY                 # "How many in stage X?"
    RECORD_QUERY                    # "Show me all leads"
    SCHEMA_QUERY                    # "What fields do I have?"
    CRM_CONFIGURATION_CHANGE        # "Add a priority field"
    GENERAL_QUESTION                # "How does this work?"
```

### How Laya Classifies Requests (Using Regex Patterns)

Laya uses **regular expressions** to detect user intent—not AI:

#### Example 1: CREATE_RECORD Detection

```python
# User says: "Create a new lead named Alice"

# Laya's pattern:
create_pattern = r"^(please\s+)?(i\s+need\s+to\s+|i\s+want\s+to\s+|can\s+you\s+)?(add|create|insert|make)\s+"

# Check:
if re.search(create_pattern, "create a new lead"):
    return IntentCategory.CREATE_RECORD  ✓
```

#### Example 2: ANALYTICS_QUERY Detection

```python
# User says: "How many leads are in negotiation?"

# Laya's patterns:
analytics_patterns = [
    r"\bhow\s+many\b",              # "how many" ✓
    r"\bcount\b",
    r"\btotal\b",
    r"\b(average|sum|max|min)\b",
]

# Check:
if any(re.search(p, "how many leads in negotiation") for p in analytics_patterns):
    return IntentCategory.ANALYTICS_QUERY  ✓
```

#### Example 3: SCHEMA_QUERY Detection

```python
# User says: "What fields do I have?"

# Laya's patterns:
schema_patterns = [
    r"\b(what|which|list|show|view)\b.*\b(fields?|columns?)\b",
]

# Check:
if re.search(r"\b(what|which|list|show|view)\b.*\b(fields?|columns?)\b", 
             "what fields do i have"):
    return IntentCategory.SCHEMA_QUERY  ✓
```

### Classification Flowchart

```
User Message
    │
    ├─→ Check: "add|create|insert|make"? 
    │   Yes? → CREATE_RECORD
    │
    ├─→ Check: "how many|count|total|avg"?
    │   Yes? → ANALYTICS_QUERY
    │
    ├─→ Check: "what|show|list" + "fields|stages|schema"?
    │   Yes? → SCHEMA_QUERY
    │
    ├─→ Check: "show|list|view|find" + "records|leads|customers"?
    │   Yes? → RECORD_QUERY
    │
    ├─→ Check: "update|change|mark|modify"?
    │   Yes? → UPDATE_RECORD
    │
    ├─→ Check: "delete|remove|drop" + "record"?
    │   Yes? → DELETE_RECORD
    │
    ├─→ Check: "add|delete" + "field|stage|column"?
    │   Yes? → CRM_CONFIGURATION_CHANGE
    │
    └─→ No match? → GENERAL_QUESTION (default)
```

### Code Location

**File:** `backend/app/services/intent_classifier.py`

```python
class IntentClassifier:
    """High-precision, schema-aware intent classifier for AURA Copilot."""
    
    @classmethod
    def classify(
        cls,
        message: str,
        conversation_history: list[dict] | None = None,
        crm_context: dict[str, Any] | None = None,
    ) -> IntentCategory:
        """Classify user message using regex patterns."""
        
        q = message.lower()
        
        # Check each intent in order
        if re.search(r"\b(add|create)\s+(a\s+|new\s+)?(field|column|stage)\b", q):
            return IntentCategory.CRM_CONFIGURATION_CHANGE
        
        if re.search(r"^(create|add|insert|make)\s+", q):
            return IntentCategory.CREATE_RECORD
        
        if any(re.search(p, q) for p in [r"\bhow\s+many\b", r"\bcount\b"]):
            return IntentCategory.ANALYTICS_QUERY
        
        # ... more patterns ...
        
        return IntentCategory.GENERAL_QUESTION
```

---

### Laya's Second Function: Input Normalization

Beyond classification, Laya also **normalizes messy user input** into safe machine identifiers.

#### The Problem

Users provide inconsistent field names:
```
User input: "Client Budget Size!", "Deal Stage**", "Email (Primary)"
Raw data: ["Client Budget Size!", "Deal Stage**", "Email (Primary)"]
```

#### Laya's Normalization Process

```python
class LayaSystem1:
    @classmethod
    def _normalize_user_input(
        cls,
        raw_strings: list[str],
        fallback_prefix: str = "field",
    ) -> dict[str, NormalizedInput]:
        """Convert messy user input to safe machine identifiers."""
        
        for raw in raw_strings:
            # Step 1: Strip special characters
            cleaned = re.sub(r"[^a-zA-Z0-9_\s-]+", "", raw)
            # Result: "Client Budget Size"
            
            # Step 2: Convert to lowercase, replace spaces with underscores
            cleaned = cleaned.lower().replace(" ", "_")
            # Result: "client_budget_size"
            
            # Step 3: Validate identifier format (must start with letter)
            if not cleaned[0].isalpha():
                cleaned = f"{fallback_prefix}_{cleaned}"
            
            # Step 4: Check against RESERVED_FIELDS
            if cleaned in RESERVED_FIELDS:  # {id, crm_id, created_at, ...}
                cleaned = f"custom_{cleaned}"
            
            # Step 5: Build bidirectional mapping
            result[cleaned] = NormalizedInput(
                machine_key="client_budget_size",    # For database
                human_label="Client Budget Size",    # For UI
                original_raw="Client Budget Size!"   # For audit
            )
```

#### Result: Clean Mapping

```
Raw Input              → Machine Key              → Human Label
─────────────────────    ─────────────────────      ──────────────
Client Budget Size!   → client_budget_size       → Client Budget Size
Deal Stage**          → deal_stage               → Deal Stage
Email (Primary)       → email_primary            → Email Primary
2024-Revenue          → revenue_2024             → Revenue 2024
```

### Laya's Third Function: Schema Repair

When Ollama generates a CRM schema, it might have errors. Laya fixes them:

#### Problems Laya Detects & Fixes

```python
# Problem 1: Capitalized entity name
{"name": "Lead"}  →  {"name": "lead"}  ✓

# Problem 2: Invalid field type
{"type": "string"}  →  {"type": "text"}  ✓

# Problem 3: Reserved field name
{"name": "created"}  →  {"name": "custom_created"}  ✓

# Problem 4: Duplicate field names
[{"name": "status"}, {"name": "status"}]  →  [{"name": "status"}, {"name": "status_1"}]  ✓

# Problem 5: Empty select options
{"type": "select", "options": []}  →  {"type": "select", "options": ["Option 1", "Option 2"]}  ✓
```

**Code Location:** `backend/app/services/laya_system1.py::repair_crm_configuration()`

---

### When Laya is Used vs. When Ollama is Used

```
User Request
    │
    ▼
LAYA CLASSIFICATION (1-10ms)
    │
    ├─ CREATE/UPDATE/DELETE/QUERY?
    │  Yes → Can Laya handle alone?
    │      ├─ Yes → EXECUTE IMMEDIATELY (no Ollama needed)
    │      │   ├─ get_crm_summary()
    │      │   ├─ query_records()
    │      │   ├─ get_status_distribution()
    │      │   └─ TOTAL TIME: 20-50ms ⚡
    │      │
    │      └─ No → Need reasoning/generation
    │          └─ ESCALATE TO OLLAMA (1-5 seconds)
    │
    └─ Not classifiable?
       → ESCALATE TO OLLAMA for understanding
```

### Real-World Impact

#### Cost Savings

```
Without Laya (all requests go to Ollama):
- 100 requests/day × 365 days = 36,500 requests/year
- ~50% are simple queries = 18,250 Ollama calls
- Local cost: $0 (Ollama is free)
- But: Slow response time (1-5s per query)

With Laya (simple queries bypass Ollama):
- 100 requests/day × 365 days = 36,500 requests/year
- 80% are simple (handled by Laya) = 29,200 Laya calls
- 20% complex (Ollama) = 7,300 Ollama calls
- Local cost: $0 (no change)
- Benefit: 80% of queries now 1-50ms (100x faster!)
```

#### Performance Improvement

```
Scenario: User says "Show me all leads"

Without Laya:
- Wait for Ollama to understand the request: 2-5 seconds ❌

With Laya:
- Detect RECORD_QUERY (20ms)
- Execute query directly (10ms)
- Total: 30ms ✓ (100x faster!)
```

---

### Decision Tree: Laya vs. Ollama

```
User: "Create a new lead named John"
    │
    ▼
Laya: Detect CREATE_RECORD (5ms)
    │
    ├─ Entity resolution: "lead" → entity found (5ms)
    │
    ├─ Extract fields: "John" → name field (5ms)
    │
    ├─ Build tool call JSON (5ms)
    │
    └─ Decision: No reasoning needed
       └─ EXECUTE IMMEDIATELY
           ├─ Validate tool
           ├─ Insert into database
           ├─ Return result
           └─ TOTAL TIME: 40ms ⚡ (no Ollama needed)

---

User: "Build a CRM for a recruitment agency"
    │
    ▼
Laya: Detect CRM_GENERATION (5ms)
    │
    ├─ Classification unclear → need reasoning
    │
    └─ Decision: Needs Ollama
       └─ ESCALATE TO OLLAMA
           ├─ Ollama reasons about recruitment
           ├─ Generates schema with candidates, interviews, offers
           ├─ Returns complete CRM config
           └─ TOTAL TIME: 1-5 seconds ⏱️ (Ollama reasoning needed)
```

---

### Safety Guardrails in Laya

Laya also prevents dangerous patterns:

```python
# Detect SQL injection attempts
SQL_INJECTION_PATTERN = re.compile(
    r"\b(UNION\s+SELECT|DROP\s+TABLE|DELETE\s+FROM)\b",
    re.IGNORECASE,
)

# Detect code execution attempts
CODE_EXEC_PATTERN = re.compile(
    r"\b(import\s+os|subprocess|eval\(|exec\()\b",
    re.IGNORECASE,
)

# If either detected → REJECT REQUEST
if SQL_INJECTION_PATTERN.search(user_input):
    return error_response("Invalid request")
```

---

### Summary: Why Laya is the Secret Sauce

| Aspect | Laya | Ollama/Groq |
|--------|------|---|
| **Technology** | Regex + Python logic | Neural network |
| **Speed** | 1–50 ms | 1–5 seconds |
| **Cost** | $0 | Free (Ollama) or $0.002 (Groq) |
| **Deterministic?** | ✓ Yes (same input = same output) | ✗ No (slightly random) |
| **Explainable?** | ✓ Yes (see exact patterns) | ✗ Black box |
| **Offline?** | ✓ Yes | ✓ Yes (Ollama) or ✗ No (Groq) |
| **Best for** | Intent, normalization, validation | Generation, reasoning, conversation |

**Result:** AURA responds instantly for routine requests (Laya), and intelligently for complex ones (Ollama). Best of both worlds.

