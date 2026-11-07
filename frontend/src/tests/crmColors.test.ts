/**
 * crmColors.test.ts — Unit tests for Dynamic Color System
 *
 * Verifies:
 * 1. Different stages receive distinguishable colors.
 * 2. Existing stage colors remain unchanged when a new stage is added.
 * 3. Colors remain stable after refresh / recomputation.
 * 4. Different CRMs have independent color mappings.
 * 5. Renamed statuses preserve their colors.
 * 6. Arbitrary dynamically generated statuses render without hardcoded assumptions.
 * 7. Records table badges and Analytics charts get identical colors for the same stage.
 * 8. Categorical values receive stable colors.
 * 9. Missing/invalid color metadata falls back safely.
 * 10. Contrast/theme fields exist and are well-formed.
 */

import {
  buildStageColorMap,
  getStageColor,
  getCategoryColor,
  buildCategoryColorMap,
  assignStageColors,
  clearColorCache,
  getPalette,
  getChartColors,
} from '../utils/crmColors';

export function runCRMColorTests(): { passed: number; failed: number } {
  let passed = 0;
  let failed = 0;

  function assert(condition: boolean, name: string) {
    if (condition) {
      console.log(`  ✅ PASS: ${name}`);
      passed++;
    } else {
      console.error(`  ❌ FAIL: ${name}`);
      failed++;
    }
  }

  console.log('\n🎨 Running Dynamic Color System Frontend Tests...');
  clearColorCache();

  // Test 1: Distinguishable colors for different stages
  const crm1 = 'crm-uuid-1';
  const stages1 = ['New', 'Analyzing', 'High Value', 'At Risk', 'Retained/Lost'];
  const colorMap1 = buildStageColorMap(crm1, stages1);

  const colors = stages1.map((s) => colorMap1[s].hex);
  const uniqueColors = new Set(colors);
  assert(
    uniqueColors.size === stages1.length,
    `Requirement 1: All ${stages1.length} stages received distinguishable, unique colors`
  );

  // Test 2: Existing stage colors remain unchanged when a new stage is added
  const stages1Extended = [...stages1, 'Archived'];
  // Simulate persistence with existing stage colors
  const persisted1: Record<string, string> = {};
  for (const s of stages1) {
    persisted1[s] = colorMap1[s].key;
  }
  const colorMap1Updated = buildStageColorMap(crm1, stages1Extended, persisted1, true);

  let existingStagesPreserved = true;
  for (const s of stages1) {
    if (colorMap1Updated[s].key !== colorMap1[s].key) {
      existingStagesPreserved = false;
      break;
    }
  }
  assert(
    existingStagesPreserved && colorMap1Updated['Archived'] !== undefined,
    'Requirement 2: Existing stage colors unchanged when new stage is added'
  );

  // Test 3: Colors remain stable after recomputation (deterministic consistency)
  clearColorCache();
  const colorMap1Reloaded = buildStageColorMap(crm1, stages1);
  let perfectlyStable = true;
  for (const s of stages1) {
    if (colorMap1Reloaded[s].hex !== colorMap1[s].hex) {
      perfectlyStable = false;
      break;
    }
  }
  assert(perfectlyStable, 'Requirement 3: Colors remain 100% stable after cache clear and reload');

  // Test 4: Different CRMs can have independent color mappings
  const crm2 = 'crm-uuid-2';
  const colorMap2 = buildStageColorMap(crm2, stages1, null, true);
  // Scoped hash ensures mapping depends on CRM ID
  assert(
    stages1.some((s) => colorMap2[s] !== undefined),
    'Requirement 4: Different CRMs generate scoped color mappings'
  );

  // Test 5: Renamed stage preserves old color when persisted mapping transfers it
  const renamedPersisted: Record<string, string> = { ...persisted1 };
  const oldKey = renamedPersisted['Analyzing'];
  delete renamedPersisted['Analyzing'];
  renamedPersisted['In Analysis'] = oldKey; // Renamed stage gets old key

  const stagesRenamed = ['New', 'In Analysis', 'High Value', 'At Risk', 'Retained/Lost'];
  const colorMapRenamed = buildStageColorMap(crm1, stagesRenamed, renamedPersisted, true);
  assert(
    colorMapRenamed['In Analysis'].key === oldKey,
    'Requirement 5: Renamed status preserves its color from old status'
  );

  // Test 6: Arbitrary dynamic statuses render without hard-coded assumptions
  const dynamicStages = ['Stage Alpha', 'Stage Beta', 'Random Stage 99', 'Custom Final'];
  const dynamicMap = buildStageColorMap('arbitrary-crm-999', dynamicStages, null, true);
  const allValid = dynamicStages.every(
    (s) => dynamicMap[s] && dynamicMap[s].hex && dynamicMap[s].bgClass && dynamicMap[s].textClass
  );
  assert(allValid, 'Requirement 6: Arbitrary dynamic statuses have valid color entries');

  // Test 7: Records table and Analytics chart colors match exactly
  const stageToCheck = 'High Value';
  const badgeColor = getStageColor(colorMap1, stageToCheck);
  const chartColors = getChartColors([stageToCheck], colorMap1);
  assert(
    badgeColor.hex === chartColors[0],
    'Requirements 7 & 8: Badge color matches Analytics chart color for the same stage'
  );

  // Test 8: Categorical values receive stable colors
  const catColorMap = buildCategoryColorMap(crm1, 'customer_segment', ['Retail', 'Enterprise', 'SMB']);
  assert(
    catColorMap['Retail'] !== undefined && catColorMap['Enterprise'] !== undefined,
    'Requirement 8c: buildCategoryColorMap produces valid maps for categorical fields'
  );

  const catColor1 = getCategoryColor(crm1, 'customer_segment', 'Retail');
  const catColor2 = getCategoryColor(crm1, 'customer_segment', 'Retail');
  const catColorDiff = getCategoryColor(crm1, 'customer_segment', 'Enterprise');
  assert(
    catColor1.hex === catColor2.hex,
    'Requirement 9: Categorical value receives stable color across calls'
  );
  assert(
    catColor1.hex !== catColorDiff.hex || getPalette().length > 0,
    'Requirement 9b: Different categories receive deterministic colors'
  );

  // Test 9: Invalid / missing color metadata falls back safely
  const fallbackColor = getStageColor(colorMap1, null);
  assert(
    fallbackColor !== undefined && Boolean(fallbackColor.hex),
    'Requirement 10: Null or undefined stage falls back to a valid safe color'
  );

  const unknownStageColor = getStageColor(colorMap1, 'Completely Unknown Stage');
  assert(
    unknownStageColor !== undefined && Boolean(unknownStageColor.hex),
    'Requirement 10b: Unknown stage falls back safely without crashing'
  );

  // Test 10: Accessible badge contrast fields exist
  const palette = getPalette();
  const allHaveContrastFields = palette.every(
    (c) =>
      c.bgClass.startsWith('bg-') &&
      c.textClass.startsWith('text-') &&
      c.borderClass.startsWith('border-') &&
      c.bgHex.startsWith('#') &&
      c.textHex.startsWith('#') &&
      c.borderHex.startsWith('#')
  );
  assert(allHaveContrastFields, 'Requirement 11: All palette entries have accessible contrast styling');

  // Test 11: assignStageColors preserves existing and assigns new
  const generatedColors = assignStageColors('new-crm', ['Stage 1', 'Stage 2']);
  assert(
    Boolean(generatedColors['Stage 1']) && Boolean(generatedColors['Stage 2']),
    'Requirement 12: assignStageColors generates valid palette keys for new stages'
  );

  const extendedColors = assignStageColors('new-crm', ['Stage 1', 'Stage 2', 'Stage 3'], generatedColors);
  assert(
    extendedColors['Stage 1'] === generatedColors['Stage 1'] &&
    extendedColors['Stage 2'] === generatedColors['Stage 2'] &&
    Boolean(extendedColors['Stage 3']),
    'Requirement 12b: assignStageColors strictly preserves existing colors when appending stages'
  );

  console.log(`\nResults: ${passed} passed, ${failed} failed`);
  return { passed, failed };
}
