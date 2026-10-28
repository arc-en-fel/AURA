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
  '#0B1F3A', // Navy
  '#6366F1', // Indigo
  '#EC4899', // Pink
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

  useEffect(() => {
    fetchAnalytics();

    // Listen for data refresh events
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

  // Get schema info to determine what to display
  const schemaInfo = analytics && 'schema_info' in analytics ? (analytics as any).schema_info || {} : {};
  const primaryEntityName = schemaInfo.primary_entity_name || 'records';
  const pipelineStages = schemaInfo.pipeline_stages || [];
  const stageFieldName = schemaInfo.stage_field_name;
  const sourceFieldName = schemaInfo.source_field_name;

  // Get total records (prefer new format, fall back to old)
  const totalRecords = (analytics && 'total_records' in analytics ? (analytics as any).total_records : (analytics as any)?.total_leads) || 0;

  // Prepare chart data
  const stageData = (analytics?.by_stage || []).map((s) => ({
    name: s.value || 'Unassigned',
    count: s.count,
    percentage: (s as any).percentage || 0,
  }));

  const sourceData = (analytics?.by_source || []).map((s) => ({
    name: s.value || 'Direct',
    count: s.count,
    percentage: (s as any).percentage || 0,
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-aura-navy">Pipeline & CRM Analytics</h2>
          <p className="text-xs text-slate-500 mt-1">
            Real-time metrics and distributions for {activeCRM.name}.
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

      {isLoading ? (
        <TableSkeleton rows={4} cols={4} />
      ) : error ? (
        <Card className="p-6 text-center text-xs text-rose-600 bg-rose-50 border-rose-200">
          <p className="font-bold">Error loading analytics</p>
          <p>{error}</p>
        </Card>
      ) : (
        <>
          {/* Key Metric KPI Card - Total Records */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Card className="p-5">
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-[10px] font-bold uppercase tracking-wider">
                  Total {primaryEntityName.charAt(0).toUpperCase() + primaryEntityName.slice(1)}
                </span>
                <Users className="w-4 h-4 text-aura-deep" />
              </div>
              <p className="text-2xl font-extrabold text-aura-navy">
                {totalRecords}
              </p>
              <p className="text-[11px] text-slate-400 mt-1">Total volume in CRM</p>
            </Card>

            {/* Show empty state if no stages or source data */}
            {stageData.length === 0 && sourceData.length === 0 && (
              <Card className="p-5 bg-slate-50 border-dashed">
                <div className="text-xs text-slate-500 text-center">
                  <p className="font-semibold mb-1">No distribution data</p>
                  <p>Add records with stage or source values to see analytics.</p>
                </div>
              </Card>
            )}
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Stage Distribution Bar Chart */}
            {stageFieldName && (
              <Card className="p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold text-aura-navy flex items-center gap-2">
                    <BarChart3 className="w-4 h-4 text-aura-cyan" />
                    Records by {stageFieldName === 'status' ? 'Status' : 'Stage'}
                  </h3>
                  <span className="text-xs text-slate-400 font-mono">
                    {pipelineStages.length} stages
                  </span>
                </div>

                {stageData.length === 0 ? (
                  <div className="h-64 flex items-center justify-center text-xs text-slate-400">
                    No stage data available. Add records with stages to see distribution.
                  </div>
                ) : (
                  <div>
                    <div className="h-72 w-full pt-2">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={stageData} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                          <XAxis
                            dataKey="name"
                            tick={{ fontSize: 11, fill: '#64748B' }}
                            interval={0}
                            angle={-20}
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

                    {/* Stage Percentages Table */}
                    <div className="mt-4 border-t border-slate-100 pt-4">
                      <h4 className="text-xs font-semibold text-slate-600 mb-3 uppercase tracking-wider">Stage Breakdown</h4>
                      <div className="space-y-2">
                        {stageData.map((stage) => (
                          <div key={stage.name} className="flex items-center justify-between text-xs">
                            <span className="text-slate-600 truncate">{stage.name}</span>
                            <div className="flex items-center gap-2">
                              <div className="w-20 bg-slate-100 rounded-full h-1">
                                <div
                                  className="bg-aura-cyan h-1 rounded-full"
                                  style={{ width: `${stage.percentage}%` }}
                                />
                              </div>
                              <span className="text-slate-500 font-mono text-right w-12">
                                {stage.percentage}%
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </Card>
            )}

            {/* Source Distribution Donut Chart */}
            {sourceFieldName && (
              <Card className="p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold text-aura-navy flex items-center gap-2">
                    <PieIcon className="w-4 h-4 text-aura-deep" />
                    Records by Source
                  </h3>
                  <span className="text-xs text-slate-400 font-mono">
                    {sourceData.length} sources
                  </span>
                </div>

                {sourceData.length === 0 ? (
                  <div className="h-64 flex items-center justify-center text-xs text-slate-400">
                    No source data available.
                  </div>
                ) : (
                  <div className="h-72 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={sourceData}
                          dataKey="count"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          innerRadius={55}
                          outerRadius={85}
                          paddingAngle={4}
                        >
                          {sourceData.map((_, index) => (
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
            )}
          </div>

          {/* Empty State: No stage or source fields configured */}
          {!stageFieldName && !sourceFieldName && (
            <Card className="p-8 text-center bg-slate-50 border-dashed border-2">
              <BarChart3 className="w-8 h-8 text-slate-400 mx-auto mb-3" />
              <p className="text-sm font-semibold text-slate-600 mb-1">No Analytics Fields Configured</p>
              <p className="text-xs text-slate-500 mb-4">
                Add a "status" or "stage" field to track pipeline, and a "source" field to track record origins.
              </p>
            </Card>
          )}
        </>
      )}
    </div>
  );
};
