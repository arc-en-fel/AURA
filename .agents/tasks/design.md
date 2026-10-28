# Design: Universal CRM Generator Fix and Post-Generation Editing Architecture

**Status:** Design  
**Date:** 2025-01-15  
**Scope:** Universal CRM generation pipeline + generic schema editor  
**Owned by:** Design review (this document defines the complete solution)

---

## Executive Overview

This design unifies three currently disconnected components into a **comprehensive field preservation and post-generation editing system**:

1. **Field Extraction & Validation Pipeline** — Extract user-requested fields, validate against generated schema, repair missing fields
2. **Universal Post-Generation Editing** — Generic CRM schema editor that works for ANY CRM type (Sales, Service, Recruitment, etc.)
3. **Backend API for Schema Modification** — RESTful endpoints for field/stage CRUD and reordering

**Key principle:** A single canonical field representation flows through the entire system: LLM generation → validation → database → frontend editing.

**Architecture diagram:**
```
USER REQUEST
    ↓
[Field Extraction Service]
    ↓
[LLM Generation]
    ↓
[Schema Preservation & Repair]
    ↓
[Field Validation Report]
    ↓
DRAFT CRM (stored in db as JSON)
    ↓
    ├─→ [User clicks "Edit CRM"]
    │       ↓
    │   [React CRMSchemaEditor Component]
    │       ↓
    │   [Local State Editing (no DB writes)]
    │       ↓
    │   [User clicks "Save Changes"]
    │       ↓
    │   [Validation on Frontend]
    │       ↓
    │   [POST/PATCH to Backend]
    │       ↓
    └─→ [Backend API Validation & Authorization]
            ↓
        [Update CRM Configuration in DB]
            ↓
        [Increment configuration_version]
            ↓
        [Return Updated CRM]
            ↓
        [Frontend Refreshes Schema UI]
```

---

## 1. Canonical Field Representation

### 1.1 Single Field Structure

All field representations must use this canonical structure:

```typescript
// Frontend TypeScript
interface CanonicalField {
  name: string;              // "assigned_agent" — lowercase identifier, machine key
  label: string;             // "Assigned Agent" — human-readable label
  type: FieldType;           // "text" | "textarea" | "email" | "number" | "date" 
                              // "datetime" | "boolean" | "select" | "multi_select" 
                              // | "phone" | "url"
  required: boolean;         // true | false
  description?: string;      // optional field description
  options?: string[];        // for select/multi_select only; must be non-empty
}

type FieldType = 
  | "text"
  | "textarea"
  | "email"
  | "number"
  | "date"
  | "datetime"
  | "boolean"
  | "select"
  | "multi_select"
  | "phone"
  | "url";
```

**Python/Pydantic equivalent (already exists in `backend/app/schemas/crm.py`):**

```python
# Already correct; no changes needed
FieldType = Literal[
    "text", "textarea", "email", "number", "date", "datetime", 
    "boolean", "select", "multi_select", "phone", "url"
]

class CRMField(StrictModel):
    name: str
    label: str
    type: FieldType
    required: bool = False
    options: list[str] | None = None
```

**Enforcement:** 
- LLM (Qwen) generates fields in this structure
- Backend validates with Pydantic `CRMField`
- Frontend consumes as `CanonicalField` TypeScript interface
- No transformation between layers — exact same structure

---

## 2. Universal Field Extraction & Preservation Pipeline

### 2.1 Field Extraction Service (FieldExtractor)

**Status:** Service exists in `backend/app/services/field_extractor.py`  
**No changes needed** — already extracts all user-requested fields correctly.

**Flow:**
```python
extracted_fields = FieldExtractor.extract_fields_from_prompt(
    "Create a CRM with: Customer Name, Email, Phone, Priority, Status"
)
# Returns: [
#   ExtractedField(original_name="Customer Name", machine_key="customer_name", ...),
#   ExtractedField(original_name="Email", machine_key="email", ...),
#   ...
# ]
```

### 2.2 Schema Preservation & Repair (SchemaPreservation)

**Status:** Service exists in `backend/app/services/schema_preservation.py`  
**No changes needed** — already validates and repairs schema correctly.

**Flow:**
```python
config_dict = SchemaPreservation.validate_and_repair_schema(
    generated_config=raw_llm_output,
    user_prompt=user_request
)
# 1. Extracts fields from prompt
# 2. Compares vs. generated fields
# 3. Adds any missing fields
# 4. Returns repaired config
```

### 2.3 Field Count Validation Report

**New:** `FieldValidationReport` response object

```python
@dataclass
class FieldValidationReport:
    """Result of comparing requested fields to generated fields."""
    is_valid: bool                              # True if counts match
    requested_field_count: int                  # How many user requested
    generated_field_count: int                  # How many were generated
    missing_fields: list[ExtractedField]       # Fields in request but not in schema
    extra_fields: list[str]                    # Fields in schema but not in request
    warnings: list[str]                        # Human-readable issues
    reason: str | None                         # Why validation failed (if not valid)
```

**Validation rules:**
1. If user requests N fields → generated schema must contain those N fields
2. If generated_field_count < requested_field_count → repair by adding missing fields
3. If repair succeeds → is_valid = True, warnings = empty or minimal
4. If repair cannot succeed → is_valid = False, reason explains why

**Integration point:** Called in `POST /api/v1/crm/generate` after LLM output is received.

---

## 3. LLM Prompt Enhancement (Critical Fix)

### 3.1 Current Problem

The Ollama/Qwen system prompt in `backend/app/services/ollama_provider.py` does NOT instruct Qwen to preserve all user-requested fields. Qwen may omit fields to simplify the schema.

### 3.2 Solution: Enhanced System Prompt

**File:** `backend/app/services/ollama_provider.py` → `_get_system_prompt()`

**Add this section to the prompt:**

```python
def _get_system_prompt(self, decision: GenerationDecision | None = None) -> str:
    # ... existing JSON schema template ...
    
    return (
        "You are an expert CRM architect system. Generate a complete CRM configuration JSON...\n"
        # ... existing constraint section ...
        "Constraints:\n"
        "- Entity names and field names must be lowercase letters and underscores only.\n"
        "- Field types must be one of: text, textarea, email, number, date, datetime, boolean, select, multi_select, phone, url.\n"
        "- Select/multi_select fields must have a non-empty list of unique string options.\n"
        "- Output valid JSON only, no explanatory markdown.\n"
        "\n"
        # ← ADD THIS CRITICAL SECTION:
        "FIELD PRESERVATION REQUIREMENT (DO NOT SKIP):\n"
        "If the user's request lists specific fields (separated by newlines, bullets, commas, etc.),\n"
        "you MUST include EVERY ONE of those fields in the generated 'fields' array.\n"
        "Count the explicitly mentioned fields and verify your generated schema has that exact count.\n"
        "Examples:\n"
        "  User: 'Customer Name, Email, Phone' → schema has 3 fields: customer_name, email, phone\n"
        "  User: 'Name\\nEmail\\nPhone\\nStatus\\nPriority' → schema has exactly 5 fields\n"
        "If uncertain about a field's type, use 'text' as default but ALWAYS include the field.\n"
        "NEVER omit or skip any field the user explicitly mentioned.\n"
    )
```

**Why:** This makes the Qwen LLM aware that field preservation is a non-negotiable requirement. Without this, Qwen may optimize the schema by omitting fields it deems optional.

---

## 4. Post-Generation Editing Backend API

### 4.1 Schema Modification Endpoints

All endpoints enforce CRM ownership via RLS + application-level authorization.

#### 4.1.1 Add Field

```
POST /api/v1/crm/{crm_id}/fields
Authorization: Bearer <user_jwt>

Request:
{
  "label": "Assigned Agent",
  "type": "select",
  "required": false,
  "options": ["Alice", "Bob", "Charlie"]
}

Response (200):
{
  "data": {
    "configuration": CRMConfiguration,
    "field_added": {
      "name": "assigned_agent",
      "label": "Assigned Agent",
      "type": "select",
      "required": false,
      "options": ["Alice", "Bob", "Charlie"]
    },
    "configuration_version": 2
  }
}

Error cases:
  - 401: Not authenticated
  - 403: CRM not owned by user (not authorized)
  - 404: CRM not found
  - 409: Field name already exists
  - 422: Invalid field type or options
```

**Backend logic:**
1. Verify user owns CRM
2. Validate field data (Pydantic CRMField)
3. Generate machine key from label (normalize to lowercase, underscores)
4. Check for duplicates within the entity
5. Append to entity's fields array
6. Increment configuration_version
7. Save to database
8. Return updated CRMConfiguration

#### 4.1.2 Update Field

```
PATCH /api/v1/crm/{crm_id}/fields/{field_name}
Authorization: Bearer <user_jwt>

Request (any combination of these):
{
  "label": "Agent Assigned",
  "required": true,
  "options": ["Alice", "Bob", "Charlie", "David"]
}

Response (200):
{
  "data": {
    "configuration": CRMConfiguration,
    "field_updated": {
      "name": "assigned_agent",
      "label": "Agent Assigned",
      "type": "select",
      "required": true,
      "options": ["Alice", "Bob", "Charlie", "David"]
    },
    "configuration_version": 3
  }
}

Error cases:
  - 401: Not authenticated
  - 403: Not authorized
  - 404: CRM or field not found
  - 409: Cannot rename field that has existing records (see section 6.3)
  - 422: Invalid field data
```

**Backend logic:**
1. Verify ownership
2. Find field by name in entity
3. Validate updated field data
4. Check for type changes that require migration (see section 6)
5. Update field properties
6. Increment configuration_version
7. Save and return

**Field renaming:** If updating `name` is requested, use a separate endpoint (see below).

#### 4.1.3 Delete Field

```
DELETE /api/v1/crm/{crm_id}/fields/{field_name}
Authorization: Bearer <user_jwt>

Response (200):
{
  "data": {
    "configuration": CRMConfiguration,
    "field_deleted": "assigned_agent",
    "configuration_version": 4,
    "records_affected": 0
  }
}

Error cases:
  - 401: Not authenticated
  - 403: Not authorized
  - 404: CRM or field not found
  - 409: Field has existing record values (see section 6.2)
  - 422: Cannot delete required system fields
```

**Backend logic:**
1. Verify ownership
2. Check if field has values in existing records:
   - Query `records` table for this crm_id/entity_name
   - Check if any record.data[field_name] is not NULL
   - If yes, return 409 with count of affected records and warning
3. If user confirms deletion, remove field from entity
4. Increment configuration_version
5. Save and return

#### 4.1.4 Reorder Fields

```
PATCH /api/v1/crm/{crm_id}/fields/reorder
Authorization: Bearer <user_jwt>

Request:
{
  "field_order": ["name", "email", "phone", "assigned_agent", "status"]
}

Response (200):
{
  "data": {
    "configuration": CRMConfiguration,
    "configuration_version": 5
  }
}

Error cases:
  - 401: Not authenticated
  - 403: Not authorized
  - 404: CRM not found
  - 422: Field list doesn't match current fields or has duplicates
```

**Backend logic:**
1. Verify ownership
2. Validate that field_order contains exactly the current fields (same set, different order)
3. Reorder fields array in entity
4. Increment configuration_version
5. Save and return

#### 4.1.5 Add Stage

```
POST /api/v1/crm/{crm_id}/stages
Authorization: Bearer <user_jwt>

Request:
{
  "name": "Negotiation",
  "position": 3  // Insert at index 3 (0-indexed)
}

Response (200):
{
  "data": {
    "configuration": CRMConfiguration,
    "stage_added": "Negotiation",
    "configuration_version": 6
  }
}

Error cases:
  - 401: Not authenticated
  - 403: Not authorized
  - 404: CRM not found
  - 409: Stage already exists
  - 422: Invalid stage name or position
```

#### 4.1.6 Update Stage

```
PATCH /api/v1/crm/{crm_id}/stages/{stage_name}
Authorization: Bearer <user_jwt>

Request:
{
  "new_name": "In Negotiation"
}

Response (200):
{
  "data": {
    "configuration": CRMConfiguration,
    "stage_updated": {
      "old_name": "Negotiation",
      "new_name": "In Negotiation"
    },
    "configuration_version": 7
  }
}

Error cases:
  - Similar to field update
```

#### 4.1.7 Delete Stage

```
DELETE /api/v1/crm/{crm_id}/stages/{stage_name}
Authorization: Bearer <user_jwt>

Response (200):
{
  "data": {
    "configuration": CRMConfiguration,
    "stage_deleted": "Negotiation",
    "configuration_version": 8,
    "records_affected": 5
  }
}

Error cases:
  - 409: Stage has records with that status value (warn user)
```

#### 4.1.8 Reorder Stages

```
PATCH /api/v1/crm/{crm_id}/stages/reorder
Authorization: Bearer <user_jwt>

Request:
{
  "stage_order": ["New", "Qualified", "Negotiation", "Proposal", "Won", "Lost"]
}

Response (200):
{
  "data": {
    "configuration": CRMConfiguration,
    "configuration_version": 9
  }
}
```

### 4.2 API Implementation Location

**File:** `backend/app/routers/crm.py`

**Add new routes after existing endpoints:**
```python
@router.post("/crm/{crm_id}/fields")
async def add_field(crm_id: UUID, body: AddFieldRequest, user_id: CurrentUser, ...):
    """Add a field to CRM entity."""
    repo = CRMRepository()
    crm = repo.get_crm(str(crm_id), str(user_id))
    if not crm:
        return error_response(404, "NOT_FOUND", "CRM not found")
    
    # ... validate and add field logic ...

@router.patch("/crm/{crm_id}/fields/{field_name}")
async def update_field(crm_id: UUID, field_name: str, body: UpdateFieldRequest, ...):
    # ... implementation ...

# ... etc for DELETE, reorder ...
```

### 4.3 Validation Rules for Each Endpoint

**Every endpoint must validate:**

1. **Authentication:** User has valid JWT
2. **Authorization:** Verified user owns the CRM (owner_id matches)
3. **Field/Stage name validity:** Lowercase identifier (regex: `^[a-z][a-z0-9_]{0,62}$`)
4. **No reserved fields:** Cannot modify/delete system fields (id, crm_id, owner_id, etc.)
5. **Schema constraints:** 
   - At least 1 field per entity
   - At most 100 fields per entity
   - Field names unique within entity
   - Select/multi_select have non-empty options
6. **Configuration version compatibility:** (Optional for MVP, useful for optimistic locking)

---

## 5. Generic CRM Schema Editor Component (Frontend)

### 5.1 Component Structure

**Location:** `frontend/src/components/CRMSchemaEditor/CRMSchemaEditor.tsx`

**No hardcoded field names or CRM-specific logic.**

```typescript
interface CRMSchemaEditorProps {
  crm: CRMConfiguration;
  onSave: (updatedConfig: CRMConfiguration) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
}

export const CRMSchemaEditor: React.FC<CRMSchemaEditorProps> = ({
  crm,
  onSave,
  onCancel,
  isLoading = false,
}) => {
  const [editingConfig, setEditingConfig] = useState<CRMConfiguration>(crm);
  const [activeTab, setActiveTab] = useState<"fields" | "stages" | "metadata">("fields");
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async () => {
    try {
      setIsSaving(true);
      // Validate config before sending
      const errors = validateCRMConfiguration(editingConfig);
      if (errors.length > 0) {
        setValidationErrors(errors);
        return;
      }
      await onSave(editingConfig);
    } catch (err) {
      setValidationErrors([err.message]);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="crm-schema-editor">
      <div className="editor-header">
        <h2>Edit CRM Schema</h2>
        <p className="crm-name">{crm.name}</p>
      </div>

      {/* Tab Navigation */}
      <div className="tabs">
        <button
          className={activeTab === "fields" ? "tab active" : "tab"}
          onClick={() => setActiveTab("fields")}
        >
          Fields
        </button>
        {crm.pipeline_stages && crm.pipeline_stages.length > 0 && (
          <button
            className={activeTab === "stages" ? "tab active" : "tab"}
            onClick={() => setActiveTab("stages")}
          >
            Stages
          </button>
        )}
        <button
          className={activeTab === "metadata" ? "tab active" : "tab"}
          onClick={() => setActiveTab("metadata")}
        >
          Metadata
        </button>
      </div>

      {/* Validation Errors */}
      {validationErrors.length > 0 && (
        <div className="validation-errors alert alert-danger">
          <ul>
            {validationErrors.map((err, i) => (
              <li key={i}>{err}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === "fields" && (
          <FieldsEditor
            entity={editingConfig.entities[0]}
            onUpdate={(updatedEntity) => {
              setEditingConfig({
                ...editingConfig,
                entities: [updatedEntity, ...editingConfig.entities.slice(1)],
              });
            }}
          />
        )}

        {activeTab === "stages" && (
          <StagesEditor
            stages={editingConfig.pipeline_stages}
            onUpdate={(updatedStages) => {
              setEditingConfig({
                ...editingConfig,
                pipeline_stages: updatedStages,
              });
            }}
          />
        )}

        {activeTab === "metadata" && (
          <MetadataEditor
            name={editingConfig.name}
            industry={editingConfig.industry}
            onUpdate={(name, industry) => {
              setEditingConfig({
                ...editingConfig,
                name,
                industry,
              });
            }}
          />
        )}
      </div>

      {/* Action Buttons */}
      <div className="editor-actions">
        <button
          className="btn btn-secondary"
          onClick={onCancel}
          disabled={isSaving}
        >
          Cancel
        </button>
        <button
          className="btn btn-primary"
          onClick={handleSave}
          disabled={isSaving || isLoading}
        >
          {isSaving ? "Saving..." : "Save Changes"}
        </button>
      </div>
    </div>
  );
};
```

### 5.2 Fields Editor Sub-Component

```typescript
interface FieldsEditorProps {
  entity: CRMEntity;
  onUpdate: (updatedEntity: CRMEntity) => void;
}

const FieldsEditor: React.FC<FieldsEditorProps> = ({ entity, onUpdate }) => {
  const [fields, setFields] = useState<CRMField[]>(entity.fields);
  const [showAddField, setShowAddField] = useState(false);
  const [editingFieldIndex, setEditingFieldIndex] = useState<number | null>(null);

  const handleAddField = (newField: CRMField) => {
    setFields([...fields, newField]);
    setShowAddField(false);
    onUpdate({ ...entity, fields: [...fields, newField] });
  };

  const handleUpdateField = (index: number, updatedField: CRMField) => {
    const newFields = [...fields];
    newFields[index] = updatedField;
    setFields(newFields);
    setEditingFieldIndex(null);
    onUpdate({ ...entity, fields: newFields });
  };

  const handleDeleteField = (index: number) => {
    if (confirm(`Delete field "${fields[index].label}"? This cannot be undone.`)) {
      const newFields = fields.filter((_, i) => i !== index);
      setFields(newFields);
      onUpdate({ ...entity, fields: newFields });
    }
  };

  const handleReorderFields = (from: number, to: number) => {
    const newFields = [...fields];
    const [movedField] = newFields.splice(from, 1);
    newFields.splice(to, 0, movedField);
    setFields(newFields);
    onUpdate({ ...entity, fields: newFields });
  };

  return (
    <div className="fields-editor">
      <div className="fields-list">
        {fields.map((field, index) => (
          <div key={index} className="field-row">
            <div className="drag-handle">⋮⋮</div>
            <div className="field-preview">
              <span className="field-label">{field.label}</span>
              <span className="field-type">{field.type}</span>
              {field.required && <span className="badge">Required</span>}
            </div>
            <button
              className="btn-icon"
              onClick={() => setEditingFieldIndex(index)}
              title="Edit"
            >
              ✎
            </button>
            <button
              className="btn-icon btn-danger"
              onClick={() => handleDeleteField(index)}
              title="Delete"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      {editingFieldIndex !== null && (
        <FieldEditModal
          field={fields[editingFieldIndex]}
          onSave={(updated) => handleUpdateField(editingFieldIndex, updated)}
          onCancel={() => setEditingFieldIndex(null)}
        />
      )}

      {showAddField && (
        <AddFieldForm
          onAdd={handleAddField}
          onCancel={() => setShowAddField(false)}
        />
      )}

      {!showAddField && (
        <button
          className="btn btn-outline"
          onClick={() => setShowAddField(true)}
        >
          + Add Field
        </button>
      )}
    </div>
  );
};
```

### 5.3 Add Field Form

```typescript
const AddFieldForm: React.FC<{
  onAdd: (field: CRMField) => void;
  onCancel: () => void;
}> = ({ onAdd, onCancel }) => {
  const [label, setLabel] = useState("");
  const [type, setType] = useState<FieldType>("text");
  const [required, setRequired] = useState(false);
  const [options, setOptions] = useState<string[]>([]);
  const [errors, setErrors] = useState<string[]>([]);

  const handleAdd = () => {
    const validation = validateField({ label, type, required, options });
    if (!validation.valid) {
      setErrors(validation.errors);
      return;
    }

    const name = normalizeLabelToKey(label);
    onAdd({
      name,
      label,
      type,
      required,
      ...(type === "select" || type === "multi_select" ? { options } : {}),
    });
  };

  return (
    <div className="add-field-form">
      <h4>Add New Field</h4>

      {errors.length > 0 && (
        <div className="errors">
          {errors.map((err, i) => (
            <p key={i} className="error-text">{err}</p>
          ))}
        </div>
      )}

      <div className="form-group">
        <label>Label</label>
        <input
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="e.g., Customer Name"
        />
        <small>Machine key will be auto-generated</small>
      </div>

      <div className="form-group">
        <label>Type</label>
        <select value={type} onChange={(e) => setType(e.target.value as FieldType)}>
          <option value="text">Text</option>
          <option value="textarea">Textarea</option>
          <option value="email">Email</option>
          <option value="phone">Phone</option>
          <option value="url">URL</option>
          <option value="number">Number</option>
          <option value="date">Date</option>
          <option value="datetime">DateTime</option>
          <option value="boolean">Yes/No</option>
          <option value="select">Dropdown (Select)</option>
          <option value="multi_select">Multi-Select</option>
        </select>
      </div>

      {(type === "select" || type === "multi_select") && (
        <div className="form-group">
          <label>Options (one per line)</label>
          <textarea
            value={options.join("\n")}
            onChange={(e) => setOptions(e.target.value.split("\n").filter(Boolean))}
            placeholder="Option 1&#10;Option 2&#10;Option 3"
            rows={3}
          />
        </div>
      )}

      <div className="form-group checkbox">
        <input
          type="checkbox"
          checked={required}
          onChange={(e) => setRequired(e.target.checked)}
        />
        <label>Required field</label>
      </div>

      <div className="form-actions">
        <button className="btn btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="btn btn-primary" onClick={handleAdd}>Add Field</button>
      </div>
    </div>
  );
};
```

### 5.4 Stages Editor Sub-Component

```typescript
const StagesEditor: React.FC<{
  stages: string[];
  onUpdate: (updatedStages: string[]) => void;
}> = ({ stages, onUpdate }) => {
  const [stageList, setStageList] = useState<string[]>(stages);
  const [showAddStage, setShowAddStage] = useState(false);

  const handleAddStage = (name: string) => {
    if (stageList.includes(name)) {
      alert("Stage already exists");
      return;
    }
    const newStages = [...stageList, name];
    setStageList(newStages);
    onUpdate(newStages);
    setShowAddStage(false);
  };

  const handleDeleteStage = (index: number) => {
    if (confirm(`Delete stage "${stageList[index]}"?`)) {
      const newStages = stageList.filter((_, i) => i !== index);
      setStageList(newStages);
      onUpdate(newStages);
    }
  };

  const handleReorderStages = (from: number, to: number) => {
    const newStages = [...stageList];
    const [moved] = newStages.splice(from, 1);
    newStages.splice(to, 0, moved);
    setStageList(newStages);
    onUpdate(newStages);
  };

  return (
    <div className="stages-editor">
      <div className="stages-list">
        {stageList.map((stage, index) => (
          <div key={index} className="stage-row">
            <div className="drag-handle">⋮⋮</div>
            <span className="stage-name">{stage}</span>
            <button
              className="btn-icon btn-danger"
              onClick={() => handleDeleteStage(index)}
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      {!showAddStage && (
        <button
          className="btn btn-outline"
          onClick={() => setShowAddStage(true)}
        >
          + Add Stage
        </button>
      )}

      {showAddStage && (
        <AddStageForm
          onAdd={handleAddStage}
          onCancel={() => setShowAddStage(false)}
        />
      )}
    </div>
  );
};
```

### 5.5 Metadata Editor Sub-Component

```typescript
const MetadataEditor: React.FC<{
  name: string;
  industry: string;
  onUpdate: (name: string, industry: string) => void;
}> = ({ name, industry, onUpdate }) => {
  const [editName, setEditName] = useState(name);
  const [editIndustry, setEditIndustry] = useState(industry);

  return (
    <div className="metadata-editor">
      <div className="form-group">
        <label>CRM Name</label>
        <input
          type="text"
          value={editName}
          onChange={(e) => {
            setEditName(e.target.value);
            onUpdate(e.target.value, editIndustry);
          }}
        />
      </div>

      <div className="form-group">
        <label>Industry</label>
        <input
          type="text"
          value={editIndustry}
          onChange={(e) => {
            setEditIndustry(e.target.value);
            onUpdate(editName, e.target.value);
          }}
        />
      </div>
    </div>
  );
};
```

### 5.6 Integration in CRM Detail Page

**File:** `frontend/src/features/crms/CRMDetailPage.tsx`

```typescript
export const CRMDetailPage: React.FC = () => {
  const { crm_id } = useParams<{ crm_id: string }>();
  const [crm, setCRM] = useState<CRMSummary | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [isSavingChanges, setIsSavingChanges] = useState(false);

  const handleEditCRM = () => {
    setIsEditing(true);
  };

  const handleSaveSchema = async (updatedConfig: CRMConfiguration) => {
    try {
      setIsSavingChanges(true);
      const response = await api.patch(`/crm/${crm_id}/configuration`, {
        configuration: updatedConfig,
      });
      setCRM(response.data.data);
      setIsEditing(false);
    } catch (err) {
      alert("Failed to save CRM: " + err.message);
    } finally {
      setIsSavingChanges(false);
    }
  };

  if (!crm) return <LoadingSpinner />;

  if (isEditing) {
    return (
      <CRMSchemaEditor
        crm={crm.configuration}
        onSave={handleSaveSchema}
        onCancel={() => setIsEditing(false)}
        isLoading={isSavingChanges}
      />
    );
  }

  return (
    <div className="crm-detail">
      <div className="crm-header">
        <h1>{crm.name}</h1>
        <button className="btn btn-primary" onClick={handleEditCRM}>
          Edit CRM
        </button>
      </div>

      {/* CRM Details and Records List */}
      {/* ... existing code ... */}
    </div>
  );
};
```

---

## 6. Record Safety During Schema Evolution

### 6.1 Adding a Field

**Safe operation.** No data loss.

**Behavior:**
- New field is added to schema with default value or NULL
- Existing records automatically support the new field:
  - NULL if no value provided
  - Default value if field has one
  - Empty array/object for complex types
- No record migration needed
- No warnings required

**Database impact:** None (JSONB allows dynamic keys)

### 6.2 Deleting a Field

**Potentially destructive.** Requires user confirmation.

**Behavior:**
1. Check if any existing records have values for this field:
   ```sql
   SELECT COUNT(*) FROM records 
   WHERE crm_id = ? 
   AND entity_name = ? 
   AND (data->>'{field_name}')::text IS NOT NULL;
   ```
2. If count > 0, return 409 with warning:
   - "This field has values in X existing records"
   - "Deleting will permanently remove this data"
   - "Continue anyway?"
3. If user confirms, remove field from schema
4. Existing records retain the field in their data until explicitly cleaned

**Database impact:** None (field remains in record.data but is not in schema)

### 6.3 Renaming a Field

**Moderately risky.** Preserves data but confuses records.

**Behavior:**
1. Check if any records have values for this field
2. If yes, return 409 with options:
   - "Rename field (data will be migrated)"
   - "Cancel"
3. If user confirms:
   - Update schema: change field.name
   - Rename key in all existing records:
     ```python
     for record in records_for_this_crm:
         if old_name in record.data:
             record.data[new_name] = record.data.pop(old_name)
     ```
   - Update records in database

**Recommendation:** For MVP, disallow renaming if records exist. Rename is lower priority.

### 6.4 Changing Field Type

**High risk.** May require data migration.

**Behavior:**
1. Some type changes are safe:
   - text → textarea (both strings)
   - text → email (both strings)
   - text → phone (both strings)
   - text → url (both strings)
   - number → text (coercion)
   - boolean → select (can map true/false to options)

2. Some type changes are unsafe:
   - select → number (options are strings, not numbers)
   - date → number (lose date semantics)
   - email → boolean (incompatible)

3. For unsafe changes:
   - Return 409: "Cannot safely convert field type X → Y with existing records"
   - Recommend: Delete and re-add field (accepting data loss)

4. For safe changes:
   - Apply change
   - Log the change for audit

**Recommendation:** For MVP, restrict type changes to safe conversions only. Document the safe/unsafe pairs.

### 6.5 Record Validation on Creation

When creating a new record, validate against current schema:

```python
def validate_record_against_schema(
    record_data: dict[str, Any],
    entity_schema: CRMEntity
) -> tuple[bool, list[str]]:
    """
    Validate record data against entity schema.
    Returns (is_valid, errors)
    """
    errors = []
    schema_fields = {f.name for f in entity_schema.fields}
    
    for field in entity_schema.fields:
        value = record_data.get(field.name)
        
        # Check required
        if field.required and value is None:
            errors.append(f"Field '{field.label}' is required")
        
        # Validate type
        if value is not None:
            type_error = validate_field_value(value, field.type)
            if type_error:
                errors.append(f"Field '{field.label}': {type_error}")
        
        # Validate select options
        if field.type in ("select", "multi_select") and value is not None:
            if field.type == "select":
                if value not in field.options:
                    errors.append(f"Field '{field.label}': invalid option '{value}'")
            else:  # multi_select
                for v in value:
                    if v not in field.options:
                        errors.append(f"Field '{field.label}': invalid option '{v}'")
    
    # Warn about extra fields (not schema violations, just info)
    extra_fields = set(record_data.keys()) - schema_fields
    if extra_fields:
        warnings.append(f"Record has extra fields not in schema: {extra_fields}")
    
    return len(errors) == 0, errors
```

---

## 7. Database Schema for Editing

### 7.1 Current Schema Assessment

**Location:** `docs/API_CONTRACTS.md` → `crms` table

**Current columns:**
- id, owner_id, name, configuration (JSONB), configuration_version, status, created_at, updated_at

**Analysis:**
- ✅ configuration_version already exists — can use for optimistic locking
- ✅ JSONB configuration can store any field structure
- ✅ Soft deletes (deleted_at) already supported for records
- ✅ Ownership (owner_id) enforced

**What needs adding:** Field edit history (optional but recommended for audit trail)

### 7.2 Optional: Add Edit History Table

**Rationale:** Track who changed what and when. Enables undo/rollback and compliance audits.

```sql
CREATE TABLE crm_configuration_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  crm_id UUID NOT NULL REFERENCES crms(id) ON DELETE CASCADE,
  actor_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE SET NULL,
  change_type TEXT NOT NULL,  -- 'field_added', 'field_updated', 'field_deleted', 'stage_added', etc.
  change_details JSONB NOT NULL,
  configuration_version_before INTEGER,
  configuration_version_after INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_crm_config_history_crm_id 
  ON crm_configuration_history(crm_id, created_at DESC);
```

**Example record:**
```json
{
  "id": "...",
  "crm_id": "...",
  "actor_id": "...",
  "change_type": "field_added",
  "change_details": {
    "field_name": "assigned_agent",
    "field_label": "Assigned Agent",
    "field_type": "select",
    "options": ["Alice", "Bob"]
  },
  "configuration_version_before": 1,
  "configuration_version_after": 2,
  "created_at": "2025-01-15T14:30:00Z"
}
```

**Decision:** Add this table for MVP+1. For MVP, skip audit history but design endpoints to be compatible with it.

### 7.3 No Changes Required for MVP

The existing `crms` table with configuration_version is sufficient:
- `configuration` (JSONB) stores entire schema
- `configuration_version` increments on each edit
- Updated records automatically support new/old fields (JSONB flexibility)
- RLS policies + owner_id enforce access control

---

## 8. AI Tooling for Schema Modifications (AURA Copilot)

### 8.1 Tool Interface for Copilot

Design tools that Copilot/Qwen can call to modify schemas:

```python
# backend/app/services/ai_tools.py

class CRMSchemaTools:
    """Tools for AURA Copilot to modify CRM schemas."""
    
    @staticmethod
    async def add_crm_field(
        crm_id: str,
        label: str,
        field_type: FieldType,
        required: bool = False,
        options: list[str] | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        """Add a field to the CRM schema."""
        # Calls POST /api/v1/crm/{crm_id}/fields internally
        # Returns updated CRMConfiguration or error
        pass
    
    @staticmethod
    async def update_crm_field(
        crm_id: str,
        field_name: str,
        label: str | None = None,
        field_type: FieldType | None = None,
        required: bool | None = None,
        options: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update a field in the CRM schema."""
        # Calls PATCH /api/v1/crm/{crm_id}/fields/{field_name}
        pass
    
    @staticmethod
    async def delete_crm_field(
        crm_id: str,
        field_name: str,
        force: bool = False,
    ) -> dict[str, Any]:
        """Delete a field from the CRM schema."""
        # Calls DELETE /api/v1/crm/{crm_id}/fields/{field_name}
        # force=True bypasses "records affected" warning
        pass
    
    @staticmethod
    async def add_crm_stage(
        crm_id: str,
        stage_name: str,
        position: int | None = None,
    ) -> dict[str, Any]:
        """Add a pipeline stage to the CRM."""
        # Calls POST /api/v1/crm/{crm_id}/stages
        pass
    
    @staticmethod
    async def update_crm_stage(
        crm_id: str,
        stage_name: str,
        new_name: str,
    ) -> dict[str, Any]:
        """Rename a pipeline stage."""
        pass
    
    @staticmethod
    async def delete_crm_stage(
        crm_id: str,
        stage_name: str,
        force: bool = False,
    ) -> dict[str, Any]:
        """Delete a pipeline stage."""
        pass
```

### 8.2 Integration with Copilot

**File:** `backend/app/routers/copilot.py` or similar

**Expose tools to Copilot via OpenAI-compatible function calling:**

```python
COPILOT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_crm_field",
            "description": "Add a new field to a CRM schema",
            "parameters": {
                "type": "object",
                "properties": {
                    "crm_id": {"type": "string", "description": "CRM ID"},
                    "label": {"type": "string", "description": "Human-readable label"},
                    "field_type": {
                        "type": "string",
                        "enum": ["text", "email", "phone", "number", "date", "select", ...],
                        "description": "Field type",
                    },
                    "required": {"type": "boolean", "default": False},
                    "options": {"type": "array", "items": {"type": "string"}, "description": "For select fields"},
                },
                "required": ["crm_id", "label", "field_type"],
            },
        },
    },
    # ... more tools ...
]
```

### 8.3 Validation on Copilot Tool Calls

**All tools must:**
1. Verify the authenticated user owns the CRM
2. Validate input using Pydantic
3. Call backend API endpoints (which enforce RLS)
4. Return structured success/error response

**Example:**
```python
@router.post("/copilot/tool-call/add-field")
async def copilot_add_field(
    tool_call: ToolCall,  # Contains crm_id, label, field_type, etc.
    user_id: CurrentUser,
):
    """Process Copilot's tool call to add a field."""
    try:
        # Validate inputs
        request = AddFieldRequest(**tool_call.parameters)
        
        # Call backend API on user's behalf
        response = await add_field(
            crm_id=request.crm_id,
            body=request,
            user_id=user_id,
        )
        
        return success_response(response)
    except Exception as err:
        return error_response(400, "TOOL_ERROR", str(err))
```

---

## 9. Data Flow: User Action to UI Refresh

### 9.1 Complete Flow Diagram

```
USER EDITS FIELD NAME
    ↓
React Component State Update
    ↓
editingConfig.entities[0].fields[0].label = "New Label"
    ↓
onUpdate() called
    ↓
CRMSchemaEditor updates editingConfig state
    ↓
(No DB write yet)
    ↓
User clicks "Save Changes"
    ↓
Frontend Validation:
  - Check field uniqueness
  - Check required constraints
  - Check select options
    ↓
Validation passes
    ↓
HTTP PATCH /api/v1/crm/{crm_id}/fields/{field_name}
  Body: {
    "label": "New Label",
    "required": false
  }
    ↓
Backend receives request
    ↓
Step 1: Verify user JWT
Step 2: Extract user_id from JWT
Step 3: Query CRM from DB
Step 4: Check owner_id == authenticated user_id
Step 5: Find field in schema
Step 6: Validate updated field (Pydantic CRMField)
Step 7: Check for schema conflicts
Step 8: Update field in entity.fields array
Step 9: Increment configuration_version
Step 10: Save to DB (Supabase)
    ↓
HTTP 200 response:
{
  "data": {
    "configuration": CRMConfiguration,
    "field_updated": {
      "name": "field_name",
      "label": "New Label",
      "type": "text",
      ...
    },
    "configuration_version": 2
  }
}
    ↓
Frontend receives response
    ↓
Update local state:
  setCRM(response.data)
    ↓
Close editor modal
    ↓
Re-render CRM detail page
    ↓
Display updated schema with new field label
    ↓
Show success toast: "CRM updated"
```

### 9.2 Error Handling Flow

```
User clicks "Save Changes"
    ↓
Frontend validation fails
    ↓
Display errors in UI:
  "Field name cannot be empty"
  "Duplicate field label"
    ↓
User fixes errors
    ↓
User clicks "Save Changes" again
    ↓
Frontend validation passes
    ↓
HTTP PATCH request
    ↓
Backend receives request
    ↓
Backend validation fails (e.g., field name already exists)
    ↓
HTTP 409 response:
{
  "error": {
    "code": "CONFLICT",
    "message": "Field 'assigned_agent' already exists",
    "request_id": "..."
  }
}
    ↓
Frontend catches 409
    ↓
Display error toast: "Field already exists"
    ↓
Keep modal open; keep user edits
    ↓
User can try different name or cancel
```

### 9.3 Handling Network Failures

```
HTTP PATCH request sent
    ↓
Network times out or fails
    ↓
Frontend catch block:
  try {
    const resp = await api.patch(...)
  } catch (err) {
    if (err.isNetworkError) {
      showError("Network error. Check your connection and try again.")
      // Keep edits in state
      // Show "Retry" button
    } else {
      showError(err.message)
    }
  }
    ↓
User clicks "Retry"
    ↓
HTTP PATCH request resent
    ↓
(either success or error response)
```

---

## 10. Decision Rationale: Why Generic vs. Hardcoded

### 10.1 Why Generic Field Representation?

**Option A (Rejected): Hardcoded field lists per CRM type**
```typescript
// BAD: Must create new editor for each CRM type
if (crmType === "SalesCRM") {
  return <SalesCRMEditor />;
} else if (crmType === "ServiceCRM") {
  return <ServiceCRMEditor />;
}
```

**Problems:**
- Code duplication across editors
- Bug in one editor not fixed in others
- Adding new CRM type requires new editor component
- Hard to maintain consistency

**Option B (Chosen): Generic, data-driven editor**
```typescript
// GOOD: One component for all CRM types
<CRMSchemaEditor crm={crm} onSave={handleSave} />
// Works for SalesCRM, ServiceCRM, RecruitmentCRM, etc.
```

**Advantages:**
- Single source of truth for field/stage editing logic
- Bug fix applies to all CRM types immediately
- New CRM types automatically supported
- Easier testing and maintenance
- Follows DRY principle

### 10.2 Why This Field Structure?

**Canonical structure chosen:**
```typescript
interface CanonicalField {
  name: string;           // machine key
  label: string;          // human label
  type: FieldType;        // enum of types
  required: boolean;
  options?: string[];     // for select types
}
```

**Why not alternatives?**

❌ **Alternative: Separate label and machine_key generation**
```typescript
{
  label: "Customer Name",
  // Machine key generated on-the-fly
}
```
- Problem: Frontend and backend might generate different machine keys
- Solution: Always store both explicitly

❌ **Alternative: Rich field metadata (description, help text, validation rules)**
```typescript
{
  name: "email",
  label: "Email",
  type: "email",
  validation: { minLength: 5, maxLength: 100 },
  description: "Contact email",
  helpText: "Enter valid email address",
}
```
- Problem: Scope creep; MVP doesn't need these
- Solution: Design for extensibility; keep core minimal
- Future: Add optional fields without breaking existing schemas

✅ **Chosen: Minimal but complete**
- Captures essential metadata
- Extensible (can add fields in future)
- Consistent across layers
- Easy to validate

### 10.3 Why Increment configuration_version?

**Purpose:** Track schema changes for:
1. Optimistic locking (prevent conflicting edits)
2. Audit trail (who changed what)
3. Client-side cache invalidation

**Why not use timestamps?**
- Timestamps can be affected by clock skew
- Version numbers are monotonic and reliable
- Easier to reason about ordering

**Implementation:**
```python
def update_crm_configuration(...):
    # Atomic increment with Supabase
    result = client.rpc("increment_config_version", {
        "p_crm_id": crm_id,
        "p_owner_id": owner_id
    }).execute()
    new_version = result.data["configuration_version_after"]
```

---

## 11. Component Architecture Summary

### 11.1 Backend Architecture

```
┌─ FastAPI Router ─────────────────────────────────┐
│  POST   /crm/generate                            │
│  POST   /crm/{crm_id}/fields                     │
│  PATCH  /crm/{crm_id}/fields/{field_name}        │
│  DELETE /crm/{crm_id}/fields/{field_name}        │
│  PATCH  /crm/{crm_id}/fields/reorder             │
│  (similar for stages)                            │
└─────────────────────────────────────────────────┘
         ↓
┌─ Services Layer ──────────────────────────────────┐
│  FieldExtractor          (extract user fields)   │
│  SchemaPreservation      (validate & repair)     │
│  CRMSchemaTools          (copilot tool calls)    │
└─────────────────────────────────────────────────┘
         ↓
┌─ Database Layer ──────────────────────────────────┐
│  CRMRepository           (Supabase Postgrest)    │
│  - create_crm()                                  │
│  - update_crm_configuration()                    │
│  - list_crms()                                   │
│  - get_crm()                                     │
└─────────────────────────────────────────────────┘
         ↓
┌─ Supabase ────────────────────────────────────────┐
│  crms table (with RLS)                           │
│  records table (with RLS)                        │
│  configuration_version tracking                 │
└─────────────────────────────────────────────────┘
```

### 11.2 Frontend Architecture

```
┌─ CRMDetailPage ───────────────────────────────────┐
│  [Edit CRM] button                               │
│  Display current schema                          │
└─────────────────────────────────────────────────┘
         ↓
   (user clicks [Edit CRM])
         ↓
┌─ CRMSchemaEditor ─────────────────────────────────┐
│  - Local editing state                           │
│  - Tab navigation: Fields | Stages | Metadata    │
│  - [Cancel] [Save Changes] buttons               │
└─────────────────────────────────────────────────┘
    ↓                                    ↓
┌─ FieldsEditor ─┐              ┌─ StagesEditor ─┐
│  List fields   │              │  List stages   │
│  + Add Field   │              │  + Add Stage   │
│  Edit/Delete   │              │  Edit/Delete   │
│  Reorder       │              │  Reorder       │
└────────────────┘              └────────────────┘
         ↓
   (user clicks [Save Changes])
         ↓
┌─ Frontend Validation ─────────────────────────────┐
│  - Check field uniqueness                        │
│  - Check select options non-empty                │
│  - Check required constraints                    │
└─────────────────────────────────────────────────┘
         ↓
   (validation passes)
         ↓
┌─ API Calls ───────────────────────────────────────┐
│  PATCH /api/v1/crm/{crm_id}/fields/...           │
│  (or POST, DELETE, etc.)                         │
└─────────────────────────────────────────────────┘
         ↓
   (backend updates DB)
         ↓
┌─ State Update ────────────────────────────────────┐
│  setCRM(response.data)                           │
│  Close editor modal                              │
│  Re-render detail page                           │
└─────────────────────────────────────────────────┘
```

---

## 12. Implementation Checklist

### Phase 1: Fix Field Preservation (CRITICAL)

- [ ] **Enhance LLM Prompt** (`ollama_provider.py`)
  - Add FIELD PRESERVATION REQUIREMENT section to system prompt
  - Test that Qwen generates all N requested fields

- [ ] **Integrate SchemaPreservation in Router** (`crm.py`)
  - Import SchemaPreservation, FieldExtractor
  - Call validate_and_repair_schema() after provider.generate_crm_config()
  - Include field_analysis in response

- [ ] **Add Validation Test** (`test_custom_crm_bug_fix.py`)
  - Test: 5 fields requested → 5 fields generated
  - Test: 10 fields requested → 10 fields generated
  - Test: Missing fields are automatically repaired

- [ ] **Verify No Regressions**
  - Run existing test suite
  - Check field counts in existing CRM types

### Phase 2: Backend API for Schema Editing

- [ ] **Implement POST /crm/{crm_id}/fields** (add field)
- [ ] **Implement PATCH /crm/{crm_id}/fields/{field_name}** (update field)
- [ ] **Implement DELETE /crm/{crm_id}/fields/{field_name}** (delete field)
- [ ] **Implement PATCH /crm/{crm_id}/fields/reorder** (reorder fields)
- [ ] **Implement stage endpoints** (similar to field endpoints)
- [ ] **Add authorization tests** (RLS + ownership checks)
- [ ] **Add API contract documentation** (update API_CONTRACTS.md)

### Phase 3: Frontend CRM Schema Editor

- [ ] **Create CRMSchemaEditor component** (generic, no hardcoded fields)
- [ ] **Create FieldsEditor sub-component** (list, add, edit, delete, reorder)
- [ ] **Create StagesEditor sub-component** (similar)
- [ ] **Create AddFieldForm** (with type selector and options)
- [ ] **Implement drag-to-reorder** (for fields and stages)
- [ ] **Add frontend validation** (before sending to backend)
- [ ] **Integrate into CRMDetailPage** ([Edit CRM] button)
- [ ] **Add error handling and success messages**

### Phase 4: Copilot Integration (Optional for MVP)

- [ ] **Define CRMSchemaTools** for Copilot
- [ ] **Expose tools via OpenAI function calling**
- [ ] **Add authorization checks**
- [ ] **Test Copilot can modify schemas**

### Phase 5: Optional: Edit History Table

- [ ] **Create crm_configuration_history table**
- [ ] **Log field/stage changes to history**
- [ ] **Create GET endpoint to retrieve history**

---

## 13. Testing Strategy

### 13.1 Unit Tests

**Field Extraction:**
```python
test_extract_5_fields_from_prompt()
test_extract_10_fields_from_prompt()
test_extract_fields_with_type_annotations()
test_deduplicate_extracted_fields()
```

**Schema Preservation:**
```python
test_repair_missing_field()
test_field_count_validation()
test_add_missing_fields_to_schema()
```

**Field Validation:**
```python
test_validate_field_uniqueness()
test_validate_select_options()
test_validate_required_fields()
```

### 13.2 Integration Tests

**Endpoint Tests:**
```python
test_add_field_to_crm()
test_update_field_label()
test_delete_field_with_no_records()
test_delete_field_with_records_fails()
test_reorder_fields()
```

**Authorization Tests:**
```python
test_user_cannot_edit_other_users_crm()
test_unauthenticated_request_fails()
test_ownership_check_enforced()
```

**End-to-End Tests:**
```python
test_generate_crm_with_5_fields_preserves_all_fields()
test_edit_crm_schema_and_create_record_with_new_field()
test_delete_field_warns_about_affected_records()
```

### 13.3 Frontend Tests

**Component Tests:**
```typescript
test_render_fields_list()
test_add_field_form_validation()
test_reorder_fields_updates_order()
test_delete_field_shows_confirmation()
```

**Integration Tests:**
```typescript
test_edit_crm_saves_to_backend()
test_error_response_shown_to_user()
test_success_message_displayed()
test_cancel_discards_unsaved_changes()
```

---

## 14. API Contract Updates

### 14.1 New Request/Response Schemas

**AddFieldRequest:**
```python
class AddFieldRequest(StrictModel):
    label: str = Field(min_length=1, max_length=100)
    type: FieldType
    required: bool = False
    options: list[str] | None = None
    description: str = ""
```

**UpdateFieldRequest:**
```python
class UpdateFieldRequest(StrictModel):
    label: str | None = None
    type: FieldType | None = None
    required: bool | None = None
    options: list[str] | None = None
    description: str | None = None
```

**FieldAddedResponse:**
```python
class FieldAddedResponse(StrictModel):
    configuration: CRMConfiguration
    field_added: CRMField
    configuration_version: int
```

### 14.2 Updated CRM Generation Response

```python
class GenerateCRMData(StrictModel):
    configuration: CRMConfiguration
    warnings: list[str] = []
    field_analysis: FieldValidationReport  # NEW
```

---

## 15. Security Considerations

### 15.1 Authorization Enforcement

**Every endpoint must:**
1. Verify JWT signature
2. Extract user_id from verified JWT
3. Query CRM with WHERE owner_id = user_id
4. Return 403 if CRM not owned by user
5. Return 404 if CRM not found (don't leak existence)

### 15.2 Input Validation

**Every endpoint must:**
1. Validate request body with Pydantic
2. Validate field names (regex: `^[a-z][a-z0-9_]{0,62}$`)
3. Validate field types against allowed enum
4. Check for reserved field names
5. Validate select options (non-empty, unique, non-special-chars)

### 15.3 Record Safety

**When deleting a field:**
1. Query records table to check for existing values
2. Warn user if field is in use
3. Only delete if user explicitly confirms (with accurate warning message)

### 15.4 No Arbitrary Code Execution

**Always validate LLM output:**
1. Qwen generates field definitions (JSON)
2. Backend validates with Pydantic before using
3. Never execute generated code or SQL
4. Never interpolate generated values without validation

---

## 16. Known Limitations & Future Work

### 16.1 MVP Limitations

1. **Single entity per CRM:** MVP assumes one main entity (e.g., "lead")
   - Future: Support multiple entities (accounts, contacts, opportunities)

2. **No field renaming:** Renaming risks data confusion
   - Future: Add migration support with data rewriting

3. **No type migration:** Cannot convert select → number safely
   - Future: Add type-migration wizard with preview

4. **No field descriptions:** Description field added to schema but not used in MVP
   - Future: Show descriptions in record forms

5. **No field ordering on records:** Fields always in schema order
   - Future: Per-user field ordering preferences

6. **No field groups:** All fields in one flat list
   - Future: Group fields into sections (Contact Info, Sales Info, etc.)

### 16.2 Future Enhancements

- Field edit history / audit trail
- Rollback CRM schema to previous version
- Bulk record migration when field type changes
- Field templates (reusable field sets)
- Conditional field visibility (show field X only if field Y = Z)
- Custom validation rules per field
- Field-level permissions (field owner, read-only, etc.)

---

## 17. Deployment & Rollout Plan

### 17.1 Local Development

1. Start with Phase 1 (field preservation fix) — lowest risk
2. Test with unit tests and end-to-end tests
3. Verify no regression in existing CRM generation

### 17.2 Staging Deployment

1. Deploy all backend changes (phases 1-2)
2. Deploy frontend schema editor (phase 3)
3. Run full test suite
4. Manual testing with various CRM types

### 17.3 Production Deployment

1. Backward compatibility: Old CRM configurations should still load
2. No data migration needed (JSONB schema is flexible)
3. Gradual rollout: 10% → 50% → 100% of users
4. Monitor for errors in production logs
5. Have rollback plan (revert backend, keep frontend disabled)

### 17.4 User Communication

- Announce new "Edit CRM" feature
- Show tutorial: how to add/edit fields
- Link to documentation

---

## Summary

This design provides a **universal, data-driven solution** for CRM generation and post-generation editing:

1. **Field Preservation** — Extract all user fields, validate against generated schema, repair missing fields
2. **Generic Editor** — One React component works for any CRM type (Sales, Service, Recruitment, etc.)
3. **Backend API** — RESTful endpoints for field/stage CRUD with full authorization and validation
4. **Canonical Representation** — Single field structure flows through entire system
5. **Record Safety** — Schema changes account for existing records (safe adds, dangerous deletes warned)

**Key principle:** Build once, scale to infinite CRM types.

