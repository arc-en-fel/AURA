# Self-Evolving CRM — Shared Coding-Agent Instructions

Read `docs/API_CONTRACTS.md`, `docs/CRM_SCHEMA.json`, and the relevant task file in `team_tasks/` before coding.

## Stack
- Frontend: React, Vite, TypeScript, Tailwind CSS
- Backend: Python, FastAPI, Pydantic v2
- Database/auth: Supabase PostgreSQL and Supabase Auth
- AI provider: provider interface for local Hugging Face/Ollama or Grok API
- Charts: Recharts

## Architecture
- CRM configuration is validated JSON metadata.
- Dynamic records live in a shared records table with JSONB values.
- Keep system identifiers, tenant/owner IDs and timestamps in normal columns.
- Never execute arbitrary SQL/code from the LLM.
- Validate all AI-generated configurations/actions.
- AI-generated configuration/workflow changes remain drafts until approved.
- Enforce authentication and CRM ownership on every scoped operation.
- Never expose privileged Supabase credentials in the frontend.

## Post-generation schema editing

Every CRM is editable after generation via a universal schema editor. Field and stage modifications work for any CRM type (Sales, Service, Recruitment, etc.). All operations are documented in `docs/API_CONTRACTS.md` section 5.17 and `docs/SCHEMA_EDITING.md`.

**Key endpoints:**
- `POST /api/v1/crm/{crm_id}/fields` — Add field
- `PATCH /api/v1/crm/{crm_id}/fields/{field_name}` — Update field properties
- `DELETE /api/v1/crm/{crm_id}/fields/{field_name}` — Delete field
- `PATCH /api/v1/crm/{crm_id}/fields/reorder` — Reorder fields
- `POST /api/v1/crm/{crm_id}/stages` — Add pipeline stage
- `PATCH /api/v1/crm/{crm_id}/stages/{stage_name}` — Rename stage
- `DELETE /api/v1/crm/{crm_id}/stages/{stage_name}` — Delete stage
- `PATCH /api/v1/crm/{crm_id}/stages/reorder` — Reorder stages

**Type conversion rules:** Changing a field type is only allowed for safe conversions (e.g., text → email). Unsafe conversions (select → number) return 409 CONFLICT; use delete + add workflow instead. See `docs/API_CONTRACTS.md` section 1.8 for the full type conversion matrix.

**Record safety:** Adding fields is safe. Deleting fields with existing records requires explicit confirmation (`?confirm=true`). Changing required state or type only affects new records, not existing ones.

## Collaboration
- Implement only the assigned module.
- Do not change shared API contracts or schemas without team approval.
- Use mocks for unfinished dependencies.
- Add tests for new behavior and run them before claiming completion.
- Do not commit `.env` or secrets.
- Report changed files, commands run, test results and remaining limitations.

## Security and authorization
- Read the API contract and assigned member task before coding.
- Never change shared schemas or endpoint contracts without team agreement.
- Never commit `.env` files, API keys, tokens, passwords, or Supabase service-role credentials.
- Never bypass authentication or authorization for convenience.
- Never use AI-generated SQL or code as executable instructions.
- Validate all incoming data against the CRM configuration before persistence.
- Never return secrets, raw database errors, or stack traces to the client.

## Development practices
- Use mock data when another module is not ready.
- Add tests for new functionality and report actual test results.
- Keep generated OpenAPI documentation aligned with the API contract.
- Use lowercase machine identifiers for entity names in API paths (e.g., `/records/lead`, not `/records/Lead`).
- Distinguish CRM generation (draft), CRM saving (persistence), and CRM activation (operational use).

