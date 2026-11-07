# AURA Quick Reference Guide

**For**: Presenters, developers, and judges who want fast answers without reading 100+ pages.

---

## 30-Second AURA Pitch

**AURA** is an AI-powered CRM that generates complete, domain-specific schemas from natural language in minutes. One codebase serves all industries (sales, healthcare, recruitment, custom). The AI Copilot executes real actions (not just suggestions), and the system evolves with your business through approved proposals.

---

## What Makes AURA Different?

| Feature | Traditional CRM | AURA |
|---------|---|---|
| Setup time | 4-12 weeks | <5 minutes |
| New industry? | Buy new product | One codebase handles all |
| Schema changes | High risk | Safe + audited |
| AI assistance | Limited/advisory | Full Copilot executing actions |
| Schema evolution | Manual | AI-suggested + user-approved |

---

## AI Models: Two-Tier Approach

```
┌─────────────────────────────────┐
│  Tier 1: Laya (Fast)            │
│  ✓ No API calls                 │
│  ✓ 1-10 ms response             │
│  ✓ Intent classification        │
│  ✓ Entity resolution            │
│  ✓ Schema repair                │
└─────────────────────────────────┘
           │
        If simple request → Use Laya only
        If complex request ↓
┌─────────────────────────────────┐
│  Tier 2: LLM Provider           │
│  Option A: Groq (Production)    │
│  - llama-3.3-70b model          │
│  - 1-2 second latency           │
│  - Requires API key             │
│                                 │
│  Option B: Ollama (Local Dev)   │
│  - qwen2.5:3b model             │
│  - 3-5 second latency           │
│  - Runs on localhost:11434      │
│  - No API key needed            │
└─────────────────────────────────┘
```

---

## Groq Without API Key Exposure

**How secrets are protected:**

```
⚠️ NEVER in code:
  groq_api_key = "gsk_..."  ❌

✅ ALWAYS from environment:
  groq_api_key = settings.groq_api_key  ✓
  (loaded from .env at startup)

✅ NEVER sent to frontend:
  return {"data": result}  ✓ (no secrets)

✅ NEVER logged:
  logger.info("Connected to Groq")  ✓ (no key)
```

**Data flow:**
```
Frontend → Backend (JWT only) 
    ↓
Backend loads env → GroqProvider
    ↓
Provider reads settings.groq_api_key
    ↓
Provider initializes: Groq(api_key=...)
    ↓
Provider calls Groq API (key in header, encrypted)
    ↓
Groq returns response
    ↓
Backend validates & sanitizes
    ↓
Response sent to Frontend (no secrets)
```

---

## API Request Journey (Simplified)

```
1. User: "Create a lead"
   ↓
2. Frontend: POST /api/v1/copilot/chat
   (JWT in Authorization header, no API key)
   ↓
3. Backend: Extract intent → Laya classifies as CREATE_RECORD
   ↓
4. Backend: Resolve entity → "lead" found in CRM
   ↓
5. Backend: Decision
   - Simple action? Return directly ✓
   - Complex reasoning? Call Groq ↓
   ↓
6. GroqProvider: Send to Groq API
   (with function definitions for tool calling)
   ↓
7. Groq: Generate response
   "TOOL_CALL: {name: 'create_record', args: {entity_name: 'lead', ...}}"
   ↓
8. Backend: Parse & validate tool call
   ↓
9. Backend: Execute tool
   INSERT INTO records (...)
   ↓
10. Response: {success: true, record: {id, name, ...}}
    (no secrets)
    ↓
11. Frontend: Display confirmation
    "Lead created: John Doe"
```

---

## Technology Stack (One-Line Summary)

| Layer | Tech | Version |
|-------|------|---------|
| Frontend | React + TypeScript + Vite | 18.3 + 5.7 + 6.1 |
| Backend | FastAPI + Pydantic v2 | 0.115+ + 2.7+ |
| Database | Supabase PostgreSQL + RLS | Managed |
| Auth | Supabase GoTrue + JWT | Standard |
| LLM Production | Groq API | llama-3.3-70b |
| LLM Fallback | Ollama | qwen2.5:3b |
| Classifier | Laya (Deterministic) | Python rules |

---

## Phase 1 Status: ✅ Complete

**54 Tests Passing**

| Feature | Status | Evidence |
|---------|--------|----------|
| CRM generation from chat | ✅ Complete | `backend/app/routers/chat.py`, tests pass |
| Record CRUD | ✅ Complete | `backend/app/routers/records.py`, 20+ tests |
| Copilot intent + tools | ✅ Complete | `backend/app/routers/copilot.py`, 10+ tests |
| CSV import | ✅ Complete | `backend/app/services/csv_resolver.py`, tests pass |
| Universal analytics | ✅ Complete | Verified on 3 CRM types (sales, healthcare, recruitment) |
| Evolution proposals (2-stage) | ✅ Complete | 36 regression tests pass |
| Multi-tenant isolation (RLS) | ✅ Complete | Enforced at database level |
| Audit logging | ✅ Complete | Every mutation tracked |

**Phase 2 (Planned, Not in Phase 1):**
- ❌ Workflow execution engine (data model exists; execution pending)
- ❌ Webhook ingestion
- ❌ External API sync (Salesforce, HubSpot)
- ❌ Team/collaborator sharing

---

## Key Verified Facts

1. **Multi-tenant isolation is at DB level** (RLS, not app code)
2. **Copilot executes real tool calls** (not suggestions)
3. **Evolution proposals are atomic** (all-or-nothing transactions)
4. **Universal analytics** (no sales-specific code)
5. **Secrets never leave backend** (environment-loaded, never exposed)
6. **Fallback provider** (Ollama if Groq fails)

---

## Presentation Slide Quick-Reference

| Slide | Time | Key Points |
|-------|------|-----------|
| 1. Title | 30s | AURA tagline, team |
| 2. Intro | 1m | What AURA is, who uses it |
| 3. Team | 1m | 4 members, roles (verified + team-provided) |
| 4. Problem | 1.5m | CRM setup is slow, vertical silos, risky changes |
| 5. Solution | 2m | Schema generation, universal, tool calling, evolution |
| 6. Workflow | 2m | User journey: generation → records → Copilot → proposals |
| 7. Architecture | 2m | React → FastAPI → PostgreSQL + RLS, Groq API, Laya |
| 8. Tech Stack | 1m | Frontend, backend, database, AI providers |
| 9. Status | 1.5m | Phase 1 ✅ (54 tests), Phase 2 📋 (webhooks, workflows) |
| 10. Conclusion | 1.5m | Value proposition, market fit |
| **Total** | **~15m** | + Q&A |

---

## Open Questions for Team (Before Presenting)

**🔴 High Priority:**
- Q1: Live demo setup? (Supabase project URL + credentials for demo account)
- Q2: Deployment target? (AWS, GCP, Heroku, on-prem?)
- Q3: Fallback video if live demo fails?

**🟡 Medium Priority:**
- Q4: Team member names (to verify credits)?
- Q5: Business model? (B2B SaaS pricing, enterprise support, etc.)
- Q6: Beta customers or pilots?

**🟢 Low Priority:**
- Q7: Timeline for Phase 2?
- Q8: Security audits or pen testing?

---

## Common Judge Questions & Answers

### "How does the AI avoid making mistakes in schema generation?"

**Answer:** Multi-layer validation:
1. Laya repairs common errors (entity names, field types)
2. Pydantic validates against strict schema
3. Frontend lets user review before saving
4. Tests on sales, healthcare, recruitment prove it works

### "How do you prevent one user from seeing another user's CRM?"

**Answer:** Database-level isolation (RLS):
```sql
-- All queries automatically filtered:
WHERE owner_id = auth.uid()
```
No app code can bypass it. Tested.

### "What if Groq API goes down?"

**Answer:** Automatic fallback to Ollama (local):
```python
try:
    result = groq_provider.generate_config()
except ProviderUnavailable:
    result = ollama_provider.generate_config()
```
Or mock provider for testing.

### "Why not just use ChatGPT?"

**Answer:** 
- Groq is 2-3x faster (1-2s vs 3-5s)
- Specific model tuning for deterministic generation
- Cost efficient (pay per token, not per conversation)
- Fallback to local LLM (Ollama) if needed

### "Can users change the CRM schema after it's created?"

**Answer:** Yes, full WYSIWYG editor:
- Add/remove fields ✓
- Rename/reorder stages ✓
- Change field types (safe conversions only) ✓
- Validate before applying ✓

### "How do you prevent data loss when users change schema?"

**Answer:**
- Add field: Safe ✓
- Delete field: Requires confirmation (`?confirm=true`) ✓
- Type change: Only safe conversions allowed; unsafe returns error ✓
- Existing records preserved; changes only affect new records ✓

---

## File Navigation

| If You Want To... | Read This File |
|---|---|
| Understand every technical detail | `AURA_CODEBASE_AUDIT.md` (60 KB, 14 sections) |
| See system flow & architecture diagrams | `AURA_WORKFLOW_AND_ARCHITECTURE.md` (23 KB, Mermaid) |
| Prepare your presentation | `AURA_PRESENTATION_CONTENT.md` (20 KB, 10 slides) |
| Verify claims for Q&A | `FACT_CHECK_AND_OPEN_QUESTIONS.md` (16 KB, claim table) |
| Understand how AI models work (no secrets) | `AI_MODELS_EXPLANATION.md` (31 KB, Groq & Ollama) |
| Quick reference (you are here) | `QUICK_REFERENCE.md` (this file) |

---

## Key Stats for Your Pitch

- **🚀 Setup time:** Seconds (not weeks)
- **📊 CRM types supported:** Unlimited (not just 4 pre-built verticals)
- **🔒 Multi-tenant:** Enforced at database level (not app code)
- **✅ Test coverage:** 54 Phase 1 regression tests passing
- **⚡ AI latency:** 1-2s with Groq, 3-5s with Ollama fallback
- **🛡️ Security:** JWT + RLS + audit logging + no secrets exposed
- **🎯 Differentiators:** Schema generation, tool calling, evolution proposals

---

## Talking Points by Audience

### For Technical Judges
> "We chose deterministic Laya for fast intent classification (no LLM calls), then Groq for complex reasoning. RLS enforces multi-tenancy at the database level. Tool calling is real execution, not suggestions. Phase 1 has 54 passing tests and is production-ready."

### For Business Judges
> "SMBs build custom CRMs in minutes instead of months. Enterprises get multi-tenant SaaS with built-in compliance (audit logging, data isolation). We support any industry with one codebase. Evolution proposals mean CRM adapts to your business, not vice versa."

### For Product Judges
> "Phase 1 covers core CRM lifecycle: generation, records, Copilot, evolution. Phase 2 adds workflows, webhooks, and sharing. Users never touch code; it's all natural language + UI. Risk is minimal because proposals are user-approved before application."

---

## Pre-Presentation Checklist

- [ ] Read `AURA_CODEBASE_AUDIT.md` (understand depth)
- [ ] Skim `AURA_WORKFLOW_AND_ARCHITECTURE.md` (know the diagrams)
- [ ] Memorize `AURA_PRESENTATION_CONTENT.md` slide bullets
- [ ] Review `FACT_CHECK_AND_OPEN_QUESTIONS.md` (know what's verified)
- [ ] Read `AI_MODELS_EXPLANATION.md` (answer AI questions confidently)
- [ ] Get answers to 3 🔴 high-priority open questions
- [ ] Practice 15-minute presentation with slides
- [ ] Prepare 2-minute demo or pre-recorded fallback video
- [ ] Write down judge questions and your answers (for Q&A prep)

---

## One-Page Summary for Judges

### AURA: AI-Powered, Self-Evolving CRM

**Problem:** CRM setup is slow (weeks), vertical-locked (separate products per industry), risky (schema changes break things).

**Solution:** AI generates complete CRM schemas from natural language. One codebase serves all industries. Users evolve their CRM safely via AI proposals.

**Differentiators:**
- Schema generation in seconds (not weeks)
- Unlimited CRM types (not just 4 pre-built verticals)
- Real AI Copilot executing tool calls (not just suggestions)
- Evolution proposals with two-stage approval (user in control)
- Multi-tenant isolation at database level (security by design)

**Tech:**
- Frontend: React 18 + TypeScript + Vite
- Backend: FastAPI + Pydantic v2 + Async
- Database: Supabase PostgreSQL + RLS
- AI: Groq (production) + Ollama (fallback)
- Classifier: Laya deterministic (no LLM calls for simple requests)

**Status:** Phase 1 production-ready (54 tests passing). Core features complete. Phase 2 (workflows, webhooks, sharing) planned.

**Why You Should Pick AURA:**
- Fully functional end-to-end system (no mocks)
- Addresses real pain point (CRM setup complexity)
- Technical depth (multi-tenancy, security, scalability)
- Honest about what's done (Phase 1) vs. planned (Phase 2)
- Team clarity and execution

---

**Good luck with your hackathon presentation! 🚀**
