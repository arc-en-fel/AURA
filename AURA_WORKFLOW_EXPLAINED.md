# AURA — How It Works (Simple Explanation)

---

## The Big Picture

AURA is a CRM that **builds itself** based on what you tell it about your business.

Instead of giving you a fixed CRM with pre-built fields, AURA asks you about your business, thinks about it using AI, and creates a custom CRM structure just for you. It can also watch how you use the CRM over time and suggest improvements — but never applies those improvements without your approval.

---

## The Two AI Models Working Together

Before explaining the workflow, it helps to understand the two AI models AURA uses and what each one does.

---

### Model 1 — Laya (The Fast Thinker)

**What it is:** A small, fast decision-making model from `convaiinnovations/laya`.

**What it does:** Laya reads your business description and answers structured questions very quickly:
- *"What industry is this business in?"* → real estate / healthcare / SaaS / e-commerce
- *"What's the best strategy for building this CRM?"* → sales pipeline / case management / transaction tracking
- *"What should AURA improve first in this CRM?"* → follow-up speed / conversion rate / reduce manual work

**How fast:** Milliseconds. Laya doesn't generate text — it just picks the best option from a predefined list.

**Think of it as:** A traffic director. It quickly reads the situation and points everyone in the right direction before the heavy work begins.

**What happens if Laya isn't installed:** AURA has a built-in rule-based backup called `LayaSystem1` that does the same job using keyword matching. The system works either way.

---

### Model 2 — Qwen3-4B via Ollama (The Deep Thinker)

**What it is:** A 4-billion parameter language model (Qwen3-4B) running locally on your machine through Ollama.

**What it does:** Qwen actually *generates* the CRM configuration. It reads your business description (enriched with Laya's decision) and writes out a full JSON structure with:
- Entity names (e.g. `lead`, `patient`, `property_listing`)
- Field names and types (text, email, number, select, date…)
- Pipeline stages (e.g. New → Contacted → Qualified → Won)

**How fast:** 15–90 seconds on a CPU. Much faster with a GPU.

**Think of it as:** The architect who actually draws the blueprint after the traffic director has told them what kind of building to design.

**What happens if Qwen/Ollama isn't running:** AURA's deterministic scaffold (`LayaSystem1`) generates a valid CRM directly from industry templates. You see an amber warning saying fallback was used.

---

## The Main Workflows

---

### Workflow 1 — Single Prompt CRM Generation

This is the "Create CRM" page. You type a description and AURA generates a CRM instantly.

```
You type:
"Build a CRM for a real estate agency to manage leads, 
 viewings, property listings, and sales pipelines."

        ↓  Step 1: Safety Check
        LayaSystem1 scans your prompt for SQL injection
        or code execution attempts. If found → blocked.

        ↓  Step 2: Laya Decides (fast)
        Laya reads your prompt and answers:
        - Industry?  →  real_estate
        - Strategy?  →  transaction_tracking
        Takes < 1 second.

        ↓  Step 3: Qwen Generates (slow, 20-90s)
        Qwen3-4B receives:
        - Your original prompt
        - Laya's decision as context
        - A strict JSON schema to follow
        Qwen writes out the full CRM configuration as JSON.

        ↓  Step 4: Repair & Validate
        LayaSystem1 cleans up Qwen's output:
        - Fixes capitalisation (e.g. "Full Name" → "full_name")
        - Removes duplicate fields
        - Fills in missing select options
        - Renames "lead" → "property_lead" based on Laya's industry
        Then Pydantic v2 validates the whole thing strictly.

        ↓  Step 5: Return Draft
        The CRM is returned to your browser as a DRAFT.
        Nothing is saved yet. You review it, then click Save.

You see:
- Entity: property_lead  
- Fields: full_name, phone, budget_max, property_type, status
- Pipeline: New Inquiry → Site Tour → Offer Made → Closed Won
```

If Qwen fails or times out at Step 3, AURA silently uses the deterministic scaffold instead and shows an amber warning banner so you know.

---

### Workflow 2 — Interactive Chat CRM Generation

This is the "Chat & Build CRM" page. Instead of one prompt, AURA has a conversation with you.

```
AURA asks: "What kind of business is this CRM for?"
You say:   "I run a dental clinic"

AURA asks: "What are the main things you need to track?"
You say:   "Patients, appointments, and treatment plans"

AURA asks: "How many stages does your process have?"
You say:   "Inquiry → Booked → Treatment → Follow-up"

AURA asks: "What's the most important field on each record?"
You say:   "Phone number and date of birth"

        After 4–5 exchanges, AURA says:
        "I have everything I need! Click Generate My CRM."

        ↓  You click "Generate My CRM"

        Qwen reads the ENTIRE conversation and generates a CRM
        that reflects everything you told it — not a generic template.

You see a CRM with:
- Entity: patient (not the generic "lead")
- Fields: full_name, phone, date_of_birth, treatment_type, status
- Pipeline: Inquiry → Booked → Treatment → Follow-up
```

The difference from Workflow 1: instead of guessing from one sentence, Qwen has 4–5 rounds of context to work from. The result is much more specific to your actual business.

---

### Workflow 3 — Saving and Using the CRM

Once you're happy with the draft:

```
You click "Save & Activate CRM"

        ↓  The configuration is sent to FastAPI
        ↓  FastAPI saves it to Supabase (PostgreSQL)
        ↓  CRM is now "active" with configuration_version = 1

Now you can:
- Add records (leads, patients, properties — whatever you defined)
- Import records from a CSV file
- Create automation workflows
- View analytics (conversion rates, pipeline breakdowns)
```

The CRM configuration lives in a JSONB column in PostgreSQL. Your records (leads, patients, etc.) also live in a shared `records` table with a JSONB `data` column — so each customer's fields are completely flexible without any schema migrations.

---

### Workflow 4 — Evolution Proposals

Over time, AURA can analyse your CRM's performance and suggest improvements. This works through a strict 2-stage approval process — the AI can never change your live CRM on its own.

```
You go to "Evolution Center" and pick an objective:
→ "Improve follow-up speed"

        ↓  Step 1: Laya Decides Priority (fast)
        Laya reads your objective + current analytics and picks:
        - Priority: improve_follow_up
        - Requires human review: yes

        ↓  Step 2: Candidate Generation
        LayaSystem1 generates 3 possible workflow proposals
        and ranks them by priority. Proposals with disallowed
        action types (e.g. "execute shell") are filtered out.

        ↓  Step 3: Proposal Created (status = pending)
        The top-ranked proposal is saved to the database.
        Example proposal:
        "Create a follow-up task 4 hours after a new lead is added"

─────────────────────────────────────────────────────────────
        Nothing has changed in your CRM yet.
        The proposal just sits there waiting for you.
─────────────────────────────────────────────────────────────

        ↓  Stage 1: You click "Approve"
        AURA checks: is the CRM still the same version?
        Is the proposal still pending? Is the change type allowed?
        If yes → status changes to "approved"

        ↓  Stage 2: You click "Apply to Live CRM"
        A confirmation dialog appears explaining exactly what
        will change. You confirm.

        ↓  PostgreSQL runs an atomic transaction:
        1. Lock both the proposal and CRM rows
        2. Create the new workflow in your CRM
        3. Increment configuration_version from 1 → 2
        4. Mark proposal as "applied"
        5. Write an audit log entry
        All 5 steps happen together or not at all.

Your CRM now has a new workflow.
The change is recorded in the audit log forever.
```

---

## How the Two Models Divide the Work

```
┌─────────────────────────────────────────────────────┐
│                    Your Input                        │
│         (prompt or chat conversation)                │
└────────────────────┬────────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │       LAYA           │  Fast classifier
          │  "What industry?"   │  Picks from a list
          │  "What strategy?"   │  < 1 second
          │  "What priority?"   │  No text generated
          └──────────┬──────────┘
                     │  Decision (industry=real_estate,
                     │            strategy=transaction_tracking)
          ┌──────────▼──────────┐
          │      QWEN3-4B        │  Deep generator
          │  Reads your input   │  Writes actual JSON
          │  + Laya's decision  │  15–90 seconds
          │  Generates full CRM │  Can produce errors
          └──────────┬──────────┘
                     │  Raw JSON output
          ┌──────────▼──────────┐
          │    LayaSystem1       │  Repair & safety net
          │  Cleans up output   │  Always runs
          │  Validates with     │  < 1 millisecond
          │  Pydantic v2        │
          └──────────┬──────────┘
                     │
          ┌──────────▼──────────┐
          │   Your CRM Draft     │
          │   (not saved yet)   │
          └─────────────────────┘
```

**In short:**
- **Laya** tells Qwen what kind of CRM to build
- **Qwen** actually builds it
- **LayaSystem1** makes sure the result is safe and valid

If Qwen fails, LayaSystem1 builds the CRM itself using industry templates. You always get a working CRM — the amber warning just tells you whether Qwen was involved or not.

---

## The Safety Rules

AURA enforces several rules that can never be bypassed:

| Rule | How it's enforced |
|---|---|
| SQL injection blocked | Regex check before any AI call |
| LLM output never executed | All output treated as data, never run as code |
| AI can't approve its own proposals | Approve and Apply are separate human-triggered endpoints |
| Only allowed workflow types | Enforced in Python AND in the PostgreSQL stored procedure |
| Changes are atomic | PostgreSQL transaction — partial changes can't happen |
| One CRM per owner | Every query includes `WHERE owner_id = your_user_id` |
| Secrets never in responses | Global exception handler strips all internals |

---

## Summary in One Paragraph

You describe your business to AURA. Laya (fast AI) quickly classifies what industry you're in and what kind of CRM strategy fits best. Qwen3-4B (local language model) then uses that context to write out a custom CRM schema as JSON. LayaSystem1 (always-on rule engine) cleans up the output, fills in any gaps, and validates the whole thing. You review the draft and save it when you're happy. Later, AURA can suggest workflow improvements — but you must explicitly approve and apply every single change through a 2-step process before anything in your live CRM changes.

---

*AURA v1.0.0 · October 2026*
