export type FieldType =
  | 'text'
  | 'textarea'
  | 'email'
  | 'number'
  | 'date'
  | 'boolean'
  | 'select'
  | 'phone';

export interface CRMField {
  name: string;
  label: string;
  type: FieldType;
  required: boolean;
  options?: string[];
}

export interface CRMEntity {
  name: string;
  label: string;
  fields: CRMField[];
}

export interface CRMConfiguration {
  schema_version: '1.0';
  name: string;
  industry: string;
  entities: CRMEntity[];
  pipeline_stages: string[];
}

export interface GenerateCRMResponse {
  configuration: CRMConfiguration;
  warnings: string[];
}

export interface CRMSummary {
  crm_id: string;
  name: string;
  status: 'active' | 'archived';
  configuration_version: number;
  configuration: CRMConfiguration;
}

export interface CRMListResponse {
  items: CRMSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface CRMRecord {
  id: string;
  crm_id: string;
  entity_name: string;
  data: Record<string, unknown>;
  source?: string | null;
  created_at: string;
  updated_at: string;
}

export interface RecordListResponse {
  items: CRMRecord[];
  total: number;
  limit: number;
  offset: number;
}

export interface ImportRowError {
  row: number;
  code: string;
  message: string;
}

export interface ImportResult {
  created: number;
  skipped: number;
  errors: ImportRowError[];
}

export type WorkflowTriggerType =
  | 'record.created'
  | 'record.updated'
  | 'record.stage_changed';

export type WorkflowActionType =
  | 'create_follow_up_task'
  | 'notify_owner'
  | 'send_email';

export interface WorkflowTrigger {
  type: WorkflowTriggerType;
  entity: string;
}

export interface WorkflowAction {
  type: WorkflowActionType;
  delay_hours?: number | null;
}

export interface WorkflowData {
  workflow_id: string;
  status: 'draft' | 'active' | 'disabled';
  name: string;
  trigger: WorkflowTrigger;
  actions: WorkflowAction[];
}

export interface CreateWorkflowPayload {
  name: string;
  trigger: WorkflowTrigger;
  actions: WorkflowAction[];
  enabled: boolean;
}

export interface AnalyticsMetricItem {
  value?: string;
  count: number;
  [key: string]: unknown;
}

export interface AnalyticsData {
  total_leads: number;
  qualified_leads: number;
  won_leads: number;
  conversion_rate: number;
  by_source: AnalyticsMetricItem[];
  by_stage: AnalyticsMetricItem[];
}

export type EvolutionObjective =
  | 'improve_follow_up'
  | 'improve_conversion'
  | 'reduce_manual_work';

export interface ProposedChange {
  type: 'workflow.update' | 'workflow.create';
  workflow_id?: string;
  delay_hours?: number;
  name?: string;
  trigger?: WorkflowTrigger;
  actions?: WorkflowAction[];
}

export type EvolutionStatus =
  | 'pending'
  | 'approved'
  | 'applied'
  | 'rejected'
  | 'stale'
  | 'failed';

export interface EvolutionProposal {
  proposal_id: string;
  status: EvolutionStatus;
  summary: string;
  proposed_change: ProposedChange;
  evidence: Record<string, unknown>[];
  approved_at?: string | null;
  approved_by?: string | null;
  applied_at?: string | null;
  applied_by?: string | null;
  rejected_at?: string | null;
  rejected_by?: string | null;
  rejection_reason?: string | null;
  application_error?: string | null;
}

// API Envelopes
export interface ApiSuccessEnvelope<T> {
  data: T;
  meta: {
    request_id?: string;
    total?: number;
    limit?: number;
    offset?: number;
  };
}

export interface ApiErrorDetail {
  field?: string | null;
  issue: string;
}

export interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: ApiErrorDetail[];
    request_id?: string;
  };
}
