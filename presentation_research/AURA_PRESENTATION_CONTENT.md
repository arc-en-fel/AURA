# AURA Hackathon Presentation: 10-Slide Content

**Presentation Goal:** Demonstrate AURA's differentiators, architecture, and market potential in 10-15 minutes.

**Format:** Each slide includes title, key bullets, visual suggestion, speaker notes, and evidence.

---

## Slide 1: Title Slide

**Title:** AURA: AI-Powered, Self-Evolving CRM

**Tagline:** Generate unlimited, domain-specific CRM configurations in natural language.

**Bullets:**
- From conversation to operational CRM in minutes
- No code changes required per new industry or workflow
- AI-assisted schema evolution based on usage patterns

**Suggested Visuals:**
- AURA logo or wordmark (if exists; otherwise minimal design)
- Background: Gradient (cyan → deep blue)
- Overlay: Simple icons representing key features (chat bubble, database, AI brain)

**Speaker Notes:**
We've built AURA, an AI-powered CRM platform that does something no traditional CRM does: it generates a complete, domain-specific schema from a natural-language conversation. Whether you need a CRM for sales, healthcare, recruitment, or a custom workflow, AURA adapts—without code changes. And as your business evolves, AURA suggests improvements based on how you actually use it.

**Evidence / File Paths:**
- README.md: High-level architecture overview
- AGENTS.md: Shared coding guidelines (differentiators section)

---

## Slide 2: Introduction – What is AURA?

**Title:** Introducing AURA: The Self-Configuring CRM

**Bullets:**
- Multi-tenant SaaS platform for sales, service, healthcare, recruitment, custom workflows
- AI-driven schema generation (no pre-built vertical silos)
- Real-time Copilot for assisted record management and analytics queries
- Evolutionary proposal system: observe usage, suggest improvements, user approves
- Built for teams: multi-tenant isolation, audit logging, version control

**Suggested Visuals:**
- Side-by-side comparison: Traditional CRM workflow vs. AURA workflow
  - Traditional: Select vertical → Configure fields → Deploy (weeks)
  - AURA: Describe need → Generate schema → Start using (minutes)
- Icon grid: Sales, Healthcare, Recruitment, Custom workflows (all supported)

**Speaker Notes:**
Existing CRMs force you into pre-built verticals: Salesforce for sales, TriZetto for healthcare, etc. Each vertical is a completely separate product. AURA is different. It's a single platform that dynamically generates CRM schemas to fit your specific business. You describe what you need. AURA listens, asks clarifying questions, and generates a complete configuration—fields, entity types, pipeline stages—all validated and ready to use. No code. No consultants. Just you and the AI.

**Evidence / File Paths:**
- backend/app/routers/chat.py: CRM generation endpoint
- backend/app/services/laya_system1.py: Dynamic schema generation (Phase 1 universal fix removes industry taxonomies)

---

## Slide 3: The Team & Contributions

**Title:** Team: Four-Person Technical Powerhouse

**Bullets:**
- **Member 1:** AI & CRM Generation Brain (Groq integration, Laya classifier, schema repair)
- **Member 2:** Backend, Database, Authentication (FastAPI, Supabase, RLS, multi-tenancy)
- **Member 3:** Frontend & UX (React, real-time UI, schema editor, analytics dashboard)
- **Member 4:** Data Ingestion, Workflows, Analytics & Evolution (CSV import, evolution proposals, analytics engine)

**Suggested Visuals:**
- Team member avatars or initials (if available)
- Role icons: 🧠 AI, ⚙️ Backend, 🎨 Frontend, 📊 Data

**Speaker Notes:**
The AURA team is small but specialized. Each member owns a critical piece of the platform. Member 1 handles all AI reasoning and schema generation. Member 2 built the rock-solid backend and multi-tenant database layer. Member 3 crafted the intuitive UI. And Member 4 handled the complex workflows: CSV ingestion, evolution proposals, and analytics. The result is a well-architected, fully-integrated system.

**Evidence / File Paths:**
- AGENTS.md: Team responsibilities and shared guidelines (verified from repo structure)
- Team task assignments visible in team_tasks/ directory

---

## Slide 4: Problem Statement – Why This Matters

**Title:** The CRM Problem (And Why It Matters)

**Bullets:**
- CRM setup is expensive and slow (weeks to months)
- One-size-fits-all CRMs create data silos (Sales CRM, Healthcare CRM, Recruitment CRM are separate products)
- Schema changes post-launch are risky and manual
- Most users can't express workflows in code; they need natural language
- Data isolation and compliance are critical in multi-tenant systems

**Suggested Visuals:**
- Pain point icons with red X: ❌ Slow (calendar), ❌ Expensive (💰), ❌ Fragmented (broken link), ❌ Risky (⚠️)
- Or: Timeline showing traditional CRM deployment vs. AURA rapid deployment

**Speaker Notes:**
Let me paint a picture. You're a healthcare clinic. You want to manage patients, appointments, and care tracks. You look at Salesforce—built for sales. You look at TriZetto—built for healthcare but expensive. You look at custom development—requires months and a big budget. Meanwhile, your clinic is losing efficiency. That's the problem AURA solves. Not in weeks or months, but in minutes, and for any vertical or custom workflow you can describe.

**Evidence / File Paths:**
- README.md: "Problem AURA Solves" section
- project context in audit prompt

---

## Slide 5: Our Solution & Why It's Better

**Title:** Our Solution: AI-Driven, Domain-Agnostic Schema Generation

**Bullets:**
- **AI-Driven Generation:** Describe your needs in natural language; Groq LLM generates complete schema in seconds
- **Universal, Not Vertical:** One codebase supports unlimited CRM types without code changes (Phase 1 fix: removed all hard-coded taxonomies)
- **Post-Generation Editing:** Schema is a draft. Add/remove/rename fields after creation. Full WYSIWYG editor
- **Real Copilot Tool Calling:** Ask the AI to create records, query analytics, modify schema. It executes validated actions, not just suggestions
- **Evolutionary Proposals:** AURA observes usage patterns, suggests improvements (e.g., "add priority field"), user approves, changes applied atomically

**Suggested Visuals:**
- Feature comparison table: AURA vs. Traditional CRM
  | Feature | Traditional | AURA |
  |---------|-----------|------|
  | Setup time | 4-12 weeks | <5 minutes |
  | Schema changes | High risk | Safe + audited |
  | Vertical-specific code | Yes (per vertical) | No (all unified) |
  | AI assistance | Limited | Full Copilot |
  | Schema evolution | Manual | AI-suggested + approved |

**Speaker Notes:**
Our solution is built on three key insights. First, AI can generate accurate CRM schemas from natural language descriptions. Second, a unified, schema-agnostic data model (JSONB records) can handle any vertical without modifications. Third, users want to direct the AI rather than configure it—they want a Copilot, not a config form. The result: AURA generates sales, healthcare, or recruitment CRMs from the same codebase in minutes. Users can edit schemas post-launch safely. And the AI actively suggests improvements based on real usage data.

**Evidence / File Paths:**
- backend/app/routers/chat.py::chat(): CRM generation endpoint
- backend/app/services/laya_system1.py: Removed hard-coded taxonomies (Phase 1 universal fix)
- backend/app/routers/crm.py: Schema editing endpoints (add/delete/reorder fields/stages)
- backend/app/routers/copilot.py: Tool calling with validation
- backend/app/routers/evolution.py: Two-stage approval for proposals

---

## Slide 6: End-to-End Workflow & Copilot

**Title:** The User Journey: Minutes from Idea to Operations

**Bullets:**
- **Step 1:** Describe CRM need → AURA asks clarifying questions via chat
- **Step 2:** AI generates schema (entities, fields, pipeline stages) from conversation
- **Step 3:** Review & save generated schema
- **Step 4:** Start creating records manually or via AI Copilot
- **Step 5 (Optional):** Ask Copilot to execute actions: "Create a new lead named Alice" → Copilot generates tool call → User confirms → Record created
- **Step 6 (Continuous):** AURA observes usage and proposes schema improvements (user approves before applying)

**Suggested Visuals:**
- Flowchart or swimlane diagram (similar to workflow diagram in AURA_WORKFLOW_AND_ARCHITECTURE.md)
- Alternatively: Screenshot or mockup of chat interface → generated schema → records page → Copilot drawer

**Speaker Notes:**
Let me walk through the experience. You open AURA, click "Generate New CRM," and have a conversation: "I run a recruitment agency." AURA asks: "What stages are in your hiring pipeline?" You answer. "What info do you track about candidates?" You describe. After a few exchanges, AURA generates a complete CRM schema. You review it, make tweaks if needed, and click save. Now you're in the records page. You can create records manually, or you can open the Copilot and say, "Add a candidate named Jane with a software engineering background." Copilot generates a confirmed action, and the record is created. Over time, as you use the system, AURA suggests improvements: "You have 50 candidates in the database. Most spend 2-3 weeks in the interview stage. Would you like to add a subtype field to distinguish interview rounds?" You approve. The change is applied automatically and atomically. That's the AURA experience.

**Evidence / File Paths:**
- backend/app/routers/chat.py: Chat generation flow
- frontend/src/features/crms/ChatCRMPage.tsx: Chat UI
- backend/app/routers/copilot.py: Tool calling
- frontend/src/features/ai-assistant/AIAssistantDrawer.tsx: Copilot drawer
- backend/app/routers/evolution.py: Evolution proposal flow

---

## Slide 7: Technical Architecture & Innovation

**Title:** Architecture: AI + Multi-Tenant Database + Universal Schema

**Bullets:**
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, Recharts analytics
- **Backend:** FastAPI + Pydantic v2 (async, modern Python)
- **Database:** Supabase PostgreSQL + Row-Level Security (RLS) for multi-tenant isolation
- **AI Reasoning:** Groq API (llama-3.3-70b) for generation; Laya deterministic classifier for fast intent matching
- **Data Model:** Single `records` table with JSONB field values (no per-CRM schema creation)
- **Authorization:** JWT + RLS policies enforce owner-based access control
- **Evolution System:** Two-stage approval (approve → apply) with atomic transactions and audit logging

**Suggested Visuals:**
- System architecture diagram (backend, frontend, database, LLM services)
- Data flow: User → FastAPI → Validation → Supabase (RLS applied) → Result
- Architecture diagram showing: Frontend (React) → Backend (FastAPI) → Supabase (PostgreSQL + RLS) → Groq (LLM)

**Speaker Notes:**
Under the hood, AURA is built on proven, scalable technologies. The frontend is modern React with real-time reactivity. The backend is FastAPI—fast, async, type-safe. The database is Supabase's managed PostgreSQL with Row-Level Security policies that automatically filter data based on user ownership. This means multi-tenancy is enforced at the database level, not in application code—a critical security principle. For AI, we integrate Groq's 70B parameter model for accurate reasoning and generation. And we have a lightweight, deterministic classifier (Laya) for fast intent detection, so we're not calling the LLM for every user interaction. The data model is the key innovation: a universal, schema-agnostic table with JSONB field values. Instead of creating a new table for each CRM or entity type, we store all records in one table, with entity name and JSONB data. This allows unlimited CRM types without code changes—something traditional CRMs can't do.

**Evidence / File Paths:**
- frontend/package.json: React, TypeScript, Tailwind, Recharts versions
- backend/requirements.txt: FastAPI, Pydantic, Groq, Supabase versions
- supabase/migrations/0001_initial_crm_schema.sql: Schema design, RLS policies
- backend/app/routers/copilot.py, chat.py: API design
- backend/app/services/laya_system1.py: Deterministic classifier
- backend/app/services/groq_provider.py: Groq integration

---

## Slide 8: Technology Stack

**Title:** Tech Stack: Modern, Production-Ready, Scalable

**Bullets:**

**Frontend:**
- React 18.3 + TypeScript 5.7 for type safety
- Vite 6.1 for fast builds and HMR
- Tailwind CSS for responsive styling
- Recharts for interactive analytics visualizations

**Backend:**
- FastAPI for async, type-safe HTTP routing
- Pydantic v2 for data validation and serialization
- Groq SDK for LLM API calls
- Supabase Python client for PostgreSQL + Auth

**Database & Auth:**
- Supabase PostgreSQL (managed)
- Row-Level Security (RLS) policies for multi-tenancy
- Supabase Auth (GoTrue) for JWT-based authentication

**AI / LLM:**
- Groq API (production): llama-3.3-70b-versatile
- Ollama (fallback): qwen2.5:3b (local dev)
- Laya: Deterministic classifier (no LLM call needed)

**Suggested Visuals:**
- Technology stack icon grid or logos: React, FastAPI, PostgreSQL, Groq, Supabase, TypeScript, Tailwind
- Or: Stacked boxes showing Frontend → Backend → Database → AI services

**Speaker Notes:**
We chose each technology deliberately. React is the industry standard for interactive UIs. FastAPI provides speed and async support—critical for handling multiple AI API calls concurrently. Supabase gives us a managed database plus built-in authentication and Row-Level Security, eliminating a lot of custom authorization code. Groq provides state-of-the-art LLM reasoning at low latency, essential for the interactive CRM generation flow. And our deterministic classifier reduces LLM calls for routine tasks. The stack is modern, proven, and scalable.

**Evidence / File Paths:**
- frontend/package.json
- backend/requirements.txt
- backend/.env.example
- supabase/migrations/0001_initial_crm_schema.sql

---

## Slide 9: What's Implemented & What's Ahead

**Title:** Current Status: Phase 1 Complete, Phase 2 Planned

**Bullets:**

**✅ Phase 1: Foundation (Complete)**
- CRM generation from natural language
- Record CRUD (create, read, update, delete)
- Post-generation schema editing (fields, stages)
- Copilot with intent classification + tool calling
- Two-stage evolution proposals (approve → apply)
- CSV import with smart status mapping
- Universal analytics (all CRM types)
- Multi-tenant isolation + audit logging

**📋 Phase 2: Expansion (Planned)**
- Workflow execution engine (automate actions)
- Webhook ingestion (external system integrations)
- External API sync (Salesforce, HubSpot)
- Shared CRM access (collaborators with roles)
- Email notifications
- Advanced custom aggregations

**Suggested Visuals:**
- Checklist of Phase 1 features with green checkmarks
- Timeline or roadmap showing Phase 1 (done) → Phase 2 (Q1 2025 estimated)

**Speaker Notes:**
AURA Phase 1 is production-ready. The core platform—generation, record management, Copilot, and evolution—is complete and tested. We ran 54 regression tests to ensure everything works end-to-end. What's missing are the Phase 2 features: workflow automation, webhook ingestion from external systems, and shared CRM access. But the fundamentals are solid. For a hackathon, Phase 1 is more than enough to demonstrate the platform's power and differentiation.

**Evidence / File Paths:**
- PHASE1_COMPLETION_REPORT.md: Phase 1 completion status (54 tests passing)
- backend/tests/: Test files proving Phase 1 features work
- backend/app/services/workflows.py: Workflow data model exists (execution engine pending Phase 2)

---

## Slide 10: Conclusion – The Value Proposition

**Title:** AURA: Democratizing CRM Customization

**Bullets:**
- **For SMBs:** Build custom CRMs in minutes, not months
- **For Enterprises:** Multi-tenant SaaS deployment with built-in compliance (audit logging, RLS, data isolation)
- **For Developers:** A platform to build upon; extensible schema, tool-calling architecture, and evolution system
- **For Industries:** One codebase serves all verticals—sales, healthcare, recruitment, custom workflows
- **The Promise:** Your CRM evolves with your business, not the other way around

**Suggested Visuals:**
- Impact infographic: 10x faster setup, 100% customizable, multi-tenant secure
- Or: Quote or testimonial mockup from a hypothetical user (healthcare clinic, recruitment agency, etc.)
- Or: Vision statement: "Every business gets a custom CRM, instantly."

**Speaker Notes:**
Most CRM adoption fails because configuration is slow, expensive, and brittle. AURA solves this by putting AI at the center. You describe your needs in plain English. The AI listens, learns, and generates a CRM tailored to your business. You use it immediately. As you use it, the AI observes patterns and suggests improvements. The system evolves with you, not against you. That's the promise of AURA. It democratizes custom CRM development, making it accessible to every team, not just those with big budgets and IT departments.

**Evidence / File Paths:**
- README.md: Value proposition and use cases
- PHASE1_COMPLETION_REPORT.md: Completion milestones
- Test coverage and architecture proofs above

---

## (Optional) Slide 11: Live Demo or Implementation Proof

**Title:** Live Demo: CRM Generation in Real Time (Optional)

**Bullets:**
- Show live chat interface: "Describe your CRM need"
- User inputs: "I run a recruitment agency"
- AURA asks clarifying questions
- User responds; AURA generates schema
- Show generated entities, fields, stages
- Create a record via Copilot: "Add a candidate"
- Show record creation confirmation and list update
- (Stretch) Show evolution proposal: "Suggestion based on your data..."

**Suggested Visuals:**
- Screen recording or live demo of the AURA interface
- Or: Series of annotated screenshots showing each step

**Speaker Notes:**
(Only if doing live or recorded demo) Here's AURA in action. I'll describe a recruitment workflow. AURA responds with follow-up questions. After I answer, it generates a complete CRM schema in seconds. Now I have fields for candidates, interviews, offers—all configured correctly. I can immediately start creating records. Let me ask the Copilot to add a candidate. The AI generates a tool call, I confirm, and the record is created. The entire workflow from idea to operational CRM took less than two minutes. That's the AURA promise.

**Evidence / File Paths:**
- Live deployment (if available) or frontend screenshots
- Test recordings or mockups

---

## Slide Sequencing Recommendations

**Timing (15-minute target):**
- Slide 1 (Title): 30 seconds (intro + thank you)
- Slide 2 (Intro): 1 minute (context)
- Slide 3 (Team): 1 minute (credibility)
- Slide 4 (Problem): 1.5 minutes (pain points)
- Slide 5 (Solution): 2 minutes (key differentiators)
- Slide 6 (Workflow): 2 minutes (user journey)
- Slide 7 (Architecture): 2 minutes (technical depth)
- Slide 8 (Tech Stack): 1 minute (credibility + scalability)
- Slide 9 (Status): 1.5 minutes (what's done, what's next)
- Slide 10 (Conclusion): 1.5 minutes (vision + closing)
- **Total:** ~15 minutes (with Q&A buffer)

**If Time is Limited (10 minutes):**
- Combine Slides 2-3 (Intro + Team)
- Skip Slide 8 (Tech Stack)
- Reduce Slide 7 (Architecture) to key points only
- Total: ~10 minutes

---

## Key Messaging by Audience

### For Judges / Investors:
- Emphasize: Scale (multi-tenant), Security (RLS, audit logging), Differentiation (schema generation, evolution)
- Evidence: Test results, architecture diagrams, Phase 1 completion

### For Developers:
- Emphasize: Tech stack (modern, proven), Architecture (clean, extensible), Tool calling (real AI execution)
- Evidence: Code references, GitHub structure, API design

### For End-Users:
- Emphasize: Speed (minutes, not weeks), Ease (natural language, no config), Intelligence (Copilot, proposals)
- Evidence: Demo, user journey, before/after timeline

---

**End of Presentation Content**
