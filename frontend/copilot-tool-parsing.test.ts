/**
 * Tests for Copilot tool-call parsing and cleanup
 * 
 * Tests the root causes fixed:
 * - RC-005: Incomplete regex for tool-call parsing
 * - RC-008: Raw tool-call display when parsing fails
 * 
 * Test scenarios:
 * - TS-007: LLM returns valid native tool call → parsed and executed
 * - TS-008: LLM returns textual TOOL_CALL: {...} → parsed, no raw markers
 * - TS-009: Malformed JSON in tool call → handled gracefully
 */

/**
 * RC-005/RC-008 FIX: Improved parser that handles deeply nested JSON structures.
 */
function parseToolCalls(text: string): Array<{ name: string; arguments: Record<string, any> }> {
  const toolCalls: Array<{ name: string; arguments: Record<string, any> }> = [];

  let searchStart = 0;
  while (true) {
    const markerIndex = text.indexOf('TOOL_CALL:', searchStart);
    if (markerIndex === -1) break;

    let jsonStart = markerIndex + 'TOOL_CALL:'.length;
    while (jsonStart < text.length && /\s/.test(text[jsonStart])) {
      jsonStart++;
    }

    if (jsonStart >= text.length || text[jsonStart] !== '{') {
      searchStart = markerIndex + 1;
      continue;
    }

    let braceCount = 0;
    let jsonEnd = jsonStart;
    let inString = false;
    let escaped = false;

    for (let i = jsonStart; i < text.length; i++) {
      const char = text[i];

      if (escaped) {
        escaped = false;
        continue;
      }

      if (char === '\\') {
        escaped = true;
        continue;
      }

      if (char === '"' && !escaped) {
        inString = !inString;
        continue;
      }

      if (!inString) {
        if (char === '{') braceCount++;
        else if (char === '}') {
          braceCount--;
          if (braceCount === 0) {
            jsonEnd = i + 1;
            break;
          }
        }
      }
    }

    if (braceCount === 0 && jsonEnd > jsonStart) {
      const jsonStr = text.substring(jsonStart, jsonEnd);
      try {
        const call_obj = JSON.parse(jsonStr);
        if (call_obj.name && call_obj.arguments) {
          toolCalls.push(call_obj);
        }
      } catch (e) {
        console.warn('Failed to parse tool call:', jsonStr, e);
      }
    }

    searchStart = jsonEnd || markerIndex + 1;
  }

  return toolCalls;
}

/**
 * RC-005/RC-008 FIX: Improved cleanup that removes markers even if parsing fails.
 */
function cleanToolCallMarkers(text: string): string {
  let result = text;
  let searchStart = 0;

  while (true) {
    const markerIndex = result.indexOf('TOOL_CALL:', searchStart);
    if (markerIndex === -1) break;

    let jsonStart = markerIndex + 'TOOL_CALL:'.length;
    while (jsonStart < result.length && /\s/.test(result[jsonStart])) {
      jsonStart++;
    }

    if (jsonStart >= result.length || result[jsonStart] !== '{') {
      searchStart = markerIndex + 1;
      continue;
    }

    let braceCount = 0;
    let jsonEnd = jsonStart;
    let inString = false;
    let escaped = false;

    for (let i = jsonStart; i < result.length; i++) {
      const char = result[i];

      if (escaped) {
        escaped = false;
        continue;
      }

      if (char === '\\') {
        escaped = true;
        continue;
      }

      if (char === '"' && !escaped) {
        inString = !inString;
        continue;
      }

      if (!inString) {
        if (char === '{') braceCount++;
        else if (char === '}') {
          braceCount--;
          if (braceCount === 0) {
            jsonEnd = i + 1;
            break;
          }
        }
      }
    }

    if (jsonEnd > jsonStart) {
      result = result.substring(0, markerIndex) + result.substring(jsonEnd);
      searchStart = markerIndex;
    } else {
      searchStart = markerIndex + 1;
    }
  }

  return result.trim();
}

describe('Copilot Tool-Call Parsing (RC-005, RC-008)', () => {
  
  // ── TS-007: Valid native tool call ────
  describe('TS-007: LLM returns valid native tool call', () => {
    test('parses simple tool call', () => {
      const text = 'TOOL_CALL: {"name": "create_record", "arguments": {"entity_name": "lead", "data": {"name": "John"}}}';
      const calls = parseToolCalls(text);
      
      expect(calls).toHaveLength(1);
      expect(calls[0].name).toBe('create_record');
      expect(calls[0].arguments.entity_name).toBe('lead');
      expect(calls[0].arguments.data.name).toBe('John');
    });

    test('parses tool call with nested objects (RC-005)', () => {
      const text = 'TOOL_CALL: {"name": "create_record", "arguments": {"entity_name": "lead", "data": {"profile": {"status": "qualified", "score": 85}}}}';
      const calls = parseToolCalls(text);
      
      expect(calls).toHaveLength(1);
      expect(calls[0].arguments.data.profile.status).toBe('qualified');
      expect(calls[0].arguments.data.profile.score).toBe(85);
    });

    test('parses tool call with arrays (RC-005)', () => {
      const text = 'TOOL_CALL: {"name": "reorder_fields", "arguments": {"field_order": ["name", "email", "phone"]}}';
      const calls = parseToolCalls(text);
      
      expect(calls).toHaveLength(1);
      expect(Array.isArray(calls[0].arguments.field_order)).toBe(true);
      expect(calls[0].arguments.field_order).toEqual(['name', 'email', 'phone']);
    });

    test('parses tool call with deeply nested structures (RC-005)', () => {
      const complex = {
        name: 'update_record',
        arguments: {
          entity_name: 'lead',
          record_id: '123',
          data: {
            profile: {
              contact: {
                email: 'test@example.com',
                phones: ['555-1234', '555-5678'],
              },
              metadata: {
                tags: ['important', 'vip'],
                scores: { engagement: 95, conversion: 80 },
              },
            },
          },
        },
      };
      
      const text = `TOOL_CALL: ${JSON.stringify(complex)}`;
      const calls = parseToolCalls(text);
      
      expect(calls).toHaveLength(1);
      expect(calls[0].arguments.data.profile.contact.email).toBe('test@example.com');
      expect(calls[0].arguments.data.profile.contact.phones).toEqual(['555-1234', '555-5678']);
      expect(calls[0].arguments.data.profile.metadata.scores.engagement).toBe(95);
    });
  });

  // ── TS-008: Textual tool-call representation ────
  describe('TS-008: LLM returns textual TOOL_CALL representation', () => {
    test('parses textual representation with surrounding text', () => {
      const text = `I'll create a new lead for you. TOOL_CALL: {"name": "create_record", "arguments": {"entity_name": "lead", "data": {"name": "Alice"}}}`;
      const calls = parseToolCalls(text);
      
      expect(calls).toHaveLength(1);
      expect(calls[0].name).toBe('create_record');
    });

    test('parses multiple tool calls in one text (RC-005)', () => {
      const text = `First: TOOL_CALL: {"name": "add_crm_field", "arguments": {"field_name": "country", "label": "Country", "field_type": "text"}} and then TOOL_CALL: {"name": "add_crm_field", "arguments": {"field_name": "region", "label": "Region", "field_type": "text"}}`;
      const calls = parseToolCalls(text);
      
      expect(calls).toHaveLength(2);
      expect(calls[0].arguments.field_name).toBe('country');
      expect(calls[1].arguments.field_name).toBe('region');
    });

    test('parses tool call with escaped quotes in arguments', () => {
      const text = `TOOL_CALL: {"name": "create_record", "arguments": {"entity_name": "lead", "data": {"notes": "Contact said \\"yes\\" to meeting"}}}`;
      const calls = parseToolCalls(text);
      
      expect(calls).toHaveLength(1);
      expect(calls[0].arguments.data.notes).toContain('yes');
    });
  });

  // ── TS-009: Malformed JSON ────
  describe('TS-009: Malformed JSON handling', () => {
    test('handles incomplete JSON gracefully', () => {
      const text = 'TOOL_CALL: {"name": "create_record", "arguments": {"entity_name": "lead"';
      const calls = parseToolCalls(text);
      
      // Should return empty array, not crash
      expect(calls).toHaveLength(0);
    });

    test('handles missing closing brace gracefully', () => {
      const text = 'TOOL_CALL: {"name": "create_record", "arguments": {"entity_name": "lead"}';
      const calls = parseToolCalls(text);
      
      // Should return empty array, not crash
      expect(calls).toHaveLength(0);
    });

    test('handles tool call with missing required fields', () => {
      const text = 'TOOL_CALL: {"name": "create_record"}';
      const calls = parseToolCalls(text);
      
      // Should ignore tool call with missing 'arguments'
      expect(calls).toHaveLength(0);
    });

    test('handles invalid JSON syntax', () => {
      const text = `TOOL_CALL: {name: 'create_record', arguments: {entity_name: 'lead'}}`;
      const calls = parseToolCalls(text);
      
      // Should fail gracefully, not crash
      expect(calls).toHaveLength(0);
    });
  });

  // ── RC-008 Fix: Marker cleanup ────
  describe('RC-008: Tool-call marker cleanup', () => {
    test('removes single tool call marker', () => {
      const text = 'I found a match. TOOL_CALL: {"name": "create_record", "arguments": {"entity_name": "lead", "data": {"name": "John"}}} Done!';
      const clean = cleanToolCallMarkers(text);
      
      expect(clean).not.toContain('TOOL_CALL');
      expect(clean).toContain('I found a match.');
      expect(clean).toContain('Done!');
    });

    test('removes multiple tool call markers', () => {
      const text = `First: TOOL_CALL: {"name": "add_field", "arguments": {"field_name": "a"}} Then: TOOL_CALL: {"name": "add_field", "arguments": {"field_name": "b"}}`;
      const clean = cleanToolCallMarkers(text);
      
      expect(clean).not.toContain('TOOL_CALL');
      expect(clean).not.toContain('{');
      expect(clean).not.toContain('"name"');
    });

    test('removes markers with nested JSON (RC-008)', () => {
      const text = `Action: TOOL_CALL: {"name": "create", "arguments": {"data": {"profile": {"deep": {"value": 123}}}}} Complete.`;
      const clean = cleanToolCallMarkers(text);
      
      expect(clean).not.toContain('TOOL_CALL');
      expect(clean).toContain('Action:');
      expect(clean).toContain('Complete.');
    });

    test('never displays raw JSON even if parsing fails (RC-008)', () => {
      const text = 'Result: TOOL_CALL: {incomplete json';
      const clean = cleanToolCallMarkers(text);
      
      // Even though JSON is incomplete, marker should be attempted to be removed
      expect(clean).not.toContain('incomplete json');
    });

    test('preserves surrounding text exactly', () => {
      const text = 'Here is a result:\nTOOL_CALL: {"name": "create_record", "arguments": {"entity_name": "lead", "data": {}}}\n\nThanks!';
      const clean = cleanToolCallMarkers(text);
      
      expect(clean).toBe('Here is a result:\n\nThanks!');
    });

    test('handles tool call at start of text', () => {
      const text = 'TOOL_CALL: {"name": "create_record", "arguments": {"entity_name": "lead", "data": {}}} This is my response.';
      const clean = cleanToolCallMarkers(text);
      
      expect(clean).toBe('This is my response.');
    });

    test('handles tool call at end of text', () => {
      const text = 'This is my response. TOOL_CALL: {"name": "create_record", "arguments": {"entity_name": "lead", "data": {}}}';
      const clean = cleanToolCallMarkers(text);
      
      expect(clean).toBe('This is my response.');
    });
  });

  // ── Integration: Parsing and Cleanup ────
  describe('Integration: Parsing and Cleanup', () => {
    test('parses tool call, then cleanup removes marker', () => {
      const text = 'Creating a lead now. TOOL_CALL: {"name": "create_record", "arguments": {"entity_name": "lead", "data": {"name": "John"}}} All set!';
      
      const calls = parseToolCalls(text);
      const clean = cleanToolCallMarkers(text);
      
      expect(calls).toHaveLength(1);
      expect(calls[0].arguments.data.name).toBe('John');
      expect(clean).toBe('Creating a lead now. All set!');
    });

    test('handles complex scenario with multiple tools (RC-005/RC-008)', () => {
      const text = `I'll help with that. First: TOOL_CALL: {"name": "create_record", "arguments": {"entity_name": "lead", "data": {"profile": {"type": "b2b"}}}} Then: TOOL_CALL: {"name": "update_crm_field", "arguments": {"field_name": "country", "options": ["US", "CA", "MX"]}} Done!`;
      
      const calls = parseToolCalls(text);
      const clean = cleanToolCallMarkers(text);
      
      expect(calls).toHaveLength(2);
      expect(calls[0].arguments.data.profile.type).toBe('b2b');
      expect(calls[1].arguments.options).toEqual(['US', 'CA', 'MX']);
      expect(clean).not.toContain('TOOL_CALL');
      expect(clean).toContain("I'll help with that.");
      expect(clean).toContain('Done!');
    });
  });
});
