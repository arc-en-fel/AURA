import {
  CRMConfiguration,
  CRMSummary,
  CRMListResponse,
  CRMRecord,
  RecordListResponse,
  ImportResult,
  WorkflowData,
  CreateWorkflowPayload,
  AnalyticsData,
  EvolutionProposal,
  EvolutionObjective,
  GenerateCRMResponse,
  ApiSuccessEnvelope,
  ApiErrorEnvelope,
} from '@/types/crm';
import { supabase } from './supabase';
import {
  INITIAL_CRMS,
  INITIAL_RECORDS,
  INITIAL_WORKFLOWS,
  INITIAL_PROPOSALS,
  INITIAL_ANALYTICS,
} from './mockData';

const env = (typeof import.meta !== 'undefined' && import.meta.env) ? import.meta.env : (typeof process !== 'undefined' ? process.env : {}) as Record<string, string>;

const BASE_URL = env.VITE_API_BASE_URL || '/api/v1';

// In-memory state for mock mode fallback when offline or explicitly enabled
class MockBackendStorage {
  crms: CRMSummary[] = [...INITIAL_CRMS];
  records: CRMRecord[] = [...INITIAL_RECORDS];
  workflows: WorkflowData[] = [...INITIAL_WORKFLOWS];
  proposals: EvolutionProposal[] = [...INITIAL_PROPOSALS];

  generateCRM(prompt: string): GenerateCRMResponse {
    const isHealthcare = prompt.toLowerCase().includes('health') || prompt.toLowerCase().includes('clinic') || prompt.toLowerCase().includes('patient');
    const isRealEstate = prompt.toLowerCase().includes('real estate') || prompt.toLowerCase().includes('property');

    if (isHealthcare) {
      return {
        configuration: {
          schema_version: '1.0',
          name: 'Clinic & Patient Care CRM',
          industry: 'healthcare',
          entities: [
            {
              name: 'patient',
              label: 'Patient',
              fields: [
                { name: 'full_name', label: 'Patient Name', type: 'text', required: true },
                { name: 'email', label: 'Email Address', type: 'email', required: false },
                { name: 'phone', label: 'Primary Phone', type: 'phone', required: true },
                { name: 'date_of_birth', label: 'Date of Birth', type: 'date', required: true },
                { name: 'blood_group', label: 'Blood Group', type: 'select', required: false, options: ['A+', 'A-', 'B+', 'B-', 'O+', 'O-', 'AB+', 'AB-'] },
                { name: 'emergency_contact', label: 'Emergency Contact Phone', type: 'phone', required: false },
                { name: 'status', label: 'Admission Status', type: 'select', required: true, options: ['Registered', 'Triage', 'In-Consultation', 'Admitted', 'Discharged'] },
              ],
            },
            {
              name: 'appointment',
              label: 'Appointment',
              fields: [
                { name: 'patient_id', label: 'Patient Reference', type: 'text', required: true },
                { name: 'doctor_name', label: 'Doctor', type: 'text', required: true },
                { name: 'appointment_date', label: 'Appointment Date', type: 'date', required: true },
                { name: 'status', label: 'Status', type: 'select', required: true, options: ['Scheduled', 'Completed', 'Cancelled', 'No-Show'] },
                { name: 'notes', label: 'Doctor Notes', type: 'textarea', required: false },
              ],
            },
          ],
          pipeline_stages: ['Registered', 'Triage', 'In-Consultation', 'Admitted', 'Discharged'],
        },
        warnings: [],
      };
    }

    if (isRealEstate) {
      return {
        configuration: {
          schema_version: '1.0',
          name: 'Premier Realty CRM',
          industry: 'real_estate',
          entities: [
            {
              name: 'property_lead',
              label: 'Property Buyer Lead',
              fields: [
                { name: 'full_name', label: 'Buyer Name', type: 'text', required: true },
                { name: 'email', label: 'Email', type: 'email', required: true },
                { name: 'phone', label: 'Phone Number', type: 'phone', required: true },
                { name: 'budget_max', label: 'Max Budget ($)', type: 'number', required: false },
                { name: 'preferred_location', label: 'Target City / Area', type: 'text', required: true },
                { name: 'status', label: 'Pipeline Stage', type: 'select', required: true, options: ['Inquiry', 'Site Visit', 'Offer Made', 'Under Escrow', 'Closed Won', 'Lost'] },
              ],
            },
            {
              name: 'listing',
              label: 'Property Listing',
              fields: [
                { name: 'title', label: 'Listing Title', type: 'text', required: true },
                { name: 'price', label: 'Asking Price ($)', type: 'number', required: true },
                { name: 'property_type', label: 'Property Type', type: 'select', required: true, options: ['Apartment', 'Villa', 'Commercial', 'Land'] },
                { name: 'is_featured', label: 'Featured Listing', type: 'boolean', required: false },
              ],
            },
          ],
          pipeline_stages: ['Inquiry', 'Site Visit', 'Offer Made', 'Under Escrow', 'Closed Won', 'Lost'],
        },
        warnings: [],
      };
    }

    // Default Sales / Custom CRM
    return {
      configuration: {
        schema_version: '1.0',
        name: 'AI Generated Sales CRM',
        industry: 'general_sales',
        entities: [
          {
            name: 'lead',
            label: 'Sales Lead',
            fields: [
              { name: 'full_name', label: 'Contact Name', type: 'text', required: true },
              { name: 'email', label: 'Email', type: 'email', required: true },
              { name: 'company', label: 'Company', type: 'text', required: false },
              { name: 'deal_value', label: 'Estimated Deal Value ($)', type: 'number', required: false },
              { name: 'status', label: 'Deal Stage', type: 'select', required: true, options: ['New', 'Contacted', 'Qualified', 'Negotiation', 'Won', 'Lost'] },
              { name: 'source', label: 'Lead Source', type: 'select', required: true, options: ['Website', 'Referral', 'Social Media', 'Direct Outreach'] },
            ],
          },
        ],
        pipeline_stages: ['New', 'Contacted', 'Qualified', 'Negotiation', 'Won', 'Lost'],
      },
      warnings: [],
    };
  }
}

const mockStorage = new MockBackendStorage();

// Determine whether to use mock adapter
let useMockMode = env.VITE_USE_MOCK === 'true';

export function setUseMockMode(enabled: boolean) {
  useMockMode = enabled;
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem('aura_use_mock', enabled ? 'true' : 'false');
  }
}

export function getUseMockMode(): boolean {
  if (typeof localStorage !== 'undefined') {
    const stored = localStorage.getItem('aura_use_mock');
    if (stored !== null) {
      return stored === 'true';
    }
  }
  return useMockMode;
}

// Request helper with automatic Bearer token and error handling
async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  // Get active Supabase session token
  const { data: sessionData } = await supabase.auth.getSession();
  const token = sessionData.session?.access_token;

  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const url = `${BASE_URL}${endpoint}`;

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
    });
  } catch (err: unknown) {
    const errorMsg = err instanceof Error ? err.message : 'Network error';
    throw new Error(`Failed to connect to backend at ${url}: ${errorMsg}`);
  }

  let json: unknown;
  try {
    json = await response.json();
  } catch {
    throw new Error(`Invalid response from backend (${response.status} ${response.statusText})`);
  }

  if (!response.ok) {
    console.error('[API ERROR] status:', response.status);
    console.error('[API ERROR] endpoint:', endpoint);
    console.error('[API ERROR] response:', json);
    const errorPayload = json as ApiErrorEnvelope;
    const message =
      errorPayload?.error?.message || `Request failed with status ${response.status}`;
    const err = new Error(message);
    (err as unknown as { code?: string; details?: unknown }).code =
      errorPayload?.error?.code || 'HTTP_ERROR';
    (err as unknown as { code?: string; details?: unknown }).details =
      errorPayload?.error?.details;
    throw err;
  }

  const successPayload = json as ApiSuccessEnvelope<T>;
  return successPayload.data;
}

// API Service Implementation
export const api = {
  // 1. CRM Generation (Draft only, not persisted)
  async generateCRM(prompt: string): Promise<GenerateCRMResponse> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 800));
      return mockStorage.generateCRM(prompt);
    }
    return await request<GenerateCRMResponse>('/crm/generate', {
      method: 'POST',
      body: JSON.stringify({ prompt }),
    });
  },

  // 2. Save CRM (Persist to database)
  async saveCRM(configuration: CRMConfiguration): Promise<CRMSummary> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 600));
      const newCrm: CRMSummary = {
        crm_id: crypto.randomUUID(),
        name: configuration.name,
        status: 'active',
        configuration_version: 1,
        configuration,
      };
      mockStorage.crms.unshift(newCrm);
      return newCrm;
    }
    return await request<CRMSummary>('/crm', {
      method: 'POST',
      body: JSON.stringify({ configuration }),
    });
  },

  // 3. List CRMs
  async listCRMs(limit = 20, offset = 0): Promise<CRMListResponse> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 300));
      return {
        items: mockStorage.crms.slice(offset, offset + limit),
        total: mockStorage.crms.length,
        limit,
        offset,
      };
    }
    return await request<CRMListResponse>(`/crm?limit=${limit}&offset=${offset}`, {
      method: 'GET',
    });
  },

  // 4. Get Single CRM
  async getCRM(crmId: string): Promise<CRMSummary> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 200));
      const found = mockStorage.crms.find((c) => c.crm_id === crmId);
      if (!found) throw new Error('CRM not found');
      return found;
    }
    return await request<CRMSummary>(`/crm/${crmId}`, {
      method: 'GET',
    });
  },

  // 4.5 Update CRM Configuration
  async updateCRMConfiguration(
    crmId: string,
    configuration: CRMConfiguration,
    expectedVersion?: number
  ): Promise<CRMSummary> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 600));
      const idx = mockStorage.crms.findIndex((c) => c.crm_id === crmId);
      if (idx === -1) throw new Error('CRM not found');
      mockStorage.crms[idx] = {
        ...mockStorage.crms[idx],
        configuration,
        configuration_version: (mockStorage.crms[idx].configuration_version || 0) + 1,
      };
      return mockStorage.crms[idx];
    }
    return await request<CRMSummary>(`/crm/${crmId}/configuration`, {
      method: 'PATCH',
      body: JSON.stringify({
        configuration,
        expected_version: expectedVersion,
      }),
    });
  },

  // 5. List Dynamic Records
  async listRecords(
    crmId: string,
    entityName: string,
    limit = 20,
    offset = 0
  ): Promise<RecordListResponse> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 300));
      const filtered = mockStorage.records.filter(
        (r) => r.crm_id === crmId && r.entity_name === entityName
      );
      return {
        items: filtered.slice(offset, offset + limit),
        total: filtered.length,
        limit,
        offset,
      };
    }
    return await request<RecordListResponse>(
      `/crm/${crmId}/records/${entityName}?limit=${limit}&offset=${offset}`,
      {
        method: 'GET',
      }
    );
  },

  // 6. Create Record
  async createRecord(
    crmId: string,
    entityName: string,
    data: Record<string, unknown>,
    source?: string
  ): Promise<CRMRecord> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 400));
      const newRecord: CRMRecord = {
        id: crypto.randomUUID(),
        crm_id: crmId,
        entity_name: entityName,
        data,
        source: source || 'Manual',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      mockStorage.records.unshift(newRecord);
      return newRecord;
    }
    return await request<CRMRecord>(`/crm/${crmId}/records/${entityName}`, {
      method: 'POST',
      body: JSON.stringify({ data, source }),
    });
  },

  // 7. Update Record
  async updateRecord(
    crmId: string,
    entityName: string,
    recordId: string,
    data: Record<string, unknown>
  ): Promise<CRMRecord> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 300));
      const idx = mockStorage.records.findIndex((r) => r.id === recordId);
      if (idx === -1) throw new Error('Record not found');
      mockStorage.records[idx] = {
        ...mockStorage.records[idx],
        data: { ...mockStorage.records[idx].data, ...data },
        updated_at: new Date().toISOString(),
      };
      return mockStorage.records[idx];
    }
    return await request<CRMRecord>(
      `/crm/${crmId}/records/${entityName}/${recordId}`,
      {
        method: 'PATCH',
        body: JSON.stringify({ data }),
      }
    );
  },

  // 8. Delete Record
  async deleteRecord(
    crmId: string,
    entityName: string,
    recordId: string
  ): Promise<{ deleted: boolean }> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 250));
      mockStorage.records = mockStorage.records.filter((r) => r.id !== recordId);
      return { deleted: true };
    }
    return await request<{ deleted: boolean }>(
      `/crm/${crmId}/records/${entityName}/${recordId}`,
      {
        method: 'DELETE',
      }
    );
  },

  // 9. Import CSV
  async importCSV(
    crmId: string,
    entityName: string,
    file: File
  ): Promise<ImportResult> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 600));
      // Mock CSV parse simulation
      const text = await file.text();
      const lines = text.split('\n').filter((l) => l.trim().length > 0);
      if (lines.length <= 1) {
        return { created: 0, skipped: 0, errors: [{ row: 1, code: 'EMPTY_FILE', message: 'No data rows found.' }] };
      }
      const headers = lines[0].split(',').map((h) => h.trim());
      let created = 0;
      for (let i = 1; i < lines.length; i++) {
        const cols = lines[i].split(',').map((c) => c.trim());
        const rowData: Record<string, unknown> = {};
        headers.forEach((h, idx) => {
          if (cols[idx]) rowData[h] = cols[idx];
        });
        mockStorage.records.push({
          id: crypto.randomUUID(),
          crm_id: crmId,
          entity_name: entityName,
          data: rowData,
          source: 'CSV',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
        created++;
      }
      return {
        created,
        skipped: 0,
        errors: [],
      };
    }
    const formData = new FormData();
    formData.append('file', file);
    return await request<ImportResult>(
      `/crm/${crmId}/records/${entityName}/import`,
      {
        method: 'POST',
        body: formData,
      }
    );
  },

  // 10. List Workflows
  async listWorkflows(crmId: string): Promise<WorkflowData[]> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 200));
      return mockStorage.workflows;
    }
    const res = await request<{ items: WorkflowData[] }>(`/crm/${crmId}/workflows`, {
      method: 'GET',
    });
    return res.items || [];
  },

  // 11. Create Workflow
  async createWorkflow(
    crmId: string,
    payload: CreateWorkflowPayload
  ): Promise<WorkflowData> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 400));
      const newWorkflow: WorkflowData = {
        workflow_id: crypto.randomUUID(),
        status: payload.enabled ? 'active' : 'draft',
        name: payload.name,
        trigger: payload.trigger,
        actions: payload.actions,
      };
      mockStorage.workflows.push(newWorkflow);
      return newWorkflow;
    }
    return await request<WorkflowData>(`/crm/${crmId}/workflows`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // 12. Analytics
  async getAnalytics(crmId: string): Promise<AnalyticsData> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 300));
      // Compute live mock stats from current records
      const leads = mockStorage.records.filter((r) => r.crm_id === crmId);
      const stageCounts: Record<string, number> = {};
      const sourceCounts: Record<string, number> = {};
      let qualified = 0;
      let won = 0;

      leads.forEach((l) => {
        const st = String(l.data['status'] || 'New');
        stageCounts[st] = (stageCounts[st] || 0) + 1;
        if (st.toLowerCase().includes('qualif')) qualified++;
        if (st.toLowerCase().includes('won')) won++;

        const src = String(l.data['source'] || 'Website');
        sourceCounts[src] = (sourceCounts[src] || 0) + 1;
      });

      const total = leads.length || INITIAL_ANALYTICS.total_leads;
      return {
        total_leads: total,
        qualified_leads: qualified || INITIAL_ANALYTICS.qualified_leads,
        won_leads: won || INITIAL_ANALYTICS.won_leads,
        conversion_rate: total > 0 ? Number((won / total).toFixed(4)) : 0.0,
        by_source: Object.keys(sourceCounts).length > 0
          ? Object.entries(sourceCounts).map(([value, count]) => ({ value, count }))
          : INITIAL_ANALYTICS.by_source,
        by_stage: Object.keys(stageCounts).length > 0
          ? Object.entries(stageCounts).map(([value, count]) => ({ value, count }))
          : INITIAL_ANALYTICS.by_stage,
      };
    }
    return await request<AnalyticsData>(`/crm/${crmId}/analytics`, {
      method: 'GET',
    });
  },

  // 13. List Evolution Proposals
  async listProposals(crmId: string): Promise<EvolutionProposal[]> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 200));
      return mockStorage.proposals;
    }
    const res = await request<{ items: EvolutionProposal[] }>(
      `/crm/${crmId}/evolution/proposals`,
      { method: 'GET' }
    );
    return res.items || [];
  },

  // 14. Create Evolution Proposal
  async createProposal(
    crmId: string,
    objective: EvolutionObjective
  ): Promise<EvolutionProposal> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 700));
      const firstWf = mockStorage.workflows[0];
      const newProposal: EvolutionProposal = {
        proposal_id: crypto.randomUUID(),
        status: 'pending',
        summary:
          objective === 'improve_follow_up'
            ? 'Shorten initial customer outreach response window to under 12 hours.'
            : objective === 'improve_conversion'
            ? 'Add an automated high-priority qualification notification for senior reps.'
            : 'Auto-assign incoming CSV and web leads to balance team workload.',
        proposed_change: firstWf
          ? {
              type: 'workflow.update',
              workflow_id: firstWf.workflow_id,
              delay_hours: 6,
            }
          : {
              type: 'workflow.create',
              name: 'Auto Lead Routing',
              trigger: { type: 'record.created', entity: 'lead' },
              actions: [{ type: 'notify_owner' }],
            },
        evidence: [
          { metric: 'conversion_velocity', observation: 'Fast response leads close 40% faster' },
        ],
      };
      mockStorage.proposals.unshift(newProposal);
      return newProposal;
    }
    return await request<EvolutionProposal>(`/crm/${crmId}/evolution/proposals`, {
      method: 'POST',
      body: JSON.stringify({ objective }),
    });
  },

  // 15. Approve Proposal (Stage 1)
  async approveProposal(
    crmId: string,
    proposalId: string,
    expectedVersion?: number
  ): Promise<EvolutionProposal> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 300));
      const idx = mockStorage.proposals.findIndex((p) => p.proposal_id === proposalId);
      if (idx === -1) throw new Error('Proposal not found');
      mockStorage.proposals[idx] = {
        ...mockStorage.proposals[idx],
        status: 'approved',
        approved_at: new Date().toISOString(),
        approved_by: '00000000-0000-0000-0000-000000000000',
      };
      return mockStorage.proposals[idx];
    }
    return await request<EvolutionProposal>(
      `/crm/${crmId}/evolution/proposals/${proposalId}/approve`,
      {
        method: 'POST',
        body: JSON.stringify({
          expected_status: 'pending',
          expected_version: expectedVersion,
        }),
      }
    );
  },

  // 16. Apply Proposal (Stage 2)
  async applyProposal(
    crmId: string,
    proposalId: string
  ): Promise<EvolutionProposal> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 450));
      const idx = mockStorage.proposals.findIndex((p) => p.proposal_id === proposalId);
      if (idx === -1) throw new Error('Proposal not found');
      const p = mockStorage.proposals[idx];
      if (p.status !== 'approved') {
        throw new Error(`Proposal is '${p.status}', not approved.`);
      }
      // Increment CRM configuration version
      const crmIdx = mockStorage.crms.findIndex((c) => c.crm_id === crmId);
      if (crmIdx !== -1) {
        mockStorage.crms[crmIdx].configuration_version += 1;
      }
      // Update workflow if workflow.update
      if (p.proposed_change.type === 'workflow.update' && p.proposed_change.workflow_id) {
        const wfIdx = mockStorage.workflows.findIndex(
          (w) => w.workflow_id === p.proposed_change.workflow_id
        );
        if (wfIdx !== -1 && p.proposed_change.delay_hours !== undefined) {
          mockStorage.workflows[wfIdx].actions[0].delay_hours = p.proposed_change.delay_hours;
        }
      }
      mockStorage.proposals[idx] = {
        ...p,
        status: 'applied',
        applied_at: new Date().toISOString(),
        applied_by: '00000000-0000-0000-0000-000000000000',
      };
      return mockStorage.proposals[idx];
    }
    return await request<EvolutionProposal>(
      `/crm/${crmId}/evolution/proposals/${proposalId}/apply`,
      {
        method: 'POST',
        body: JSON.stringify({}),
      }
    );
  },

  // 17. Reject Proposal
  async rejectProposal(
    crmId: string,
    proposalId: string,
    reason: string
  ): Promise<EvolutionProposal> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 300));
      const idx = mockStorage.proposals.findIndex((p) => p.proposal_id === proposalId);
      if (idx === -1) throw new Error('Proposal not found');
      mockStorage.proposals[idx] = {
        ...mockStorage.proposals[idx],
        status: 'rejected',
        rejection_reason: reason,
        rejected_at: new Date().toISOString(),
        rejected_by: '00000000-0000-0000-0000-000000000000',
      };
      return mockStorage.proposals[idx];
    }
    return await request<EvolutionProposal>(
      `/crm/${crmId}/evolution/proposals/${proposalId}/reject`,
      {
        method: 'POST',
        body: JSON.stringify({ reason }),
      }
    );
  },

  // 18. CRM Chat — send a message and receive next question or readiness signal
  async chatCRM(
    messages: { role: 'user' | 'assistant'; content: string }[],
    generateNow = false,
    crmType?: string,
    questAnswers?: {  // ← NEW: Pass structured answers from questionnaire
      crm_type?: string;
      tracks?: string;
      pipeline_stages?: string;
      key_fields?: string;
      team_size?: string;
    }
  ): Promise<{
    reply?: string;
    ready_to_generate?: boolean;
    fallback_used?: boolean;
    configuration?: import('@/types/crm').CRMConfiguration;
    warnings?: string[];
  }> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 700));
      const userCount = messages.filter((m) => m.role === 'user').length;
      if (generateNow) {
        const userText = messages.filter((m) => m.role === 'user').map((m) => m.content).join(' ');
        const isHealthcare = userText.toLowerCase().includes('health') || userText.toLowerCase().includes('clinic');
        const isRealEstate = userText.toLowerCase().includes('real estate') || userText.toLowerCase().includes('property');
        const industrySeed = crmType || (isHealthcare ? 'healthcare' : isRealEstate ? 'real_estate' : 'general_sales');
        return {
          configuration: {
            schema_version: '1.0',
            name: `${industrySeed.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())} CRM`,
            industry: industrySeed,
            entities: [{
              name: 'lead', label: 'Lead',
              fields: [
                { name: 'full_name', label: 'Full Name', type: 'text', required: true },
                { name: 'email', label: 'Email', type: 'email', required: true },
                { name: 'status', label: 'Status', type: 'select', required: true, options: ['New', 'Active', 'Won', 'Lost'] },
              ],
            }],
            pipeline_stages: ['New', 'Active', 'Won', 'Lost'],
          },
          warnings: ['Mock mode: CRM generated from conversation summary.'],
        };
      }
      const mockQuestions = [
        "What are the main things you need to track — leads, clients, deals, appointments?",
        "How many stages does your typical process have? For example: New → Contacted → Won.",
        "What's the most important field you need on each record?",
        "What size is your team — solo, small (2–10), or larger?",
      ];
      const idx = Math.min(userCount - 1, mockQuestions.length - 1);
      const ready = userCount >= mockQuestions.length;
      return {
        reply: ready ? "I have everything I need! Click 'Generate My CRM' to create your custom CRM." : mockQuestions[idx],
        ready_to_generate: ready,
        fallback_used: true,
      };
    }
    const payload = { 
      messages, 
      generate_now: generateNow, 
      crm_type: crmType ?? null,
      quest_answers: questAnswers ?? {},  // ← NEW: Send structured answers
    };
    console.log('[CRM CHAT] Request payload:', JSON.stringify(payload, null, 2));
    
    return await request<{
      reply?: string;
      ready_to_generate?: boolean;
      fallback_used?: boolean;
      configuration?: import('@/types/crm').CRMConfiguration;
      warnings?: string[];
    }>('/crm/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // 19. Co-pilot chat — CRM-aware conversational assistant
  async copilotChat(
    messages: { role: 'user' | 'assistant'; content: string }[],
    crmId?: string | null,
  ): Promise<{
    reply: string;
    nav_route?: string | null;
    nav_label?: string | null;
    fallback?: boolean;
  }> {
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 700));
      const q = (messages[messages.length - 1]?.content ?? '').toLowerCase();
      if (q.includes('evolution') || q.includes('improve') || q.includes('proposal')) {
        return { reply: 'To propose improvements, use the Evolution Center. AURA will generate an AI-powered change proposal for your review.', nav_route: '/evolution', nav_label: 'Go to Evolution Center', fallback: true };
      }
      if (q.includes('workflow') || q.includes('automation')) {
        return { reply: 'Workflows fire automatically when a record event occurs. You can view and manage them on the Workflows page.', nav_route: '/workflows', nav_label: 'View Workflows', fallback: true };
      }
      if (q.includes('record') || q.includes('lead') || q.includes('import')) {
        return { reply: 'Records are stored dynamically using your CRM schema. You can create, edit, and import them on the Records page.', nav_route: '/records', nav_label: 'Open Records', fallback: true };
      }
      if (q.includes('analytics') || q.includes('conversion') || q.includes('metric')) {
        return { reply: 'AURA tracks total leads, conversion rate, and pipeline stage breakdowns on the Analytics page.', nav_route: '/analytics', nav_label: 'View Analytics', fallback: true };
      }
      return { reply: "I can help with questions about your CRM configuration, records, workflows, analytics, and evolution proposals. What would you like to know?", nav_route: null, nav_label: null, fallback: true };
    }
    return await request<{ reply: string; nav_route?: string | null; nav_label?: string | null; fallback?: boolean }>(
      '/copilot/chat',
      {
        method: 'POST',
        body: JSON.stringify({ messages, crm_id: crmId ?? null }),
      },
    );
  },
};
