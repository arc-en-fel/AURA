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
    const cleanPrompt = prompt.trim();
    // Dynamically derive CRM title
    const titleMatch = cleanPrompt.match(/(?:create|build|generate|make)\s+(?:a|an)?\s*([a-zA-Z0-9\s_-]+?)(?:crm|\.|$)/i);
    const rawName = titleMatch ? titleMatch[1].trim() : cleanPrompt.slice(0, 30);
    const crmName = rawName.length > 3 ? `${rawName} CRM` : 'Custom Dynamic CRM';

    // Extract potential fields from prompt
    const lines = cleanPrompt.split(/[\n,;]+/);
    const candidateFields: Array<import('@/types/crm').CRMField> = [];
    const candidateStages: string[] = [];

    // Check if stages are specified (e.g. Statuses: A, B, C or Stages: A -> B -> C)
    const stageMatch = cleanPrompt.match(/(?:statuses|stages|pipeline):\s*([^\n\r]+)/i);
    if (stageMatch) {
      stageMatch[1].split(/[,\->]+/).forEach((s) => {
        const trimmed = s.trim();
        if (trimmed && !candidateStages.includes(trimmed)) candidateStages.push(trimmed);
      });
    }

    // Common field extraction from prompt text
    for (const line of lines) {
      const trimmed = line.trim().replace(/^[-*•\d.]+\s*/, '');
      if (trimmed.length > 2 && trimmed.length < 40 && !trimmed.toLowerCase().includes('crm')) {
        const fieldKey = trimmed.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
        if (fieldKey && !candidateFields.some((f) => f.name === fieldKey)) {
          let fieldType: any = 'text';
          if (fieldKey.includes('email')) fieldType = 'email';
          else if (fieldKey.includes('phone') || fieldKey.includes('tel')) fieldType = 'phone';
          else if (fieldKey.includes('revenue') || fieldKey.includes('price') || fieldKey.includes('budget') || fieldKey.includes('cost') || fieldKey.includes('value')) fieldType = 'currency';
          else if (fieldKey.includes('score') || fieldKey.includes('count') || fieldKey.includes('time') || fieldKey.includes('age') || fieldKey.includes('frequency')) fieldType = 'number';
          else if (fieldKey.includes('date') || fieldKey.includes('dob')) fieldType = 'date';
          else if (fieldKey.includes('status') || fieldKey.includes('stage')) fieldType = 'status';
          else if (fieldKey.includes('priority') || fieldKey.includes('segment') || fieldKey.includes('type') || fieldKey.includes('source')) fieldType = 'select';

          candidateFields.push({
            name: fieldKey,
            label: trimmed.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
            type: fieldType,
            required: candidateFields.length === 0,
            options: fieldType === 'select' ? ['Tier 1', 'Tier 2', 'General'] : undefined,
          });
        }
      }
    }

    // Ensure we have reasonable fallback fields if prompt was short
    if (candidateFields.length === 0) {
      candidateFields.push(
        { name: 'name', label: 'Name', type: 'text', required: true },
        { name: 'status', label: 'Status', type: 'status', required: true },
        { name: 'notes', label: 'Notes', type: 'textarea', required: false }
      );
    }

    const stages = candidateStages.length > 0 ? candidateStages : ['New', 'In Progress', 'Completed'];

    return {
      configuration: {
        schema_version: '1.0',
        name: crmName,
        industry: 'custom',
        entities: [
          {
            name: candidateFields[0].name.includes('name') ? candidateFields[0].name.replace(/_name$/, '') || 'record' : 'record',
            label: candidateFields[0].label.replace(/\s*Name$/i, '') || 'Record',
            fields: candidateFields,
          },
        ],
        pipeline_stages: stages,
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
    let result: CRMRecord;
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 400));
      result = {
        id: crypto.randomUUID(),
        crm_id: crmId,
        entity_name: entityName,
        data,
        source: source || 'Manual',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      mockStorage.records.unshift(result);
    } else {
      result = await request<CRMRecord>(`/crm/${crmId}/records/${entityName}`, {
        method: 'POST',
        body: JSON.stringify({ data, source }),
      });
    }
    if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('records-changed'));
    return result;
  },

  // 7. Update Record
  async updateRecord(
    crmId: string,
    entityName: string,
    recordId: string,
    data: Record<string, unknown>
  ): Promise<CRMRecord> {
    let result: CRMRecord;
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 300));
      const idx = mockStorage.records.findIndex((r) => r.id === recordId);
      if (idx === -1) throw new Error('Record not found');
      mockStorage.records[idx] = {
        ...mockStorage.records[idx],
        data: { ...mockStorage.records[idx].data, ...data },
        updated_at: new Date().toISOString(),
      };
      result = mockStorage.records[idx];
    } else {
      result = await request<CRMRecord>(
        `/crm/${crmId}/records/${entityName}/${recordId}`,
        {
          method: 'PATCH',
          body: JSON.stringify({ data }),
        }
      );
    }
    if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('records-changed'));
    return result;
  },

  // 8. Delete Record
  async deleteRecord(
    crmId: string,
    entityName: string,
    recordId: string
  ): Promise<{ deleted: boolean }> {
    let result: { deleted: boolean };
    if (getUseMockMode()) {
      await new Promise((r) => setTimeout(r, 250));
      mockStorage.records = mockStorage.records.filter((r) => r.id !== recordId);
      result = { deleted: true };
    } else {
      result = await request<{ deleted: boolean }>(
        `/crm/${crmId}/records/${entityName}/${recordId}`,
        {
          method: 'DELETE',
        }
      );
    }
    if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('records-changed'));
    return result;
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
      const crm = mockStorage.crms.find((c) => c.crm_id === crmId);
      const records = mockStorage.records.filter((r) => r.crm_id === crmId);
      const total = records.length;
      const stages = crm?.configuration?.pipeline_stages || ['New', 'In Progress', 'Completed'];
      const primaryEntity = crm?.configuration?.entities?.[0];

      // Stage counts with all configured stages represented
      const stageCounts: Record<string, number> = {};
      stages.forEach((s) => { stageCounts[s] = 0; });
      records.forEach((r) => {
        const val = String(r.data['status'] || r.data['stage'] || stages[0] || 'New');
        stageCounts[val] = (stageCounts[val] || 0) + 1;
      });

      const byStage = Object.entries(stageCounts).map(([value, count]) => ({
        value,
        count,
        percentage: total > 0 ? Number(((count / total) * 100).toFixed(1)) : 0,
      }));

      // Categorical & Numeric metrics
      const numericMetrics: Record<string, any> = {};
      const categoricalMetrics: Record<string, any> = {};
      const kpiCards: Array<{ label: string; value: string | number; subtitle: string }> = [];

      if (primaryEntity) {
        for (const field of primaryEntity.fields) {
          if (field.type === 'number' || field.type === 'currency') {
            const vals = records
              .map((r) => Number(r.data[field.name]))
              .filter((v) => !isNaN(v) && v !== null && v !== undefined);
            if (vals.length > 0) {
              const totalVal = vals.reduce((a, b) => a + b, 0);
              const avgVal = totalVal / vals.length;
              numericMetrics[field.name] = {
                label: field.label,
                count: vals.length,
                total: Number(totalVal.toFixed(2)),
                avg: Number(avgVal.toFixed(2)),
                min: Math.min(...vals),
                max: Math.max(...vals),
              };
              if (kpiCards.length < 2) {
                kpiCards.push({
                  label: `Avg ${field.label}`,
                  value: field.type === 'currency' ? `$${avgVal.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : avgVal.toFixed(1),
                  subtitle: `Total: ${field.type === 'currency' ? '$' : ''}${totalVal.toLocaleString()}`,
                });
              }
            }
          } else if (field.type === 'select' && field.name !== 'status') {
            const distMap: Record<string, number> = {};
            records.forEach((r) => {
              const v = String(r.data[field.name] || 'Unknown');
              distMap[v] = (distMap[v] || 0) + 1;
            });
            categoricalMetrics[field.name] = {
              label: field.label,
              distribution: Object.entries(distMap).map(([val, cnt]) => ({
                value: val,
                count: cnt,
                percentage: total > 0 ? Number(((cnt / total) * 100).toFixed(1)) : 0,
              })),
            };
          }
        }
      }

      return {
        total_records: total,
        total_leads: total,
        by_stage: byStage,
        by_source: [],
        numeric_metrics: numericMetrics,
        categorical_metrics: categoricalMetrics,
        kpi_cards: kpiCards,
        schema_info: {
          primary_entity_name: primaryEntity?.name || 'record',
          primary_entity_label: primaryEntity?.label || 'Record',
          stage_field_name: 'status',
          pipeline_stages: stages,
          available_fields: primaryEntity ? primaryEntity.fields.map((f) => f.name) : [],
        },
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

      // Detect action intents and return TOOL_CALL responses
      const crm = crmId ? mockStorage.crms.find((c) => c.crm_id === crmId) : null;
      const entityName = crm?.configuration?.entities?.[0]?.name || 'record';

      // Create record action
      if (q.match(/\b(create|add|new|insert)\b.*\b(record|entry|item|lead|customer|ticket|candidate)\b/)) {
        const fields = crm?.configuration?.entities?.[0]?.fields || [];
        const mockData: Record<string, any> = {};
        fields.forEach((f) => {
          if (f.type === 'text') mockData[f.name] = 'Sample Value';
          else if (f.type === 'email') mockData[f.name] = 'sample@example.com';
          else if (f.type === 'number' || f.type === 'currency') mockData[f.name] = 100;
          else if (f.type === 'select' || f.type === 'status') mockData[f.name] = f.options?.[0] || 'New';
          else if (f.type === 'boolean') mockData[f.name] = false;
          else if (f.type === 'date') mockData[f.name] = new Date().toISOString().split('T')[0];
          else mockData[f.name] = '';
        });
        return {
          reply: `Creating a new ${entityName} record for you. TOOL_CALL: {"name": "create_record", "arguments": {"entity_name": "${entityName}", "data": ${JSON.stringify(mockData)}}}`,
          nav_route: null, nav_label: null, fallback: true,
        };
      }

      // Delete record action
      if (q.match(/\b(delete|remove|trash)\b.*\b(record|entry|item)\b/)) {
        return {
          reply: `To delete a record, please specify the record ID or name. You can also delete records directly from the Records page.`,
          nav_route: '/records', nav_label: 'Open Records', fallback: true,
        };
      }

      // Update record action
      if (q.match(/\b(update|change|modify|edit|set)\b.*\b(record|entry|status|field|value)\b/)) {
        return {
          reply: `To update a record, specify the record you want to change and what field to update. You can also edit records directly from the Records page.`,
          nav_route: '/records', nav_label: 'Open Records', fallback: true,
        };
      }

      // Add field action
      if (q.match(/\b(add|create|new)\b.*\b(field|column)\b/)) {
        return {
          reply: `I'll add a new field. TOOL_CALL: {"name": "add_crm_field", "arguments": {"entity_name": "${entityName}", "field_name": "new_field", "field_type": "text", "label": "New Field"}}`,
          nav_route: null, nav_label: null, fallback: true,
        };
      }

      // Analytics question
      if (q.includes('analytics') || q.includes('metric') || q.includes('stats') || q.includes('how many')) {
        return { reply: 'You can view all dynamic analytics — pipeline stages, numeric aggregations, and KPI cards — on the Analytics page.', nav_route: '/analytics', nav_label: 'View Analytics', fallback: true };
      }

      // Schema / fields question
      if (q.includes('field') || q.includes('schema') || q.includes('what') && q.includes('track')) {
        const fieldList = crm?.configuration?.entities?.[0]?.fields?.map((f) => `${f.label} (${f.type})`).join(', ') || 'No fields configured';
        return { reply: `Your CRM tracks these fields: ${fieldList}`, nav_route: null, nav_label: null, fallback: true };
      }

      return { reply: "I can help with your CRM — ask me to create records, view analytics, add fields, or explain your pipeline. What would you like to do?", nav_route: null, nav_label: null, fallback: true };
    }
    return await request<{ reply: string; nav_route?: string | null; nav_label?: string | null; fallback?: boolean }>(
      '/copilot/chat',
      {
        method: 'POST',
        body: JSON.stringify({ messages, crm_id: crmId ?? null }),
      },
    );
  },

  // 20. Execute a copilot tool call
  async executeToolCall(
    crmId: string,
    toolCallRequest: {
      tool_name: string;
      arguments: Record<string, any>;
    }
  ): Promise<any> {
    if (getUseMockMode()) {
      // Mock: simulate immediate success
      await new Promise((r) => setTimeout(r, 300));
      return {
        success: true,
        data: { id: crypto.randomUUID(), created_at: new Date().toISOString() },
      };
    }

    const result = await request<any>(
      '/copilot/tool-call',
      {
        method: 'POST',
        body: JSON.stringify({
          tool_name: toolCallRequest.tool_name,
          crm_id: crmId,
          arguments: toolCallRequest.arguments,
        }),
      },
    );

    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('records-changed'));
      if (['add_crm_field', 'delete_crm_field', 'add_crm_stage', 'delete_crm_stage', 'update_crm_field'].includes(toolCallRequest.tool_name)) {
        window.dispatchEvent(new CustomEvent('crm-config-changed'));
      }
    }

    return result;
  },
};
