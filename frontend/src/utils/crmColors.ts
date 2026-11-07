/**
 * crmColors.ts — Shared, schema-driven color assignment for AURA CRM
 *
 * Provides:
 *  1. A curated palette of 16 accessible, visually distinct colors.
 *  2. Deterministic hash-based assignment so the same CRM+stage always
 *     gets the same color, even without persisted metadata.
 *  3. Persistence support via an optional `stage_colors` map stored in
 *     `CRMConfiguration.ui_config`.
 *  4. Both hex values (for Recharts) and Tailwind-compatible CSS classes
 *     (for badges/pills).
 *
 * The palette is designed for:
 *  - Sufficient contrast on white / light backgrounds
 *  - Readability for common color-vision deficiencies
 *  - Subtle tinted badge backgrounds with matching borders and readable text
 */

// ─── Palette ────────────────────────────────────────────────────────────────

export interface ColorEntry {
  /** Key used for persistence and lookup */
  key: string;
  /** Primary hex color for charts */
  hex: string;
  /** Subtle tinted background for badges (Tailwind or inline) */
  bgClass: string;
  /** Matching border for badges */
  borderClass: string;
  /** Readable foreground text for badges */
  textClass: string;
  /** Inline style fallback for bg (for dynamic CSS) */
  bgHex: string;
  /** Inline style fallback for border */
  borderHex: string;
  /** Inline style fallback for text */
  textHex: string;
}

/**
 * 16-color curated palette. Designed for:
 * - Visual distinction between adjacent items
 * - Sufficient contrast ratios
 * - Friendly naming for persistence
 */
const PALETTE: ColorEntry[] = [
  {
    key: 'blue',
    hex: '#3B82F6',
    bgClass: 'bg-blue-50', borderClass: 'border-blue-200', textClass: 'text-blue-700',
    bgHex: '#EFF6FF', borderHex: '#BFDBFE', textHex: '#1D4ED8',
  },
  {
    key: 'emerald',
    hex: '#10B981',
    bgClass: 'bg-emerald-50', borderClass: 'border-emerald-200', textClass: 'text-emerald-700',
    bgHex: '#ECFDF5', borderHex: '#A7F3D0', textHex: '#047857',
  },
  {
    key: 'amber',
    hex: '#F59E0B',
    bgClass: 'bg-amber-50', borderClass: 'border-amber-200', textClass: 'text-amber-700',
    bgHex: '#FFFBEB', borderHex: '#FDE68A', textHex: '#B45309',
  },
  {
    key: 'rose',
    hex: '#F43F5E',
    bgClass: 'bg-rose-50', borderClass: 'border-rose-200', textClass: 'text-rose-700',
    bgHex: '#FFF1F2', borderHex: '#FECDD3', textHex: '#BE123C',
  },
  {
    key: 'violet',
    hex: '#8B5CF6',
    bgClass: 'bg-violet-50', borderClass: 'border-violet-200', textClass: 'text-violet-700',
    bgHex: '#F5F3FF', borderHex: '#DDD6FE', textHex: '#6D28D9',
  },
  {
    key: 'cyan',
    hex: '#06B6D4',
    bgClass: 'bg-cyan-50', borderClass: 'border-cyan-200', textClass: 'text-cyan-700',
    bgHex: '#ECFEFF', borderHex: '#A5F3FC', textHex: '#0E7490',
  },
  {
    key: 'orange',
    hex: '#F97316',
    bgClass: 'bg-orange-50', borderClass: 'border-orange-200', textClass: 'text-orange-700',
    bgHex: '#FFF7ED', borderHex: '#FED7AA', textHex: '#C2410C',
  },
  {
    key: 'indigo',
    hex: '#6366F1',
    bgClass: 'bg-indigo-50', borderClass: 'border-indigo-200', textClass: 'text-indigo-700',
    bgHex: '#EEF2FF', borderHex: '#C7D2FE', textHex: '#4338CA',
  },
  {
    key: 'teal',
    hex: '#14B8A6',
    bgClass: 'bg-teal-50', borderClass: 'border-teal-200', textClass: 'text-teal-700',
    bgHex: '#F0FDFA', borderHex: '#99F6E4', textHex: '#0F766E',
  },
  {
    key: 'pink',
    hex: '#EC4899',
    bgClass: 'bg-pink-50', borderClass: 'border-pink-200', textClass: 'text-pink-700',
    bgHex: '#FDF2F8', borderHex: '#FBCFE8', textHex: '#BE185D',
  },
  {
    key: 'lime',
    hex: '#84CC16',
    bgClass: 'bg-lime-50', borderClass: 'border-lime-200', textClass: 'text-lime-700',
    bgHex: '#F7FEE7', borderHex: '#D9F99D', textHex: '#4D7C0F',
  },
  {
    key: 'sky',
    hex: '#0EA5E9',
    bgClass: 'bg-sky-50', borderClass: 'border-sky-200', textClass: 'text-sky-700',
    bgHex: '#F0F9FF', borderHex: '#BAE6FD', textHex: '#0369A1',
  },
  {
    key: 'fuchsia',
    hex: '#D946EF',
    bgClass: 'bg-fuchsia-50', borderClass: 'border-fuchsia-200', textClass: 'text-fuchsia-700',
    bgHex: '#FDF4FF', borderHex: '#F5D0FE', textHex: '#A21CAF',
  },
  {
    key: 'red',
    hex: '#EF4444',
    bgClass: 'bg-red-50', borderClass: 'border-red-200', textClass: 'text-red-700',
    bgHex: '#FEF2F2', borderHex: '#FECACA', textHex: '#B91C1C',
  },
  {
    key: 'yellow',
    hex: '#EAB308',
    bgClass: 'bg-yellow-50', borderClass: 'border-yellow-200', textClass: 'text-yellow-700',
    bgHex: '#FEFCE8', borderHex: '#FEF08A', textHex: '#A16207',
  },
  {
    key: 'slate',
    hex: '#64748B',
    bgClass: 'bg-slate-100', borderClass: 'border-slate-300', textClass: 'text-slate-700',
    bgHex: '#F1F5F9', borderHex: '#CBD5E1', textHex: '#334155',
  },
];

// ─── Deterministic hash ─────────────────────────────────────────────────────

/**
 * Simple, fast 32-bit hash (djb2) of a string.
 * Used as a deterministic fallback when persisted colors are unavailable.
 */
function djb2Hash(str: string): number {
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash + str.charCodeAt(i)) | 0; // hash * 33 + c
  }
  return Math.abs(hash);
}

// ─── Color Map Builder ──────────────────────────────────────────────────────

export interface StageColorMap {
  [stageName: string]: ColorEntry;
}

/**
 * In-memory cache keyed by `crmId` to avoid recomputing on every render.
 */
const colorMapCache = new Map<string, StageColorMap>();

/**
 * Build a stage → ColorEntry map for a CRM.
 *
 * Priority:
 *  1. Persisted `ui_config.stage_colors` from the CRM configuration
 *  2. Deterministic hash-based fallback (CRM ID + stage name)
 *
 * @param crmId        Unique CRM identifier (used for hash scoping)
 * @param stages       Ordered array of pipeline stage names
 * @param persisted    Optional persisted color map (stage → palette key)
 * @param forceRefresh If true, bypass cache
 */
export function buildStageColorMap(
  crmId: string,
  stages: string[],
  persisted?: Record<string, string> | null,
  forceRefresh = false,
): StageColorMap {
  const cacheKey = crmId;

  if (!forceRefresh && colorMapCache.has(cacheKey)) {
    const cached = colorMapCache.get(cacheKey)!;
    // Verify cached map covers all current stages
    const allPresent = stages.every((s) => s in cached);
    if (allPresent) return cached;
  }

  const paletteByKey = new Map(PALETTE.map((c) => [c.key, c]));
  const map: StageColorMap = {};
  const usedIndices = new Set<number>();

  for (const stage of stages) {
    // 1. Try persisted color
    if (persisted && persisted[stage]) {
      const entry = paletteByKey.get(persisted[stage]);
      if (entry) {
        map[stage] = entry;
        usedIndices.add(PALETTE.indexOf(entry));
        continue;
      }
    }

    // 2. Deterministic hash fallback scoped to CRM + stage
    const hash = djb2Hash(`${crmId}::${stage}`);
    let idx = hash % PALETTE.length;

    // Avoid collisions with already-assigned colors when possible
    let attempts = 0;
    while (usedIndices.has(idx) && attempts < PALETTE.length) {
      idx = (idx + 1) % PALETTE.length;
      attempts++;
    }

    map[stage] = PALETTE[idx];
    usedIndices.add(idx);
  }

  colorMapCache.set(cacheKey, map);
  return map;
}

/**
 * Get the ColorEntry for a specific stage value.
 * Returns a safe fallback (slate) if stage is not found.
 */
export function getStageColor(
  colorMap: StageColorMap,
  stageValue: string | undefined | null,
): ColorEntry {
  if (!stageValue) return PALETTE[PALETTE.length - 1]; // slate fallback
  return colorMap[stageValue] ?? PALETTE[djb2Hash(stageValue || '') % PALETTE.length];
}

// ─── Category Colors (for select fields, etc.) ─────────────────────────────

/**
 * Get a deterministic color for a categorical value (non-stage).
 * Scoped by CRM ID + field name + category value.
 */
export function getCategoryColor(
  crmId: string,
  fieldName: string,
  categoryValue: string,
): ColorEntry {
  const hash = djb2Hash(`${crmId}::${fieldName}::${categoryValue}`);
  return PALETTE[hash % PALETTE.length];
}

/**
 * Build a color map for a set of categorical values in a specific field.
 */
export function buildCategoryColorMap(
  crmId: string,
  fieldName: string,
  values: string[],
): StageColorMap {
  const map: StageColorMap = {};
  const usedIndices = new Set<number>();

  for (const value of values) {
    const hash = djb2Hash(`${crmId}::${fieldName}::${value}`);
    let idx = hash % PALETTE.length;

    let attempts = 0;
    while (usedIndices.has(idx) && attempts < PALETTE.length) {
      idx = (idx + 1) % PALETTE.length;
      attempts++;
    }

    map[value] = PALETTE[idx];
    usedIndices.add(idx);
  }

  return map;
}

// ─── Color Assignment for CRM Generation ────────────────────────────────────

/**
 * Generate a stage_colors map for a newly created CRM.
 * Assigns randomized but deterministic palette keys to each stage.
 * Returns a Record<stageName, paletteKey> suitable for persisting in ui_config.
 */
export function assignStageColors(
  crmId: string,
  stages: string[],
  existingColors?: Record<string, string> | null,
): Record<string, string> {
  const result: Record<string, string> = {};
  const usedKeys = new Set<string>();

  // Preserve existing assignments
  if (existingColors) {
    for (const [stage, key] of Object.entries(existingColors)) {
      if (stages.includes(stage) && PALETTE.some((p) => p.key === key)) {
        result[stage] = key;
        usedKeys.add(key);
      }
    }
  }

  // Assign new colors for stages that don't have one
  for (const stage of stages) {
    if (result[stage]) continue;

    const hash = djb2Hash(`${crmId}::${stage}`);
    let idx = hash % PALETTE.length;

    let attempts = 0;
    while (usedKeys.has(PALETTE[idx].key) && attempts < PALETTE.length) {
      idx = (idx + 1) % PALETTE.length;
      attempts++;
    }

    result[stage] = PALETTE[idx].key;
    usedKeys.add(PALETTE[idx].key);
  }

  return result;
}

/**
 * Clear the in-memory cache for a specific CRM or all CRMs.
 */
export function clearColorCache(crmId?: string): void {
  if (crmId) {
    colorMapCache.delete(crmId);
  } else {
    colorMapCache.clear();
  }
}

/**
 * Get the raw palette for external use (e.g., chart color arrays).
 */
export function getPalette(): readonly ColorEntry[] {
  return PALETTE;
}

/**
 * Get an array of hex colors for a given stage color map, in stage order.
 */
export function getChartColors(
  stages: string[],
  colorMap: StageColorMap,
): string[] {
  return stages.map((s) => getStageColor(colorMap, s).hex);
}

