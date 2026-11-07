# CSV Import Header Mapping Fix — Requirements Document

**Request Type:** Bug fix + feature enhancement  
**Priority:** High  
**Date:** 2025-04-15  

---

## Summary

The CSV import pipeline fails when users upload valid CSV files with column headers that match the CRM entity's display labels (e.g., `CUSTOMER NAME` instead of `customer_name`). The preview displays data correctly but the confirmation step fails with "Unknown CSV columns" error.

The root cause is that the backend header validation (section 5.10 of API_CONTRACTS.md, line ~240 in `backend/app/routers/records.py`) compares CSV headers directly against canonical field names without normalizing capitalization, whitespace, or spaces-vs-underscores formatting. The frontend preview parses CSV passively without validation, masking the mismatch until backend rejection.

This fix implements a **universal, schema-driven header resolver** that normalizes headers at parse time, resolves them against both canonical field names and display labels, and validates ambiguity safely—without hard-coding entity or CRM-specific mappings.

---

## Assumptions

1. **Field labels are stable but formatted for display.** Every CRM field has a canonical `name` (lowercase, underscores: `customer_name`) and a `label` (title case, spaces: `Customer Name`) in the schema. Headers submitted by users match one or the other format, possibly with additional normalization (capitalization, spaces/underscores, whitespace).

2. **Display labels are unique within an entity.** A field's label does not conflict with another field's label or canonical name. This is enforced during CRM configuration validation in `backend/app/schemas/crm.py`.

3. **Preview and import must use identical header resolution.** Frontend preview and backend import must apply the same normalization and resolution logic so validation passes consistently.

4. **No aliases are currently configured in the schema.** The CRM schema stores only `name` and `label` per field. If field aliases are added in the future, the resolver should use them as a fallback.

5. **UTF-8 with optional BOM is the only encoding.** CSV files are UTF-8; the backend already handles BOM stripping with `decode("utf-8-sig")`.

6. **Ambiguity is rare but must be detected.** E.g., if two fields have labels `Status` and `Status Code` and a header is provided as `Status`, the resolver should fail rather than guess.

7. **Authorization and tenant isolation are already enforced.** This fix does not change authentication, CRM ownership verification, or database access patterns. All existing authorization checks remain in place.

---

## Functional Requirements

### 1. Header Normalization (Non-negotiable)

For every CSV header:
- **Trim whitespace:** Remove leading/trailing spaces.
- **Remove UTF-8 BOM:** If present (e.g., from Excel export), strip it before normalization.
- **Normalize capitalization:** Convert to lowercase for matching purposes.
- **Support formatting variations:** Treat spaces and underscores as equivalent (e.g., `customer_name` ≈ `customer name` ≈ `CUSTOMER_NAME` ≈ `Customer Name`).

**Acceptance criteria:**
- CSV header `  CUSTOMER NAME  ` resolves to field `customer_name`.
- CSV header `Customer_Name` resolves to field `customer_name`.
- CSV header `CUSTOMER_NAME` resolves to field `customer_name`.
- BOM-prefixed header `\xefBOMCUSTOMER NAME` is stripped and resolves correctly.

### 2. Header-to-Field Resolution

The resolver must attempt to match a normalized CSV header in this order:

1. **Exact canonical-name match:** `customer_name` (canonical field name).
2. **Exact display-label match (normalized):** `customer_name` ← from field label `Customer Name`.
3. **Safe formatting equivalence:** If the normalized header differs from canonical name only by spaces/underscores, treat as a match (e.g., `customer name` matches `customer_name`).

**Acceptance criteria:**
- CSV header `customer_name` matches field with canonical name `customer_name`.
- CSV header `Customer Name` matches field with label `Customer Name` → resolves to canonical name `customer_name`.
- CSV header `CUSTOMER_NAME` matches field with canonical name `customer_name`.
- Unknown header `billing_address` (not in schema) is rejected.

### 3. Ambiguity Detection

If a header could map to multiple fields or if a field's label creates a collision with another field, the resolver must detect and report this safely.

**Acceptance criteria:**
- If an entity has two fields with labels `Status` and `Status Code`, CSV header `Status` is rejected as ambiguous (cannot determine which field to use).
- If an entity has fields `customer_name` and `customer_name_display`, CSV header `CUSTOMER_NAME` is rejected as ambiguous.
- Error message clearly indicates the ambiguity (e.g., "Header 'Status' could match multiple fields: status, status_code").

### 4. Duplicate Header Detection

If two or more CSV columns normalize to the same field name, the import must fail before any rows are processed.

**Acceptance criteria:**
- CSV with headers `customer_name` and `CUSTOMER_NAME` (both resolve to same field) is rejected with error "Duplicate column 'customer_name'".
- Error is caught during header validation, not during row processing.

### 5. Unknown Header Handling

Any CSV header that does not resolve to a field in the entity schema must be rejected with a clear error message that distinguishes between:
- Genuinely unknown columns (not in schema at all).
- Valid display labels or canonical names that should work but did not for some reason.

**Acceptance criteria:**
- CSV with header `billing_city` (not in entity schema) is rejected with "Unknown column 'billing_city'".
- Error message lists all unknown columns if multiple are present.
- Error is returned at 422 VALIDATION_ERROR status before any rows are processed.

### 6. Empty and Malformed CSV Files

The import must reject empty CSV files, files with no header row, and files with inconsistent column counts.

**Acceptance criteria:**
- Empty file (0 bytes or only whitespace) is rejected with status 422 "CSV file is empty".
- File with no header row is rejected with "CSV has no header row".
- File with trailing commas or inconsistent columns per row does not crash; rows are parsed as best as possible.

### 7. Backend Validation (Canonical Names)

After header resolution, the backend must:
- Store the **resolved canonical field names** in the validation pipeline, not the original CSV headers.
- Validate record data using canonical names (this already occurs in `validate_csv_row` / `validate_record_data`).
- Ensure type coercion and required-field checks use canonical names.

**Acceptance criteria:**
- CSV row `{"CUSTOMER NAME": "Acme", ...}` is internally converted to `{"customer_name": "Acme", ...}` before validation.
- Type checking, required-field validation, and enum validation work correctly on resolved data.
- Database stores the correct field values mapped to canonical field names.

### 8. Frontend Preview Consistency

The frontend CSV preview (in `CSVImportModal.tsx`) must apply the same header normalization and resolution rules as the backend before displaying the preview.

**Acceptance criteria:**
- Frontend preview shows headers resolved to canonical names (or display labels for readability).
- If headers are ambiguous or unknown, the preview displays a warning before the user clicks "Confirm & Import".
- Preview validation errors prevent the upload button from being enabled.

### 9. Error Messages and Feedback

Error messages must distinguish between:
- Unknown columns (not in schema).
- Ambiguous headers (resolve to multiple fields).
- Required fields missing.
- Invalid field values (type mismatch, invalid enum option).

**Acceptance criteria:**
- Unknown column error: `"Unknown CSV columns: billing_address, phone_ext. Valid columns are: customer_name, customer_segment, ..."`
- Ambiguous header error: `"CSV header 'Status' is ambiguous and could match multiple fields: status, status_code. Please clarify your CSV header."`
- Missing required field error: `"Missing required field 'customer_segment' in CSV."`

---

## Non-Functional Requirements

### Performance
- Header resolution must complete in < 100ms for CSVs with 100+ columns.
- No new external dependencies or expensive regex operations.
- Resolution logic runs once at header-validation time, not per row.

### Compatibility
- Solution must work with **any dynamically generated CRM entity** without CRM-specific hard-coding.
- Solution must support all field types currently defined (text, textarea, email, number, date, boolean, select, phone, url, status, currency, datetime).
- Solution must not break existing valid imports that already use canonical field names.

### Security
- No changes to authentication, authorization, or tenant isolation.
- No arbitrary code execution or dynamic field creation based on CSV headers.
- CSV values are still sanitized against formula injection.
- Backend repeats schema validation after header resolution (defense in depth).

### Maintainability
- Header resolver should be a **single, reusable function** that both frontend and backend can use.
- All header-resolution logic must be centralized in one module (e.g., `backend/app/services/csv_utils.py`) to avoid duplication.
- Frontend can import or re-implement the same algorithm (TypeScript version) or call backend via preview endpoint.

---

## Acceptance Criteria

Specific, testable, numbered conditions for sign-off:

1. **Test Case 1 — Exact canonical headers:** CSV with headers `customer_name, customer_segment, total_revenue, purchase_frequency, customer_value, crm_status` imports successfully and all 6 fields map to the corresponding entity fields.

2. **Test Case 2 — Display-label headers:** CSV with headers `CUSTOMER NAME, CUSTOMER SEGMENT, TOTAL REVENUE, PURCHASE FREQUENCY, CUSTOMER VALUE, CRM STATUS` imports successfully; each header resolves to the correct canonical field and records persist correctly.

3. **Test Case 3 — Mixed-case headers:** CSV with headers `Customer Name, customer_segment, TOTAL_REVENUE, purchase frequency, Customer_Value, crm status` imports successfully; all headers normalize and resolve correctly.

4. **Test Case 4 — Spaces vs. underscores:** CSV with headers `customer name, customer_segment, total_revenue` imports successfully (spaces and underscores are treated equivalently).

5. **Test Case 5 — Whitespace handling:** CSV headers with leading/trailing spaces (`  customer_name  `) normalize and resolve correctly.

6. **Test Case 6 — UTF-8 BOM:** CSV file with UTF-8 BOM prefix imports successfully; BOM is stripped during parsing.

7. **Test Case 7 — Unknown columns rejected:** CSV with headers including unknown column `billing_address` returns 422 VALIDATION_ERROR with message listing unknown columns before any rows are processed.

8. **Test Case 8 — Duplicate headers rejected:** CSV with two columns both resolving to `customer_name` (e.g., `customer_name` and `CUSTOMER_NAME`) returns 422 VALIDATION_ERROR with "Duplicate column" message.

9. **Test Case 9 — Ambiguous schema labels:** CRM entity with fields `status` and `status_code`; CSV header `Status` is rejected as ambiguous with a clear error message.

10. **Test Case 10 — Missing required fields:** CSV without a required field (e.g., no `customer_segment`) returns 422 with "Missing required field" error.

11. **Test Case 11 — Invalid field values:** CSV row with invalid enum value (e.g., `crm_status: INVALID_STATUS`) is skipped with error code `INVALID_OPTION` and row number; valid rows still import.

12. **Test Case 12 — Empty CSV file:** Uploading a 0-byte or whitespace-only CSV returns 422 "CSV file is empty".

13. **Test Case 13 — No header row:** CSV with no header row returns 422 "CSV has no header row".

14. **Test Case 14 — Second CRM schema:** A different CRM (not Machine Identifier) with completely different entity/field names imports CSV successfully; resolver works universally.

15. **Test Case 15 — Bulk insertion success:** Six-column example CSV with 100 valid rows imports successfully; database contains all 100 records with correct field mappings and values.

16. **Test Case 16 — Tenant isolation:** User A cannot import CSV into User B's CRM; authorization check prevents access (return 404 or 403).

17. **Test Case 17 — Preview matches backend:** Frontend preview and backend import use identical header-resolution rules; a CSV that previews correctly will import successfully.

18. **Test Case 18 — All field types supported:** CRM entity with text, email, number, date, boolean, select, phone, textarea fields imports CSV correctly with proper type coercion for each field type.

19. **Test Case 19 — Large CSV performance:** CSV with 1000 rows imports in < 5 seconds; no timeout or performance degradation.

20. **Test Case 20 — Existing imports unbroken:** Existing tests and valid imports that use exact canonical headers continue to pass without modification.

---

## Out of Scope

1. **Field alias definitions:** Adding a new `aliases` field to the CRM schema is out of scope. This fix uses only `name` and `label`. If aliases are added in the future, the resolver can be extended to use them.

2. **CSV column reordering:** Allowing users to reorder or remap columns in the UI is out of scope. The fix resolves headers automatically; manual remapping is not required.

3. **Partial imports:** If some rows fail validation, the entire import is rolled back or skipped rows are not persisted. This behavior is already implemented; no change is required.

4. **Dynamic field creation:** Do not automatically create missing fields based on CSV headers. Unknown headers are rejected; users must update their CRM schema first.

5. **CSV format options:** Support for other delimiters (tab, semicolon, pipe) is out of scope. Only standard UTF-8 CSV (comma-delimited) is supported.

6. **Import scheduling or webhooks:** Scheduling CSV imports or triggering imports via webhooks is out of scope.

7. **Advanced type conversion:** E.g., converting "Jan 1, 2024" to ISO date format `2024-01-01`. Only standard formats are supported; invalid formats are rejected.

8. **Changes to existing API contracts:** The endpoint `/api/v1/crm/{crm_id}/records/{entity_name}/import` request/response contract remains unchanged (section 5.10 of API_CONTRACTS.md).

9. **Database schema changes:** No new columns, tables, or indexes are required. The fix operates entirely within the existing data model.

10. **Workflow or evolution changes:** This fix does not trigger workflows or evolution proposals. Bulk imports are treated as regular record creation.

---

## Implementation Scope

**Backend Changes:**
- New module: `backend/app/services/csv_utils.py` containing the reusable header resolver.
- Modified: `backend/app/routers/records.py` — import and use the resolver in `import_csv` endpoint.
- Modified: `backend/app/services/validation.py` — update to accept pre-resolved canonical field names.
- Tests: `backend/tests/test_csv_import.py` — 20 test cases covering all acceptance criteria.

**Frontend Changes:**
- Modified: `frontend/src/features/records/CSVImportModal.tsx` — integrate header resolver and show validation errors during preview.
- Optional: Frontend can use the same resolver logic (reimplemented in TypeScript) or call backend preview endpoint.

**Documentation Updates:**
- Update `docs/API_CONTRACTS.md` section 5.10 to document header normalization behavior.
- Add `docs/CSV_IMPORT_GUIDE.md` with examples of supported header formats.

---

## Testing Strategy

**Unit Tests (Backend):**
- Test header normalization (trim, BOM, lowercase, spacing).
- Test header-to-field resolution (canonical, display label, equivalence).
- Test ambiguity detection and duplicate detection.
- Test error messages for unknown/ambiguous/duplicate headers.
- Test with multiple CRM schemas (universal behavior).

**Integration Tests (Backend):**
- End-to-end CSV import with various header formats.
- Row-by-row validation after header resolution.
- Database assertion: verify records are stored with correct field names and values.
- Verify authorization checks still work.

**End-to-End Tests (Frontend + Backend):**
- Upload CSV with various header formats in CSVImportModal.
- Verify preview displays resolved headers and correct row data.
- Verify upload succeeds and records appear in records list.

**Regression Tests:**
- Existing tests in `backend/tests/test_record_response_contract.py` continue to pass.
- Existing tests in `frontend/src/tests/api.test.ts` continue to pass.
- Any hard-coded header mappings are removed (none should exist).

---

## Success Definition

All 20 acceptance criteria pass, including:
- Six-column example CSV imports successfully with display-label headers.
- Same resolver works for any CRM entity without CRM-specific code.
- Error messages are clear and actionable.
- Preview and import use identical logic.
- Tenant isolation and authorization remain enforced.
- Performance is acceptable (< 5 seconds for 1000 rows).
- All existing tests pass; no regressions.

---

## References

- **API Contract:** `docs/API_CONTRACTS.md`, section 5.10 (CSV import endpoint).
- **CRM Schema:** `docs/CRM_SCHEMA.json` (example entity and field definitions).
- **Backend Routes:** `backend/app/routers/records.py::import_csv` (current implementation).
- **Validation Service:** `backend/app/services/validation.py` (row validation logic).
- **Frontend Modal:** `frontend/src/features/records/CSVImportModal.tsx` (preview UI).
- **Schemas:** `backend/app/schemas/crm.py::CRMField`, `CRMEntity` (field structure).
