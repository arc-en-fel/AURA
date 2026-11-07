# CRM Schema Editing Guide

**Status:** MVP Implementation  
**Target Audience:** Backend developers, frontend developers, QA engineers  
**Related Documents:** `docs/API_CONTRACTS.md` (sections 1.5–1.9, 5.17), `docs/CRM_SCHEMA.json`, `AGENTS.md`

This document explains how CRM schema (fields and pipeline stages) editing works in AURA, when to use each endpoint, and how to handle common scenarios.

---

## Table of Contents

1. [Overview](#overview)
2. [CRM Lifecycle and Editing Windows](#crm-lifecycle-and-editing-windows)
3. [Field Operations](#field-operations)
4. [Stage Operations](#stage-operations)
5. [Authorization and Ownership](#authorization-and-ownership)
6. [Type Conversion and Data Safety](#type-conversion-and-data-safety)
7. [Error Handling](#error-handling)
8. [Frontend Integration Patterns](#frontend-integration-patterns)
9. [Backend Implementation Checklist](#backend-implementation-checklist)
10. [Testing Strategy](#testing-strategy)

---

## Overview

AURA CRMs are **not immutable after generation**. Users can edit the schema (fields and stages) at any time. All schema editing is:

- **Generic**: Same endpoints work for any CRM type (Sales, Service, Recruitment, Real Estate, etc.)
- **Safe**: Existing record data is protected during schema changes
- **Auditable**: Each change increments `configuration_version` for optimistic concurrency control
- **Reversible**: Deletes require explicit confirmation; changes don't affect existing records (except deletions)

**Key principle:** Schema changes are operational safety operations, not data migrations. The database handles schema versioning through JSONB and `configuration_version`, not table migrations.

---

## CRM Lifecycle and Editing Windows

Understanding when editing is available is critical for frontend workflows.

### Phase 1: GENERATION

```
User submits prompt
         ↓
POST /api/v1/crm/generate
         ↓
Backend returns draft configuration (not saved to DB)
         ↓
User sees [Save CRM] and [Edit Before Saving] buttons
```

**During generation:**
- Configuration exists in-memory only
- User can [Edit Before Saving] to modify draft locally
- No `crm_id` yet (not saved)
- Cannot use field/stage edit endpoints (those require `crm_id`)
- User can [Save CRM] → POST /api/v1/crm with final configuration

### Phase 2: SAVE

```
User clicks [Save CRM]
         ↓
Frontend calls POST /api/v1/crm with configuration
         ↓
Backend persists to DB, assigns crm_id, sets configuration_version=1
         ↓
CRM now visible in GET /api/v1/crm list
```

**After save:**
- `crm_id` is assigned
- CRM appears on CRM list page
- [Edit CRM] button becomes available
- Field/stage endpoints can now be used

### Phase 3: ACTIVE

```
CRM in database, records may exist
         ↓
User clicks [Edit CRM]
         ↓
Frontend fetches current configuration
         ↓
Editor opens with live configuration
         ↓
User makes changes → calls individual field/stage endpoints
         ↓
Each operation increments configuration_version
         ↓
UI refreshes with updated configuration
```

**During active editing:**
- Field and stage endpoints are available
- Records continue to exist unchanged
- Type conversions are validated (409 CONFLICT for unsafe conversions)
- Deletions may trigger 409 CONFLICT if records have that field/stage value

---

## Field Operations

All field operations assume a **single primary entity** per CRM (the first entity in `entities[]`). For multi-entity CRMs, future versions may extend this.

### Adding a Field

**Endpoint:** `POST /api/v1/crm/{crm_id}/fields`

**Scope:** Always adds to the primary entity (index 0).

**Request:**
```json
{
  "field_name": "company",
  "label": "Company Name",
  "field_type": "text",
  "required": false,
  "options": null
}
```

**Validation:**
- `field_name` must be a valid identifier: lowercase, letters/digits/underscores, starts with letter, 1–64 chars
- `field_name` must not already exist in the entity
- `field_name` must not be a reserved system field (`id`, `crm_id`, `owner_id`, `created_at`, `updated_at`, `deleted_at`, `entity_name`, `data`, `source`)
- `label` must be 1–100 characters
- `field_type` must be one of: `text`, `textarea`, `email`, `number`, `date`, `datetime`, `boolean`, `phone`, `url`, `select`, `multi_select`
- If `field_type` is `select` or `multi_select`, `options` must be provided and must be a non-empty array of unique strings
- If `field_type` is not `select`/`multi_select`, `options` must be `null` or omitted

**Response:** 201 with updated configuration and new `configuration_version`

**Impact on records:**
- All existing records get a `null` value for the new field (safe)
- New records can populate the new field
- No data migration needed

**Example workflow:**
```
1. User clicks [+ Add Field]
2. User enters: name="company", label="Company Name", type="text"
3. Frontend validates (at least for basic checks)
4. Frontend calls POST /api/v1/crm/{crm_id}/fields with request
5. Backend validates, adds field to configuration
6. Backend increments configuration_version: 1 → 2
7. Backend saves to DB
8. Frontend receives updated configuration with company field
9. UI refreshes to show new field
```

### Updating a Field

**Endpoint:** `PATCH /api/v1/crm/{crm_id}/fields/{field_name}`

**Scope:** Updates field in the primary entity.

**Request:**
```json
{
  "label": "Company / Organization",
  "field_type": "text",
  "required": true,
  "options": null
}
```

**Validation:**
- All request fields are optional; only provided fields are updated
- If `field_type` is changed, check type conversion rules (section 6 of this guide)
- If type conversion is unsafe and records exist, return 409 CONFLICT
- New `field_type` must be valid; if `select`/`multi_select`, `options` must be provided
- If changing to non-select and `options` is provided, return 422 VALIDATION_ERROR

**Type Conversion:** See section **[Type Conversion and Data Safety](#type-conversion-and-data-safety)** below.

**Response:** 200 with updated configuration and new `configuration_version`

**Impact on records:**
- Changing `label`: No impact (label is presentation-only)
- Changing `required`: Only affects new records, not existing ones
- Changing `field_type` (safe conversion): Safe; existing values are compatible
- Changing `field_type` (unsafe conversion): Blocked with 409; user must delete and re-add
- Adding/removing options: No impact on existing values, only new record validation

**Example workflow:**
```
1. User clicks on a field to edit
2. User changes label and marks as required
3. Frontend validates
4. Frontend calls PATCH /api/v1/crm/{crm_id}/fields/company
5. Backend validates, updates field definition
6. Backend increments configuration_version: 2 → 3
7. Frontend refreshes UI
```

### Deleting a Field

**Endpoint:** `DELETE /api/v1/crm/{crm_id}/fields/{field_name}`

**Query parameter:** `?confirm=true` (required if field has existing values)

**Validation:**
- Field must exist in the entity
- If field is the **only field** in the entity, return 422 VALIDATION_ERROR (cannot have zero fields)
- If field has values in existing records and `confirm` is not `true`, return 409 CONFLICT with affected record count
- If `confirm=true`, proceed with deletion (user acknowledges data loss)

**Response:** 200 with updated configuration

**Impact on records:**
- Field is removed from configuration
- Existing record data is **not modified**; the field key may still exist in record JSON but is ignored
- New records do not include the deleted field
- Data is **permanently lost** (for MVP; future versions may support undelete)

**Confirm workflow:**
```
1. User clicks delete on a field
2. Backend checks if field has values
3. If yes, return 409 CONFLICT with message: "Company field has 12 record(s). Delete anyway?"
4. Frontend shows confirmation dialog
5. User confirms
6. Frontend calls DELETE /api/v1/crm/{crm_id}/fields/company?confirm=true
7. Backend deletes the field (no further check needed)
8. Response: 200 with updated configuration
```

### Reordering Fields

**Endpoint:** `PATCH /api/v1/crm/{crm_id}/fields/reorder`

**Request:**
```json
{
  "field_order": ["full_name", "email", "company", "status"]
}
```

**Validation:**
- `field_order` must be an array of field names
- `field_order` must contain **exactly** the current field names (all and only)
- No duplicates; all current fields must be present; no new fields
- If mismatch, return 422 VALIDATION_ERROR with details

**Response:** 200 with updated configuration

**Impact on records:**
- Field order is presentation-only; no record data is affected
- Queries and API responses return fields in the new order

**Example:**
```
1. User drags Company field from position 3 to position 2
2. New order: ["full_name", "email", "company", "status"]
3. Frontend calls PATCH with field_order
4. Backend validates order
5. Backend updates configuration.entities[0].fields with reordered array
6. Response: 200 with configuration_version incremented
```

---

## Stage Operations

Pipeline stages are global to the CRM (stored in `configuration.pipeline_stages[]`).

### Adding a Stage

**Endpoint:** `POST /api/v1/crm/{crm_id}/stages`

**Request:**
```json
{
  "stage_name": "Negotiation",
  "position": 3
}
```

**Validation:**
- `stage_name` must be 1–100 characters
- `stage_name` must be unique (not already in `pipeline_stages`)
- `position`, if provided, must be 0 ≤ position ≤ current_stage_count
- If `position` is omitted, appends to end (position = current_stage_count)

**Response:** 201 with updated configuration

**Impact on records:**
- New stage is added to configuration
- Existing records with other stage values are unaffected
- New records can be created with the new stage

**Example:**
```
Current stages: ["New", "Qualified", "Proposal", "Won", "Lost"]
Position not specified → append
New stages: ["New", "Qualified", "Proposal", "Won", "Lost", "Negotiation"]

OR

Position: 3 → insert at index 3
New stages: ["New", "Qualified", "Proposal", "Negotiation", "Won", "Lost"]
```

### Updating a Stage (Rename)

**Endpoint:** `PATCH /api/v1/crm/{crm_id}/stages/{stage_name}`

**Request:**
```json
{
  "new_stage_name": "Advanced Negotiation"
}
```

**Validation:**
- Old stage must exist
- New stage name must be unique (not already in pipeline_stages)
- New stage name must be 1–100 characters

**Response:** 200 with updated configuration

**Impact on records:**
- Configuration is updated with new stage name
- **Existing records are NOT migrated** (MVP limitation)
- Records that had the old stage value retain that value
- Stage becomes "orphaned" (not in current configuration)
- UI may show stage as unmapped/unknown
- Future versions will support record migration

**Caution:**
```
Stage "New" → renamed to "Incoming"
Old records with stage="New" still have stage="New"
UI shows: "New" (not in config, shown as "Unknown" or similar)
```

### Deleting a Stage

**Endpoint:** `DELETE /api/v1/crm/{crm_id}/stages/{stage_name}`

**Query parameter:** `?confirm=true` (required if stage has existing records)

**Validation:**
- Stage must exist
- If this is the **only stage**, return 422 VALIDATION_ERROR
- If stage has records with that stage value and `confirm` is not `true`, return 409 CONFLICT
- If `confirm=true`, proceed (user acknowledges records will be orphaned)

**Response:** 200 with updated configuration

**Impact on records:**
- Stage is removed from configuration
- Records with that stage value are not modified; stage value remains in data
- Records become orphaned (stage no longer in config)

**Example:**
```
1. User clicks delete on "Lost" stage
2. Backend checks: "Lost" stage has 5 records
3. Return 409: "Stage has 5 record(s). Delete and orphan records?"
4. User clicks confirm
5. Frontend calls DELETE /api/v1/crm/{crm_id}/stages/Lost?confirm=true
6. Backend deletes stage
7. 5 records now have orphaned stage value
```

### Reordering Stages

**Endpoint:** `PATCH /api/v1/crm/{crm_id}/stages/reorder`

**Request:**
```json
{
  "stage_order": ["New", "Negotiation", "Proposal", "Won", "Lost"]
}
```

**Validation:**
- Must contain exactly the current stages
- No duplicates; all current stages must be present

**Response:** 200 with updated configuration

**Impact on records:**
- Only presentation order changes
- No record data affected

---

## Authorization and Ownership

Every schema editing operation enforces authorization. Requests must include a valid Supabase JWT.

### Authorization checks:

1. **Verify JWT:** Backend verifies the token and extracts `user_id`
2. **Check CRM ownership:** `SELECT crm.owner_id FROM crms WHERE id = :crm_id`
   - If `owner_id != user_id`, return 404 NOT_FOUND (do not leak CRM existence)
   - If CRM does not exist, return 404 NOT_FOUND
3. **Proceed:** If authorized, process the operation

### Response codes:

- **200/201:** Success
- **404 NOT_FOUND:** CRM does not exist OR caller is not the owner
- **401 UNAUTHENTICATED:** JWT missing or invalid
- **403 FORBIDDEN:** CRM is archived (future; not in MVP)
- **409 CONFLICT:** Data loss warning, type conversion unsafe, field/stage already exists, version conflict
- **422 VALIDATION_ERROR:** Invalid request

### No partial authorization:

Field/stage operations are all-or-nothing. The backend does not allow editing "public" fields or allow team members to co-edit without explicit row-level sharing (future feature).

---

## Type Conversion and Data Safety

When updating a field's type, the backend validates the conversion against a type conversion matrix.

### Safe conversions (allowed, no data loss):

| From | To | Notes |
|------|-----|-------|
| `text` | `textarea`, `email`, `phone`, `url` | All text-compatible |
| `textarea` | `text`, `email`, `phone`, `url` | If content is single-line or URL-compatible |
| `email` | `text`, `url` | Email is a subset of text/URL |
| `phone` | `text` | Phone is a subset of text |
| `url` | `text` | URL is a subset of text |
| `number` | `text` | Can display as text |
| `date` | `text` | Format: YYYY-MM-DD |
| `datetime` | `text`, `date` | Text: ISO 8601; date loses time |
| `boolean` | `select` | With options ["true", "false"] |

### Unsafe conversions (blocked with 409 CONFLICT):

| From | To | Reason |
|------|-----|--------|
| `select` | `number`, `text`, `date`, `boolean` | Enum values may not parse |
| `multi_select` | *any* | Comma-separated data incompatible |
| `number` | `date`, `boolean`, `select`, `email` | Numeric format incompatible |
| `date` | `boolean`, `number`, `select`, `email` | Date format incompatible |
| `boolean` | `date`, `number`, `email`, `phone`, `url` | Boolean incompatible with complex types |

### Error response for unsafe conversion:

```json
{
  "error": {
    "code": "CONFLICT",
    "message": "Cannot convert field type select → number with existing records. Delete the field and add a new one.",
    "details": [
      {"field": "field_type", "issue": "Unsafe conversion with 5 existing records"}
    ],
    "request_id": "req_example"
  }
}
```

### Workaround for unsupported conversions:

If a user needs to change a field type in an incompatible way:

1. Delete the old field (confirms they accept data loss)
2. Add a new field with desired type and name (or new name)
3. Manually migrate data if needed (out-of-band)

---

## Error Handling

### Common error scenarios:

**Scenario 1: User tries to add a field with a name that already exists**
```
Request: POST /api/v1/crm/{crm_id}/fields
Body: { field_name: "email", ... }
Response: 409 CONFLICT
Message: "Field 'email' already exists in entity 'lead'"
```

**Scenario 2: User tries to convert select → number**
```
Request: PATCH /api/v1/crm/{crm_id}/fields/status
Body: { field_type: "number" }
Response: 409 CONFLICT
Message: "Cannot convert field type select → number with existing records. Delete the field and add a new one."
```

**Scenario 3: User tries to delete the only field**
```
Request: DELETE /api/v1/crm/{crm_id}/fields/company
Response: 422 VALIDATION_ERROR
Message: "Cannot delete the last field in an entity. An entity must have at least one field."
```

**Scenario 4: User tries to delete a field with 50 records**
```
Request: DELETE /api/v1/crm/{crm_id}/fields/company
Response: 409 CONFLICT
Message: "Field 'company' has 50 record(s) with values. Deletion would lose data. Confirm deletion."
Details: [{ field: "confirm", issue: "50 records use this field" }]
```

Then:
```
Request: DELETE /api/v1/crm/{crm_id}/fields/company?confirm=true
Response: 200 OK
Data: updated configuration
```

**Scenario 5: User tries to reorder fields with a mismatch**
```
Request: PATCH /api/v1/crm/{crm_id}/fields/reorder
Body: { field_order: ["full_name", "email"] }
Current fields: ["full_name", "email", "company", "status"]
Response: 422 VALIDATION_ERROR
Message: "Field order mismatch: missing 'company', 'status'"
```

---

## Frontend Integration Patterns

### Pattern 1: Edit Draft Before Saving

```typescript
// After generating CRM
const draft = await POST /api/v1/crm/generate (prompt)
// Draft configuration is in-memory
// User clicks [Edit Before Saving]
// Open editor with draft config
// User makes changes (purely local state)
// User clicks [Save CRM]
// POST /api/v1/crm { configuration: updatedDraft }
```

### Pattern 2: Edit Existing CRM

```typescript
// User clicks [Edit CRM] on a saved CRM
const crm = await GET /api/v1/crm/{crm_id}
// Fetch current configuration
// Open editor with crm.configuration

// User adds a field
await POST /api/v1/crm/{crm_id}/fields { field_name, label, ... }
// Response includes updated configuration_version

// User deletes a stage
try {
  await DELETE /api/v1/crm/{crm_id}/stages/{stage_name}
} catch (error) {
  if (error.code === "409") {
    // Stage has records; ask user to confirm
    showConfirmDialog()
    await DELETE /api/v1/crm/{crm_id}/stages/{stage_name}?confirm=true
  }
}

// User clicks [Save Changes]
// UI refreshes from latest GET /api/v1/crm/{crm_id}
```

### Pattern 3: Batch Sequential Operations

```typescript
// If frontend wants to batch multiple changes:
const operations = [
  { type: "add_field", ... },
  { type: "delete_field", ... },
  { type: "reorder_fields", ... }
]

for (const op of operations) {
  if (op.type === "add_field") {
    const result = await POST /api/v1/crm/{crm_id}/fields (op.data)
    updateLocalState(result.data.configuration)
  } else if (op.type === "delete_field") {
    // Handle potential 409 CONFLICT
    try {
      const result = await DELETE /api/v1/crm/{crm_id}/fields/{op.field_name}
    } catch (e) {
      if (e.code === "409") {
        const result = await DELETE /api/v1/crm/{crm_id}/fields/{op.field_name}?confirm=true
      }
    }
  }
  // ... etc
}
```

### Pattern 4: Optimistic Locking (Future)

```typescript
// In future, for safety against concurrent edits:
// Each operation includes expected_version
await PATCH /api/v1/crm/{crm_id}/fields/{field_name} {
  label: "New Label",
  expected_version: 5  // current version before this change
}

// If CRM was edited by another user (version mismatch), return 409
// Handle conflict: fetch latest, retry with new version
```

---

## Backend Implementation Checklist

### CRM Editor Service (`backend/app/services/crm_editor.py`)

- [ ] `add_field(config, entity_name, field_name, label, type, required, options) -> config`
  - [ ] Validate field name (identifier format, not reserved, not duplicate)
  - [ ] Validate type and options
  - [ ] Add to entity.fields[]
  - [ ] Return updated config

- [ ] `update_field(config, entity_name, field_name, label, type, required, options) -> config`
  - [ ] Find field in entity
  - [ ] Validate type conversion (check matrix)
  - [ ] Update field properties
  - [ ] Return updated config

- [ ] `delete_field(config, entity_name, field_name) -> config`
  - [ ] Validate field exists
  - [ ] Validate entity has >1 field after deletion
  - [ ] Remove field from entity.fields[]
  - [ ] Return updated config

- [ ] `reorder_fields(config, entity_name, field_order) -> config`
  - [ ] Validate field_order matches current fields
  - [ ] Reorder entity.fields[] to match field_order
  - [ ] Return updated config

- [ ] `add_pipeline_stage(config, stage_name, position) -> config`
  - [ ] Validate stage_name unique
  - [ ] Validate position in range
  - [ ] Insert into pipeline_stages[] at position
  - [ ] Return updated config

- [ ] `update_pipeline_stage(config, old_stage_name, new_stage_name) -> config`
  - [ ] Validate old stage exists
  - [ ] Validate new stage name unique
  - [ ] Update in pipeline_stages[]
  - [ ] Return updated config

- [ ] `delete_pipeline_stage(config, stage_name) -> config`
  - [ ] Validate stage exists
  - [ ] Validate >1 stage remains after deletion
  - [ ] Remove from pipeline_stages[]
  - [ ] Return updated config

- [ ] `reorder_pipeline_stages(config, stage_order) -> config`
  - [ ] Validate stage_order matches current stages
  - [ ] Reorder pipeline_stages[]
  - [ ] Return updated config

### Router Endpoints (`backend/app/routers/crm.py`)

- [ ] `POST /api/v1/crm/{crm_id}/fields`
  - [ ] Auth check + CRM ownership
  - [ ] Call CRMSchemaEditor.add_field()
  - [ ] Validate resulting config with Pydantic
  - [ ] Call repo.update_crm_configuration()
  - [ ] Return 201 with updated config and version

- [ ] `PATCH /api/v1/crm/{crm_id}/fields/{field_name}`
  - [ ] Auth check + CRM ownership
  - [ ] Call CRMSchemaEditor.update_field()
  - [ ] Type conversion validation (409 for unsafe)
  - [ ] Pydantic validation
  - [ ] repo.update_crm_configuration()
  - [ ] Return 200 with updated config

- [ ] `DELETE /api/v1/crm/{crm_id}/fields/{field_name}`
  - [ ] Auth check + CRM ownership
  - [ ] Check if field has record values (count_records_by_field_value)
  - [ ] If yes and not ?confirm=true: return 409 with count
  - [ ] If ?confirm=true: proceed
  - [ ] Call CRMSchemaEditor.delete_field()
  - [ ] repo.update_crm_configuration()
  - [ ] Return 200 with updated config

- [ ] `PATCH /api/v1/crm/{crm_id}/fields/reorder`
  - [ ] Auth check + CRM ownership
  - [ ] Call CRMSchemaEditor.reorder_fields()
  - [ ] Pydantic validation
  - [ ] repo.update_crm_configuration()
  - [ ] Return 200 with updated config

- [ ] Stage endpoints (POST, PATCH, DELETE, PATCH reorder)
  - [ ] Same pattern as field endpoints

### Database/Repository (`backend/app/database.py`)

- [ ] `update_crm_configuration(crm_id, owner_id, configuration) -> crm_record`
  - [ ] Verify ownership
  - [ ] Serialize configuration to JSON
  - [ ] Execute: `UPDATE crms SET configuration = $1, configuration_version = configuration_version + 1 WHERE id = $2`
  - [ ] Return updated record
  - [ ] Or: use Supabase update() API

- [ ] `count_records_by_field_value(crm_id, entity_name, field_name, field_value) -> int`
  - [ ] Query records with entity_name
  - [ ] Count where data->>field_name = field_value (or similar)
  - [ ] Return count

---

## Testing Strategy

### Unit Tests (backend)

**CRMSchemaEditor service:**
```python
def test_add_field_valid():
    config = { entities: [{ name: "lead", fields: [...] }], pipeline_stages: [...] }
    new_config = CRMSchemaEditor.add_field(config, "lead", "company", "Company", "text", False, None)
    assert new_config["entities"][0]["fields"][-1]["name"] == "company"

def test_add_field_duplicate():
    config = { entities: [{ name: "lead", fields: [{ name: "email", ... }] }], ... }
    with pytest.raises(ValueError, match="already exists"):
        CRMSchemaEditor.add_field(config, "lead", "email", "Email", "email", ...)

def test_update_field_unsafe_conversion():
    config = { entities: [{ name: "lead", fields: [{ name: "status", type: "select", options: [...] }] }], ... }
    with pytest.raises(ValueError, match="unsafe"):
        CRMSchemaEditor.update_field(config, "lead", "status", type="number")

def test_delete_field_only_field():
    config = { entities: [{ name: "lead", fields: [{ name: "name", ... }] }], ... }
    with pytest.raises(ValueError, match="last field"):
        CRMSchemaEditor.delete_field(config, "lead", "name")

def test_reorder_fields_mismatch():
    config = { entities: [{ name: "lead", fields: [{ name: "a" }, { name: "b" }, { name: "c" }] }], ... }
    with pytest.raises(ValueError, match="mismatch"):
        CRMSchemaEditor.reorder_fields(config, "lead", ["a", "b"])  # missing "c"
```

### Integration Tests (backend)

```python
def test_add_field_persists():
    # 1. Create CRM
    crm = repo.create_crm(owner_id, "Test CRM", config)
    crm_id = crm["id"]
    
    # 2. Add field via endpoint
    response = client.post(
        f"/api/v1/crm/{crm_id}/fields",
        json={"field_name": "company", "label": "Company", "field_type": "text"},
        headers={"Authorization": f"Bearer {user_token}"}
    )
    
    # 3. Verify response
    assert response.status_code == 201
    assert response.data.configuration_version == 2
    assert response.data.configuration.entities[0].fields[-1].name == "company"
    
    # 4. Fetch CRM and verify persistence
    crm = repo.get_crm(crm_id, user_id)
    assert crm["configuration_version"] == 2
    assert crm["configuration"]["entities"][0]["fields"][-1]["name"] == "company"

def test_delete_field_with_records_requires_confirm():
    # 1. Create CRM and record
    crm = repo.create_crm(owner_id, "Test CRM", config)
    crm_id = crm["id"]
    record = repo.create_record(crm_id, "lead", {"company": "ACME"})
    
    # 2. Try to delete company field without confirm
    response = client.delete(
        f"/api/v1/crm/{crm_id}/fields/company",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    
    # 3. Expect 409
    assert response.status_code == 409
    assert "confirm" in response.error.message
    
    # 4. Delete with confirm=true
    response = client.delete(
        f"/api/v1/crm/{crm_id}/fields/company?confirm=true",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    
    # 5. Expect 200
    assert response.status_code == 200
    assert response.data.configuration_version == 2

def test_field_operation_not_authorized():
    # User A's CRM, User B tries to edit
    crm = repo.create_crm(user_a_id, "CRM", config)
    response = client.post(
        f"/api/v1/crm/{crm['id']}/fields",
        json={"field_name": "company", ...},
        headers={"Authorization": f"Bearer {user_b_token}"}
    )
    assert response.status_code == 404  # Do not leak CRM existence
```

### Frontend E2E Tests

```typescript
it("allows user to add a field and see it in record creation", () => {
  cy.loginAs("user@example.com")
  cy.visit("/crms/123")
  cy.contains("Edit CRM").click()
  cy.contains("Add Field").click()
  cy.get('input[name="field_name"]').type("company")
  cy.get('input[name="label"]').type("Company Name")
  cy.get('select[name="field_type"]').select("text")
  cy.contains("Add Field").click()
  cy.wait("@postField").its("response.statusCode").should("eq", 201)
  cy.contains("Company Name").should("be.visible")
  cy.contains("Close Editor").click()
  cy.contains("Add Record").click()
  cy.contains("Company Name").should("be.visible")
})

it("warns when deleting a field with records", () => {
  cy.loginAs("user@example.com")
  // Create CRM with record
  cy.visit("/crms/123")
  cy.contains("Edit CRM").click()
  cy.contains("button", "Delete").first().click()  // delete Company field
  cy.contains("Company has").should("be.visible")  // warning
  cy.contains("Delete Anyway").click()
  cy.wait("@deleteField").its("response.statusCode").should("eq", 200)
})
```

---

## FAQ

**Q: Can I rename a field?**
A: Not in MVP. Use delete + add workflow. Future versions will support safe renaming with record migration.

**Q: What happens to records when I delete a field?**
A: Records are not modified. The field key may still exist in the JSONB data but is ignored. The field is no longer in the configuration.

**Q: Can I change a select field to a number field?**
A: No. This is an unsafe conversion (409 CONFLICT). Delete the field and add a new number field instead.

**Q: Can I have multiple entities and edit each separately?**
A: In MVP, all field operations apply to the primary entity (first entity). Future versions will support per-entity editors.

**Q: Can multiple users edit the same CRM schema concurrently?**
A: Currently, no concurrency control beyond basic ownership checks. Last-write-wins. Future versions will implement optimistic locking with `expected_version`.

**Q: What about API versioning for schema changes?**
A: API contract changes go through design review and are documented in `API_CONTRACTS.md`. Breaking changes should increment API version (e.g., `/api/v2`).

---

## Related Documents

- `docs/API_CONTRACTS.md` — Complete API specification (sections 1.5–1.9, 5.17)
- `docs/CRM_SCHEMA.json` — Example CRM configuration structure
- `backend/app/schemas/crm.py` — Pydantic models for all endpoints
- `backend/app/services/crm_editor.py` — Core editing logic
- `backend/app/routers/crm.py` — FastAPI endpoint implementations
- `AGENTS.md` — Shared coding standards and guidelines

