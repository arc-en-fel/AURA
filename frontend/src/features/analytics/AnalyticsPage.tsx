import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts';
import {
  BarChart3,
  RefreshCw,
  PieChart as PieIcon,
  Users,
  TrendingUp,
  Activity,
  Layers,
  Hash,
  Minus,
} from 'lucide-react';
import { useCRM } from '@/context/CRMContext';
import { formatNumber } from '@/utils/format';
import { buildStageColorMap, getStageColor, getCategoryColor } from '@/utils/crmColors';
import { AnalyticsData } from '@/types/crm';
import { api } from '@/services/api';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { TableSkeleton } from '@/components/ui/LoadingSkeleton';
import { useNavigate } from 'react-router-dom';

// ─── Shared tooltip styles ────────────────────────────────────────────────────
const TOOLTIP_STYLE = {
  backgroundColor: '#0B1F3A',
  borderRadius: '8px',
  border: 'none',
  fontSize: '12px',
  color: '#fff',
};
const TOOLTIP_LABEL_STYLE = { color: '#fff' };
const TOOLTIP_ITEM_STYLE  = { color: '#fff' };

// ─── Chart accent palette ─────────────────────────────────────────────────────
const CHART_COLORS = [
  '#22d3ee', '#6366f1', '#10b981', '#f59e0b',
  '#ef4444', '#8b5cf6', '#14b8a6', '#f97316',
];

// ─── Bucketing helper ─────────────────────────────────────────────────────────

interface Bucket {
  name: string;
  count: number;
  percentage: number;
  lo: number;
  hi: number;
}

/**
 * Compute "nice" histogram bins from an array of finite numbers.
 * Returns [] when there is nothing meaningful to show.
 */
function computeBuckets(values: number[], maxBins = 8): Bucket[] {
  const valid = values.filter((v) => typeof v === 'number' && isFinite(v));
  if (valid.length === 0) return [];

  const min = Math.min(...valid);
  const max = Math.max(...valid);

  if (min === max) {
    return [{ name: formatNumber(min), count: valid.length, percentage: 100, lo: min, hi: max }];
  }

  const range = max - min;
  const rawStep = range / maxBins;
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const niceSteps = [1, 2, 2.5, 5, 10];
  let step = mag * niceSteps[niceSteps.length - 1];
  for (const m of niceSteps) {
    if (mag * m >= rawStep) { step = mag * m; break; }
  }

  const start = Math.floor(min / step) * step;
  const raw: Bucket[] = [];

  for (let lo = start; lo < max + step; lo += step) {
    const hi = lo + step;
    const count = valid.filter((v) => v >= lo && v < hi).length;
    if (count === 0 && raw.length === 0) continue;
    raw.push({ name: `${formatNumber(lo)}–${formatNumber(hi)}`, count, percentage: 0, lo, hi });
    if (raw.length >= maxBins) break;
  }

  // Drop empty trailing bins
  while (raw.length > 0 && raw[raw.length - 1].count === 0) raw.pop();

  const total = raw.reduce((s, b) => s + b.count, 0);
  raw.forEach((b) => { b.percentage = total > 0 ? Math.round((b.count / total) * 100) : 0; });

  return raw;
}

/** Compute median of an array of numbers. */
function median(values: number[]): number {
  const sorted = [...values].filter(isFinite).sort((a, b) => a - b);
  if (sorted.length === 0) return 0;
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

// ─── Stat pill ────────────────────────────────────────────────────────────────
const StatPill: React.FC<{ label: string; value: string | number; accent?: boolean }> = ({
  label, value, accent,
}) => (
  <div className={`flex flex-col items-center justify-center rounded-lg px-3 py-2 ${
    accent ? 'bg-aura-navy/5 border border-aura-cyan/20' : 'bg-slate-50 border border-slate-100'
  }`}>
    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-0.5">{label}</span>
    <span className={`text-sm font-extrabold ${accent ? 'text-aura-navy' : 'text-slate-700'}`}>
      {typeof value === 'number' ? formatNumber(value) : value}
    </span>
  </div>
);

// ─── Numeric Distribution Card ────────────────────────────────────────────────

interface NumericMetric {
  label: string;
  count: number;
  total: number;
  avg: number;
  min: number;
  max: number;
  median?: number;
  values?: number[];
}

interface NumericDistributionCardProps {
  fieldKey: string;
  metric: NumericMetric;
  colorIndex: number;
}

const NumericDistributionCard: React.FC<NumericDistributionCardProps> = ({
  fieldKey,
  metric,
  colorIndex,
}) => {
  const { label, count, total, avg, min, max, values } = metric;
  const med = metric.median ?? (values ? median(values) : 0);

  const buckets = useMemo(() => {
    // Prefer raw values for bucketing
    if (values && values.length > 1) return computeBuckets(values);
    // With aggregates only (no raw values), we can't build a reliable histogram
    return [];
  }, [values]);

  const hasDistribution = buckets.length >= 2;
  const barColor = CHART_COLORS[colorIndex % CHART_COLORS.length];

  const nullCount = (values ? (metric.count - values.filter(isFinite).length) : 0);

  return (
    <Card className="p-5 space-y-4" data-field={fieldKey}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-bold text-aura-navy flex items-center gap-1.5">
            <Hash className="w-3.5 h-3.5 text-aura-cyan shrink-0" />
            {label}
          </h3>
          <p className="text-[11px] text-slate-400 mt-0.5">
            {count} valid record{count !== 1 ? 's' : ''}
            {nullCount > 0 && ` · ${nullCount} missing`}
          </p>
        </div>
        <span
          className="text-[10px] font-bold px-2 py-0.5 rounded-full border"
          style={{ color: barColor, borderColor: barColor, background: `${barColor}15` }}
        >
          numeric
        </span>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-3 sm:grid-cols-5 gap-1.5">
        <StatPill label="Count" value={count} accent />
        <StatPill label="Total"   value={formatNumber(total)} />
        <StatPill label="Avg"     value={formatNumber(avg)} accent />
        <StatPill label="Median"  value={formatNumber(med)} />
        <StatPill label="Min / Max" value={`${formatNumber(min)} – ${formatNumber(max)}`} />
      </div>

      {/* Distribution chart */}
      {hasDistribution ? (
        <>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">
              Value Distribution
            </p>
            <div className="h-44 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={buckets} margin={{ top: 4, right: 4, left: -22, bottom: 36 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 9, fill: '#94a3b8' }}
                    interval={0}
                    angle={-30}
                    textAnchor="end"
                  />
                  <YAxis
                    tick={{ fontSize: 10, fill: '#94a3b8' }}
                    allowDecimals={false}
                  />
                  <Tooltip
                    contentStyle={TOOLTIP_STYLE}
                    labelStyle={TOOLTIP_LABEL_STYLE}
                    itemStyle={TOOLTIP_ITEM_STYLE}
                    formatter={(v: number, _n: string, item: any) => [
                      `${v} records (${item?.payload?.percentage ?? 0}%)`,
                      'Count',
                    ]}
                  />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]} fill={barColor} maxBarSize={60} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Percentage breakdown */}
          <div className="border-t border-slate-100 pt-3 space-y-1.5">
            {buckets.map((b) => (
              <div key={b.name} className="flex items-center gap-2 text-xs">
                <span className="text-slate-600 font-medium truncate flex-1">{b.name}</span>
                <div className="w-20 bg-slate-100 rounded-full h-1.5 overflow-hidden shrink-0">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${b.percentage}%`, backgroundColor: barColor }}
                  />
                </div>
                <span className="text-slate-400 font-mono text-[10px] w-16 text-right shrink-0">
                  {b.count} · {b.percentage}%
                </span>
              </div>
            ))}
          </div>
        </>
      ) : count === 0 ? (
        <div className="h-24 flex items-center justify-center text-xs text-slate-400 bg-slate-50 rounded-lg border border-dashed">
          <span className="flex items-center gap-1.5">
            <Minus className="w-3.5 h-3.5" />
            No values recorded for this field yet.
          </span>
        </div>
      ) : count === 1 || min === max ? (
        <div className="h-24 flex items-center justify-center text-xs text-slate-400 bg-slate-50 rounded-lg border border-dashed">
          All {count} records share the same value ({formatNumber(min)}). No distribution to show.
        </div>
      ) : (
        <div className="h-24 flex items-center justify-center text-xs text-slate-400 bg-slate-50 rounded-lg border border-dashed">
          Distribution unavailable — refresh analytics or add more records.
        </div>
      )}
    </Card>
  );
};

// ─── Main AnalyticsPage ───────────────────────────────────────────────────────

export const AnalyticsPage: React.FC = () => {
  const { activeCRM } = useCRM();
  const navigate = useNavigate();

  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAnalytics = useCallback(async () => {
    if (!activeCRM) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getAnalytics(activeCRM.crm_id);
      setAnalytics(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch analytics');
    } finally {
      setIsLoading(false);
    }
  }, [activeCRM]);

  // Clear immediately on CRM change
  useEffect(() => {
    setAnalytics(null);
    fetchAnalytics();
  }, [activeCRM?.crm_id, fetchAnalytics]);

  // Refresh on record mutations
  useEffect(() => {
    window.addEventListener('records-changed', fetchAnalytics);
    return () => window.removeEventListener('records-changed', fetchAnalytics);
  }, [fetchAnalytics]);

  if (!activeCRM) {
    return (
      <EmptyState
        icon={<BarChart3 className="w-6 h-6" />}
        title="No Active CRM Selected"
        description="Select a CRM to view pipeline analytics and record distributions."
        actionLabel="Go to My CRMs"
        onAction={() => navigate('/crms')}
      />
    );
  }

  // ── Derive display values ──────────────────────────────────────────────────
  const schemaInfo = (analytics as any)?.schema_info || {};
  const primaryEntityName =
    schemaInfo.primary_entity_label ||
    (activeCRM.configuration?.entities?.[0]?.label ?? 'Record');
  const pipelineStages =
    schemaInfo.pipeline_stages ||
    activeCRM.configuration?.pipeline_stages || [];
  const totalRecords =
    (analytics as any)?.total_records ?? (analytics as any)?.total_leads ?? 0;

  const stageColorMap = useMemo(() =>
    activeCRM ? buildStageColorMap(
      activeCRM.crm_id,
      pipelineStages,
      activeCRM.configuration?.ui_config?.stage_colors,
    ) : {},
    [activeCRM, pipelineStages],
  );

  const kpiCards: Array<{ label: string; value: string | number; subtitle: string }> =
    (analytics as any)?.kpi_cards || [];

  const statusFieldLabel = schemaInfo.stage_field_label || 'CRM Status';

  // Canonical status aggregation consumed by both Bar Chart and Donut Chart
  const statusData = (analytics?.status_distribution || analytics?.by_stage || []).map((s: any) => ({
    name: s.status || s.value || s.name || 'Unassigned',
    count: Number(s.count ?? 0),
    percentage: Number(s.percentage ?? 0),
  }));

  const totalStatusCount = statusData.reduce((acc, curr) => acc + curr.count, 0);
  // Exclude zero-count categories from actual donut slices per requirement
  const donutSlices = statusData.filter((s) => s.count > 0);

  const categoricalMetrics: Record<
    string,
    { label: string; distribution: Array<{ value: string; count: number; percentage: number }> }
  > = (analytics as any)?.categorical_metrics || {};

  const numericMetrics: Record<string, NumericMetric> =
    (analytics as any)?.numeric_metrics || {};

  const numericEntries = Object.entries(numericMetrics);

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-aura-navy">{activeCRM.name} Analytics</h2>
          <p className="text-xs text-slate-500 mt-1">
            Schema-driven analytics from live CRM records — updates automatically after mutations.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={fetchAnalytics}
          isLoading={isLoading}
          leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
        >
          Refresh Data
        </Button>
      </div>

      {isLoading && !analytics ? (
        <TableSkeleton rows={4} cols={4} />
      ) : error ? (
        <Card className="p-6 text-center text-xs text-rose-600 bg-rose-50 border-rose-200">
          <p className="font-bold">Error loading analytics</p>
          <p>{error}</p>
        </Card>
      ) : (
        <>
          {/* ── KPI row ─────────────────────────────────────────────────────── */}
          <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Total records */}
            <Card className="p-4 sm:p-5">
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-[10px] font-bold uppercase tracking-wider truncate">
                  Total {primaryEntityName}s
                </span>
                <Users className="w-4 h-4 text-aura-cyan shrink-0" />
              </div>
              <p className="text-2xl font-extrabold text-aura-navy">{formatNumber(totalRecords)}</p>
              <p className="text-[11px] text-slate-400 mt-1">All records in CRM</p>
            </Card>

            {/* Pipeline stages */}
            <Card className="p-4 sm:p-5">
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-[10px] font-bold uppercase tracking-wider truncate">
                  Pipeline Stages
                </span>
                <Layers className="w-4 h-4 text-aura-deep shrink-0" />
              </div>
              <p className="text-2xl font-extrabold text-aura-navy">{pipelineStages.length}</p>
              <p className="text-[11px] text-slate-400 mt-1">Configured workflow stages</p>
            </Card>

            {/* Dynamic KPI cards (up to 2) */}
            {kpiCards.length > 0 ? (
              kpiCards.slice(0, 2).map((kpi, idx) => (
                <Card key={idx} className="p-4 sm:p-5">
                  <div className="flex items-center justify-between text-slate-400 mb-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider truncate">
                      {kpi.label}
                    </span>
                    <TrendingUp className="w-4 h-4 text-emerald-600 shrink-0" />
                  </div>
                  <p className="text-2xl font-extrabold text-aura-navy truncate">{kpi.value}</p>
                  <p className="text-[11px] text-slate-400 mt-1 truncate">{kpi.subtitle}</p>
                </Card>
              ))
            ) : numericEntries.length > 0 ? (
              numericEntries.slice(0, 2).map(([key, m]) => (
                <Card key={key} className="p-4 sm:p-5">
                  <div className="flex items-center justify-between text-slate-400 mb-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider truncate">
                      Avg {m.label}
                    </span>
                    <Hash className="w-4 h-4 text-aura-cyan shrink-0" />
                  </div>
                  <p className="text-2xl font-extrabold text-aura-navy">{formatNumber(m.avg)}</p>
                  <p className="text-[11px] text-slate-400 mt-1">Total: {formatNumber(m.total)}</p>
                </Card>
              ))
            ) : (
              <Card className="p-4 sm:p-5">
                <div className="flex items-center justify-between text-slate-400 mb-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider truncate">Entities</span>
                  <Activity className="w-4 h-4 text-aura-yellow shrink-0" />
                </div>
                <p className="text-2xl font-extrabold text-aura-navy">
                  {activeCRM.configuration?.entities?.length || 1}
                </p>
                <p className="text-[11px] text-slate-400 mt-1">Data models in schema</p>
              </Card>
            )}
          </div>

          {/* ── Charts row ───────────────────────────────────────────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* 1. Synchronized Status & Stage Distribution Bar Chart */}
            <Card className="p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-aura-navy flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-aura-cyan" />
                  Status &amp; Stage Distribution
                </h3>
                <span className="text-xs text-slate-400 font-mono">{statusData.length} stages</span>
              </div>

              {totalStatusCount === 0 ? (
                <div className="h-64 flex flex-col items-center justify-center text-xs text-slate-400">
                  <BarChart3 className="w-8 h-8 text-slate-200 mb-2" />
                  <span>No stage data yet. Add records to see distribution.</span>
                </div>
              ) : (
                <div>
                  <div className="h-72 w-full pt-2">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={statusData} margin={{ top: 10, right: 10, left: -20, bottom: 30 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                        <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#64748B' }} interval={0} angle={-25} textAnchor="end" />
                        <YAxis tick={{ fontSize: 11, fill: '#64748B' }} allowDecimals={false} />
                        <Tooltip
                          contentStyle={TOOLTIP_STYLE}
                          labelStyle={TOOLTIP_LABEL_STYLE}
                          itemStyle={TOOLTIP_ITEM_STYLE}
                          formatter={(v: any, _name: any, item: any) => [
                            `${v} records (${item?.payload?.percentage ?? 0}%)`,
                            'Count',
                          ]}
                        />
                        <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                          {statusData.map((entry, i) => {
                            const c = getStageColor(stageColorMap, entry.name);
                            return <Cell key={`bar-${i}`} fill={c.hex} />;
                          })}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Stage Breakdown Progress List */}
                  <div className="mt-4 border-t border-slate-100 pt-4 space-y-2">
                    <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">
                      Stage Percentages
                    </h4>
                    {statusData.map((stage) => {
                      const c = getStageColor(stageColorMap, stage.name);
                      return (
                        <div key={stage.name} className="flex items-center justify-between text-xs">
                          <span className="text-slate-600 font-medium truncate max-w-[150px] flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: c.hex }} />
                            {stage.name}
                          </span>
                          <div className="flex items-center gap-2">
                            <div className="w-24 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                              <div className="h-full rounded-full transition-all" style={{ width: `${stage.percentage}%`, backgroundColor: c.hex }} />
                            </div>
                            <span className="text-slate-500 font-mono text-right w-16 text-[11px]">{stage.count} ({stage.percentage}%)</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </Card>

            {/* 2. Synchronized CRM Status Donut Chart */}
            <Card className="p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-aura-navy flex items-center gap-2">
                  <PieIcon className="w-4 h-4 text-aura-deep" />
                  {statusFieldLabel} Distribution
                </h3>
                <span className="text-xs text-slate-400 font-mono">
                  {donutSlices.length} active / {statusData.length} stages
                </span>
              </div>

              {totalStatusCount === 0 ? (
                <div className="h-64 flex flex-col items-center justify-center text-xs text-slate-400">
                  <PieIcon className="w-8 h-8 text-slate-200 mb-2" />
                  <span>No status records available yet.</span>
                </div>
              ) : (
                <div>
                  <div className="h-72 w-full pt-2">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={donutSlices}
                          dataKey="count"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          innerRadius={55}
                          outerRadius={85}
                          paddingAngle={donutSlices.length > 1 ? 4 : 0}
                        >
                          {donutSlices.map((entry) => {
                            const c = getStageColor(stageColorMap, entry.name);
                            return <Cell key={`donut-${entry.name}`} fill={c.hex} />;
                          })}
                        </Pie>
                        <Tooltip
                          contentStyle={TOOLTIP_STYLE}
                          labelStyle={TOOLTIP_LABEL_STYLE}
                          itemStyle={TOOLTIP_ITEM_STYLE}
                          formatter={(v: any, _name: any, item: any) => [
                            `${v} records (${item?.payload?.percentage ?? 0}%)`,
                            'Count',
                          ]}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Stage Breakdown Legend List (Includes ALL configured stages with 0-count clearly shown) */}
                  <div className="mt-4 border-t border-slate-100 pt-4 space-y-2">
                    <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">
                      Stage Proportions
                    </h4>
                    {statusData.map((stage) => {
                      const c = getStageColor(stageColorMap, stage.name);
                      return (
                        <div key={stage.name} className="flex items-center justify-between text-xs">
                          <span className="text-slate-600 font-medium truncate max-w-[150px] flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: c.hex }} />
                            {stage.name}
                          </span>
                          <div className="flex items-center gap-2">
                            <div className="w-24 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                              <div
                                className="h-full rounded-full transition-all"
                                style={{ width: `${stage.percentage}%`, backgroundColor: c.hex }}
                              />
                            </div>
                            <span className="text-slate-500 font-mono text-right w-16 text-[11px]">
                              {stage.count} ({stage.percentage}%)
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </Card>
          </div>

          {/* Categorical Visualizations for Other Fields (if present) */}
          {Object.keys(categoricalMetrics).length > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {Object.entries(categoricalMetrics).map(([fieldKey, catMetric]) => (
                <Card key={fieldKey} className="p-5 space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-bold text-aura-navy flex items-center gap-2">
                      <PieIcon className="w-4 h-4 text-aura-cyan" />
                      {primaryEntityName} by {catMetric.label}
                    </h3>
                    <span className="text-xs text-slate-400 font-mono">
                      {catMetric.distribution.length} categories
                    </span>
                  </div>

                  {catMetric.distribution.length === 0 ? (
                    <div className="h-64 flex items-center justify-center text-xs text-slate-400">
                      No distribution data yet.
                    </div>
                  ) : (
                    <div className="h-72 w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie
                            data={catMetric.distribution}
                            dataKey="count"
                            nameKey="value"
                            cx="50%" cy="50%"
                            innerRadius={55} outerRadius={85} paddingAngle={4}
                          >
                            {catMetric.distribution.map((entry, i) => {
                              const c = getCategoryColor(activeCRM.crm_id, fieldKey, entry.value);
                              return <Cell key={`c-${i}`} fill={c.hex} />;
                            })}
                          </Pie>
                          <Tooltip
                            contentStyle={TOOLTIP_STYLE}
                            labelStyle={TOOLTIP_LABEL_STYLE}
                            itemStyle={TOOLTIP_ITEM_STYLE}
                            formatter={(v: any) => [`${v} records`, 'Count']}
                          />
                          <Legend verticalAlign="bottom" wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }} />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </Card>
              ))}
            </div>
          )}

          {/* ── Numeric Analytics & Distribution ─────────────────────────────── */}
          {numericEntries.length > 0 && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Hash className="w-4 h-4 text-emerald-600" />
                <h3 className="text-sm font-bold text-aura-navy">
                  Numeric Analytics &amp; Distribution
                </h3>
                <span className="text-xs text-slate-400 font-mono ml-auto">
                  {numericEntries.length} numeric field{numericEntries.length !== 1 ? 's' : ''}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {numericEntries.map(([fieldKey, metric], i) => (
                  <NumericDistributionCard
                    key={fieldKey}
                    fieldKey={fieldKey}
                    metric={metric}
                    colorIndex={i}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};
