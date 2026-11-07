import { normalizeHeader, parseCSV, resolveCSVHeaders } from '../utils/csvResolver';
import { CRMField } from '../types/crm';

export function runCSVResolverTests(): { passed: number; failed: number } {
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

  console.log('\n🧪 Running Universal CSV Resolver Frontend Tests...');

  // 1. Normalization
  assert(normalizeHeader('\ufeffCustomer Name') === 'customer name', '1.1 normalizeHeader removes UTF-8 BOM');
  assert(normalizeHeader('  CUSTOMER_NAME  ') === 'customer name', '1.2 normalizeHeader trims and converts underscores');
  assert(normalizeHeader('customer-name') === 'customer name', '1.3 normalizeHeader converts hyphens');
  assert(normalizeHeader('CUSTOMER   NAME') === 'customer name', '1.4 normalizeHeader collapses multiple spaces');

  // 2. CSV Parser
  const parsed = parseCSV('header1,"header, 2",header3\r\nval1,"val, 2",val3\r\n');
  assert(parsed.headers.length === 3, '2.1 parseCSV handles quoted commas in headers');
  assert(parsed.headers[1] === 'header, 2', '2.2 parseCSV extracts quoted comma value cleanly');
  assert(parsed.rows.length === 1, '2.3 parseCSV parses row correctly');
  assert(parsed.rows[0][1] === 'val, 2', '2.4 parseCSV extracts quoted comma value in row');

  // 3. Machine Identifier schema fields
  const machineFields: CRMField[] = [
    { name: 'customer_name', label: 'Customer Name', type: 'text', required: true },
    { name: 'customer_segment', label: 'Customer Segment', type: 'text', required: false },
    { name: 'total_revenue', label: 'Total Revenue', type: 'currency', required: false },
    { name: 'purchase_frequency', label: 'Purchase Frequency', type: 'number', required: false },
    { name: 'customer_value', label: 'Customer Value', type: 'text', required: false },
    { name: 'crm_status', label: 'CRM Status', type: 'status', required: false },
  ];

  // 4. Six uppercase display labels
  const sixHeaders = [
    'CUSTOMER NAME',
    'CUSTOMER SEGMENT',
    'TOTAL REVENUE',
    'PURCHASE FREQUENCY',
    'CUSTOMER VALUE',
    'CRM STATUS',
  ];

  const res1 = resolveCSVHeaders(sixHeaders, machineFields, 'Machine Identifier');
  assert(res1.isValid === true, '3.1 Six uppercase display labels are accepted');
  assert(res1.errors.length === 0, '3.2 Zero errors on valid display labels');
  assert(res1.headerMap['CUSTOMER NAME'] === 'customer_name', '3.3 CUSTOMER NAME -> customer_name');
  assert(res1.headerMap['CUSTOMER SEGMENT'] === 'customer_segment', '3.4 CUSTOMER SEGMENT -> customer_segment');
  assert(res1.headerMap['TOTAL REVENUE'] === 'total_revenue', '3.5 TOTAL REVENUE -> total_revenue');
  assert(res1.headerMap['PURCHASE FREQUENCY'] === 'purchase_frequency', '3.6 PURCHASE FREQUENCY -> purchase_frequency');
  assert(res1.headerMap['CUSTOMER VALUE'] === 'customer_value', '3.7 CUSTOMER VALUE -> customer_value');
  assert(res1.headerMap['CRM STATUS'] === 'crm_status', '3.8 CRM STATUS -> crm_status');

  // 5. Exact canonical headers
  const canonicalHeaders = ['customer_name', 'customer_segment', 'total_revenue'];
  const res2 = resolveCSVHeaders(canonicalHeaders, machineFields, 'Machine Identifier');
  assert(res2.isValid === true, '4.1 Canonical field names resolve cleanly');
  assert(res2.headerMap['customer_name'] === 'customer_name', '4.2 Exact canonical header maps to itself');

  // 6. Unknown columns
  const badHeaders = ['customer_name', 'unknown_field_xyz'];
  const res3 = resolveCSVHeaders(badHeaders, machineFields, 'Machine Identifier');
  assert(res3.isValid === false, '5.1 Unknown column causes isValid=false');
  assert(res3.unknownHeaders.includes('unknown_field_xyz'), '5.2 Unknown header tracked');
  assert(res3.errors[0].includes('Unknown CSV columns'), '5.3 Error message identifies unknown columns');

  // 7. Duplicate columns resolving to same field
  const dupHeaders = ['CUSTOMER NAME', 'customer_name'];
  const res4 = resolveCSVHeaders(dupHeaders, machineFields, 'Machine Identifier');
  assert(res4.isValid === false, '6.1 Duplicate column mapping causes isValid=false');
  assert(Boolean(res4.duplicateFields['customer_name']), '6.2 Duplicate field tracked');
  assert(res4.errors.some((e) => e.includes('Duplicate CSV column mapping')), '6.3 Error identifies duplicate mapping');

  // 8. Empty column header
  const emptyHeaders = ['customer_name', '', 'total_revenue'];
  const res5 = resolveCSVHeaders(emptyHeaders, machineFields, 'Machine Identifier');
  assert(res5.isValid === false, '7.1 Empty column header causes isValid=false');
  assert(res5.errors.some((e) => e.includes('empty column header')), '7.2 Error identifies empty header position');

  // 9. Second CRM schema: Healthcare
  const healthcareFields: CRMField[] = [
    { name: 'patient_name', label: 'Patient Full Name', type: 'text', required: true },
    { name: 'blood_group', label: 'Blood Group', type: 'select', required: false },
  ];
  const res6 = resolveCSVHeaders(['PATIENT FULL NAME', 'BLOOD GROUP'], healthcareFields, 'Patient');
  assert(res6.isValid === true, '8.1 Healthcare CRM display labels resolve dynamically');
  assert(res6.headerMap['PATIENT FULL NAME'] === 'patient_name', '8.2 PATIENT FULL NAME -> patient_name');
  assert(res6.headerMap['BLOOD GROUP'] === 'blood_group', '8.3 BLOOD GROUP -> blood_group');

  return { passed, failed };
}

if (process.argv[1]?.endsWith('csvResolver.test.ts')) {
  const { failed } = runCSVResolverTests();
  if (failed > 0) process.exit(1);
}

