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

  // Test 8: Supabase OAuth & Client Configuration Audit
  try {
    const { supabase, isSupabaseConfigured } = await import('../services/supabase');
    assert(isSupabaseConfigured, '8.1 Supabase client is properly configured with public credentials');

    // 8.2 Client key security check
    const anonKey = process.env.VITE_SUPABASE_ANON_KEY || '';
    if (anonKey) {
      const parts = anonKey.split('.');
      if (parts.length === 3) {
        const payload = JSON.parse(Buffer.from(parts[1], 'base64').toString('utf8'));
        assert(payload.role === 'anon', '8.2 Supabase client uses anon role key and never exposes service_role');
        assert(payload.role !== 'service_role', '8.3 Service-role keys are strictly absent from client bundle');
      }
    }

    // 8.3 Google OAuth URL generation
    const googleOAuth = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: 'http://localhost:5173/auth/callback' },
    });
    assert(Boolean(googleOAuth.data?.url), '8.4 Google OAuth generates authorization endpoint URL');
    assert(
      Boolean(googleOAuth.data?.url?.includes('provider=google')),
      '8.5 Google OAuth target URL references provider=google'
    );

    // 8.4 GitHub OAuth URL generation
    const githubOAuth = await supabase.auth.signInWithOAuth({
      provider: 'github',
      options: { redirectTo: 'http://localhost:5173/auth/callback' },
    });
    assert(Boolean(githubOAuth.data?.url), '8.6 GitHub OAuth generates authorization endpoint URL');
    assert(
      Boolean(githubOAuth.data?.url?.includes('provider=github')),
      '8.7 GitHub OAuth target URL references provider=github'
    );

    // 8.5 Provider backend enablement audit (proves providers are not enabled in Gotrue)
    if (googleOAuth.data?.url) {
      const gRes = await fetch(googleOAuth.data.url);
      const gData = await gRes.json().catch(() => ({}));
      assert(
        gRes.status === 400 && gData.msg === 'Unsupported provider: provider is not enabled',
        '8.8 Gotrue correctly reports Google provider is not enabled in dashboard'
      );
    }
    if (githubOAuth.data?.url) {
      const ghRes = await fetch(githubOAuth.data.url);
      const ghData = await ghRes.json().catch(() => ({}));
      assert(
        ghRes.status === 400 && ghData.msg === 'Unsupported provider: provider is not enabled',
        '8.9 Gotrue correctly reports GitHub provider is not enabled in dashboard'
      );
    }
  } catch (e) {
    assert(false, `8. Supabase OAuth Audit error: ${e}`);
  }

  // Test 9: Live Adapter Selection & No Silent Mock Fallback
  try {
    const { api, setUseMockMode, getUseMockMode } = await import('../services/api');

    // 9.1 Adapter mode toggle
    setUseMockMode(false);
    assert(getUseMockMode() === false, '9.1 FastAPI Live mode can be explicitly activated');

    // 9.2 Verify live mode does not silently fallback to mock data on network error
    let threwErrorInLiveMode = false;
    try {
      // Calling generateCRM in live mode when no server is on port 8000 during test
      await api.generateCRM('Create an aerospace parts tracking CRM');
    } catch (err: unknown) {
      threwErrorInLiveMode = true;
      const msg = err instanceof Error ? err.message : String(err);
      assert(
        msg.includes('Failed to connect to backend') || msg.includes('ECONNREFUSED') || msg.includes('fetch failed'),
        '9.2 Live mode throws explicit network error instead of silently returning mock data'
      );
    }
    assert(threwErrorInLiveMode, '9.3 Live mode strictly rejects silent mock fallback');

    // 9.3 Switch back to mock mode for isolated unit tests
    setUseMockMode(true);
    assert(getUseMockMode() === true, '9.4 Explicit mock adapter mode can be restored');
    const mockRes = await api.generateCRM('healthcare clinic');
    assert(mockRes.configuration.industry === 'healthcare', '9.5 Mock adapter serves in-memory responses when explicitly active');
  } catch (e) {
    assert(false, `9. Live Adapter & Error Handling error: ${e}`);
  }

  console.log(`\n📊 Test Results: ${passed} Passed, ${failed} Failed`);
  return { passed, failed };
}
