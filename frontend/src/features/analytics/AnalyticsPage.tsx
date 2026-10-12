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
  TrendingUp,
  Award,
  Users,
  Percent,
  RefreshCw,
  PieChart as PieIcon,
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

  const stageData = (analytics?.by_stage || []).map((s) => ({
    name: s.value || 'Unassigned',
    count: s.count,
  }));

  const sourceData = (analytics?.by_source || []).map((s) => ({
    name: s.value || 'Direct',
    count: s.count,
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-aura-navy">Pipeline & CRM Analytics</h2>
          <p className="text-xs text-slate-500 mt-1">
            Real-time conversion metrics and stage distribution for {activeCRM.name}.
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
          {/* Key Metric KPI Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Card className="p-5">
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-[10px] font-bold uppercase tracking-wider">
                  Total Leads/Records
                </span>
                <Users className="w-4 h-4 text-aura-deep" />
              </div>
              <p className="text-2xl font-extrabold text-aura-navy">
                {analytics?.total_leads ?? 0}
              </p>
              <p className="text-[11px] text-slate-400 mt-1">Total volume in entity</p>
            </Card>

            <Card className="p-5">
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-[10px] font-bold uppercase tracking-wider">
                  Qualified
                </span>
                <TrendingUp className="w-4 h-4 text-blue-500" />
              </div>
              <p className="text-2xl font-extrabold text-aura-navy">
                {analytics?.qualified_leads ?? 0}
              </p>
              <p className="text-[11px] text-slate-400 mt-1">Qualified pipeline opportunities</p>
            </Card>

            <Card className="p-5">
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-[10px] font-bold uppercase tracking-wider">
                  Won Deals
                </span>
                <Award className="w-4 h-4 text-emerald-500" />
              </div>
              <p className="text-2xl font-extrabold text-emerald-600">
                {analytics?.won_leads ?? 0}
              </p>
              <p className="text-[11px] text-slate-400 mt-1">Closed won conversions</p>
            </Card>

            <Card className="p-5">
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-[10px] font-bold uppercase tracking-wider">
                  Conversion Rate
                </span>
                <Percent className="w-4 h-4 text-amber-500" />
              </div>
              <p className="text-2xl font-extrabold text-amber-600">
                {analytics ? `${(analytics.conversion_rate * 100).toFixed(1)}%` : '0%'}
              </p>
              <p className="text-[11px] text-slate-400 mt-1">Won leads / total leads</p>
            </Card>
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Stage Distribution Bar Chart */}
            <Card className="p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-aura-navy flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-aura-cyan" />
                  Records by Pipeline Stage
                </h3>
                <span className="text-xs text-slate-400 font-mono">by_stage</span>
              </div>

              {stageData.length === 0 ? (
                <div className="h-64 flex items-center justify-center text-xs text-slate-400">
                  No stage metrics recorded yet.
                </div>
              ) : (
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
                      />
                      <Bar dataKey="count" fill="#00B8D9" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>

            {/* Source Distribution Donut Chart */}
            <Card className="p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-aura-navy flex items-center gap-2">
                  <PieIcon className="w-4 h-4 text-aura-deep" />
                  Lead Volume by Acquisition Source
                </h3>
                <span className="text-xs text-slate-400 font-mono">by_source</span>
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
          </div>
        </>
      )}
    </div>
  );
};
