import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Database,
  GitBranch,
  BarChart3,
  Dna,
  Layers,
  Calendar,
  Hash,
  Type,
  ToggleLeft,
  Mail,
  Phone,
  ListFilter,
  FileText,
  Edit,
} from 'lucide-react';
import { api } from '@/services/api';
import { CRMSummary, AnalyticsData, WorkflowData, EvolutionProposal, FieldType, CRMConfiguration } from '@/types/crm';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { TableSkeleton } from '@/components/ui/LoadingSkeleton';
import { useCRM } from '@/context/CRMContext';
import { useToast } from '@/context/ToastContext';
import { CRMSchemaEditor } from '@/components/CRMSchemaEditor/CRMSchemaEditor';

export const CRMDetailPage: React.FC = () => {
  const { crmId } = useParams<{ crmId: string }>();
  const navigate = useNavigate();
  const { selectCRM, setActiveEntityByName } = useCRM();
  const { success, error: toastError } = useToast();

  const [crm, setCrm] = useState<CRMSummary | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [workflows, setWorkflows] = useState<WorkflowData[]>([]);
  const [proposals, setProposals] = useState<EvolutionProposal[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [isSavingEdits, setIsSavingEdits] = useState(false);

  useEffect(() => {
    if (!crmId) return;
    setIsLoading(true);
    Promise.all([
      api.getCRM(crmId),
      api.getAnalytics(crmId).catch(() => null),
      api.listWorkflows(crmId).catch(() => []),
      api.listProposals(crmId).catch(() => []),
    ])
      .then(([crmData, analyticsData, workflowsData, proposalsData]) => {
        setCrm(crmData);
        setAnalytics(analyticsData);
        setWorkflows(workflowsData);
        setProposals(proposalsData);
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Failed to load CRM';
        setError(msg);
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [crmId]);

  const handleSaveCRMConfiguration = async (updatedConfig: CRMConfiguration) => {
    if (!crm) return;
    
    try {
      setIsSavingEdits(true);
      const updated = await api.updateCRMConfiguration(crm.crm_id, updatedConfig, crm.configuration_version);
      setCrm(updated);
      setIsEditing(false);
      success('CRM configuration updated successfully!');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to update CRM';
      toastError(msg);
      throw err; // Re-throw so modal stays open
    } finally {
      setIsSavingEdits(false);
    }
  };

  if (isLoading) {
    return <TableSkeleton rows={6} cols={3} />;
  }

  if (error || !crm) {
    return (
      <div className="p-8 text-center space-y-4">
        <h3 className="text-lg font-bold text-aura-navy">CRM Not Found</h3>
        <p className="text-xs text-slate-500">{error || 'Could not locate this CRM.'}</p>
        <Button onClick={() => navigate('/crms')} variant="outline">
          Back to My CRMs
        </Button>
      </div>
    );
  }

  const handleOpenEntityRecords = (entityName: string) => {
    selectCRM(crm.crm_id);
    setActiveEntityByName(entityName);
    navigate('/records');
  };

  const getFieldTypeIcon = (type: FieldType) => {
    switch (type) {
      case 'text':
        return <Type className="w-3.5 h-3.5 text-slate-500" />;
      case 'textarea':
        return <FileText className="w-3.5 h-3.5 text-slate-500" />;
      case 'number':
        return <Hash className="w-3.5 h-3.5 text-blue-500" />;
      case 'email':
        return <Mail className="w-3.5 h-3.5 text-indigo-500" />;
      case 'phone':
        return <Phone className="w-3.5 h-3.5 text-emerald-500" />;
      case 'date':
        return <Calendar className="w-3.5 h-3.5 text-amber-500" />;
      case 'boolean':
        return <ToggleLeft className="w-3.5 h-3.5 text-purple-500" />;
      case 'select':
        return <ListFilter className="w-3.5 h-3.5 text-cyan-500" />;
      default:
        return <Type className="w-3.5 h-3.5 text-slate-400" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Breadcrumb & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/crms')}
            leftIcon={<ArrowLeft className="w-4 h-4" />}
          >
            All CRMs
          </Button>
          <div className="h-4 w-px bg-slate-200" />
          <h2 className="text-xl font-bold text-aura-navy">{crm.name}</h2>
          <Badge variant={crm.status}>{crm.status}</Badge>
          <Badge variant="cyan">v{crm.configuration_version}</Badge>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsEditing(true)}
            leftIcon={<Edit className="w-4 h-4" />}
          >
            Edit CRM
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              selectCRM(crm.crm_id);
              navigate('/workflows');
            }}
            leftIcon={<GitBranch className="w-4 h-4" />}
          >
            Workflows ({workflows.length})
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              selectCRM(crm.crm_id);
              navigate('/analytics');
            }}
            leftIcon={<BarChart3 className="w-4 h-4" />}
          >
            Analytics
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              selectCRM(crm.crm_id);
              navigate('/evolution');
            }}
            leftIcon={<Dna className="w-4 h-4 text-aura-cyan" />}
          >
            Evolution ({proposals.length})
          </Button>
        </div>
      </div>

      {/* Overview Statistics Banner */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card className="p-4">
          <span className="text-[10px] font-bold uppercase text-slate-400">Total Leads/Records</span>
          <p className="text-xl font-bold text-aura-navy mt-1">
            {analytics?.total_leads ?? 0}
          </p>
        </Card>
        <Card className="p-4">
          <span className="text-[10px] font-bold uppercase text-slate-400">Qualified</span>
          <p className="text-xl font-bold text-aura-navy mt-1">
            {analytics?.qualified_leads ?? 0}
          </p>
        </Card>
        <Card className="p-4">
          <span className="text-[10px] font-bold uppercase text-slate-400">Won</span>
          <p className="text-xl font-bold text-emerald-600 mt-1">
            {analytics?.won_leads ?? 0}
          </p>
        </Card>
        <Card className="p-4">
          <span className="text-[10px] font-bold uppercase text-slate-400">Conversion Rate</span>
          <p className="text-xl font-bold text-amber-600 mt-1">
            {analytics && (analytics.conversion_rate !== undefined) ? `${((analytics.conversion_rate ?? 0) * 100).toFixed(1)}%` : '0%'}
          </p>
        </Card>
      </div>

      {/* Pipeline Stages Flow */}
      {crm.configuration.pipeline_stages?.length > 0 && (
        <Card className="p-5">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
            Active Pipeline Stages
          </h3>
          <div className="flex flex-wrap items-center gap-2">
            {crm.configuration.pipeline_stages.map((stage, idx) => (
              <div key={stage} className="flex items-center gap-2">
                <span className="px-3 py-1.5 rounded-lg bg-slate-100 border border-slate-200 text-xs font-bold text-aura-navy flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-aura-cyan" />
                  {stage}
                </span>
                {idx < crm.configuration.pipeline_stages.length - 1 && (
                  <span className="text-slate-300 font-bold">→</span>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Entity Schemas Deep Inspection */}
      <div className="space-y-4">
        <h3 className="text-sm font-bold text-aura-navy uppercase tracking-wider">
          Configured Entities & Dynamic Fields ({crm.configuration.entities.length})
        </h3>

        <div className="grid grid-cols-1 gap-5">
          {crm.configuration.entities.map((entity) => (
            <Card key={entity.name} className="overflow-hidden border border-slate-200">
              <div className="p-4 bg-slate-50/70 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-aura-navy text-white flex items-center justify-center font-bold text-xs">
                    <Layers className="w-4 h-4 text-aura-cyan" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-aura-navy">{entity.label}</h4>
                    <p className="text-xs text-slate-400 font-mono">
                      API machine identifier: <code>/records/{entity.name}</code>
                    </p>
                  </div>
                </div>

                <Button
                  size="sm"
                  variant="primary"
                  onClick={() => handleOpenEntityRecords(entity.name)}
                  leftIcon={<Database className="w-3.5 h-3.5" />}
                >
                  Manage {entity.label} Records
                </Button>
              </div>

              {/* Fields Table */}
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-white border-b border-slate-100 text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                    <tr>
                      <th className="py-2.5 px-4">Field Label</th>
                      <th className="py-2.5 px-4">Machine Name</th>
                      <th className="py-2.5 px-4">Field Type</th>
                      <th className="py-2.5 px-4">Requirement</th>
                      <th className="py-2.5 px-4">Options / Constraints</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white">
                    {entity.fields.map((f) => (
                      <tr key={f.name} className="hover:bg-slate-50/60">
                        <td className="py-3 px-4 font-semibold text-aura-charcoal">
                          {f.label}
                        </td>
                        <td className="py-3 px-4 font-mono text-slate-500 text-[11px]">
                          {f.name}
                        </td>
                        <td className="py-3 px-4">
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-medium">
                            {getFieldTypeIcon(f.type)}
                            <span className="capitalize">{f.type}</span>
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          {f.required ? (
                            <span className="text-rose-600 font-bold text-[11px] bg-rose-50 px-2 py-0.5 rounded">
                              Required
                            </span>
                          ) : (
                            <span className="text-slate-400">Optional</span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-slate-500">
                          {f.options && f.options.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {f.options.map((opt) => (
                                <span
                                  key={opt}
                                  className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 text-slate-600"
                                >
                                  {opt}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ))}
        </div>
      </div>

      {/* CRM Schema Editor Modal */}
      {isEditing && crm && (
        <CRMSchemaEditor
          crm={crm.configuration}
          onSave={handleSaveCRMConfiguration}
          onCancel={() => setIsEditing(false)}
          isLoading={isSavingEdits}
        />
      )}
    </div>
  );
};
