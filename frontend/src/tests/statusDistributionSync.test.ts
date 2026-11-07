/**
 * statusDistributionSync.test.ts — Verification of Canonical Status Aggregation
 * and Synchronization between Status Bar Chart and Donut Chart.
 */

import { api, setUseMockMode } from '../services/api';
import { buildStageColorMap, getStageColor } from '../utils/crmColors';
import { CRMField } from '../types/crm';

export async function runStatusDistributionSyncTests(): Promise<{ passed: number; failed: number }> {
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

  console.log('\n🧪 Running Status Distribution & Chart Synchronization Tests...');
  setUseMockMode(true);

  const pipelineStages = ['New', 'Analyzing', 'High Value', 'At Risk', 'Retained/Lost'];

  const machineFields: CRMField[] = [
    { name: 'customer_name', label: 'Customer Name', type: 'text', required: true },
    { name: 'total_revenue', label: 'Total Revenue', type: 'currency', required: false },
    {
      name: 'crm_status',
      label: 'CRM Status',
      type: 'status',
      required: false,
      options: pipelineStages,
    },
  ];

  // 1. Create a CRM with entity 'machine_identifier' and custom status field 'crm_status'
  const savedCrm = await api.saveCRM({
    schema_version: '1.0',
    name: 'Analytical_E_Commerce_Sync_CRM',
    industry: 'ecommerce',
    entities: [
      {
        name: 'machine_identifier',
        label: 'Machine Identifier',
        fields: machineFields,
      },
    ],
    pipeline_stages: pipelineStages,
  });

  assert(Boolean(savedCrm?.crm_id), '1.1 Created test CRM with crm_status field and 5 stages');

  // 2. Populate exactly 71 records all with status 'New'
  const createdRecordIds: string[] = [];
  for (let i = 1; i <= 71; i++) {
    const rec = await api.createRecord(
      savedCrm.crm_id,
      'machine_identifier',
      {
        customer_name: `Customer ${i}`,
        total_revenue: 100 * i,
        crm_status: 'New',
      },
      'CSV'
    );
    createdRecordIds.push(rec.id);
  }
  assert(createdRecordIds.length === 71, '1.2 Populated exactly 71 records in New status');

  // 3. Fetch canonical analytics
  const analytics1 = await api.getAnalytics(savedCrm.crm_id);
  assert(analytics1.total_records === 71, '1.3 Analytics reports total_records === 71');

  // 4. Verify canonical status distribution
  const statusDist = analytics1.status_distribution || analytics1.by_stage || [];
  assert(statusDist.length === 5, '1.4 Canonical distribution contains all 5 configured stages');

  const newStage = statusDist.find((s) => (s.status || s.value) === 'New');
  assert(newStage?.count === 71, '1.5 Canonical status reports exactly 71 under "New"');
  assert(newStage?.percentage === 100, '1.6 Canonical status reports 100% under "New"');

  const zeroStages = statusDist.filter((s) => (s.status || s.value) !== 'New');
  assert(
    zeroStages.every((s) => s.count === 0 && s.percentage === 0),
    '1.7 Zero-count stages (Analyzing, High Value, At Risk, Retained/Lost) have 0 count and 0%'
  );

  // 5. Test Donut Chart slices (zero-count stages excluded from pie slices)
  const donutSlices1 = statusDist.filter((s) => s.count > 0);
  assert(donutSlices1.length === 1, '1.8 Donut chart has exactly 1 slice when all 71 records are New');
  assert(donutSlices1[0].percentage === 100, '1.9 Donut single slice represents 100%');

  // 6. Bar chart and Donut chart data parity
  const barCounts = statusDist.map((s) => ({ stage: s.status || s.value, count: s.count }));
  const donutCounts = statusDist.map((s) => ({ stage: s.status || s.value, count: s.count }));
  assert(
    JSON.stringify(barCounts) === JSON.stringify(donutCounts),
    '1.10 Bar chart counts strictly equal Donut chart counts for every stage'
  );

  // 7. Verify crm_status is NOT duplicated in categorical_metrics
  const catMetrics = (analytics1.categorical_metrics || {}) as Record<string, any>;
  assert(
    !catMetrics['crm_status'],
    '1.11 Status field (crm_status) is excluded from categorical_metrics to prevent duplicate charts'
  );

  // 8. Test Moving a Record from New to Analyzing
  await api.updateRecord(
    savedCrm.crm_id,
    'machine_identifier',
    createdRecordIds[0],
    { crm_status: 'Analyzing' }
  );

  const analytics2 = await api.getAnalytics(savedCrm.crm_id);
  const statusDist2 = analytics2.status_distribution || analytics2.by_stage || [];
  const updatedNew = statusDist2.find((s) => (s.status || s.value) === 'New');
  const updatedAnalyzing = statusDist2.find((s) => (s.status || s.value) === 'Analyzing');

  assert(updatedNew?.count === 70, '2.1 Moving record updates "New" count to 70');
  assert(updatedAnalyzing?.count === 1, '2.2 Moving record updates "Analyzing" count to 1');

  const donutSlices2 = statusDist2.filter((s) => s.count > 0);
  assert(donutSlices2.length === 2, '2.3 Donut chart now has exactly 2 active slices');

  const totalDonutPct = Number(donutSlices2.reduce((acc, s) => acc + (s.percentage || 0), 0).toFixed(1));
  assert(
    totalDonutPct >= 99.5 && totalDonutPct <= 100.5,
    `2.4 Donut percentages sum to ~100% (${totalDonutPct}%)`
  );

  // 9. Deleting a record updates both charts
  await api.deleteRecord(savedCrm.crm_id, 'machine_identifier', createdRecordIds[1]);
  const analytics3 = await api.getAnalytics(savedCrm.crm_id);
  assert(analytics3.total_records === 70, '3.1 Total records decreased to 70 after deletion');
  const statusDist3 = analytics3.status_distribution || analytics3.by_stage || [];
  const postDeleteNew = statusDist3.find((s) => (s.status || s.value) === 'New');
  assert(postDeleteNew?.count === 69, '3.2 "New" count decreased to 69 after record deletion');

  // 10. Dynamic Color Mapping Consistency
  const colorMap = buildStageColorMap(savedCrm.crm_id, pipelineStages);
  const newColor = getStageColor(colorMap, 'New');
  const analyzingColor = getStageColor(colorMap, 'Analyzing');
  assert(Boolean(newColor.hex), '4.1 Stage "New" receives valid hex color');
  assert(Boolean(analyzingColor.hex), '4.2 Stage "Analyzing" receives valid hex color');
  assert(newColor.hex !== analyzingColor.hex, '4.3 Distinct stages receive distinct colors');

  // Verify color stability across multiple lookups (same CRM + stage = same color)
  const newColorAgain = getStageColor(colorMap, 'New');
  assert(newColor.hex === newColorAgain.hex, '4.4 Stage colors are stable across multiple calls');

  return { passed, failed };
}

if (process.argv[1]?.endsWith('statusDistributionSync.test.ts')) {
  runStatusDistributionSyncTests().then(({ failed }) => {
    if (failed > 0) process.exit(1);
  });
}
