# CSV Import Header Mapping Fix — Design Review

**Review Date:** 2025-04-15  
**Reviewer:** Design Review Agent  
**Design Status:** CHANGES_REQUESTED  
**Revision:** 1.0  

---

## Verdict: CHANGES_REQUESTED

**Summary:** The design is well-structured and identifies the root cause correctly, but contains 1 HIGH-severity gap and several MEDIUM-severity ambiguities that must be resolved before implementation. All findings are concrete and actionable.

---

## Findings

### 1. **HIGH: Ambiguous Header-to-Field Resolution Order — May Produce Incorrect Matches**

**Severity:** HIGH  
**Location:** Design section "3. New Module: CSVHeaderResolver" → "_find_field_for_header" algorithm  
**Problem:**

The resolution algorithm describes a three-step priority order:
1. Exact match against canonical names
2. Exact match against normalized labels  
3. Safe formatting equivalence (spaces/underscores)

However, the pseudocode implementation has a **logical flaw**: steps 1 and 2 both perform exact string comparisons on different representations of the same data. The precedence between canonical-name matches and label matches is never defined in the pseudocode when both could apply.

**Example scenario:**
- Field A: `name: "status"`, `label: "Status"`
- Field B: `name: "my_status"`, `label: "STATUS"` (all caps label)
- CSV header: `status`

After normalization, the header is `status`. In step 1, it matches Field A's canonical name. But after lowercase normalization in step 2, does it also check if `status` equals Field B's label? The pseudocode doesn't clarify. If a label is also exactly `status` (after normalization), which field wins?

**The requirements state:** "If a header could map to multiple fields, return error (AMBIGUOUS_HEADER)." This implies we must be able to detect when both a canonical name and a label could match. The pseudocode doesn't show this detection clearly.

**Concrete Fix:**

Clarify the resolution order with explicit pseudocode or a decision matrix:

```python
def _find_field_for_header(self, normalized_header: str) -> tuple[str | None, list[str]]:
    """
    Find canonical field(s) that match this header.
    
    Resolution order (first match wins):
    1. Exact match against canonical names (e.g., normalized_header == "customer_name")
    2. Exact match against normalized labels (e.g., normalized_header == "customer name" 
       after label "Customer Name" is normalized)
    3. Safe formatting equivalence (apply _normalize_for_comparison to both)
    
    If step 1 matches, stop and return that field (canonical name wins).
    If step 2 matches, stop and return that field.
    If step 3 matches more than one field, return all as ambiguous.
    
    Returns (canonical_name, ambiguous_names):
    - If exactly one match found: (canonical_name, [])
    - If multiple matches possible: (None, [all_matching_names])
    - If no match: (None, [])
    """
    # Try canonical names first (highest priority)
    for canonical_name in self._field_by_name.keys():
        if canonical_name == normalized_header:
            return canonical_name, []
    
    # Try label matches second (medium priority)
    matches_from_labels = []
    for field in self.entity.fields:
        label_norm = self._normalize_for_comparison(field.label)
        if label_norm == normalized_header:
            matches_from_labels.append(field)
    
    if len(matches_from_labels) == 1:
        return matches_from_labels[0].name, []
    elif len(matches_from_labels) > 1:
        return None, [f.name for f in matches_from_labels]
    
    # Try formatting equivalence as fallback (lowest priority)
    header_normalized = self._normalize_for_comparison(normalized_header)
    matches_from_equivalence = []
    
    for canonical_name, field in self._field_by_name.items():
        canonical_normalized = self._normalize_for_comparison(canonical_name)
        if canonical_normalized == header_normalized:
            matches_from_equivalence.append((canonical_name, field))
    
    for field in self.entity.fields:
        label_normalized = self._normalize_for_comparison(field.label)
        if label_normalized == header_normalized and field.name not in [m[0] for m in matches_from_equivalence]:
            matches_from_equivalence.append((field.name, field))
    
    if len(matches_from_equivalence) == 1:
        return matches_from_equivalence[0][0], []
    elif len(matches_from_equivalence) > 1:
        return None, [m[0] for m in matches_from_equivalence]
    
    return None, []
```

This clarifies that canonical-name matches take precedence, and formatting equivalence is a fallback.

---

### 2. **MEDIUM: Contradictory Treatment of Spaces/Underscores in Normalization**

**Severity:** MEDIUM  
**Location:** Design section "3. New Module: CSVHeaderResolver" → `_normalize_for_comparison` description and usage  
**Problem:**

The design defines two distinct normalization functions:
- `_normalize_header(header)`: Trims, removes BOM, lowercases. Does NOT normalize spaces/underscores.
- `_normalize_for_comparison(text)`: Converts underscores to spaces, collapses multiple spaces, lowercases.

However, the algorithm doesn't clearly state **when each normalization is applied**. The pseudocode shows:

```python
# Step 2: Exact match against normalized labels
for label_norm, field_or_fields in self._field_by_label.items():
    if label_norm == normalized_header:  # <-- Which normalization?
```

Is `normalized_header` the result of `_normalize_header()` or `_normalize_for_comparison()`?

**Example scenario:**
- Field: `name: "customer_name"`, `label: "Customer Name"`
- CSV header: `customer name` (with a space, not underscore)

Step 1: `_normalize_header("customer name")` → `"customer name"` (no underscore normalization applied).  
Step 2: Should we match `"customer name"` against the canonical name `"customer_name"`? The design says "safe formatting equivalence" treats them as equivalent, but that's step 3.

So where does the match occur? Is it supposed to fail at step 2 and succeed at step 3? This is unclear.

**Concrete Fix:**

Explicitly define when each normalization function is applied:

```
Pseudocode:
1. Trim, remove BOM, lowercase: normalized_header = _normalize_header(raw_header)
   → used for exact canonical-name matching

2. Apply _normalize_for_comparison to canonical names and labels:
   → used for comparing labels and canonical names in step 2 and step 3

3. Steps 2 and 3 both use _normalize_for_comparison() applied to the LABEL and CANONICAL NAME,
   not to normalized_header.
   
   Step 2: 
     label_for_comparison = _normalize_for_comparison(field.label)
     canonical_for_comparison = _normalize_for_comparison(field.name)
     if label_for_comparison == _normalize_for_comparison(normalized_header):  <-- Apply to header too!
       match found
   
   Step 3:
     Same logic, but report ambiguity if multiple matches.
```

OR, simpler: **Apply `_normalize_for_comparison()` to the CSV header once upfront**, so all three steps use the same normalized form:

```python
def resolve_headers(self, raw_headers: list[str]) -> tuple[...]:
    for raw_header in raw_headers:
        normalized = self._normalize_header(raw_header)
        # Now normalized is: trimmed, BOM-stripped, lowercase
        # But NOT space/underscore normalized yet
        
        # For matching, apply space/underscore normalization
        normalized_for_matching = self._normalize_for_comparison(normalized)
        
        # Then check canonical names, labels, and equivalence using normalized_for_matching
        canonical_name, ambiguous = self._find_field_for_header(normalized_for_matching)
```

This makes it clear: there's one normalization pass, then all matching logic uses that.

---

### 3. **MEDIUM: Missing Specification for Building Lookup Tables in `__init__`**

**Severity:** MEDIUM  
**Location:** Design section "3. New Module: CSVHeaderResolver" → `__init__` method  
**Problem:**

The `__init__` method calls `self._build_lookup_tables()`, but this function is never defined in the pseudocode. The design later references `self._field_by_name` and `self._field_by_label`, but doesn't specify:

1. What happens if two fields have the **same label** (which the design notes is rare but possible)?
2. Does `_field_by_label` map labels to a single field or a list of fields?
3. How is the lookup structure organized?

From the pseudocode, it appears:
```python
self._field_by_label[label_norm] = field  # Single field per label
# OR
self._field_by_label[label_norm] = [field, field2, ...]  # List if ambiguous
```

The later resolution logic checks `isinstance(self._field_by_label[label_norm], list)`, suggesting it stores lists for ambiguous labels. But the initialization code isn't shown.

**Concrete Fix:**

Add explicit initialization pseudocode:

```python
def _build_lookup_tables(self):
    """Build field lookup tables for fast resolution."""
    self._field_by_name = {f.name: f for f in self.entity.fields}
    
    # Group fields by normalized label
    self._field_by_label = {}
    for field in self.entity.fields:
        label_norm = self._normalize_for_comparison(field.label)
        
        if label_norm not in self._field_by_label:
            self._field_by_label[label_norm] = field
        else:
            # Ambiguous: multiple fields with the same label (edge case)
            if not isinstance(self._field_by_label[label_norm], list):
                self._field_by_label[label_norm] = [self._field_by_label[label_norm]]
            self._field_by_label[label_norm].append(field)
```

---

### 4. **MEDIUM: Unclear Error Message for Duplicate Columns**

**Severity:** MEDIUM  
**Location:** Design section "2. Backend Flow" → error handling for duplicates, and section "3. CSVHeaderResolver" → error messages  
**Problem:**

The design shows this error message for duplicates:

```
"Duplicate column 'customer_name' (appears as 'customer_name' and 'CUSTOMER_NAME')"
```

But the pseudocode error building in `resolve_headers()` does not collect or format the original CSV headers that caused the duplicate. It only has:

```python
if canonical_name in seen_canonical:
    errors.append({
        "code": "DUPLICATE_COLUMN",
        "message": f"Duplicate column '{canonical_name}' (appears as '{seen_canonical[canonical_name]}' and '{raw_header}')"
    })
```

This works **if** `seen_canonical` stores the raw CSV header, but it's initialized as `seen_canonical = {}` with no definition of what value it stores. The pseudocode suggests it stores the raw header name, but this should be explicit.

**Concrete Fix:**

Clarify the tracking:

```python
seen_canonical = {}  # Maps canonical_field_name -> original_raw_csv_header_that_mapped_to_it

for raw_header in raw_headers:
    normalized = self._normalize_header(raw_header)
    canonical_name, ambiguous = self._find_field_for_header(normalized)
    
    if canonical_name in seen_canonical:
        prev_raw_header = seen_canonical[canonical_name]
        errors.append({
            "code": "DUPLICATE_COLUMN",
            "message": f"Duplicate column: both '{prev_raw_header}' and '{raw_header}' map to field '{canonical_name}'"
        })
        continue
    
    seen_canonical[canonical_name] = raw_header
    header_mapping[raw_header] = canonical_name
```

---

### 5. **MEDIUM: Frontend Implementation Option Not Decided**

**Severity:** MEDIUM  
**Location:** Design section "5. Frontend Integration"  
**Problem:**

The design offers two options:
- **Option A (Preferred):** Frontend calls backend preview endpoint to validate headers.
- **Option B:** Frontend re-implements header resolver in TypeScript.

Then states: "For this design, we proceed with **Option B** (client-side validation)."

However, **Option B has a significant maintainability cost:** it requires the TypeScript and Python implementations to stay perfectly synchronized. If the Python resolver is later enhanced or fixed, the TypeScript version must be updated identically, or preview and import will diverge.

The design does **not** explain:
1. Why Option B was chosen over Option A (what are the tradeoffs?).
2. How to ensure both implementations stay in sync.
3. What happens if they diverge (e.g., one catches an ambiguity, the other doesn't)?

Additionally, the design doesn't specify whether the TypeScript version should be auto-generated, manually maintained, or use a shared algorithm library.

**Concrete Fix:**

Either:
1. **Recommend Option A:** Add a lightweight backend `POST /api/v1/crm/{crm_id}/records/{entity_name}/validate-headers` endpoint that returns `{valid: bool, errors: [...]}`. Frontend calls it during preview to validate headers. This eliminates sync issues.
   
   OR

2. **If Option B is chosen, add explicit requirements:**
   - Maintain a single source of truth (e.g., shared algorithm documentation or code-generation script).
   - Add regression tests that validate TypeScript and Python implementations produce identical results for the same input.
   - Update both implementations in the same pull request.
   - Add a test case comparing outputs from both implementations.

---

### 6. **MEDIUM: Empty/Malformed CSV Handling Not Fully Specified**

**Severity:** MEDIUM  
**Location:** Design section "3. New Module: CSVHeaderResolver" → error handling  
**Problem:**

The design correctly identifies that empty CSV files and files with no header row must be rejected. The backend code already handles these (lines 237–244 of `backend/app/routers/records.py`):

```python
if not content.strip():
    return error_response(422, "VALIDATION_ERROR", "CSV file is empty.")

if not reader.fieldnames:
    return error_response(422, "VALIDATION_ERROR", "CSV has no header row.")
```

However, the design **doesn't clarify what happens if a header is empty or missing** (e.g., a CSV with a blank column header like `,,`).

Test case 5 (Whitespace handling) mentions trimmed headers, but doesn't cover the case where a header is entirely whitespace (`  ` or a tab character).

**Concrete Fix:**

Add explicit handling for empty/whitespace-only headers:

```python
def resolve_headers(self, raw_headers: list[str]) -> tuple[dict[str, str], list[dict[str, str]]]:
    for raw_header in raw_headers:
        normalized = self._normalize_header(raw_header)
        
        # Check for empty headers (after trimming)
        if not normalized:
            errors.append({
                "code": "UNKNOWN_COLUMN",
                "message": f"Empty column header (contains only whitespace)."
            })
            continue
        
        # ... rest of resolution logic
```

And add a test case:
- **Test Case 21 (NEW):** CSV with empty/whitespace-only column headers is rejected with "Empty column header" error.

---

### 7. **MEDIUM: Row-Level Error Handling vs. Header Validation Interaction Not Specified**

**Severity:** MEDIUM  
**Location:** Design section "2. Backend Flow" → transition from header validation to row processing  
**Problem:**

The design states:

> "If header validation fails, return 422 with error details **before processing any rows**."

This is correct. However, the design does **not** clarify **what to do if header validation succeeds but a row contains a field that was not validated during header resolution**.

For example:
1. CSV has headers: `customer_name, customer_segment, unknown_field`
2. Header validation should fail with "unknown_field is unknown".
3. BUT: what if the header normalization somehow introduces a **new field** that wasn't in the schema? (Unlikely, but worth clarifying the guard.)

More realistically: The design doesn't explain the contract between header resolution and row validation. After header resolution succeeds, are we guaranteed that all rows will only contain keys that exist in the entity schema?

**Concrete Fix:**

Add a note in the design:

```
After successful header resolution:
1. All keys in header_mapping are guaranteed to be valid canonical field names.
2. During row processing, the remapped row (using header_mapping) will only contain
   keys that are in the entity schema.
3. Row validation (via validate_csv_row) will not encounter unknown fields,
   because header validation already filtered them.
4. However, validate_csv_row still performs its own "unknown field" check as a safety net.
```

And verify in the code that row validation's "unknown field" check is indeed redundant but harmless.

---

### 8. **MEDIUM: Test Case 17 (Preview-Backend Consistency) Lacks Specification**

**Severity:** MEDIUM  
**Location:** Requirements section "Acceptance criteria" → Test Case 17  
**Problem:**

Test Case 17 states:

> "Test Case 17 — Preview matches backend: Frontend preview and backend import use identical header-resolution rules; a CSV that previews correctly will import successfully."

However, the design **does not specify how to verify this**. The test case doesn't say:
1. How do you measure "identical header-resolution rules"?
2. What's the test input and expected output?
3. How does the frontend expose its resolution results for comparison?

Additionally, if Option B (TypeScript reimplementation) is chosen, **identical behavior is not automatically guaranteed**. TypeScript and Python can have subtle differences in:
- String normalization (Unicode handling, case conversions).
- Regex or string-matching semantics.
- Floating-point precision (not relevant here, but shows the principle).

**Concrete Fix:**

Add explicit test specification:

```
Test Case 17 (Frontend-Backend Consistency):
Inputs:
  - CRM entity with fields: customer_name, customer_segment, total_revenue
  - CSV headers: CUSTOMER NAME, CUSTOMER SEGMENT, TOTAL REVENUE
  - Frontend calls resolveCSVHeaders(headers, entity)
  - Backend receives same headers in POST /api/v1/crm/{crm_id}/records/{entity_name}/import

Expected behavior:
  - Frontend resolution returns: 
    { 
      mapping: { 
        "CUSTOMER NAME": "customer_name",
        "CUSTOMER SEGMENT": "customer_segment",
        "TOTAL REVENUE": "total_revenue"
      },
      errors: []
    }
  - Backend import succeeds and returns 201 with created > 0.

Test implementation:
  - Call frontend resolver and log output.
  - Call backend import endpoint with same file.
  - Verify both return success (no errors).
  - Verify backend response includes the expected number of created records.

If Option B (TypeScript implementation) is used:
  - Add a dedicated test that calls both Python and TypeScript resolvers
    with identical input and compares their outputs for equality.
```

---

### 9. **MEDIUM: Design Does Not Reference Actual API_CONTRACTS.md Endpoint Specification**

**Severity:** MEDIUM  
**Location:** Design section "1. Backend Flow" and "Overview"  
**Problem:**

The design describes modifying the `import_csv` endpoint but does **not cite or quote the actual endpoint specification from `docs/API_CONTRACTS.md` section 5.10**. This means:

1. The design doesn't verify that the endpoint signature and request/response format remain compatible.
2. The design doesn't confirm whether the API contract requires any updates.
3. The design doesn't clarify whether the error response format matches the contract.

From the actual `docs/API_CONTRACTS.md`, the endpoint is:

```
POST /api/v1/crm/{crm_id}/records/{entity_name}/import
Auth: required. Content type: multipart/form-data, field name file.
```

The design should verify:
- Request format: Still multipart with `file` field? ✅ (Yes, unchanged)
- Response format: Still returns `{created, skipped, errors}`? ✅ (Yes, unchanged)
- Error codes: Does the new `UNKNOWN_COLUMN`, `DUPLICATE_COLUMN`, `AMBIGUOUS_HEADER` conflict with the existing contract? (Needs verification)

**Concrete Fix:**

Add a section to the design:

```
## 6. API Contract Verification

Verified against docs/API_CONTRACTS.md section 5.10:

**Request:**
- Content-Type: multipart/form-data ✅ (unchanged)
- Field name: file ✅ (unchanged)
- Path: POST /api/v1/crm/{crm_id}/records/{entity_name}/import ✅ (unchanged)

**Response (Success):**
- Status: 200 ✅
- Body: { created: int, skipped: int, errors: Array } ✅ (unchanged)

**Response (Errors):**
- 404 NOT_FOUND: CRM or entity not found ✅ (unchanged)
- 403 FORBIDDEN: CRM archived ✅ (unchanged)
- 413 PAYLOAD_TOO_LARGE: File size or row count exceeded ✅ (unchanged)
- 422 VALIDATION_ERROR: CSV validation failed (NEW error codes: UNKNOWN_COLUMN, DUPLICATE_COLUMN, AMBIGUOUS_HEADER) ⚠️

**New error codes to add to API_CONTRACTS.md:**
- UNKNOWN_COLUMN: CSV header does not match any field in the entity schema.
- DUPLICATE_COLUMN: Multiple CSV headers resolve to the same field.
- AMBIGUOUS_HEADER: CSV header could match multiple fields (ambiguous schema labels).

Note: These are specializations of VALIDATION_ERROR; they do not require new HTTP status codes.
```

---

### 10. **MEDIUM: Missing Specification for Validation of Multiple Entity Types**

**Severity:** MEDIUM  
**Location:** Design section "5. Make the solution universal" and test case 14  
**Problem:**

The design claims the solution is "universal" and Test Case 14 requires testing with "a different CRM (not Machine Identifier) with completely different entity/field names."

However, the design **does not specify which CRM types or entities to test**. The test case is vague:

> "Test Case 14 — Second CRM schema: A different CRM (not Machine Identifier) with completely different entity/field names imports CSV successfully; resolver works universally."

What if:
1. The second CRM doesn't exist yet in the test database?
2. The second CRM has fields with overlapping names/labels with Machine Identifier, causing false matches?
3. The second CRM has ambiguous labels (design edge case)?

**Concrete Fix:**

Specify Test Case 14 more clearly:

```
Test Case 14 (Expanded):
  Precondition:
    - Create CRM A with entity "customer" (fields: customer_name, customer_segment, etc.)
    - Create CRM B with entity "contact" (fields: contact_first_name, contact_email, etc.)
      — Completely different field names to avoid accidental overlap
    - Create CRM C with entity "lead" (fields: full_name, company, status, source)
      — Different entity name, overlapping field names (e.g., "status" exists in A and C)

  Test:
    - Import CSV into CRM A entity "customer" with display-label headers
      → Expected: Success, all fields resolve correctly
    - Import CSV into CRM B entity "contact" with display-label headers
      → Expected: Success, resolver works for different entity
    - Import CSV into CRM C entity "lead" with headers that could be ambiguous
      (e.g., "Status" when field "status" exists in both CRM A and CRM C)
      → Expected: Success in CRM C context only (resolver is entity-scoped, not global)

  Validation:
    - Verify that each CRM's resolver is independent (CRM A's resolver does not leak into CRM B).
    - Verify that field names from CRM A are not matched in CRM B.
```

---

### 11. **NIT: Performance Claim Not Validated Against Implementation**

**Severity:** NIT  
**Location:** Design section "Performance Considerations"  
**Problem:**

The design claims:

> "Header Resolution: O(n × m) where n = CSV headers, m = entity fields. For typical CSVs (< 100 columns) and entities (< 100 fields), resolution completes in < 1ms."

However:
1. The pseudocode complexity is not analyzed.
2. No benchmark is provided.
3. The claim "< 1ms" is not verified against the actual implementation.

The pseudocode has nested loops in `_find_field_for_header()`:

```python
for canonical_name in self._field_by_name.keys():
    if canonical_name == normalized_header:  # O(1) string comparison
        return canonical_name, []

for label_norm, field_or_fields in self._field_by_label.items():
    if label_norm == normalized_header:  # O(1) per field
        ...

for label_norm, field_or_fields in self._field_by_label.items():
    if label_norm == header_normalized:  # O(1) per field
        ...
```

This is O(m) per header, so O(n × m) total. For n=100, m=100, that's 10,000 comparisons, which is fast in Python but the "< 1ms" claim should be benchmarked, not assumed.

**Concrete Fix:**

Either:
1. Add a performance benchmark in the test suite:
   ```python
   def test_performance_large_entity_and_csv():
       """Benchmark header resolution for large CSV and entity."""
       entity = _create_entity_with_100_fields()
       csv_headers = _create_csv_headers_100_columns()
       
       resolver = CSVHeaderResolver(entity)
       start = time.time()
       mapping, errors = resolver.resolve_headers(csv_headers)
       elapsed = (time.time() - start) * 1000  # Convert to ms
       
       assert elapsed < 10, f"Resolution took {elapsed}ms; expected < 10ms"
       assert len(errors) == 0
   ```

OR

2. Remove the specific "< 1ms" claim and replace it with "Performs well for typical CSVs and entities" (less specific but safer).

---

### 12. **NIT: Frontend TypeScript Implementation Skeleton Not Provided**

**Severity:** NIT  
**Location:** Design section "5. Frontend Integration"  
**Problem:**

The design provides a pseudocode sketch for the TypeScript `csvHeaderResolver.ts` but **does not define the complete interface or algorithm**. The sketch is incomplete:

```typescript
export interface HeaderResolutionResult {
  mapping: Record<string, string>;  // csv_header -> canonical_field_name
  errors: Array<{ code: string; message: string }>;
}

export function resolveCSVHeaders(
  headers: string[],
  entity: CRMEntity,
): HeaderResolutionResult {
  // Implement same normalization and resolution logic
  // as backend CSVHeaderResolver
}
```

The comment says "Implement same normalization and resolution logic" but doesn't specify **what that logic is**. This could lead to the frontend implementation diverging from the backend.

**Concrete Fix:**

If Option B (TypeScript implementation) is chosen, provide complete pseudocode for the TypeScript version in the same level of detail as the Python version, including:
- `normalizeHeader()` function
- `normalizeForComparison()` function
- `findFieldForHeader()` function
- Full `resolveCSVHeaders()` implementation

OR, if this detail is deferred to implementation, state explicitly:

```
Frontend Implementation Approach:
- The TypeScript resolver MUST implement the same algorithm as the Python resolver.
- Use this design document as the source of truth.
- Add a regression test that calls both resolvers with identical input and compares outputs.
- If outputs differ, debug and fix both implementations to match.
```

---

## Verified Assumptions

✅ **Verified against source code:**

1. **Field labels and canonical names exist in the schema.**
   - Confirmed: `backend/app/schemas/crm.py`, class `CRMField`, has both `name` and `label` attributes.
   - `name`: Validated as lowercase identifier, required.
   - `label`: String, required, 1–100 characters.

2. **Current backend validation compares CSV headers directly against canonical names without normalization.**
   - Confirmed: `backend/app/routers/records.py`, line 250–254:
     ```python
     field_names = {f.name for f in entity.fields}
     csv_fields = set(reader.fieldnames or [])
     unknown_fields = csv_fields - field_names
     if unknown_fields:
         return error_response(422, "VALIDATION_ERROR", f"Unknown CSV columns: {', '.join(unknown_fields)}")
     ```
   - This directly compares raw CSV headers against canonical field names without any normalization.

3. **Frontend CSV preview does not validate headers.**
   - Confirmed: `frontend/src/features/records/CSVImportModal.tsx`, lines 40–60:
     - `handleFileChange()` parses the CSV and displays preview rows.
     - No header validation or normalization is performed.
     - Only the backend `/import` endpoint validates headers (after user clicks "Confirm & Import").

4. **Existing validation service `validate_csv_row()` works with canonical field names.**
   - Confirmed: `backend/app/services/validation.py`, line 155–165:
     - Checks that row keys exist in `field_map`, which maps canonical names to field objects.
     - No special handling needed; the validator already expects canonical names.

5. **UTF-8 BOM handling is already implemented in the backend.**
   - Confirmed: `backend/app/routers/records.py`, line 240:
     ```python
     text = content.decode("utf-8-sig")  # Handle BOM
     ```
   - The `utf-8-sig` codec automatically strips the BOM.

6. **API response format for CSV import is `{created, skipped, errors}`.**
   - Confirmed: `backend/app/routers/records.py`, line 288–294:
     ```python
     return success_response({
         "created": imported_count,
         "skipped": skipped_count,
         "errors": [...],
     })
     ```

7. **Authorization checks are already enforced in the import endpoint.**
   - Confirmed: `backend/app/routers/records.py`, line 213–219:
     - `_verify_crm_access()` checks CRM ownership.
     - Returns 404 if not found/not owned (does not leak existence).

8. **File size and row count limits are already enforced.**
   - Confirmed: `backend/app/routers/records.py`:
     - Line 233: `MAX_CSV_SIZE = 5 * 1024 * 1024` (5 MB)
     - Line 234: `MAX_CSV_ROWS = 10000`
     - Lines 235, 273: Validation against these limits.

---

## Unverified / Wrong Assumptions

⚠️ **Claims in the design that were not fully verified or are incomplete:**

1. **Assumption: "Display labels are unique within an entity."**
   - **Status:** Partially unverified.
   - **Evidence:** The design (Requirements section, Assumption 2) states: "A field's label does not conflict with another field's label or canonical name. This is enforced during CRM configuration validation in `backend/app/schemas/crm.py`."
   - **Reality:** I searched `backend/app/schemas/crm.py` and found validation for field names and select field options, but **no explicit validator that enforces label uniqueness within an entity**.
   - **Impact:** If two fields have the same label, the header resolver's behavior becomes ambiguous (as discussed in Finding #1).
   - **Recommendation:** Verify whether label uniqueness is enforced. If not, the resolver must handle ambiguous labels gracefully (which the design does attempt to do, but the logic is unclear).

2. **Assumption: "Frontend can call backend via preview endpoint or re-implement the resolver."**
   - **Status:** Not fully addressed.
   - **Evidence:** No preview endpoint currently exists in the codebase. The design proposes adding one (Option A) or re-implementing in TypeScript (Option B), but doesn't commit to either.
   - **Impact:** Until the frontend approach is decided, the implementation path is unclear.
   - **Recommendation:** Decide between Option A and Option B before implementation begins.

3. **Claim: "The preview uses different parsing logic from the actual import."**
   - **Status:** Verified as correct.
   - **Evidence:** 
     - Frontend preview: Splits by newlines and commas, no normalization.
     - Backend import: Uses Python's `csv.DictReader()`, which handles quoted fields, escaped commas, etc.
   - **Impact:** The design correctly identifies this as a source of inconsistency.
   - **Recommendation:** No action needed; design addresses this.

---

## Summary of Findings

| # | Severity | Category | Status |
|---|----------|----------|--------|
| 1 | HIGH | Ambiguous resolution algorithm | Needs clarification |
| 2 | MEDIUM | Contradictory normalization | Needs clarification |
| 3 | MEDIUM | Missing initialization spec | Needs clarification |
| 4 | MEDIUM | Unclear error messages | Needs clarification |
| 5 | MEDIUM | Frontend approach not decided | Needs clarification |
| 6 | MEDIUM | Empty header handling | Needs specification |
| 7 | MEDIUM | Error interaction unclear | Needs clarification |
| 8 | MEDIUM | Test 17 underspecified | Needs detail |
| 9 | MEDIUM | API contract not referenced | Needs verification |
| 10 | MEDIUM | Universal test underspecified | Needs detail |
| 11 | NIT | Performance claim unvalidated | Can be addressed in implementation |
| 12 | NIT | TypeScript skeleton incomplete | Can be deferred to implementation |

**HIGH findings:** 1  
**MEDIUM findings:** 9  
**NIT findings:** 2  

---

## Recommendations for Implementer

1. **Before starting implementation**, resolve findings #1–5 with the design author. These are blocking for correct behavior.

2. **Add explicit fixtures and test data** for findings #6–10 to the test spec.

3. **For the frontend**, make an explicit decision: Option A (backend validation endpoint) or Option B (TypeScript reimplementation with sync tests).

4. **For label uniqueness**, verify in `backend/app/schemas/crm.py` whether it's already enforced. If not, document the ambiguity handling in the resolver.

5. **Add a test that compares Python and TypeScript resolvers** with identical inputs to ensure they produce identical outputs (especially for edge cases like UTF-8 BOM, multiple spaces, mixed case).

---

## Next Steps

1. ✏️ **Design Author:** Address findings #1–5 and resubmit for re-review.
2. 🔍 **Reviewer:** Re-check against updated design before passing to implementation.
3. 💻 **Implementer:** After design approval, ensure all edge cases from findings #6–12 are covered in tests.

