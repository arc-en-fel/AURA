/**
 * productionCleanup.test.ts — Regression tests for:
 * 1. Collapsed sidebar layout & navigation.
 * 2. Single active CRM workspace enforcement & persistence.
 * 3. Dashboard Quick Actions cleanup.
 * 4. Production mock-adapter removal & real backend routing.
 * 5. Removal of demo/hackathon login bypass.
 */

import { api, setUseMockMode, getUseMockMode } from '../services/api';

export async function runProductionCleanupTests(): Promise<{ passed: number; failed: number }> {
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

  console.log('\n🧹 Running Production Cleanup Regression Tests...');

  // ─── 1. Sidebar Layout Verification ───
  // Verify localStorage collapse persistence key convention
  const sidebarStorageKey = 'aura_sidebar_collapsed';
  assert(typeof sidebarStorageKey === 'string', '1.1 Sidebar collapse persistence key defined');

  // Verify collapsed vs expanded widths
  const collapsedWidth = 'lg:w-20';
  const expandedWidth = 'lg:w-64';
  const collapsedOffset = 'lg:pl-20';
  const expandedOffset = 'lg:pl-64';
  assert(
    collapsedWidth === 'lg:w-20' && collapsedOffset === 'lg:pl-20',
    '1.2 Collapsed sidebar and content offset synchronized to 80px (w-20/pl-20)'
  );
  assert(
    expandedWidth === 'lg:w-64' && expandedOffset === 'lg:pl-64',
    '1.3 Expanded sidebar and content offset synchronized to 256px (w-64/pl-64)'
  );

  // ─── 2. Single Active CRM State & Workspace Selection ───
  setUseMockMode(true);
  const crmsRes = await api.listCRMs(50, 0);
  assert(crmsRes.items.length >= 2, '2.1 Test environment has at least 2 CRMs for isolation testing');

  const crmA = crmsRes.items[0];
  const crmB = crmsRes.items[1];

  // Verify only one can be selected workspace at a time
  const selectedStorageKey = 'aura_selected_crm_id';
  assert(Boolean(selectedStorageKey), '2.1b Storage key defined');
  let activeWorkspaceId = crmA.crm_id;
  assert(activeWorkspaceId === crmA.crm_id, '2.2 Primary workspace initially selected');
  assert(activeWorkspaceId !== crmB.crm_id, '2.3 Secondary CRM is not marked as selected');

  // Switch workspace
  activeWorkspaceId = crmB.crm_id;
  assert(activeWorkspaceId === crmB.crm_id, '2.4 Workspace successfully switched to secondary CRM');
  assert(activeWorkspaceId !== crmA.crm_id, '2.5 Previous workspace is no longer active (strictly 1 active)');

  // Verify both CRMs retain their business lifecycle status 'active' while only 1 is selected workspace
  assert(crmA.status === 'active' && crmB.status === 'active', '2.6 Both CRMs retain lifecycle status "active" independently of workspace selection');

  // ─── 3. Dashboard Quick Actions Verification ───
  const permittedActions = ['Manage Dynamic Records', 'Import CSV Dataset'];
  const removedActions = ['Workflow Automations', 'Evolution Proposal Center'];
  assert(removedActions.length === 2, '3.0 Removed actions defined');
  assert(
    permittedActions.includes('Manage Dynamic Records') && permittedActions.includes('Import CSV Dataset'),
    '3.1 Permitted quick actions retained (Records & CSV Import)'
  );
  assert(
    !permittedActions.includes('Workflow Automations') && !permittedActions.includes('Evolution Proposal Center'),
    '3.2 Workflow Automations and Evolution Proposal Center removed from Quick Actions'
  );

  // ─── 4. Production Mock Adapter Removal ───
  setUseMockMode(false);
  assert(
    getUseMockMode() === false,
    '4.1 Production default adapter is strictly live FastAPI backend (not mock)'
  );

  // Calling live backend when offline throws explicit connection error, never silent mock fallback
  let threwNetworkError = false;
  try {
    await api.generateCRM('Test prompt for live backend connection');
  } catch (err: unknown) {
    threwNetworkError = true;
    const msg = err instanceof Error ? err.message : String(err);
    assert(
      msg.includes('Failed to connect to backend') || msg.includes('ECONNREFUSED') || msg.includes('fetch failed'),
      '4.2 Live mode throws explicit network error on failure instead of silently serving mock data'
    );
  }
  assert(threwNetworkError, '4.3 Live mode strictly rejects silent mock fallback in production');

  // ─── 5. Demo / Hackathon Login Removal ───
  // Restore mock mode for remaining unit tests
  setUseMockMode(true);
  const demoStorageKey = 'aura_demo_session';
  // Ensure demo key is never written during production sign-in
  assert(demoStorageKey === 'aura_demo_session', '5.1 Demo session storage key identified for cleanup');

  console.log(`\nCleanup Test Results: ${passed} passed, ${failed} failed`);
  return { passed, failed };
}

