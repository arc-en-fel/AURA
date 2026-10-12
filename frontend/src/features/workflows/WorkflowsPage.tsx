import React, { useState, useEffect, useCallback } from 'react';
import {
  GitBranch,
  Plus,
  Zap,
  Clock,
  Bell,
  Mail,
  Dna,
  Info,
} from 'lucide-react';
import { useCRM } from '@/context/CRMContext';
import { WorkflowData, WorkflowTriggerType, WorkflowActionType } from '@/types/crm';
import { api } from '@/services/api';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Modal } from '@/components/ui/Modal';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { EmptyState } from '@/components/ui/EmptyState';
import { TableSkeleton } from '@/components/ui/LoadingSkeleton';
import { useToast } from '@/context/ToastContext';
import { useNavigate } from 'react-router-dom';

export const WorkflowsPage: React.FC = () => {
  const { activeCRM } = useCRM();
  const { success, error: toastError } = useToast();
  const navigate = useNavigate();

  const [workflows, setWorkflows] = useState<WorkflowData[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  // Form state
  const [name, setName] = useState('');
  const [triggerType, setTriggerType] = useState<WorkflowTriggerType>('record.created');
  const [triggerEntity, setTriggerEntity] = useState('');
  const [actionType, setActionType] = useState<WorkflowActionType>('create_follow_up_task');
  const [delayHours, setDelayHours] = useState<number>(24);
  const [enabled, setEnabled] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const fetchWorkflows = useCallback(async () => {
    if (!activeCRM) return;
    setIsLoading(true);
    try {
      const data = await api.listWorkflows(activeCRM.crm_id);
      setWorkflows(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch workflows.';
      toastError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [activeCRM, toastError]);

  useEffect(() => {
    fetchWorkflows();
    if (activeCRM?.configuration?.entities?.length) {
      setTriggerEntity(activeCRM.configuration.entities[0].name);
    }
  }, [fetchWorkflows, activeCRM]);

  const handleCreateWorkflow = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeCRM) return;

    if (!name.trim()) {
      toastError('Please provide a workflow name.');
      return;
    }

    setIsSubmitting(true);
    try {
      await api.createWorkflow(activeCRM.crm_id, {
        name,
        trigger: {
          type: triggerType,
          entity: triggerEntity,
        },
        actions: [
          {
            type: actionType,
            delay_hours: actionType === 'create_follow_up_task' ? delayHours : null,
          },
        ],
        enabled,
      });
      success(`Workflow "${name}" created!`);
      setIsCreateModalOpen(false);
      setName('');
      fetchWorkflows();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create workflow.';
      toastError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const getActionIcon = (type: WorkflowActionType) => {
    switch (type) {
      case 'create_follow_up_task':
        return <Clock className="w-4 h-4 text-amber-500" />;
      case 'notify_owner':
        return <Bell className="w-4 h-4 text-blue-500" />;
      case 'send_email':
        return <Mail className="w-4 h-4 text-indigo-500" />;
    }
  };

  if (!activeCRM) {
    return (
      <EmptyState
        icon={<GitBranch className="w-6 h-6" />}
        title="No Active CRM Selected"
        description="Select a CRM to view and configure event-driven workflows."
        actionLabel="Go to My CRMs"
        onAction={() => navigate('/crms')}
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-aura-navy">Workflows & Automations</h2>
          <p className="text-xs text-slate-500 mt-1">
            Event-driven triggers and allowlisted automations for {activeCRM.name}.
          </p>
        </div>

        <Button
          variant="primary"
          onClick={() => setIsCreateModalOpen(true)}
          leftIcon={<Plus className="w-4 h-4 text-aura-cyan" />}
        >
          Create Workflow
        </Button>
      </div>

      {/* RLS Security Architecture Notice */}
      <div className="p-4 rounded-xl bg-blue-50 border border-blue-200 text-xs text-blue-900 flex items-start gap-3">
        <Info className="w-5 h-5 text-aura-deep shrink-0 mt-0.5" />
        <div className="space-y-1">
          <p className="font-bold text-aura-navy">
            Architectural Guard: Evolution-Controlled Updates
          </p>
          <p className="leading-relaxed text-slate-700">
            Under AURA's database security design, direct in-place mutations to existing workflows are restricted. To optimize delays, triggers, or actions on existing workflows, propose and approve changes through the{' '}
            <button
              onClick={() => navigate('/evolution')}
              className="font-bold text-aura-cyan underline"
            >
              Evolution Center
            </button>
            . This ensures transaction atomicity, audit logging, and configuration version increments.
          </p>
        </div>
      </div>

      {/* Workflows List */}
      {isLoading ? (
        <TableSkeleton rows={4} cols={3} />
      ) : workflows.length === 0 ? (
        <EmptyState
          icon={<GitBranch className="w-6 h-6" />}
          title="No Workflows Registered"
          description="Create event-triggered automations or use AI Evolution to recommend workflows."
          actionLabel="Create First Workflow"
          onAction={() => setIsCreateModalOpen(true)}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {workflows.map((wf) => (
            <Card key={wf.workflow_id} className="p-5 flex flex-col justify-between">
              <div>
                <div className="flex items-start justify-between gap-2 mb-3">
                  <h3 className="font-bold text-sm text-aura-navy">{wf.name}</h3>
                  <Badge variant={wf.status}>{wf.status}</Badge>
                </div>

                {/* Trigger Details */}
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-100 text-xs space-y-1 mb-3">
                  <div className="flex items-center gap-2 text-slate-500 font-bold uppercase text-[10px]">
                    <Zap className="w-3.5 h-3.5 text-amber-500" />
                    Trigger Event
                  </div>
                  <p className="font-mono text-aura-charcoal">
                    <code>{wf.trigger.type}</code> on entity{' '}
                    <span className="font-bold text-aura-navy">{wf.trigger.entity}</span>
                  </p>
                </div>

                {/* Actions Details */}
                <div className="space-y-2">
                  <p className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">
                    Execution Actions ({wf.actions.length})
                  </p>
                  {wf.actions.map((act, i) => (
                    <div
                      key={i}
                      className="p-2.5 rounded-lg bg-white border border-slate-200 text-xs flex items-center justify-between"
                    >
                      <div className="flex items-center gap-2">
                        {getActionIcon(act.type)}
                        <span className="font-semibold text-aura-charcoal">
                          {act.type.replace(/_/g, ' ')}
                        </span>
                      </div>
                      {act.delay_hours !== null && act.delay_hours !== undefined && (
                        <span className="text-[11px] font-mono font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded">
                          Delay: {act.delay_hours}h
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Evolution action CTA */}
              <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
                <span className="text-slate-400 text-[10px] font-mono">
                  ID: {wf.workflow_id.slice(0, 8)}...
                </span>
                <button
                  onClick={() => navigate('/evolution')}
                  className="inline-flex items-center gap-1 font-semibold text-aura-cyan hover:underline"
                >
                  <Dna className="w-3.5 h-3.5" />
                  Evolve Workflow
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Create Workflow Modal */}
      {isCreateModalOpen && (
        <Modal
          isOpen={isCreateModalOpen}
          onClose={() => setIsCreateModalOpen(false)}
          title="Create Allowlisted Workflow"
          description="Registers an event-driven automation for the active CRM."
          maxWidth="lg"
        >
          <form onSubmit={handleCreateWorkflow} className="space-y-4">
            <Input
              label="Workflow Name"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Follow-up after new lead"
            />

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Select
                label="Trigger Event"
                value={triggerType}
                onChange={(e) => setTriggerType(e.target.value as WorkflowTriggerType)}
                options={[
                  { label: 'Record Created (record.created)', value: 'record.created' },
                  { label: 'Record Updated (record.updated)', value: 'record.updated' },
                  { label: 'Stage Changed (record.stage_changed)', value: 'record.stage_changed' },
                ]}
              />

              <Select
                label="Trigger Entity"
                value={triggerEntity}
                onChange={(e) => setTriggerEntity(e.target.value)}
                options={activeCRM.configuration.entities.map((ent) => ({
                  label: `${ent.label} (${ent.name})`,
                  value: ent.name,
                }))}
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Select
                label="Allowlisted Action"
                value={actionType}
                onChange={(e) => setActionType(e.target.value as WorkflowActionType)}
                options={[
                  { label: 'Create Follow-up Task', value: 'create_follow_up_task' },
                  { label: 'Notify CRM Owner', value: 'notify_owner' },
                  { label: 'Send Automated Email', value: 'send_email' },
                ]}
              />

              {actionType === 'create_follow_up_task' && (
                <Input
                  label="Execution Delay (Hours)"
                  type="number"
                  min={0}
                  max={8760}
                  value={String(delayHours)}
                  onChange={(e) => setDelayHours(Number(e.target.value))}
                />
              )}
            </div>

            <div className="flex items-center gap-3 pt-2">
              <input
                type="checkbox"
                id="wf-enabled"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                className="w-4 h-4 rounded text-aura-cyan focus:ring-aura-cyan border-slate-300"
              >
              </input>
              <label htmlFor="wf-enabled" className="text-xs font-semibold text-slate-700 cursor-pointer">
                Enable immediately (uncheck to save as draft)
              </label>
            </div>

            <div className="flex justify-end gap-2 pt-4 border-t border-slate-100">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setIsCreateModalOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit" variant="primary" size="sm" isLoading={isSubmitting}>
                Save Workflow
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
};
