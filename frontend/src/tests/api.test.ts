import { api, setUseMockMode } from '../services/api';
import { CRMConfiguration } from '../types/crm';

export async function runFrontendTests() {
  console.log('🧪 Starting AURA Frontend & Integration Verification Tests...\n');
  let passed = 0;
  let failed = 0;

  function assert(condition: boolean, testName: string) {
    if (condition) {
      console.log(`  ✅ PASS: ${testName}`);
      passed++;
    } else {
      console.error(`  ❌ FAIL: ${testName}`);
      failed++;
    }
  }

  // Ensure mock mode is active for deterministic headless unit tests
  setUseMockMode(true);

  // Test 1: CRM Generation (Draft only, not persisted)
  try {
    const draftRes = await api.generateCRM('Create a B2B SaaS CRM to track enterprise leads and demos');
    assert(Boolean(draftRes.configuration), '1.1 AI CRM generation returns draft configuration');
    assert(draftRes.configuration.entities.length > 0, '1.2 Draft contains entities');
    assert(draftRes.configuration.entities[0].fields.length > 0, '1.3 Entity has dynamic fields');
    assert(draftRes.configuration.schema_version === '1.0', '1.4 Adheres to schema_version 1.0');
  } catch (e) {
    assert(false, `1. Generation error: ${e}`);
  }

  // Test 2: CRM Persistence (Save CRM)
  let savedCrmId = '';
  try {
    const testConfig: CRMConfiguration = {
      schema_version: '1.0',
      name: 'Automated Test CRM',
      industry: 'technology',
      entities: [
        {
          name: 'lead',
          label: 'Sales Lead',
          fields: [
            { name: 'full_name', label: 'Full Name', type: 'text', required: true },
            { name: 'email', label: 'Work Email', type: 'email', required: true },
            { name: 'status', label: 'Stage', type: 'select', required: true, options: ['New', 'Won', 'Lost'] },
          ],
        },
      ],
      pipeline_stages: ['New', 'Won', 'Lost'],
    };

    const saved = await api.saveCRM(testConfig);
    savedCrmId = saved.crm_id;
    assert(Boolean(saved.crm_id), '2.1 Save CRM returns unique crm_id UUID');
    assert(saved.configuration_version === 1, '2.2 New CRM starts at configuration_version 1');
    assert(saved.status === 'active', '2.3 New CRM status is active');
  } catch (e) {
    assert(false, `2. Save CRM error: ${e}`);
  }

  // Test 3: Dynamic Records CRUD
  let createdRecordId = '';
  try {
    const record = await api.createRecord(savedCrmId, 'lead', {
      full_name: 'Jane Doe',
      email: 'jane@example.com',
      status: 'New',
    }, 'Website');

    createdRecordId = record.id;
    assert(Boolean(record.id), '3.1 Record creation returns id');
    assert(record.data.full_name === 'Jane Doe', '3.2 Record data stored correctly');
    assert(record.source === 'Website', '3.3 Record source tagged');

    // List records
    const listRes = await api.listRecords(savedCrmId, 'lead');
    assert(listRes.items.some((r) => r.id === createdRecordId), '3.4 List records includes newly created record');

    // Update record
    const updated = await api.updateRecord(savedCrmId, 'lead', createdRecordId, {
      status: 'Won',
    });
    assert(updated.data.status === 'Won', '3.5 Update record updates stage to Won');

    // Delete record (soft-delete)
    const delRes = await api.deleteRecord(savedCrmId, 'lead', createdRecordId);
    assert(delRes.deleted === true, '3.6 Soft-delete returns deleted: true');
  } catch (e) {
    assert(false, `3. Dynamic Record CRUD error: ${e}`);
  }

  // Test 4: CSV Import Contract
  try {
    const csvContent = 'full_name,email,status\nAlice Smith,alice@test.com,New\nBob Jones,bob@test.com,Won';
    const csvBlob = new Blob([csvContent], { type: 'text/csv' });
    const csvFile = new File([csvBlob], 'leads.csv', { type: 'text/csv' });

    const importRes = await api.importCSV(savedCrmId, 'lead', csvFile);
    assert(importRes.created === 2, '4.1 CSV Import returns created count matching rows');
    assert(importRes.skipped === 0, '4.2 Zero skipped rows on valid CSV');
  } catch (e) {
    assert(false, `4. CSV Import error: ${e}`);
  }

  // Test 5: Analytics Resolution
  try {
    const analytics = await api.getAnalytics(savedCrmId);
    assert(typeof analytics.total_leads === 'number', '5.1 Analytics returns total_leads number');
    assert(typeof analytics.conversion_rate === 'number', '5.2 Analytics returns conversion_rate float');
    assert(Array.isArray(analytics.by_stage), '5.3 Analytics returns by_stage breakdown');
    assert(Array.isArray(analytics.by_source), '5.4 Analytics returns by_source breakdown');
  } catch (e) {
    assert(false, `5. Analytics error: ${e}`);
  }

  // Test 6: Workflows
  let workflowId = '';
  try {
    const wf = await api.createWorkflow(savedCrmId, {
      name: 'Auto Follow-up Workflow',
      trigger: { type: 'record.created', entity: 'lead' },
      actions: [{ type: 'create_follow_up_task', delay_hours: 24 }],
      enabled: true,
    });
    workflowId = wf.workflow_id;
    assert(Boolean(workflowId), '6.1 Create workflow returns workflow_id');
    assert(wf.status === 'active', '6.2 Workflow created with active status');

    const wfList = await api.listWorkflows(savedCrmId);
    assert(wfList.length > 0, '6.3 List workflows contains registered automations');
  } catch (e) {
    assert(false, `6. Workflows error: ${e}`);
  }

  // Test 7: Evolution Proposals Two-Stage Lifecycle
  try {
    // 7.1 Create proposal
    const proposal = await api.createProposal(savedCrmId, 'improve_follow_up');
    assert(proposal.status === 'pending', '7.1 New evolution proposal has status pending');
    assert(Boolean(proposal.proposal_id), '7.2 Proposal has valid proposal_id');

    // 7.2 Stage 1: Approve
    const approved = await api.approveProposal(savedCrmId, proposal.proposal_id, 1);
    assert(approved.status === 'approved', '7.3 Stage 1: Proposal successfully transitioned to approved');
    assert(Boolean(approved.approved_at), '7.4 Approval timestamp populated');

    // 7.3 Stage 2: Apply
    const applied = await api.applyProposal(savedCrmId, proposal.proposal_id);
    assert(applied.status === 'applied', '7.5 Stage 2: Proposal transitioned to applied');
    assert(Boolean(applied.applied_at), '7.6 Application timestamp populated');

    // Verify CRM configuration version incremented
    const crmAfterApply = await api.getCRM(savedCrmId);
    assert(crmAfterApply.configuration_version > 1, '7.7 Applying proposal incremented configuration_version');

    // 7.4 Rejection
    const p2 = await api.createProposal(savedCrmId, 'reduce_manual_work');
    const rejected = await api.rejectProposal(savedCrmId, p2.proposal_id, 'Not aligned with sales cycle');
    assert(rejected.status === 'rejected', '7.8 Reject proposal sets status to rejected');
    assert(rejected.rejection_reason === 'Not aligned with sales cycle', '7.9 Rejection reason stored in audit record');
  } catch (e) {
    assert(false, `7. Evolution Lifecycle error: ${e}`);
  }

  console.log(`\n📊 Test Results: ${passed} Passed, ${failed} Failed`);
  return { passed, failed };
}
