import {
  CRMConfiguration,
  CRMSummary,
  CRMRecord,
  WorkflowData,
  AnalyticsData,
  EvolutionProposal,
} from '@/types/crm';

export const INITIAL_SAAS_CONFIG: CRMConfiguration = {
  schema_version: '1.0',
  name: 'SaaS Growth CRM',
  industry: 'saas',
  entities: [
    {
      name: 'lead',
      label: 'Lead',
      fields: [
        { name: 'full_name', label: 'Full Name', type: 'text', required: true },
        { name: 'email', label: 'Work Email', type: 'email', required: true },
        { name: 'company', label: 'Company Name', type: 'text', required: false },
        { name: 'phone', label: 'Phone Number', type: 'phone', required: false },
        {
          name: 'source',
          label: 'Lead Source',
          type: 'select',
          required: true,
          options: ['Website', 'LinkedIn', 'Referral', 'Outbound', 'Event'],
        },
        {
          name: 'status',
          label: 'Lead Stage',
          type: 'select',
          required: true,
          options: ['New', 'Qualified', 'Demo', 'Proposal', 'Won', 'Lost'],
        },
        { name: 'deal_value', label: 'Estimated Deal Value ($)', type: 'number', required: false },
        { name: 'notes', label: 'Internal Notes', type: 'textarea', required: false },
      ],
    },
    {
      name: 'contact',
      label: 'Customer Contact',
      fields: [
        { name: 'full_name', label: 'Full Name', type: 'text', required: true },
        { name: 'email', label: 'Email', type: 'email', required: true },
        { name: 'role', label: 'Job Title', type: 'text', required: false },
        { name: 'primary_contact', label: 'Primary Decision Maker', type: 'boolean', required: false },
      ],
    },
  ],
  pipeline_stages: ['New', 'Qualified', 'Demo', 'Proposal', 'Won', 'Lost'],
};

export const INITIAL_CRMS: CRMSummary[] = [
  {
    crm_id: '7d56637e-61ea-4ea2-9749-d7547e127201',
    name: 'SaaS Growth CRM',
    status: 'active',
    configuration_version: 1,
    configuration: INITIAL_SAAS_CONFIG,
  },
];

export const INITIAL_RECORDS: CRMRecord[] = [
  {
    id: 'a1111111-1111-1111-1111-111111111111',
    crm_id: '7d56637e-61ea-4ea2-9749-d7547e127201',
    entity_name: 'lead',
    data: {
      full_name: 'Sarah Connor',
      email: 'sarah@cyberdyne.io',
      company: 'Cyberdyne Systems',
      phone: '+1-555-0199',
      source: 'Website',
      status: 'Qualified',
      deal_value: 24000,
      notes: 'Interested in enterprise AI workflow automation.',
    },
    source: 'Website',
    created_at: new Date(Date.now() - 86400000 * 3).toISOString(),
    updated_at: new Date(Date.now() - 86400000 * 2).toISOString(),
  },
  {
    id: 'a2222222-2222-2222-2222-222222222222',
    crm_id: '7d56637e-61ea-4ea2-9749-d7547e127201',
    entity_name: 'lead',
    data: {
      full_name: 'Marcus Vance',
      email: 'm.vance@acmecloud.com',
      company: 'Acme Cloud Corp',
      phone: '+1-555-0144',
      source: 'LinkedIn',
      status: 'Demo',
      deal_value: 48000,
      notes: 'Scheduled product demo for Tuesday next week.',
    },
    source: 'LinkedIn',
    created_at: new Date(Date.now() - 86400000 * 5).toISOString(),
    updated_at: new Date(Date.now() - 86400000 * 1).toISOString(),
  },
  {
    id: 'a3333333-3333-3333-3333-333333333333',
    crm_id: '7d56637e-61ea-4ea2-9749-d7547e127201',
    entity_name: 'lead',
    data: {
      full_name: 'Elena Rostova',
      email: 'elena@innovate-tech.de',
      company: 'Innovate Tech Europe',
      phone: '+49-30-901820',
      source: 'Referral',
      status: 'Won',
      deal_value: 85000,
      notes: 'Signed 2-year annual SaaS contract.',
    },
    source: 'Referral',
    created_at: new Date(Date.now() - 86400000 * 12).toISOString(),
    updated_at: new Date(Date.now() - 86400000 * 4).toISOString(),
  },
  {
    id: 'a4444444-4444-4444-4444-444444444444',
    crm_id: '7d56637e-61ea-4ea2-9749-d7547e127201',
    entity_name: 'lead',
    data: {
      full_name: 'David Chen',
      email: 'dchen@starlight-ai.co',
      company: 'Starlight Labs',
      phone: '+1-555-0182',
      source: 'Website',
      status: 'New',
      deal_value: 15000,
      notes: 'Requested inbound evaluation demo.',
    },
    source: 'Website',
    created_at: new Date(Date.now() - 86400000 * 1).toISOString(),
    updated_at: new Date(Date.now() - 86400000 * 1).toISOString(),
  },
];

export const INITIAL_WORKFLOWS: WorkflowData[] = [
  {
    workflow_id: 'w1111111-1111-1111-1111-111111111111',
    name: 'New Lead Auto Follow-up',
    status: 'active',
    trigger: {
      type: 'record.created',
      entity: 'lead',
    },
    actions: [
      {
        type: 'create_follow_up_task',
        delay_hours: 24,
      },
    ],
  },
  {
    workflow_id: 'w2222222-2222-2222-2222-222222222222',
    name: 'High-Value Lead Alert',
    status: 'draft',
    trigger: {
      type: 'record.stage_changed',
      entity: 'lead',
    },
    actions: [
      {
        type: 'notify_owner',
      },
    ],
  },
];

export const INITIAL_PROPOSALS: EvolutionProposal[] = [
  {
    proposal_id: 'p1111111-1111-1111-1111-111111111111',
    status: 'pending',
    summary: 'Accelerate follow-up delay from 24h to 12h to increase response rates by 34%',
    proposed_change: {
      type: 'workflow.update',
      workflow_id: 'w1111111-1111-1111-1111-111111111111',
      delay_hours: 12,
    },
    evidence: [
      { metric: 'response_latency', observation: 'Leads followed up within 12h have 2.4x higher conversion' },
      { metric: 'pipeline_stagnation', observation: '42% of leads wait over 24h for initial touch' },
    ],
    approved_at: null,
    approved_by: null,
    applied_at: null,
    applied_by: null,
  },
];

export const INITIAL_ANALYTICS: AnalyticsData = {
  total_leads: 4,
  qualified_leads: 1,
  won_leads: 1,
  conversion_rate: 0.25,
  by_source: [
    { value: 'Website', count: 2 },
    { value: 'LinkedIn', count: 1 },
    { value: 'Referral', count: 1 },
  ],
  by_stage: [
    { value: 'New', count: 1 },
    { value: 'Qualified', count: 1 },
    { value: 'Demo', count: 1 },
    { value: 'Won', count: 1 },
  ],
};
