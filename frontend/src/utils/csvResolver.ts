import { CRMField } from '@/types/crm';

/**
 * Normalize a header string for matching.
 *
 * 1. Strips leading and trailing whitespace.
 * 2. Strips UTF-8 BOM characters (\ufeff, \uffef).
 * 3. Converts to lowercase.
 * 4. Collapses runs of whitespace, underscores, and hyphens into a single space.
 */
export function normalizeHeader(value: string): string {
  if (!value) return '';
  return value
    .replace(/^[\ufeff\uffef]+/, '')
    .trim()
    .toLowerCase()
    .replace(/[\s_\-]+/g, ' ')
    .trim();
}

/**
 * Robust RFC 4180 CSV parser for browser environments.
 * Correctly parses quoted fields, escaped quotes (""), commas, and CRLF/LF newlines.
 */
export function parseCSV(text: string): {
  headers: string[];
  rows: string[][];
  error?: string;
} {
  if (!text || !text.replace(/^[\ufeff\uffef]+/, '').trim()) {
    return { headers: [], rows: [], error: 'CSV file is empty.' };
  }

  const cleaned = text.replace(/^[\ufeff\uffef]+/, '');
  const rows: string[][] = [];
  let currentRow: string[] = [];
  let currentField = '';
  let insideQuotes = false;
  let i = 0;

  while (i < cleaned.length) {
    const char = cleaned[i];
    const nextChar = cleaned[i + 1];

    if (insideQuotes) {
      if (char === '"' && nextChar === '"') {
        // Escaped double quote
        currentField += '"';
        i += 2;
        continue;
      }
      if (char === '"') {
        // End of quoted field
        insideQuotes = false;
        i++;
        continue;
      }
      currentField += char;
      i++;
    } else {
      if (char === '"') {
        insideQuotes = true;
        i++;
      } else if (char === ',') {
        currentRow.push(currentField.trim());
        currentField = '';
        i++;
      } else if (char === '\r' && nextChar === '\n') {
        currentRow.push(currentField.trim());
        currentField = '';
        if (currentRow.some((c) => c.length > 0)) {
          rows.push(currentRow);
        }
        currentRow = [];
        i += 2;
      } else if (char === '\n' || char === '\r') {
        currentRow.push(currentField.trim());
        currentField = '';
        if (currentRow.some((c) => c.length > 0)) {
          rows.push(currentRow);
        }
        currentRow = [];
        i++;
      } else {
        currentField += char;
        i++;
      }
    }
  }

  // Final field / row
  if (currentField.length > 0 || currentRow.length > 0) {
    currentRow.push(currentField.trim());
    if (currentRow.some((c) => c.length > 0)) {
      rows.push(currentRow);
    }
  }

  if (rows.length === 0) {
    return { headers: [], rows: [], error: 'CSV file has no content.' };
  }

  const headers = rows[0];
  const dataRows = rows.slice(1);
  return { headers, rows: dataRows };
}

export interface HeaderResolution {
  index: number;
  rawHeader: string;
  canonicalName: string | null;
  displayLabel: string | null;
  field: CRMField | null;
  status: 'matched' | 'unknown' | 'ambiguous' | 'duplicate' | 'empty';
  errorMessage?: string;
}

export interface CSVResolutionResult {
  isValid: boolean;
  resolutions: HeaderResolution[];
  headerMap: Record<string, string>; // rawHeader -> canonicalName
  indexMap: Record<number, string>;  // columnIndex -> canonicalName
  errors: string[];
  warnings: string[];
  unknownHeaders: string[];
  duplicateFields: Record<string, string[]>;
  ambiguousHeaders: Record<string, string[]>;
}

/**
 * Universal schema-driven CSV header resolver.
 * Maps CSV column headers to canonical entity fields using tiered resolution:
 *   Tier 1: Exact canonical field name (name === raw)
 *   Tier 2: Exact display label or alias (label === raw)
 *   Tier 3: Case-insensitive canonical name
 *   Tier 4: Case-insensitive display label or alias
 *   Tier 5: Normalized separators & whitespace (underscores vs spaces)
 */
export function resolveCSVHeaders(
  headers: string[],
  fields: CRMField[],
  entityLabel: string = 'Entity'
): CSVResolutionResult {
  if (!headers || headers.length === 0) {
    return {
      isValid: false,
      resolutions: [],
      headerMap: {},
      indexMap: {},
      errors: ['CSV has no header row.'],
      warnings: [],
      unknownHeaders: [],
      duplicateFields: {},
      ambiguousHeaders: {},
    };
  }

  const resolutions: HeaderResolution[] = [];
  const unknownHeaders: string[] = [];
  const ambiguousHeaders: Record<string, string[]> = {};
  const emptyIndices: number[] = [];

  headers.forEach((raw, idx) => {
    const cleaned = raw.replace(/^[\ufeff\uffef]+/, '').trim();
    if (!cleaned) {
      emptyIndices.push(idx + 1);
      resolutions.push({
        index: idx,
        rawHeader: raw,
        canonicalName: null,
        displayLabel: null,
        field: null,
        status: 'empty',
        errorMessage: `Empty column header at position ${idx + 1}`,
      });
      return;
    }

    const norm = normalizeHeader(cleaned);
    let matchedField: CRMField | null = null;
    let candidates: CRMField[] = [];

    // Tier 1: Exact canonical name
    candidates = fields.filter((f) => f.name === cleaned);
    if (candidates.length === 1) {
      matchedField = candidates[0];
    } else if (candidates.length > 1) {
      ambiguousHeaders[raw] = candidates.map((c) => c.name);
      resolutions.push({
        index: idx,
        rawHeader: raw,
        canonicalName: null,
        displayLabel: null,
        field: null,
        status: 'ambiguous',
        errorMessage: `Ambiguous header: matches multiple fields (${candidates.map((c) => c.name).join(', ')})`,
      });
      return;
    }

    // Tier 2: Exact display label
    if (!matchedField) {
      candidates = fields.filter((f) => f.label === cleaned);
      if (candidates.length === 1) {
        matchedField = candidates[0];
      } else if (candidates.length > 1) {
        ambiguousHeaders[raw] = candidates.map((c) => c.name);
        resolutions.push({
          index: idx,
          rawHeader: raw,
          canonicalName: null,
          displayLabel: null,
          field: null,
          status: 'ambiguous',
        });
        return;
      }
    }

    // Tier 3: Case-insensitive canonical name
    if (!matchedField) {
      candidates = fields.filter((f) => f.name.toLowerCase() === cleaned.toLowerCase());
      if (candidates.length === 1) {
        matchedField = candidates[0];
      } else if (candidates.length > 1) {
        ambiguousHeaders[raw] = candidates.map((c) => c.name);
        resolutions.push({
          index: idx,
          rawHeader: raw,
          canonicalName: null,
          displayLabel: null,
          field: null,
          status: 'ambiguous',
        });
        return;
      }
    }

    // Tier 4: Case-insensitive display label
    if (!matchedField) {
      candidates = fields.filter((f) => f.label.toLowerCase() === cleaned.toLowerCase());
      if (candidates.length === 1) {
        matchedField = candidates[0];
      } else if (candidates.length > 1) {
        ambiguousHeaders[raw] = candidates.map((c) => c.name);
        resolutions.push({
          index: idx,
          rawHeader: raw,
          canonicalName: null,
          displayLabel: null,
          field: null,
          status: 'ambiguous',
        });
        return;
      }
    }

    // Tier 5: Normalized separators & whitespace
    if (!matchedField) {
      candidates = fields.filter(
        (f) => norm === normalizeHeader(f.name) || norm === normalizeHeader(f.label)
      );
      if (candidates.length === 1) {
        matchedField = candidates[0];
      } else if (candidates.length > 1) {
        ambiguousHeaders[raw] = candidates.map((c) => c.name);
        resolutions.push({
          index: idx,
          rawHeader: raw,
          canonicalName: null,
          displayLabel: null,
          field: null,
          status: 'ambiguous',
        });
        return;
      }
    }

    if (matchedField) {
      resolutions.push({
        index: idx,
        rawHeader: raw,
        canonicalName: matchedField.name,
        displayLabel: matchedField.label,
        field: matchedField,
        status: 'matched',
      });
    } else {
      unknownHeaders.push(raw);
      resolutions.push({
        index: idx,
        rawHeader: raw,
        canonicalName: null,
        displayLabel: null,
        field: null,
        status: 'unknown',
        errorMessage: `Unknown column: does not match any field in ${entityLabel}`,
      });
    }
  });

  const errors: string[] = [];
  const warnings: string[] = [];

  if (emptyIndices.length > 0) {
    errors.push(`CSV contains empty column header at position(s): ${emptyIndices.join(', ')}.`);
  }

  if (unknownHeaders.length > 0) {
    const quoted = unknownHeaders.map((h) => (h.includes(' ') ? `'${h}'` : h)).join(', ');
    errors.push(
      `Unknown CSV columns: ${quoted}. Column(s) do not match any field name or display label in entity '${entityLabel}'.`
    );
  }

  if (Object.keys(ambiguousHeaders).length > 0) {
    for (const [hdr, cands] of Object.entries(ambiguousHeaders)) {
      errors.push(`Ambiguous CSV column '${hdr}': matches multiple fields (${cands.join(', ')}).`);
    }
  }

  // Detect duplicate columns mapped to same field
  const fieldToHeaders: Record<string, string[]> = {};
  for (const r of resolutions) {
    if (r.canonicalName) {
      if (!fieldToHeaders[r.canonicalName]) {
        fieldToHeaders[r.canonicalName] = [];
      }
      fieldToHeaders[r.canonicalName].push(r.rawHeader);
    }
  }

  const duplicateFields: Record<string, string[]> = {};
  for (const [fname, hdrs] of Object.entries(fieldToHeaders)) {
    if (hdrs.length > 1) {
      duplicateFields[fname] = hdrs;
      errors.push(
        `Duplicate CSV column mapping for field '${fname}': multiple columns resolve to this field (${hdrs.map((h) => `'${h}'`).join(', ')}).`
      );
      // Mark matching resolutions as duplicate
      for (const r of resolutions) {
        if (r.canonicalName === fname) {
          r.status = 'duplicate';
          r.errorMessage = `Duplicate column mapping for field '${fname}'`;
        }
      }
    }
  }

  // Check required fields
  const mappedFieldNames = new Set(
    resolutions.filter((r) => r.status === 'matched').map((r) => r.canonicalName!)
  );
  for (const f of fields) {
    if (f.required && !mappedFieldNames.has(f.name)) {
      warnings.push(`Required field '${f.label}' (${f.name}) is not mapped in the CSV.`);
    }
  }

  const isValid = errors.length === 0;
  const headerMap: Record<string, string> = {};
  const indexMap: Record<number, string> = {};

  if (isValid) {
    for (const r of resolutions) {
      if (r.canonicalName) {
        headerMap[r.rawHeader] = r.canonicalName;
        indexMap[r.index] = r.canonicalName;
      }
    }
  }

  return {
    isValid,
    resolutions,
    headerMap,
    indexMap,
    errors,
    warnings,
    unknownHeaders,
    duplicateFields,
    ambiguousHeaders,
  };
}

export interface UnmatchedEnumValue {
  fieldName: string;
  fieldLabel: string;
  rawValue: string;
  count: number;
  rowNumbers: number[];
  allowedOptions: string[];
}

/**
 * Scan all CSV rows to identify any distinct values in enum/status fields that
 * do not match the CRM schema's allowed options.
 */
export function findUnmatchedEnumValues(
  rows: string[][],
  indexMap: Record<number, string>,
  fields: CRMField[],
  pipelineStages: string[] = []
): UnmatchedEnumValue[] {
  const result: Map<string, UnmatchedEnumValue> = new Map();

  rows.forEach((row, rIdx) => {
    const rowNum = rIdx + 2; // Row 1 is header
    row.forEach((cell, colIdx) => {
      const fieldName = indexMap[colIdx];
      if (!fieldName) return;

      const field = fields.find((f) => f.name === fieldName);
      if (!field || (field.type !== 'select' && field.type !== 'status' && field.type !== 'multi_select')) {
        return;
      }

      const allowed = field.options && field.options.length > 0
        ? field.options
        : (field.type === 'status' ? pipelineStages : []);

      if (allowed.length === 0) return;

      const valTrimmed = (cell || '').trim();
      if (!valTrimmed) return;

      if (field.type === 'multi_select') {
        const parts = valTrimmed.split(/[,;]/).map((p) => p.trim()).filter(Boolean);
        for (const part of parts) {
          const matched = allowed.some((opt) => opt.toLowerCase() === part.toLowerCase());
          if (!matched) {
            const key = `${fieldName}:::${part}`;
            const existing = result.get(key);
            if (existing) {
              existing.count += 1;
              existing.rowNumbers.push(rowNum);
            } else {
              result.set(key, {
                fieldName,
                fieldLabel: field.label,
                rawValue: part,
                count: 1,
                rowNumbers: [rowNum],
                allowedOptions: allowed,
              });
            }
          }
        }
      } else {
        const matched = allowed.some((opt) => opt.toLowerCase() === valTrimmed.toLowerCase());
        if (!matched) {
          const key = `${fieldName}:::${valTrimmed}`;
          const existing = result.get(key);
          if (existing) {
            existing.count += 1;
            existing.rowNumbers.push(rowNum);
          } else {
            result.set(key, {
              fieldName,
              fieldLabel: field.label,
              rawValue: valTrimmed,
              count: 1,
              rowNumbers: [rowNum],
              allowedOptions: allowed,
            });
          }
        }
      }
    });
  });

  return Array.from(result.values());
}
