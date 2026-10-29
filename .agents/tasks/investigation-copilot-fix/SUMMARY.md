# AURA Copilot Investigation — Quick Summary

## Problem Statement

When a user asks the AURA Copilot to "add a lead," the system:
1. Creates a record in the **wrong entity** (falls back to the first entity instead of clarifying)
2. Displays **raw JSON tool-call markers** in the conversation UI

## Root Causes (8 Identified)

### Critical (Must Fix First)

| ID | Issue | Location | Fix |
|----|-------|----------|-----|
| RC-001 | Silent entity fallback | `ai_tools.py:_resolve_entity()` | Return `None` instead of `entities[0]` when no match found |
| RC-002 | Hardcoded example entity names | `copilot.py:_build_system_prompt()` | Use actual CRM entities in examples, not "lead", "customer" |

### High Priority

| ID | Issue | Location | Fix |
|----|-------|----------|-----|
| RC-003 | Missing explicit entity list in prompt | `copilot.py` | Add "VALID ENTITY NAMES: ..." section |
| RC-004 | No entity validation before tool execution | `copilot.py:execute_tool_call()` | Validate entity_name exists in CRM config |
| RC-005 | Incomplete regex for tool-call parsing | `AIAssistantDrawer.tsx:parseToolCalls()` | Use JSON parser instead of regex; handle failures |

### Medium Priority

| ID | Issue | Location | Fix |
|----|-------|----------|-----|
| RC-006 | No pre-validation of LLM-generated arguments | `copilot.py:_universal_action_reply()` | Validate entity_name before generating tool call |
| RC-007 | Missing required-field collection | `ai_tools.py, copilot.py` | Ask user for missing required fields before creating record |
| RC-008 | Raw tool-call display on parsing failure | `AIAssistantDrawer.tsx` | Never display unparseable markers to users |

## Impact

- **Records created in wrong entities** → Data integrity issue
- **LLM learns invalid entity names from examples** → Hallucinates non-existent entities
- **Raw JSON in UI** → Confusing user experience
- **No field collection workflow** → Validation errors instead of guided input

## Files to Modify

### Backend (3 files)
- `backend/app/routers/copilot.py` — System prompt, entity validation, tool dispatch
- `backend/app/services/ai_tools.py` — Entity resolution, record creation
- `backend/app/routers/records.py` — Optional: add entity validation

### Frontend (1 file)
- `frontend/src/features/ai-assistant/AIAssistantDrawer.tsx` — Tool-call parsing, display

## Implementation Phases

1. **Phase 1 (CRITICAL)**: System prompt + entity context → Ensures LLM uses valid entity names
2. **Phase 2 (CRITICAL)**: Entity resolution + validation → Prevents fallback to wrong entity
3. **Phase 3 (HIGH)**: Frontend parsing improvements → Raw JSON never displayed
4. **Phase 4 (MEDIUM)**: Required field collection → Better UX for incomplete data
5. **Phase 5 (ALL)**: Comprehensive testing → 14 test scenarios covering all cases

## Success Criteria

- ✓ "Add a lead" uses actual lead entity (or asks for clarification)
- ✓ No invalid entity names in tool calls
- ✓ Backend validates entity names before execution
- ✓ Raw TOOL_CALL markers never appear in UI
- ✓ Missing fields collected via conversation (not validation errors)
- ✓ All test scenarios pass

## Next Steps

1. Read `INVESTIGATION_REPORT.md` for detailed analysis
2. Read `ROOT_CAUSES.json` for structured root causes and test scenarios
3. Design phase will create detailed API contracts and implementation plans
4. Implementation follows design in dependency order (Phase 1 → 2 → 3 → 4 → 5)

---

**Investigation Date**: 2025-10-29  
**Status**: Complete → Ready for Design Phase
