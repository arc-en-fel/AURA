# AURA Workflow and Architecture Document

**Purpose:** Visualization and explanation of AURA's user journey, system architecture, and AI decision trees.

---

## 1. User Journey: From Sign-Up to Copilot-Assisted Operations

### High-Level Flow

```mermaid
graph LR
    A["User Sign-Up<br/>(Supabase Auth)"] --> B["Login<br/>JWT Token"]
    B --> C["Dashboard"]
    C --> D{"Action?"}
    D -->|"Build New CRM"| E["CRM Generation Chat"]
    D -->|"Manage Existing CRM"| F["Select CRM from List"]
    E --> G["AI Generates Schema"]
    G --> H["Review & Save Config"]
    H --> I["CRM Saved"]
    F --> I
    I --> J["Records Page"]
    J --> K{"User Action?"}
    K -->|"Create/Update Records"| L["Copilot Tool Calling"]
    K -->|"Query Analytics"| M["Copilot Analytics Query"]
    K -->|"CSV Import"| N["Bulk Upload"]
    L --> O["Copilot: Generate Tool Call"]
    O --> P["Backend: Validate & Execute"]
    P --> Q["Update Records"]
    M --> R["Analytics Query & Visualization"]
    N --> S["Smart Status Mapping"]
    S --> Q
    Q --> T["User Sees Results"]
```

### Detailed: CRM Generation (Steps 1-5)

```mermaid
sequenceDiagram
    participant User as User<br/>(Browser)
    participant Frontend as Frontend<br/>(React)
    participant Backend as Backend<br/>(FastAPI)
    participant Groq as Groq<br/>(LLM)
    participant Supabase as Supabase<br/>(PostgreSQL)

    User->>Frontend: Click "Build New CRM"
    Frontend->>Frontend: Navigate to /chat-crm
    User->>Frontend: Type: "Sales CRM for my team"
    Frontend->>Backend: POST /api/v1/crm/chat<br/>(message, history)
    Backend->>Groq: Chat: Next question?
    Groq-->>Backend: "What stages in your pipeline?"
    Backend-->>Frontend: Reply
    Frontend->>User: Show question
    User->>Frontend: Answer: "Prospecting, Qualification, etc."
    Frontend->>Backend: POST /api/v1/crm/chat<br/>(generate_now=true)
    Backend->>Groq: Generate CRM config from conversation
    Groq-->>Backend: {"entities": [...], "fields": [...]}
    Backend->>Backend: Validate config (Pydantic)
    Backend->>Backend: Repair/sanitize names
    Backend-->>Frontend: {"configuration": {...}, "ready": true}
    Frontend->>User: Show draft CRM schema
    User->>Frontend: Click "Save & Activate"
    Frontend->>Backend: POST /api/v1/crm<br/>(config, auth: JWT)
    Backend->>Backend: Verify ownership (auth.uid)
    Backend->>Supabase: INSERT INTO crms<br/>(owner_id=auth.uid, config=...)
    Supabase-->>Backend: Success (crm_id)
    Backend-->>Frontend: CRM saved
    Frontend->>User: "CRM ready! Manage records at /records"
```

### Detailed: Copilot Record Creation (Steps 6-7a)

```mermaid
sequenceDiagram
    participant User as User
    participant Frontend as Frontend
    participant Backend as Backend
    participant Supabase as Supabase
    participant Laya as Laya<br/>(Classifier)
    participant Groq as Groq<br/>(LLM)

    User->>Frontend: Open Copilot<br/>Type: "Create lead Alice Smith"
    Frontend->>Backend: POST /api/v1/copilot/chat<br/>(message, crm_context)
    Backend->>Laya: Classify intent
    Laya-->>Backend: CREATE_RECORD
    Backend->>Laya: Resolve entity: "lead"
    Laya-->>Backend: entity_id, label
    Backend->>Backend: Generate tool call JSON
    Backend-->>Frontend: {"reply": "...", "tool_call": {...}}
    Frontend->>User: Show: "Create lead Alice Smith?"
    User->>Frontend: Click Confirm
    Frontend->>Backend: POST /api/v1/copilot/execute-tool<br/>(tool_call)
    Backend->>Backend: Parse & validate tool call
    Backend->>Backend: Check: entity exists, fields valid
    Backend->>Supabase: INSERT INTO records<br/>(crm_id, entity_name, data={...})
    Supabase-->>Backend: Success (record_id)
    Backend-->>Frontend: {"success": true, "record": {...}}
    Frontend->>User: "Record created!"
    Frontend->>Frontend: Refresh records table
    User->>User: See new lead in list
```

### Detailed: Copilot Analytics Query (Steps 7b)

```mermaid
sequenceDiagram
    participant User as User
    participant Frontend as Frontend
    participant Backend as Backend
    participant Laya as Laya
    participant Supabase as Supabase

    User->>Frontend: Copilot: "How many deals in negotiation?"
    Frontend->>Backend: POST /api/v1/copilot/chat<br/>(message, crm_context)
    Backend->>Laya: Classify intent
    Laya-->>Backend: ANALYTICS_QUERY
    Backend->>Laya: Resolve entity: "deal"
    Laya-->>Backend: entity_id
    Backend->>Backend: Parse stage: "negotiation"
    Backend->>Supabase: SELECT COUNT(*) FROM records<br/>WHERE entity_name='deal'<br/>AND data->>'stage'='Negotiation'
    Supabase-->>Backend: count=8
    Backend-->>Frontend: {"reply": "You have 8 deals...", "count": 8}
    Frontend->>User: Show result
```

### Detailed: Evolution Proposal Lifecycle (Steps 8)

```mermaid
sequenceDiagram
    participant Background as Background Service
    participant Backend as Backend
    participant Groq as Groq
    participant Supabase as Supabase
    participant User as User
    participant Frontend as Frontend

    Background->>Backend: Trigger: analyze CRM usage
    Backend->>Supabase: Fetch CRM config + record stats
    Supabase-->>Backend: {"records": 150, "entities": 2, ...}
    Backend->>Groq: Generate improvement proposal
    Groq-->>Backend: "Add priority field to leads"
    Backend->>Backend: Validate proposal structure
    Backend->>Supabase: INSERT evolution_proposals<br/>(status='pending', proposed_change={...})
    Supabase-->>Backend: proposal_id
    
    Frontend->>Backend: GET /api/v1/crm/{id}/proposals
    Backend->>Supabase: SELECT * FROM evolution_proposals<br/>WHERE status IN ('pending', 'approved')
    Supabase-->>Backend: [proposal]
    Backend-->>Frontend: proposals_list
    Frontend->>User: Show: "Pending proposal: Add priority field"
    
    User->>Frontend: Click "Approve"
    Frontend->>Backend: PUT /api/v1/crm/{id}/proposals/{pid}/approve
    Backend->>Supabase: CALL approve_evolution_proposal(pid)
    Supabase->>Supabase: Check: owned, pending, not stale
    Supabase->>Supabase: UPDATE proposals<br/>SET status='approved'
    Supabase-->>Backend: "approved"
    Backend-->>Frontend: Success
    Frontend->>User: "Approved! Ready to apply."
    
    User->>Frontend: Click "Apply"
    Frontend->>Backend: PUT /api/v1/crm/{id}/proposals/{pid}/apply
    Backend->>Supabase: CALL apply_evolution_proposal(pid)
    Supabase->>Supabase: Lock proposal & CRM rows
    Supabase->>Supabase: Check: approved, version matches
    Supabase->>Supabase: Atomic transaction:<br/>1. UPDATE CRM config<br/>2. Increment version<br/>3. UPDATE proposal SET applied<br/>4. INSERT audit_log
    Supabase-->>Backend: "applied"
    Backend-->>Frontend: Success
    Frontend->>User: "Applied! Field added to leads."
```

---

## 2. System Architecture

### High-Level Component Diagram

```mermaid
graph TB
    subgraph "Client (Browser)"
        React["React 18 App<br/>(TypeScript)"]
        Router["React Router<br/>(Navigation)"]
        Auth["Auth Context<br/>(JWT Session)"]
        CRMCtx["CRM Context<br/>(Active CRM)"]
        React --> Router
        React --> Auth
        React --> CRMCtx
    end

    subgraph "Frontend Services"
        API["API Client<br/>(Supabase + FastAPI)"]
        Colors["Color Assignment<br/>(Dynamic Palettes)"]
        CSV["CSV Resolver<br/>(Smart Mapping)"]
    end

    subgraph "FastAPI Backend (Port 8000)"
        Main["FastAPI App<br/>(main.py)"]
        Auth_BE["Auth Middleware<br/>(JWT Verification)"]
        Routers["API Routers"]
        Services["Business Logic"]
        Validation["Input Validation<br/>(Pydantic)"]
        
        Main --> Auth_BE
        Main --> Routers
        Auth_BE --> Validation
        Routers --> Services
        
        subgraph "Routers (REST API)"
            CRM_R["CRM Router<br/>(/crm)"]
            Records_R["Records Router<br/>(/records)"]
            Chat_R["Chat Router<br/>(/crm/chat)"]
            Copilot_R["Copilot Router<br/>(/copilot)"]
            Evolution_R["Evolution Router<br/>(/evolution)"]
            Workflows_R["Workflows Router<br/>(/workflows)"]
        end

        subgraph "Services (Business Logic)"
            Laya["Laya System1<br/>(Deterministic)"]
            Intent["Intent Classifier<br/>(Rule-based)"]
            CRMEditor["CRM Editor<br/>(Schema Mutations)"]
            Tools["CRM Schema Tools<br/>(CRUD Operations)"]
            CSVRes["CSV Resolver<br/>(Smart Mapping)"]
            AIProvider["AI Provider Factory<br/>(Groq/Ollama)"]
            GroqProv["Groq Provider<br/>(Production LLM)"]
            OllamaProv["Ollama Provider<br/>(Fallback LLM)"]
        end

        Routers --> Laya
        Routers --> Intent
        Routers --> CRMEditor
        Routers --> Tools
        Routers --> CSVRes
        Routers --> AIProvider
        AIProvider --> GroqProv
        AIProvider --> OllamaProv
    end

    subgraph "Supabase (PostgreSQL + Auth)"
        GoTrue["Supabase Auth<br/>(GoTrue, JWT)"]
        DB["PostgreSQL Database"]
        RLS["Row-Level Security<br/>(Authorization)"]
        
        subgraph "Database Tables"
            Crms_T["crms<br/>(metadata, config)"]
            Records_T["records<br/>(JSONB data)"]
            Workflows_T["workflows<br/>(automation)"]
            Proposals_T["evolution_proposals<br/>(suggestions)"]
            Audit_T["audit_logs<br/>(immutable trail)"]
        end
        
        DB --> Crms_T
        DB --> Records_T
        DB --> Workflows_T
        DB --> Proposals_T
        DB --> Audit_T
        DB --> RLS
    end

    subgraph "External LLM Services"
        GroqAPI["Groq API<br/>(llama-3.3-70b)"]
        OllamaLocal["Ollama Local<br/>(qwen2.5:3b)"]
    end

    React --> API
    React --> Colors
    React --> CSV
    
    API --> Main
    
    GroqProv --> GroqAPI
    OllamaProv --> OllamaLocal
    
    Main --> GoTrue
    Main --> DB
    RLS --> Crms_T
    RLS --> Records_T
    RLS --> Workflows_T
    RLS --> Proposals_T

    style React fill:#0ea5e9
    style Main fill:#34d399
    style DB fill:#f59e0b
    style GroqAPI fill:#c084fc
    style OllamaLocal fill:#34d399
```

### Data Flow: Request to Database

```mermaid
graph LR
    A["User Request<br/>(React Component)"] 
    --> B["API Client<br/>(Supabase JS or HTTP)"]
    --> C["FastAPI Endpoint<br/>(JWT Verified)"]
    --> D["Authorization Check<br/>(CRM Ownership)"]
    --> E["Business Logic Service<br/>(Laya, Tools, etc.)"]
    --> F["Parameterized Query<br/>(No SQL Injection)"]
    --> G["Supabase Client<br/>(JWT Context)"]
    --> H["PostgreSQL<br/>RLS Policy Applied"]
    --> I["Query Result<br/>(Filtered by auth.uid)"]
    --> J["Response<br/>(Cleaned, No Secrets)"]
    --> K["Frontend State Update<br/>(React)"]
    --> L["User Sees Result<br/>(UI)"]
    
    style A fill:#0ea5e9
    style H fill:#f59e0b
    style K fill:#0ea5e9
```

### Component Responsibilities

| Component | Responsibility | Technology |
|-----------|----------------|-----------|
| **React Frontend** | User interaction, form handling, routing | React 18, TypeScript, Vite |
| **API Client** | HTTP requests to FastAPI, Supabase auth | @supabase/supabase-js, fetch |
| **FastAPI App** | HTTP routing, request/response handling, middleware | FastAPI, Uvicorn |
| **Auth Middleware** | JWT verification, user context extraction | python-jose, Supabase |
| **CRM Editor** | Schema mutations (add/delete/reorder fields/stages) | Python, JSONB manipulation |
| **Tools** | Record CRUD, entity resolution | Python, Supabase client |
| **Laya System1** | Fast, deterministic classification and repair | Python rules engine |
| **Intent Classifier** | Intent detection (ANALYTICS_QUERY, CREATE_RECORD, etc.) | Python heuristics |
| **Groq Provider** | LLM API calls for generation and reasoning | groq Python SDK |
| **Ollama Provider** | Local LLM fallback | ollama Python SDK |
| **Supabase Auth** | User authentication, JWT issuance | GoTrue (Supabase service) |
| **PostgreSQL** | Data persistence, transactions, RLS enforcement | Supabase managed |
| **RLS Policies** | Row-level authorization, multi-tenant isolation | PostgreSQL policies |

---

## 3. AI Copilot Tool-Execution Flowchart

### Two-Phase Copilot Decision Tree

```mermaid
graph TD
    A["User Message<br/>+ CRM Context"] 
    --> B["Phase 1: Intent Classification<br/>(Deterministic / Laya)"]
    
    B --> C{"Intent Type?"}
    
    C -->|"READ_ONLY"| D["ANALYTICS_QUERY,<br/>RECORD_QUERY,<br/>HELP_REQUEST"]
    C -->|"MUTATION"| E["CREATE_RECORD,<br/>UPDATE_RECORD,<br/>DELETE_RECORD,<br/>SCHEMA_MUTATION"]
    
    D --> F["Phase 2a: Resolve Entity<br/>(If Applicable)"]
    E --> F
    
    F --> G{"Ambiguous?"}
    G -->|"No"| H["Phase 2b: Build Response"]
    G -->|"Yes"| I["Ask for Clarification"]
    I --> J["Return to User"]
    
    H --> K{"Mutation<br/>Request?"}
    
    K -->|"No<br/>(Read-Only)"| L["Execute Query<br/>(Laya or Backend)"]
    K -->|"Yes<br/>(Mutation)"| M["Generate Tool Call JSON<br/>(Laya or Groq)"]
    
    L --> N["Fetch Data"]
    N --> O["Aggregate / Format"]
    O --> P["Return Answer"]
    
    M --> Q["Return Tool Call<br/>to Frontend"]
    
    P --> R["Frontend: Display Result"]
    Q --> S["Frontend: Show Confirmation<br/>Dialog"]
    
    S --> T{"User<br/>Confirms?"}
    T -->|"Cancel"| U["Discard"]
    T -->|"OK"| V["Execute Tool Call<br/>(Backend)"]
    
    V --> W["Validate Arguments"]
    W --> X{"Valid?"}
    X -->|"No"| Y["Return Error"]
    X -->|"Yes"| Z["Execute CRM Operation<br/>(INSERT/UPDATE/DELETE)"]
    
    Z --> AA["Return Result<br/>to Frontend"]
    AA --> AB["Update UI"]
    AB --> R
    
    Y --> R
    J --> R
    U --> R
    
    style A fill:#0ea5e9
    style B fill:#34d399
    style M fill:#f59e0b
    style V fill:#34d399
    style R fill:#0ea5e9
```

### Tool Allowlist & Execution

```mermaid
graph LR
    A["Tool Call<br/>Generated"]
    --> B["Allowlist Check"]
    
    B --> C{"Tool<br/>Allowed?"}
    
    C -->|"No"| D["Error:<br/>Unauthorized Tool"]
    C -->|"Yes"| E["Parse Arguments"]
    
    E --> F["Schema Validation"]
    F --> G{"Valid<br/>Args?"}
    
    G -->|"No"| H["Error:<br/>Invalid Arguments"]
    G -->|"Yes"| I{"Requires<br/>Confirmation?"}
    
    I -->|"Read-Only"| J["Execute Immediately"]
    I -->|"Mutation"| K["Show User Confirmation"]
    
    K --> L{"User<br/>Approves?"}
    L -->|"No"| M["Cancel"]
    L -->|"Yes"| J
    
    J --> N["Call Tool Function<br/>(CRMSchemaTools)"]
    N --> O["Database Operation<br/>(INSERT/UPDATE/DELETE)"]
    O --> P["Return Result"]
    
    M --> P
    D --> P
    H --> P
    
    P --> Q["Response to Frontend"]
    
    style J fill:#34d399
    style O fill:#f59e0b
    style Q fill:#0ea5e9
```

---

## 4. Evolution Proposal: Approval to Application

### Two-Stage Workflow

```mermaid
graph LR
    A["Proposal<br/>Generated"]
    --> B["Status: pending"]
    
    B --> C["User Reviews"]
    C --> D{"Decision?"}
    
    D -->|"Reject"| E["DELETE Proposal<br/>or Mark Rejected"]
    D -->|"Approve"| F["Stage 1:<br/>APPROVE"]
    
    F --> G["RPC:<br/>approve_evolution_proposal"]
    G --> H["Check Authorization<br/>(Owner?)"]
    H --> I{"Owner?"}
    
    I -->|"No"| J["Error:<br/>Not Owner"]
    I -->|"Yes"| K["Check Status<br/>(pending?)"]
    
    K --> L{"Pending?"}
    L -->|"No"| M["Error:<br/>Not Pending"]
    L -->|"Yes"| N["Check Staleness<br/>(version match?)"]
    
    N --> O{"Not Stale?"}
    O -->|"Stale"| P["Mark Stale<br/>Return stale"]
    O -->|"Current"| Q["UPDATE Status<br/>pending → approved"]
    
    Q --> R["INSERT Audit Log<br/>(approval)"]
    R --> S["Return: approved"]
    
    S --> T["Status: approved"]
    
    T --> U["User Reads:<br/>Ready to apply?"]
    U --> V{"Apply?"}
    
    V -->|"No"| W["Leave Approved"]
    V -->|"Yes"| X["Stage 2:<br/>APPLY"]
    
    X --> Y["RPC:<br/>apply_evolution_proposal"]
    Y --> Z["Lock Proposal & CRM Rows"]
    Z --> AA["Check Authorization"]
    AA --> AB["Check Status<br/>(approved?)"]
    AB --> AC["Check Staleness"]
    
    AC --> AD{"All Checks<br/>Pass?"}
    AD -->|"No"| AE["Rollback<br/>Return Error"]
    AD -->|"Yes"| AF["Execute Allowlisted Change<br/>(Atomic)"]
    
    AF --> AG["1. UPDATE CRM Config"]
    AG --> AH["2. Increment Version"]
    AH --> AI["3. UPDATE Proposal<br/>approved → applied"]
    AI --> AJ["4. INSERT Audit Log<br/>(application)"]
    AJ --> AK["COMMIT Transaction"]
    
    AK --> AL["Status: applied"]
    
    E --> AM["End: Rejected"]
    J --> AM
    M --> AM
    P --> AM
    AE --> AM
    W --> AM
    AL --> AN["End: Applied"]
    
    style F fill:#fbbf24
    style X fill:#f59e0b
    style AF fill:#34d399
    style AN fill:#10b981
    style AM fill:#ef4444
```

---

## 5. Database Schema Relationships

```mermaid
erDiagram
    USERS ||--o{ CRMS : "owns"
    USERS ||--o{ RECORDS : "creates"
    USERS ||--o{ EVOLUTION_PROPOSALS : "approves_or_applies"
    USERS ||--o{ AUDIT_LOGS : "performs_action"
    
    CRMS ||--o{ RECORDS : "contains"
    CRMS ||--o{ WORKFLOWS : "defines"
    CRMS ||--o{ EVOLUTION_PROPOSALS : "receives_proposals"
    CRMS ||--o{ AUDIT_LOGS : "action_targets"
    
    RECORDS ||--o{ AUDIT_LOGS : "tracked_by"
    EVOLUTION_PROPOSALS ||--o{ AUDIT_LOGS : "tracked_by"
    
    USERS {
        uuid id PK
        string email
        string encrypted_password
    }
    
    CRMS {
        uuid id PK
        uuid owner_id FK
        string name
        jsonb configuration
        int configuration_version
        text status
        timestamptz created_at
        timestamptz updated_at
    }
    
    RECORDS {
        uuid id PK
        uuid crm_id FK
        string entity_name
        jsonb data
        string source
        uuid owner_id FK
        timestamptz created_at
        timestamptz updated_at
        timestamptz deleted_at
    }
    
    WORKFLOWS {
        uuid id PK
        uuid crm_id FK
        string name
        jsonb trigger
        jsonb actions
        text status
    }
    
    EVOLUTION_PROPOSALS {
        uuid id PK
        uuid crm_id FK
        text status
        string summary
        jsonb proposed_change
        int configuration_version_at_creation
        timestamptz approved_at
        uuid approved_by FK
        timestamptz applied_at
        uuid applied_by FK
    }
    
    AUDIT_LOGS {
        uuid id PK
        uuid crm_id FK
        uuid user_id FK
        string action
        string entity_type
        uuid entity_id FK
        jsonb old_values
        jsonb new_values
        timestamptz created_at
    }
```

---

## 6. Security Architecture

### Authentication & Authorization Flow

```mermaid
graph TD
    A["User Visits<br/>Frontend"]
    --> B["Supabase Auth Check"]
    B --> C{"JWT Token<br/>Valid?"}
    
    C -->|"No"| D["Redirect to Login"]
    D --> E["User Logs In"]
    E --> F["Supabase GoTrue<br/>Issues JWT"]
    
    C -->|"Yes"| G["Frontend Stores JWT"]
    F --> G
    
    G --> H["User Navigates"]
    H --> I["Include JWT in API Request<br/>Authorization: Bearer ..."]
    
    I --> J["FastAPI Receives Request"]
    J --> K["CurrentUser Dependency"]
    K --> L["Extract sub from JWT"]
    L --> M["Call Supabase API<br/>with JWT Context"]
    
    M --> N["Supabase Auth Verifies JWT"]
    N --> O["Sets auth.uid() = sub"]
    
    O --> P["Business Logic Executes<br/>(e.g., fetch CRMs)"]
    P --> Q["Database Query<br/>SELECT * FROM crms"]
    
    Q --> R["RLS Policy Applied"]
    R --> S["WHERE owner_id = auth.uid()"]
    S --> T["Only User's CRMs<br/>Returned"]
    
    T --> U["Response Sanitized<br/>(No Secrets)"]
    U --> V["Response Sent to Frontend"]
    V --> W["User Sees Data<br/>(Their CRMs Only)"]
    
    style G fill:#10b981
    style O fill:#10b981
    style S fill:#10b981
    style W fill:#0ea5e9
```

### RLS (Row-Level Security) Enforcement

```mermaid
graph LR
    A["User Token<br/>(auth.uid = UUID-1)"]
    --> B["Query: SELECT * FROM records"]
    
    B --> C["RLS Policy Applied"]
    
    C --> D["Policy:<br/>auth.uid() IN<br/>SELECT owner_id<br/>FROM crms<br/>WHERE id = crm_id"]
    
    D --> E{"User Owns<br/>CRM?"}
    
    E -->|"No"| F["0 Rows Returned<br/>(Silent Filter)"]
    E -->|"Yes"| G["Records Returned<br/>(User Sees Data)"]
    
    F --> H["Response:<br/>Empty Array"]
    G --> H
    
    style A fill:#0ea5e9
    style C fill:#34d399
    style E fill:#f59e0b
    style H fill:#0ea5e9
```

---

## 7. LLM Integration: System 1 vs. System 2

### Decision Tree: When to Use Each System

```mermaid
graph TD
    A["Copilot Request"]
    --> B{"Simple?"}
    
    B -->|"Yes:<br/>Clear intent,<br/>known entity"| C["System 1: Laya<br/>(Fast, Rules)"]
    B -->|"No:<br/>Ambiguous,<br/>creative reasoning"| D["System 2: Groq<br/>(Slow, LLM)"]
    
    C --> E{"Classify<br/>Intent"}
    E -->|"Read-Only"| F["Execute Query"]
    E -->|"Mutation"| G["Generate Tool Call<br/>(Heuristic)"]
    
    D --> H["Call Groq API"]
    H --> I{"Task?"}
    I -->|"CRM Gen"| J["Generate Config JSON"]
    I -->|"Copilot"| K["Reason + Generate Tool"]
    I -->|"Evolution"| L["Analyze Usage +<br/>Suggest Change"]
    
    F --> M["Result"]
    G --> M
    J --> M
    K --> M
    L --> M
    
    M --> N["Response to User"]
    
    style C fill:#34d399
    style D fill:#c084fc
    style N fill:#0ea5e9
```

### Fallback Strategy

```mermaid
graph LR
    A["Request Arrives"]
    --> B["Try Groq API<br/>(Production)"]
    
    B --> C{"Groq<br/>Available?"}
    
    C -->|"Yes"| D["Use Groq<br/>Response"]
    C -->|"No"| E["Fallback: Ollama<br/>(Local Dev)"]
    
    E --> F{"Ollama<br/>Available?"}
    
    F -->|"Yes"| G["Use Ollama<br/>Response"]
    F -->|"No"| H["Fallback: Laya<br/>(Deterministic)"]
    
    H --> I{"Laya Can<br/>Handle?"}
    
    I -->|"Yes"| J["Use Laya<br/>Response"]
    I -->|"No"| K["Error:<br/>Service Unavailable"]
    
    D --> L["Response"]
    G --> L
    J --> L
    K --> L
    
    style B fill:#c084fc
    style E fill:#34d399
    style H fill:#fbbf24
    style L fill:#0ea5e9
```

---

## 8. Scaling Considerations

### Multi-Tenant Architecture

```mermaid
graph TB
    subgraph "Shared Infrastructure"
        LB["Load Balancer"]
        BE1["Backend Instance 1"]
        BE2["Backend Instance 2"]
        BE3["Backend Instance N"]
        Supabase["Supabase<br/>(Shared DB +<br/>RLS Isolation)"]
    end
    
    subgraph "Tenant A"
        User_A["User A<br/>(JWT)"]
    end
    
    subgraph "Tenant B"
        User_B["User B<br/>(JWT)"]
    end
    
    subgraph "Tenant N"
        User_N["User N<br/>(JWT)"]
    end
    
    User_A --> LB
    User_B --> LB
    User_N --> LB
    
    LB --> BE1
    LB --> BE2
    LB --> BE3
    
    BE1 --> Supabase
    BE2 --> Supabase
    BE3 --> Supabase
    
    style User_A fill:#0ea5e9
    style User_B fill:#0ea5e9
    style User_N fill:#0ea5e9
    style Supabase fill:#f59e0b
    style BE1 fill:#34d399
    style BE2 fill:#34d399
    style BE3 fill:#34d399
```

**Key Points:**
- RLS enforces isolation at database level (no app-layer complexity)
- Horizontal scaling: Add more backend instances behind load balancer
- Supabase handles connection pooling and query scaling
- All tenant data in single tables; RLS filters transparently

---

**End of Workflow and Architecture Document**
