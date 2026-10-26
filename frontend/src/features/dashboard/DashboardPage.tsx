import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Sparkles,
  Layers,
  Database,
  GitBranch,
  Dna,
  ArrowRight,
  TrendingUp,
  CheckCircle,
  FileSpreadsheet,
} from 'lucide-react';
import { useCRM } from '@/context/CRMContext';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import { api } from '@/services/api';
import { AnalyticsData } from '@/types/crm';

export const DashboardPage: React.FC = () => {
  const { user } = useAuth();
  const { crms, activeCRM, selectCRM, isLoading } = useCRM();
  const navigate = useNavigate();
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);

  useEffect(() => {
    if (activeCRM) {
      api.getAnalytics(activeCRM.crm_id).then(setAnalytics).catch(() => {});
    }
  }, [activeCRM]);

  return (
    <div className="space-y-6">
      {/* Welcome Banner */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-aura-navy via-aura-deep to-aura-navy text-white p-6 sm:p-8 shadow-card border border-slate-800">
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="space-y-2 max-w-xl">
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-aura-cyan/20 border border-aura-cyan/30 text-aura-cyan text-[11px] font-bold uppercase tracking-wider">
              <Sparkles className="w-3.5 h-3.5" />
              Autonomous CRM Architecture
            </div>
            <h2 className="text-xl sm:text-2xl font-extrabold tracking-tight">
              Welcome back, {user?.user_metadata?.name || user?.email?.split('@')[0] || 'Operator'}
            </h2>
            <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
              AURA allows you to generate complete customized CRMs from natural-language descriptions, manage dynamic records, and approve evolutionary proposals safely.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="yellow"
              onClick={() => navigate('/chat-crm')}
              leftIcon={<Sparkles className="w-4 h-4" />}
            >
              Build New CRM
            </Button>
            {activeCRM && (
              <Button
                variant="outline"
                className="bg-white/10 text-white border-white/20 hover:bg-white/20"
                onClick={() => navigate('/records')}
                leftIcon={<Database className="w-4 h-4" />}
              >
                Open Records
              </Button>
            )}
          </div>
        </div>

        {/* Background decorative glow */}
        <div className="absolute -right-10 -bottom-10 w-64 h-64 bg-aura-cyan/10 rounded-full blur-3xl pointer-events-none" />
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="p-4 sm:p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Active CRMs
            </span>
            <div className="w-8 h-8 rounded-lg bg-blue-50 text-aura-deep flex items-center justify-center">
              <Layers className="w-4 h-4" />
            </div>
          </div>
          <p className="text-2xl font-bold text-aura-navy mt-3">{crms.length}</p>
          <p className="text-[11px] text-slate-400 mt-1">Tenant isolated workspaces</p>
        </Card>

        <Card className="p-4 sm:p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Total Records
            </span>
            <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
              <Database className="w-4 h-4" />
            </div>
          </div>
          <p className="text-2xl font-bold text-aura-navy mt-3">
            {analytics?.total_leads ?? 0}
          </p>
          <p className="text-[11px] text-slate-400 mt-1">In active CRM entities</p>
        </Card>

        <Card className="p-4 sm:p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Conversion Rate
            </span>
            <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
              <TrendingUp className="w-4 h-4" />
            </div>
          </div>
          <p className="text-2xl font-bold text-aura-navy mt-3">
            {analytics ? `${(analytics.conversion_rate * 100).toFixed(1)}%` : '0%'}
          </p>
          <p className="text-[11px] text-slate-400 mt-1">
            {analytics?.won_leads ?? 0} won deals
          </p>
        </Card>

        <Card className="p-4 sm:p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Config Version
            </span>
            <div className="w-8 h-8 rounded-lg bg-cyan-50 text-aura-cyan flex items-center justify-center">
              <Dna className="w-4 h-4" />
            </div>
          </div>
          <p className="text-2xl font-bold text-aura-navy mt-3">
            {activeCRM ? `v${activeCRM.configuration_version}` : 'v1.0'}
          </p>
          <p className="text-[11px] text-slate-400 mt-1">Optimistic locking guard</p>
        </Card>
      </div>

      {/* Main Grid: Active CRM Deep Dive & Quick Actions */}
      {crms.length === 0 && !isLoading ? (
        <EmptyState
          icon={<Layers className="w-6 h-6" />}
          title="No CRMs Created Yet"
          description="AURA lets you create a tailor-made CRM architecture in seconds using natural language prompts."
          actionLabel="Build Your First CRM"
          onAction={() => navigate('/chat-crm')}
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Active CRM Snapshot */}
          {activeCRM && (
            <Card className="p-5 sm:p-6 lg:col-span-2 space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-slate-100">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-lg font-bold text-aura-navy">
                      {activeCRM.name}
                    </h3>
                    <Badge variant={activeCRM.status}>{activeCRM.status}</Badge>
                    <Badge variant="cyan">v{activeCRM.configuration_version}</Badge>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    Industry focus: <span className="font-semibold capitalize">{activeCRM.configuration.industry.replace('_', ' ')}</span>
                  </p>
                </div>

                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => navigate(`/crms/${activeCRM.crm_id}`)}
                  rightIcon={<ArrowRight className="w-3.5 h-3.5" />}
                >
                  View Full Schema
                </Button>
              </div>

              {/* Entities Summary */}
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
                  Configured Dynamic Entities ({activeCRM.configuration.entities.length})
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {activeCRM.configuration.entities.map((ent) => (
                    <div
                      key={ent.name}
                      onClick={() => navigate('/records')}
                      className="p-3.5 rounded-xl border border-slate-200/80 hover:border-aura-cyan/60 bg-slate-50/50 hover:bg-white cursor-pointer transition-all"
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="font-bold text-sm text-aura-navy">
                          {ent.label}
                        </span>
                        <code className="text-[10px] text-slate-400 font-mono">
                          /{ent.name}
                        </code>
                      </div>
                      <p className="text-xs text-slate-500">
                        {ent.fields.length} dynamic fields (
                        {ent.fields.filter((f) => f.required).length} required)
                      </p>
                      <div className="mt-2.5 flex flex-wrap gap-1">
                        {ent.fields.slice(0, 4).map((f) => (
                          <span
                            key={f.name}
                            className="text-[10px] px-1.5 py-0.5 rounded bg-white border border-slate-200 text-slate-600 font-medium"
                          >
                            {f.label}
                          </span>
                        ))}
                        {ent.fields.length > 4 && (
                          <span className="text-[10px] text-slate-400 py-0.5">
                            +{ent.fields.length - 4} more
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Pipeline Stages Flow */}
              {activeCRM.configuration.pipeline_stages?.length > 0 && (
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2.5">
                    Pipeline Stages
                  </h4>
                  <div className="flex flex-wrap items-center gap-2">
                    {activeCRM.configuration.pipeline_stages.map((stage, i) => (
                      <React.Fragment key={stage}>
                        <div className="px-3 py-1 rounded-lg bg-slate-100 text-xs font-semibold text-aura-navy border border-slate-200">
                          {stage}
                        </div>
                        {i < activeCRM.configuration.pipeline_stages.length - 1 && (
                          <ArrowRight className="w-3.5 h-3.5 text-slate-300 shrink-0" />
                        )}
                      </React.Fragment>
                    ))}
                  </div>
                </div>
              )}
            </Card>
          )}

          {/* Quick Actions Column */}
          <div className="space-y-4">
            <Card className="p-5 space-y-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Quick Actions
              </h3>
              <div className="space-y-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full justify-start text-xs font-semibold"
                  onClick={() => navigate('/records')}
                  leftIcon={<Database className="w-4 h-4 text-aura-cyan" />}
                >
                  Manage Dynamic Records
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full justify-start text-xs font-semibold"
                  onClick={() => navigate('/records')}
                  leftIcon={<FileSpreadsheet className="w-4 h-4 text-emerald-600" />}
                >
                  Import CSV Dataset
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full justify-start text-xs font-semibold"
                  onClick={() => navigate('/evolution')}
                  leftIcon={<Dna className="w-4 h-4 text-amber-500" />}
                >
                  Evolution Proposal Center
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full justify-start text-xs font-semibold"
                  onClick={() => navigate('/workflows')}
                  leftIcon={<GitBranch className="w-4 h-4 text-aura-deep" />}
                >
                  Workflow Automations
                </Button>
              </div>
            </Card>

            {/* Other User CRMs Quick Switcher */}
            <Card className="p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  Your CRMs ({crms.length})
                </h3>
                <button
                  onClick={() => navigate('/crms')}
                  className="text-xs text-aura-cyan hover:underline font-semibold"
                >
                  View all
                </button>
              </div>

              <div className="space-y-2">
                {crms.slice(0, 4).map((c) => (
                  <div
                    key={c.crm_id}
                    onClick={() => selectCRM(c.crm_id)}
                    className={`p-2.5 rounded-xl border text-xs cursor-pointer flex items-center justify-between transition-all ${
                      activeCRM?.crm_id === c.crm_id
                        ? 'border-aura-cyan bg-cyan-50/40 text-aura-navy font-bold'
                        : 'border-slate-100 hover:border-slate-200 text-slate-700'
                    }`}
                  >
                    <div className="truncate pr-2">
                      <p className="truncate font-medium">{c.name}</p>
                      <p className="text-[10px] text-slate-400">v{c.configuration_version}</p>
                    </div>
                    {activeCRM?.crm_id === c.crm_id && (
                      <CheckCircle className="w-4 h-4 text-aura-cyan shrink-0" />
                    )}
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
};
