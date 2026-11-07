export type FieldType =
  | 'text'
  | 'textarea'
  | 'email'
  | 'number'
  | 'currency'
  | 'date'
  | 'datetime'
  | 'boolean'
  | 'select'
  | 'multi_select'
  | 'phone'
  | 'url'
  | 'status';

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

export interface UIConfig {
  /** Mapping of pipeline stage name → palette color key (e.g. 'New' → 'blue') */
  stage_colors?: Record<string, string>;
  [key: string]: unknown;
}

export interface CRMConfiguration {
  schema_version: '1.0';
  name: string;
  industry: string;
  entities: CRMEntity[];
  pipeline_stages: string[];
  ui_config?: UIConfig | null;
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
  duplicate?: number;
  failed?: number;
  total_rows?: number;
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
  name?: string;
  status?: string;
  count: number;
  percentage?: number;
  [key: string]: unknown;
}

export interface NumericMetricItem {
  field_name: string;
  field_label: string;
  type: 'number' | 'currency';
  total: number;
  average: number;
  min: number;
  max: number;
  median?: number;
  values?: number[];
}

export interface CategoricalMetricItem {
  field_name: string;
  field_label: string;
  distribution: AnalyticsMetricItem[];
}

export interface KPICardItem {
  id: string;
  title: string;
  value: string | number;
  subtitle?: string;
  format?: 'number' | 'currency' | 'percent' | 'text';
}

export interface AnalyticsData {
  // Universal metrics
  total_records?: number;
  entity_name?: string;
  entity_label?: string;
  status_distribution?: AnalyticsMetricItem[];
  by_stage?: AnalyticsMetricItem[];
  missing_status_count?: number;
  by_source?: AnalyticsMetricItem[];
  numeric_metrics?: NumericMetricItem[] | Record<string, any>;
  categorical_metrics?: CategoricalMetricItem[] | Record<string, any>;
  kpi_cards?: Array<KPICardItem | { id?: string; title?: string; label?: string; value: string | number; subtitle?: string; format?: string }>;
  schema_info?: {
    primary_entity_name?: string;
    primary_entity_label?: string;
    pipeline_stages?: string[];
    stage_field_name?: string | null;
    stage_field_label?: string | null;
    source_field_name?: string | null;
    available_fields?: string[];
    categorical_fields?: Array<{ name: string; label: string }>;
    numeric_fields?: Array<{ name: string; label: string; type: string }>;
  };
  // Backward compatibility
  total_leads?: number;
  qualified_leads?: number;
  won_leads?: number;
  conversion_rate?: number;
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
