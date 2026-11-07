import { findUnmatchedEnumValues, resolveCSVHeaders } from '../utils/csvResolver';
import { CRMField } from '../types/crm';
import { api, setUseMockMode } from '../services/api';

export async function runStatusMappingTests(): Promise<{ passed: number; failed: number }> {
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

  console.log('\n🧪 Running Universal Status & Enum Mapping Frontend Tests...');
  setUseMockMode(true);

  const pipelineStages = ['New', 'Analyzing', 'High Value', 'At Risk', 'Retained/Lost'];

  const machineFields: CRMField[] = [
    { name: 'customer_name', label: 'Customer Name', type: 'text', required: true },
    { name: 'customer_segment', label: 'Customer Segment', type: 'text', required: false },
    { name: 'total_revenue', label: 'Total Revenue', type: 'currency', required: false },
    { name: 'purchase_frequency', label: 'Purchase Frequency', type: 'number', required: false },
    { name: 'customer_value', label: 'Customer Value', type: 'text', required: false },
    {
      name: 'crm_status',
      label: 'CRM Status',
      type: 'status',
      required: false,
      options: pipelineStages,
    },
  ];

  const headers = ['CUSTOMER NAME', 'CUSTOMER SEGMENT', 'TOTAL REVENUE', 'PURCHASE FREQUENCY', 'CUSTOMER VALUE', 'CRM STATUS'];
  const headerRes = resolveCSVHeaders(headers, machineFields, 'Machine Identifier');

  // Generate 100 rows: 66 valid ('New', 'High Value'), 20 'Retained', 14 'Lost'
  const rows: string[][] = [];
  for (let i = 1; i <= 66; i++) {
    const st = i % 2 === 0 ? 'New' : 'High Value';
    rows.push([`Customer ${i}`, 'Enterprise', `${i * 1000}`, '5', 'Medium', st]);
  }
  for (let i = 67; i <= 86; i++) {
    rows.push([`Customer ${i}`, 'SMB', `${i * 500}`, '2', 'Low', 'Retained']);
  }
  for (let i = 87; i <= 100; i++) {
    rows.push([`Customer ${i}`, 'Enterprise', `${i * 2000}`, '10', 'High', 'Lost']);
  }

  // 1. Detection of unmatched enum values
  const unmatched = findUnmatchedEnumValues(rows, headerRes.indexMap, machineFields, pipelineStages);
  assert(unmatched.length === 2, '1.1 Detected exactly 2 distinct unmatched status values (Retained, Lost)');

  const retainedItem = unmatched.find((u) => u.rawValue === 'Retained');
  assert(Boolean(retainedItem), '1.2 "Retained" detected in scan');
  assert(retainedItem?.count === 20, '1.3 "Retained" has occurrence count of 20');
  assert(retainedItem?.allowedOptions.includes('Retained/Lost') === true, '1.4 "Retained/Lost" present in permitted destination options');

  const lostItem = unmatched.find((u) => u.rawValue === 'Lost');
  assert(Boolean(lostItem), '1.5 "Lost" detected in scan');
  assert(lostItem?.count === 14, '1.6 "Lost" has occurrence count of 14');

  // 2. Mock API Import without mappings (first attempt: 66 created, 34 failed)
  const csvText = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
  const csvBlob = new Blob([csvText], { type: 'text/csv' });
  const csvFile = new File([csvBlob], 'ecommerce.csv', { type: 'text/csv' });

  // Save CRM into mock adapter so entities and stages are known
  const savedCrm = await api.saveCRM({
    schema_version: '1.0',
    name: 'Analytical_E_Commerce_CRM',
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

  const res1 = await api.importCSV(savedCrm.crm_id, 'machine_identifier', csvFile);
  assert(res1.created === 66, '2.1 Initial import without mappings creates 66 records');
  assert(res1.skipped === 34, '2.2 Initial import skips 34 records with invalid status');
  assert(res1.errors.length === 34, '2.3 Exactly 34 row-level validation errors returned');
  assert(res1.errors.every((e) => e.code === 'INVALID_OPTION'), '2.4 All 34 errors have code INVALID_OPTION');

  // 3. Retry with Value Mappings + Deduplication (second attempt)
  const mappings = {
    crm_status: {
      Retained: 'Retained/Lost',
      Lost: 'Retained/Lost',
    },
  };

  const res2 = await api.importCSV(savedCrm.crm_id, 'machine_identifier', csvFile, mappings, true);
  assert(res2.created === 34, '3.1 Retry creates exactly 34 remaining records');
  assert(res2.duplicate === 66, '3.2 Retry preserves 66 existing records without duplicate creation');
  assert(res2.skipped === 0, '3.3 Zero skipped rows on successful retry');
  assert(res2.errors.length === 0, '3.4 Zero errors returned on successful retry');

  // 4. User explicit skip (__SKIP__)
  const skipMappings = {
    crm_status: {
      Retained: 'Retained/Lost',
      Lost: '__SKIP__',
    },
  };
  const savedCrm2 = await api.saveCRM({
    schema_version: '1.0',
    name: 'Analytical_E_Commerce_CRM_2',
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
  const res3 = await api.importCSV(savedCrm2.crm_id, 'machine_identifier', csvFile, skipMappings, false);
  assert(res3.created === 86, '4.1 Created 86 records (66 valid + 20 mapped Retained)');
  assert(res3.skipped === 14, '4.2 Skipped 14 records where Lost was mapped to __SKIP__');
  assert(res3.errors.some((e) => e.code === 'USER_SKIPPED'), '4.3 Errors identify USER_SKIPPED reason');

  return { passed, failed };
}

if (process.argv[1]?.endsWith('statusMapping.test.ts')) {
  runStatusMappingTests().then(({ failed }) => {
    if (failed > 0) process.exit(1);
  });
}
