import React, { useState, useEffect, useCallback } from 'react';
import {
  Dna,
  Sparkles,
  CheckCircle2,
  Play,
  XCircle,
  Clock,
  FileText,
  ShieldCheck,
  RefreshCw,
} from 'lucide-react';
import { useCRM } from '@/context/CRMContext';
import {
  EvolutionProposal,
  EvolutionObjective,
  ProposedChange,
} from '@/types/crm';
import { api } from '@/services/api';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Modal } from '@/components/ui/Modal';
import { Select } from '@/components/ui/Select';
import { EmptyState } from '@/components/ui/EmptyState';
import { TableSkeleton } from '@/components/ui/LoadingSkeleton';
import { useToast } from '@/context/ToastContext';
import { useNavigate } from 'react-router-dom';

export const EvolutionPage: React.FC = () => {
  const { activeCRM, refreshCRMs } = useCRM();
  const { success, error: toastError } = useToast();
  const navigate = useNavigate();

  const [proposals, setProposals] = useState<EvolutionProposal[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [selectedObjective, setSelectedObjective] =
    useState<EvolutionObjective>('improve_follow_up');

  // Modal states
  const [selectedProposal, setSelectedProposal] = useState<EvolutionProposal | null>(null);
  const [rejectingProposal, setRejectingProposal] = useState<EvolutionProposal | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [isRejecting, setIsRejecting] = useState(false);
  const [applyingProposal, setApplyingProposal] = useState<EvolutionProposal | null>(null);
  const [isApplying, setIsApplying] = useState(false);
  const [isApproving, setIsApproving] = useState(false);

  const fetchProposals = useCallback(async () => {
    if (!activeCRM) return;
    setIsLoading(true);
    try {
      const data = await api.listProposals(activeCRM.crm_id);
      setProposals(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch proposals.';
      toastError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [activeCRM, toastError]);

  useEffect(() => {
    fetchProposals();
  }, [fetchProposals]);

  // Generate a new proposal via AI
  const handleGenerateProposal = async () => {
    if (!activeCRM) return;
    setIsGenerating(true);
    try {
      const proposal = await api.createProposal(activeCRM.crm_id, selectedObjective);
      success('New evolutionary proposal synthesized!');
      setProposals((prev) => [proposal, ...prev]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to generate proposal.';
      toastError(msg);
    } finally {
      setIsGenerating(false);
    }
  };

  // Stage 1: Approve
  const handleApprove = async (proposal: EvolutionProposal) => {
    if (!activeCRM) return;
    setIsApproving(true);
    try {
      const approved = await api.approveProposal(
        activeCRM.crm_id,
        proposal.proposal_id,
        activeCRM.configuration_version
      );
      success('Proposal approved! Stage 1 complete. You can now apply the changes to live CRM.');
      setProposals((prev) =>
        prev.map((p) => (p.proposal_id === approved.proposal_id ? approved : p))
      );
      if (selectedProposal?.proposal_id === approved.proposal_id) {
        setSelectedProposal(approved);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Approval failed.';
      toastError(msg);
    } finally {
      setIsApproving(false);
    }
  };

  // Stage 2: Apply
  const handleApply = async () => {
    if (!activeCRM || !applyingProposal) return;
    setIsApplying(true);
    try {
      const applied = await api.applyProposal(
        activeCRM.crm_id,
        applyingProposal.proposal_id
      );
      success('Evolution proposal atomically applied to CRM configuration!');
      setApplyingProposal(null);
      await refreshCRMs();
      setProposals((prev) =>
        prev.map((p) => (p.proposal_id === applied.proposal_id ? applied : p))
      );
      if (selectedProposal?.proposal_id === applied.proposal_id) {
        setSelectedProposal(applied);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Application failed.';
      toastError(msg);
    } finally {
      setIsApplying(false);
    }
  };

  // Reject
  const handleReject = async () => {
    if (!activeCRM || !rejectingProposal) return;
    if (!rejectionReason.trim()) {
      toastError('Please provide a reason for rejection.');
      return;
    }
    setIsRejecting(true);
    try {
      const rejected = await api.rejectProposal(
        activeCRM.crm_id,
        rejectingProposal.proposal_id,
        rejectionReason
      );
      success('Proposal marked as rejected.');
      setRejectingProposal(null);
      setRejectionReason('');
      setProposals((prev) =>
        prev.map((p) => (p.proposal_id === rejected.proposal_id ? rejected : p))
      );
      if (selectedProposal?.proposal_id === rejected.proposal_id) {
        setSelectedProposal(rejected);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Rejection failed.';
      toastError(msg);
    } finally {
      setIsRejecting(false);
    }
  };

  if (!activeCRM) {
    return (
      <EmptyState
        icon={<Dna className="w-6 h-6" />}
        title="No Active CRM Selected"
        description="Select a CRM to view and manage self-evolving architecture proposals."
        actionLabel="Go to My CRMs"
        onAction={() => navigate('/crms')}
      />
    );
  }

  const renderProposedChangeDetails = (change: ProposedChange) => {
    if (change.type === 'workflow.update') {
      return (
        <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs space-y-1">
          <p className="font-bold text-aura-navy">Type: Workflow Mutation (workflow.update)</p>
          <p className="font-mono text-slate-600">
            Target Workflow ID: <code>{change.workflow_id}</code>
          </p>
          <p className="text-amber-700 font-semibold">
            Proposed Action Delay: {change.delay_hours} hours
          </p>
        </div>
      );
    }

    if (change.type === 'workflow.create') {
      return (
        <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs space-y-1">
          <p className="font-bold text-aura-navy">Type: Workflow Synthesis (workflow.create)</p>
          <p className="font-semibold text-slate-700">Name: {change.name}</p>
          <p className="font-mono text-slate-600">
            Trigger: {change.trigger?.type} on entity '{change.trigger?.entity}'
          </p>
        </div>
      );
    }

    return <pre className="text-xs">{JSON.stringify(change, null, 2)}</pre>;
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-cyan-50 border border-cyan-200 text-aura-cyan text-[11px] font-bold uppercase tracking-wider mb-2">
            <Dna className="w-3.5 h-3.5" />
            Controlled Self-Evolution
          </div>
          <h2 className="text-xl font-bold text-aura-navy">Evolution Center</h2>
          <p className="text-xs text-slate-500 mt-1">
            Review AI-proposed architectural and workflow changes with strict 2-stage human authorization.
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={fetchProposals}
          isLoading={isLoading}
          leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
        >
          Refresh Proposals
        </Button>
      </div>

      {/* Two-Stage Lifecycle Explanatory Notice */}
      <div className="p-4 rounded-xl bg-amber-50/70 border border-amber-200 text-xs text-amber-900 flex items-start gap-3">
        <ShieldCheck className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <p className="font-bold text-amber-950">
            Two-Stage Human Approval Protocol
          </p>
          <p className="text-slate-700 leading-relaxed">
            AI suggestions never execute code or mutate live CRM configurations automatically.
            <br />
            <strong>Stage 1 (Approve):</strong> Verifies configuration staleness and marks the proposal ready.
            <br />
            <strong>Stage 2 (Apply):</strong> Atomically modifies allowlisted workflow actions, increments configuration version, and inserts an audit log entry.
          </p>
        </div>
      </div>

      {/* Synthesis Trigger Card */}
      <Card className="p-5 border-slate-200 bg-white">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <h3 className="text-sm font-bold text-aura-navy flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-aura-cyan" />
              Synthesize AI Evolution Proposal
            </h3>
            <p className="text-xs text-slate-500">
              Evaluates current CRM metrics and benchmarks to recommend operational improvements.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Select
              className="w-48 text-xs"
              value={selectedObjective}
              onChange={(e) => setSelectedObjective(e.target.value as EvolutionObjective)}
              options={[
                { label: 'Improve Follow-up Speed', value: 'improve_follow_up' },
                { label: 'Increase Conversion Rate', value: 'improve_conversion' },
                { label: 'Reduce Manual Workload', value: 'reduce_manual_work' },
              ]}
            />
            <Button
              variant="yellow"
              size="sm"
              onClick={handleGenerateProposal}
              isLoading={isGenerating}
              leftIcon={<Sparkles className="w-4 h-4 text-aura-navy" />}
            >
              Generate Proposal
            </Button>
          </div>
        </div>
      </Card>

      {/* Proposals List */}
      {isLoading ? (
        <TableSkeleton rows={4} cols={3} />
      ) : proposals.length === 0 ? (
        <EmptyState
          icon={<Dna className="w-6 h-6" />}
          title="No Evolution Proposals Generated"
          description="Use the generator above to create your first objective-driven proposal."
          actionLabel="Synthesize Proposal"
          onAction={handleGenerateProposal}
        />
      ) : (
        <div className="space-y-4">
          {proposals.map((proposal) => {
            const isPending = proposal.status === 'pending';
            const isApproved = proposal.status === 'approved';
            const isApplied = proposal.status === 'applied';

            return (
              <Card
                key={proposal.proposal_id}
                className="p-5 border-slate-200 hover:border-slate-300 transition-all shadow-subtle space-y-3"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <Badge variant={proposal.status}>{proposal.status}</Badge>
                    <span className="text-xs font-mono text-slate-400">
                      ID: {proposal.proposal_id.slice(0, 8)}...
                    </span>
                  </div>

                  {proposal.approved_at && (
                    <span className="text-[11px] text-slate-400 flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      Approved: {new Date(proposal.approved_at).toLocaleTimeString()}
                    </span>
                  )}
                </div>

                <div>
                  <h4 className="text-sm font-bold text-aura-navy leading-snug">
                    {proposal.summary}
                  </h4>
                </div>

                {/* Proposed Change Preview */}
                {renderProposedChangeDetails(proposal.proposed_change)}

                {/* Evidence citations if present */}
                {proposal.evidence && proposal.evidence.length > 0 && (
                  <div className="pt-2">
                    <p className="text-[10px] font-bold uppercase text-slate-400 tracking-wider mb-1">
                      Evidence & Observational Data:
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {proposal.evidence.map((ev, i) => (
                        <div
                          key={i}
                          className="text-[11px] px-2.5 py-1 rounded bg-slate-100 text-slate-600 border border-slate-200"
                        >
                          <span className="font-semibold text-aura-deep">
                            {String(ev['metric'] || 'Metric')}:
                          </span>{' '}
                          {String(ev['observation'] || JSON.stringify(ev))}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Lifecycle Actions Bar */}
                <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setSelectedProposal(proposal)}
                      leftIcon={<FileText className="w-3.5 h-3.5" />}
                    >
                      Audit Details
                    </Button>
                  </div>

                  <div className="flex items-center gap-2">
                    {/* Stage 1: Approve Button */}
                    {isPending && (
                      <>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setRejectingProposal(proposal)}
                          className="text-rose-600 hover:bg-rose-50"
                        >
                          Reject
                        </Button>
                        <Button
                          variant="accent"
                          size="sm"
                          onClick={() => handleApprove(proposal)}
                          isLoading={isApproving}
                          leftIcon={<CheckCircle2 className="w-3.5 h-3.5" />}
                        >
                          Approve (Stage 1)
                        </Button>
                      </>
                    )}

                    {/* Stage 2: Apply Button */}
                    {isApproved && (
                      <>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setRejectingProposal(proposal)}
                          className="text-rose-600 hover:bg-rose-50"
                        >
                          Reject
                        </Button>
                        <Button
                          variant="yellow"
                          size="sm"
                          onClick={() => setApplyingProposal(proposal)}
                          leftIcon={<Play className="w-3.5 h-3.5" />}
                        >
                          Apply to Live CRM (Stage 2)
                        </Button>
                      </>
                    )}

                    {/* Applied State */}
                    {isApplied && (
                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700 bg-emerald-50 px-3 py-1.5 rounded-lg border border-emerald-200">
                        <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                        Applied to CRM Config
                      </span>
                    )}

                    {proposal.status === 'rejected' && (
                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-rose-700 bg-rose-50 px-3 py-1.5 rounded-lg border border-rose-200">
                        <XCircle className="w-4 h-4 text-rose-600" />
                        Rejected: {proposal.rejection_reason || 'By Operator'}
                      </span>
                    )}
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Stage 2 Apply Confirmation Dialog */}
      {applyingProposal && (
        <Modal
          isOpen={Boolean(applyingProposal)}
          onClose={() => setApplyingProposal(null)}
          title="Apply Evolution Proposal Atomically"
          description={`This operation will modify the targeted workflow and advance the CRM configuration version to v${activeCRM.configuration_version + 1}.`}
        >
          <div className="space-y-4">
            <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-900 space-y-1">
              <p className="font-bold">Transaction Atomicity Guarantee:</p>
              <p>
                The backend locks both CRM and proposal rows in a single transaction, modifies the target workflow action, increments the configuration version, and writes an audit log entry.
              </p>
            </div>

            {renderProposedChangeDetails(applyingProposal.proposed_change)}

            <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setApplyingProposal(null)}
                disabled={isApplying}
              >
                Cancel
              </Button>
              <Button
                variant="yellow"
                size="sm"
                onClick={handleApply}
                isLoading={isApplying}
                leftIcon={<Play className="w-4 h-4" />}
              >
                Confirm & Apply Atomically
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Reject Proposal Modal */}
      {rejectingProposal && (
        <Modal
          isOpen={Boolean(rejectingProposal)}
          onClose={() => setRejectingProposal(null)}
          title="Reject Evolution Proposal"
          description="Provide an operational rationale for the audit record."
        >
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-bold uppercase text-slate-700 mb-1.5">
                Rejection Reason *
              </label>
              <textarea
                rows={3}
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                placeholder="e.g. Current business cycle requires a longer nurturing window..."
                className="w-full text-xs p-3 rounded-lg border border-slate-300 focus:border-rose-400 outline-none"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setRejectingProposal(null)}
                disabled={isRejecting}
              >
                Cancel
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={handleReject}
                isLoading={isRejecting}
              >
                Confirm Rejection
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Proposal Audit Details Modal */}
      {selectedProposal && (
        <Modal
          isOpen={Boolean(selectedProposal)}
          onClose={() => setSelectedProposal(null)}
          title="Evolution Proposal Audit Record"
          description={`Proposal ID: ${selectedProposal.proposal_id}`}
          maxWidth="lg"
        >
          <div className="space-y-3 text-xs">
            <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 rounded-lg">
              <div>
                <span className="text-[10px] text-slate-400 font-bold uppercase">Status</span>
                <p className="font-semibold text-aura-navy">{selectedProposal.status}</p>
              </div>
              <div>
                <span className="text-[10px] text-slate-400 font-bold uppercase">Summary</span>
                <p className="font-semibold">{selectedProposal.summary}</p>
              </div>
            </div>

            <div>
              <span className="text-[10px] text-slate-400 font-bold uppercase">Proposed Mutation</span>
              {renderProposedChangeDetails(selectedProposal.proposed_change)}
            </div>

            <div className="grid grid-cols-2 gap-3 p-3 border border-slate-200 rounded-lg">
              <div>
                <span className="text-[10px] text-slate-400 font-bold uppercase">Approved At</span>
                <p>{selectedProposal.approved_at || 'Not yet approved'}</p>
              </div>
              <div>
                <span className="text-[10px] text-slate-400 font-bold uppercase">Applied At</span>
                <p>{selectedProposal.applied_at || 'Not yet applied'}</p>
              </div>
            </div>

            {selectedProposal.application_error && (
              <div className="p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-lg">
                <span className="font-bold">Application Error:</span>{' '}
                {selectedProposal.application_error}
              </div>
            )}

            <div className="flex justify-end pt-3">
              <Button variant="primary" size="sm" onClick={() => setSelectedProposal(null)}>
                Close
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
