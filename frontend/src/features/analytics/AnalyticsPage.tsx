import React, { useEffect, useState, useCallback } from 'react';
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
  Calculator,
} from 'lucide-react';
import { useCRM } from '@/context/CRMContext';
import { AnalyticsData } from '@/types/crm';
import { api } from '@/services/api';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { TableSkeleton } from '@/components/ui/LoadingSkeleton';
import { useNavigate } from 'react-router-dom';

const AURA_CHART_COLORS = [
  '#00B8D9', // Cyan
  '#123B63', // Deep Blue
  '#FFC928', // Yellow
  '#22C55E', // Green
  '#6366F1', // Indigo
  '#EC4899', // Pink
  '#8B5CF6', // Purple
  '#F97316', // Orange
];

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
      const msg = err instanceof Error ? err.message : 'Failed to fetch analytics';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [activeCRM]);

  // Requirement #19: Clear old analytics state immediately on CRM change so another CRM's data is never displayed
  useEffect(() => {
    setAnalytics(null);
    fetchAnalytics();
  }, [activeCRM?.crm_id, fetchAnalytics]);

  // Requirement #20: Record mutations must update analytics automatically
  useEffect(() => {
    const handleRecordsChanged = () => fetchAnalytics();
    window.addEventListener('records-changed', handleRecordsChanged);
    return () => {
      window.removeEventListener('records-changed', handleRecordsChanged);
    };
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

  // Universal dynamic schema extraction
  const schemaInfo = (analytics as any)?.schema_info || {};
  const primaryEntityName =
    schemaInfo.primary_entity_label ||
    (activeCRM.configuration?.entities?.[0]?.label ?? 'Record');
  const pipelineStages =
    schemaInfo.pipeline_stages ||
    activeCRM.configuration?.pipeline_stages ||
    [];
  const totalRecords =
    (analytics as any)?.total_records ??
    (analytics as any)?.total_leads ??
    0;

  // Dynamic KPI Cards
  const kpiCards: Array<{ label: string; value: string | number; subtitle: string }> =
    (analytics as any)?.kpi_cards || [];

  // Stage distribution
  const stageData = (analytics?.by_stage || []).map((s) => ({
    name: s.value || 'Unassigned',
    count: s.count,
    percentage: (s as any).percentage || 0,
  }));

  // Dynamic Categorical Metrics
  const categoricalMetrics: Record<
    string,
    { label: string; distribution: Array<{ value: string; count: number; percentage: number }> }
  > = (analytics as any)?.categorical_metrics || {};

  // Dynamic Numeric Metrics
  const numericMetrics: Record<
    string,
    { label: string; count: number; total: number; avg: number; min: number; max: number }
  > = (analytics as any)?.numeric_metrics || {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-aura-navy">
            {activeCRM.name} Analytics
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Dynamic schema-driven analytics derived from active CRM entities and records.
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
          {/* Dynamic KPI Cards Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* 1. Universal Total Volume Card */}
            <Card className="p-4 sm:p-5">
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-[10px] font-bold uppercase tracking-wider truncate">
                  Total {primaryEntityName}s
                </span>
                <Users className="w-4 h-4 text-aura-cyan shrink-0" />
              </div>
              <p className="text-2xl font-extrabold text-aura-navy">
                {totalRecords.toLocaleString()}
              </p>
              <p className="text-[11px] text-slate-400 mt-1">Total volume in CRM</p>
            </Card>

            {/* 2. Pipeline Stages Card */}
            <Card className="p-4 sm:p-5">
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-[10px] font-bold uppercase tracking-wider truncate">
                  Pipeline Stages
                </span>
                <Layers className="w-4 h-4 text-aura-deep shrink-0" />
              </div>
              <p className="text-2xl font-extrabold text-aura-navy">
                {pipelineStages.length}
              </p>
              <p className="text-[11px] text-slate-400 mt-1">Configured workflow stages</p>
            </Card>

            {/* 3 & 4. Additional Dynamic KPI Cards derived by schema */}
            {kpiCards.length > 0 ? (
              kpiCards.slice(0, 2).map((kpi, idx) => (
                <Card key={idx} className="p-4 sm:p-5">
                  <div className="flex items-center justify-between text-slate-400 mb-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider truncate">
                      {kpi.label}
                    </span>
                    <TrendingUp className="w-4 h-4 text-emerald-600 shrink-0" />
                  </div>
                  <p className="text-2xl font-extrabold text-aura-navy truncate">
                    {kpi.value}
                  </p>
                  <p className="text-[11px] text-slate-400 mt-1 truncate">{kpi.subtitle}</p>
                </Card>
              ))
            ) : Object.keys(numericMetrics).length > 0 ? (
              Object.entries(numericMetrics)
                .slice(0, 2)
                .map(([key, metric]) => (
                  <Card key={key} className="p-4 sm:p-5">
                    <div className="flex items-center justify-between text-slate-400 mb-2">
                      <span className="text-[10px] font-bold uppercase tracking-wider truncate">
                        Avg {metric.label}
                      </span>
                      <Calculator className="w-4 h-4 text-aura-cyan shrink-0" />
                    </div>
                    <p className="text-2xl font-extrabold text-aura-navy">
                      {metric.avg.toLocaleString()}
                    </p>
                    <p className="text-[11px] text-slate-400 mt-1">
                      Total: {metric.total.toLocaleString()}
                    </p>
                  </Card>
                ))
            ) : (
              <Card className="p-4 sm:p-5">
                <div className="flex items-center justify-between text-slate-400 mb-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider truncate">
                    Entities
                  </span>
                  <Activity className="w-4 h-4 text-aura-yellow shrink-0" />
                </div>
                <p className="text-2xl font-extrabold text-aura-navy">
                  {activeCRM.configuration?.entities?.length || 1}
                </p>
                <p className="text-[11px] text-slate-400 mt-1">Data models in schema</p>
              </Card>
            )}
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Status / Stage Distribution Bar Chart (Requirement #15) */}
            <Card className="p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-aura-navy flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-aura-cyan" />
                  Status & Stage Distribution
                </h3>
                <span className="text-xs text-slate-400 font-mono">
                  {stageData.length} stages
                </span>
              </div>

              {stageData.length === 0 ? (
                <div className="h-64 flex flex-col items-center justify-center text-xs text-slate-400">
                  <BarChart3 className="w-8 h-8 text-slate-200 mb-2" />
                  <span>No stage data available yet.</span>
                  <span className="text-[11px] text-slate-300 mt-0.5">
                    Add records to visualize pipeline distribution.
                  </span>
                </div>
              ) : (
                <div>
                  <div className="h-72 w-full pt-2">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        data={stageData}
                        margin={{ top: 10, right: 10, left: -20, bottom: 30 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                        <XAxis
                          dataKey="name"
                          tick={{ fontSize: 10, fill: '#64748B' }}
                          interval={0}
                          angle={-25}
                          textAnchor="end"
                        />
                        <YAxis tick={{ fontSize: 11, fill: '#64748B' }} allowDecimals={false} />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: '#0B1F3A',
                            color: '#fff',
                            borderRadius: '8px',
                            border: 'none',
                            fontSize: '12px',
                          }}
                          formatter={(value: any) => [`${value} records`, 'Count']}
                        />
                        <Bar dataKey="count" fill="#00B8D9" radius={[6, 6, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Stage Breakdown Progress List */}
                  <div className="mt-4 border-t border-slate-100 pt-4 space-y-2">
                    <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">
                      Stage Percentages
                    </h4>
                    {stageData.map((stage) => (
                      <div key={stage.name} className="flex items-center justify-between text-xs">
                        <span className="text-slate-600 font-medium truncate max-w-[150px]">
                          {stage.name}
                        </span>
                        <div className="flex items-center gap-2">
                          <div className="w-24 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-aura-cyan h-full rounded-full transition-all"
                              style={{ width: `${stage.percentage}%` }}
                            />
                          </div>
                          <span className="text-slate-500 font-mono text-right w-12 text-[11px]">
                            {stage.percentage}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Card>

            {/* Dynamic Categorical Chart: Primary Categorical Attribute (Requirement #18) */}
            {Object.keys(categoricalMetrics).length > 0 ? (
              Object.entries(categoricalMetrics)
                .slice(0, 1)
                .map(([fieldKey, catMetric]) => (
                  <Card key={fieldKey} className="p-5 space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-bold text-aura-navy flex items-center gap-2">
                        <PieIcon className="w-4 h-4 text-aura-deep" />
                        {primaryEntityName} by {catMetric.label}
                      </h3>
                      <span className="text-xs text-slate-400 font-mono">
                        {catMetric.distribution.length} categories
                      </span>
                    </div>

                    {catMetric.distribution.length === 0 ? (
                      <div className="h-64 flex items-center justify-center text-xs text-slate-400">
                        No distribution data available yet.
                      </div>
                    ) : (
                      <div className="h-72 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie
                              data={catMetric.distribution}
                              dataKey="count"
                              nameKey="value"
                              cx="50%"
                              cy="50%"
                              innerRadius={55}
                              outerRadius={85}
                              paddingAngle={4}
                            >
                              {catMetric.distribution.map((_, index) => (
                                <Cell
                                  key={`cell-${index}`}
                                  fill={AURA_CHART_COLORS[index % AURA_CHART_COLORS.length]}
                                />
                              ))}
                            </Pie>
                            <Tooltip
                              contentStyle={{
                                backgroundColor: '#0B1F3A',
                                color: '#fff',
                                borderRadius: '8px',
                                border: 'none',
                                fontSize: '12px',
                              }}
                              formatter={(value: any) => [`${value} records`, 'Count']}
                            />
                            <Legend
                              verticalAlign="bottom"
                              wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }}
                            />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                    )}
                  </Card>
                ))
            ) : analytics?.by_source && analytics.by_source.length > 0 ? (
              <Card className="p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold text-aura-navy flex items-center gap-2">
                    <PieIcon className="w-4 h-4 text-aura-deep" />
                    Records by Origin
                  </h3>
                </div>
                <div className="h-72 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={analytics.by_source}
                        dataKey="count"
                        nameKey="value"
                        cx="50%"
                        cy="50%"
                        innerRadius={55}
                        outerRadius={85}
                        paddingAngle={4}
                      >
                        {analytics.by_source.map((_, index) => (
                          <Cell
                            key={`cell-${index}`}
                            fill={AURA_CHART_COLORS[index % AURA_CHART_COLORS.length]}
                          />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#0B1F3A',
                          color: '#fff',
                          borderRadius: '8px',
                          border: 'none',
                          fontSize: '12px',
                        }}
                      />
                      <Legend verticalAlign="bottom" wrapperStyle={{ fontSize: '11px' }} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </Card>
            ) : (
              <Card className="p-8 text-center bg-slate-50 border-dashed border flex flex-col items-center justify-center">
                <BarChart3 className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                <p className="text-sm font-semibold text-slate-600 mb-1">
                  Categorical Visualizations
                </p>
                <p className="text-xs text-slate-400 max-w-xs">
                  Add select or category fields to your CRM to visualize distributions automatically.
                </p>
              </Card>
            )}
          </div>

          {/* Dynamic Numeric Metric Breakdown (Requirement #16) */}
          {Object.keys(numericMetrics).length > 0 && (
            <Card className="p-5 space-y-4">
              <h3 className="text-sm font-bold text-aura-navy flex items-center gap-2">
                <Calculator className="w-4 h-4 text-emerald-600" />
                Numeric Aggregations & Metrics
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200 text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                    <tr>
                      <th className="py-2.5 px-4">Field</th>
                      <th className="py-2.5 px-4">Record Count</th>
                      <th className="py-2.5 px-4">Total</th>
                      <th className="py-2.5 px-4">Average</th>
                      <th className="py-2.5 px-4">Min</th>
                      <th className="py-2.5 px-4">Max</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white font-mono text-slate-700">
                    {Object.entries(numericMetrics).map(([fieldKey, metric]) => (
                      <tr key={fieldKey} className="hover:bg-slate-50/60">
                        <td className="py-3 px-4 font-sans font-semibold text-aura-navy">
                          {metric.label}
                        </td>
                        <td className="py-3 px-4">{metric.count}</td>
                        <td className="py-3 px-4 font-bold text-emerald-700">
                          {metric.total.toLocaleString()}
                        </td>
                        <td className="py-3 px-4">{metric.avg.toLocaleString()}</td>
                        <td className="py-3 px-4">{metric.min.toLocaleString()}</td>
                        <td className="py-3 px-4">{metric.max.toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
};
