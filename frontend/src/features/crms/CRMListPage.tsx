import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FolderKanban,
  Sparkles,
  Search,
  ArrowRight,
  CheckCircle,
} from 'lucide-react';
import { useCRM } from '@/context/CRMContext';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import { TableSkeleton } from '@/components/ui/LoadingSkeleton';

export const CRMListPage: React.FC = () => {
  const { crms, activeCRM, selectCRM, isLoading } = useCRM();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');

  const filteredCRMs = crms.filter(
    (c) =>
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.configuration.industry.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-aura-navy">My CRMs</h2>
          <p className="text-xs text-slate-500 mt-1">
            Manage your autonomous CRM instances, schemas, and versions.
          </p>
        </div>

        <Button
          variant="primary"
          onClick={() => navigate('/create-crm')}
          leftIcon={<Sparkles className="w-4 h-4 text-aura-cyan" />}
        >
          Generate New CRM
        </Button>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex items-center gap-3 bg-white p-3 rounded-xl border border-slate-200/80 shadow-subtle">
        <Search className="w-4 h-4 text-slate-400 shrink-0" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search CRMs by name or industry..."
          className="flex-1 text-xs outline-none bg-transparent placeholder-slate-400"
        />
        {search && (
          <button
            onClick={() => setSearch('')}
            className="text-xs text-slate-400 hover:text-slate-600"
          >
            Clear
          </button>
        )}
      </div>

      {/* CRM Cards Grid */}
      {isLoading ? (
        <TableSkeleton rows={4} cols={3} />
      ) : filteredCRMs.length === 0 ? (
        <EmptyState
          icon={<FolderKanban className="w-6 h-6" />}
          title={search ? 'No Matching CRMs Found' : 'No CRMs Created Yet'}
          description={
            search
              ? 'Try refining your search keyword.'
              : 'Generate your first CRM architecture using natural-language AI prompts.'
          }
          actionLabel="Generate CRM"
          onAction={() => navigate('/create-crm')}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredCRMs.map((crm) => {
            const isActive = activeCRM?.crm_id === crm.crm_id;
            return (
              <Card
                key={crm.crm_id}
                hoverable
                className={`p-5 flex flex-col justify-between transition-all ${
                  isActive ? 'border-aura-cyan ring-1 ring-aura-cyan shadow-card' : ''
                }`}
              >
                <div>
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <h3 className="font-bold text-base text-aura-navy truncate">
                      {crm.name}
                    </h3>
                    <Badge variant={crm.status}>{crm.status}</Badge>
                  </div>

                  <div className="flex items-center gap-2 mb-4">
                    <span className="text-xs font-semibold text-aura-deep capitalize">
                      {crm.configuration.industry.replace('_', ' ')}
                    </span>
                    <span className="text-slate-300">•</span>
                    <Badge variant="cyan" size="sm">
                      v{crm.configuration_version}
                    </Badge>
                  </div>

                  {/* Entities list pill */}
                  <div className="mb-4">
                    <p className="text-[10px] font-bold uppercase text-slate-400 tracking-wider mb-2">
                      Entities ({crm.configuration.entities.length})
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {crm.configuration.entities.map((ent) => (
                        <span
                          key={ent.name}
                          className="text-[11px] px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-medium border border-slate-200"
                        >
                          {ent.label} ({ent.fields.length} fields)
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Pipeline preview */}
                  {crm.configuration.pipeline_stages?.length > 0 && (
                    <div className="mb-4">
                      <p className="text-[10px] font-bold uppercase text-slate-400 tracking-wider mb-1.5">
                        Stages ({crm.configuration.pipeline_stages.length})
                      </p>
                      <p className="text-xs text-slate-600 truncate">
                        {crm.configuration.pipeline_stages.join(' → ')}
                      </p>
                    </div>
                  )}
                </div>

                {/* Card Action Footer */}
                <div className="pt-4 border-t border-slate-100 flex items-center justify-between gap-2">
                  <Button
                    variant={isActive ? 'accent' : 'outline'}
                    size="sm"
                    onClick={() => selectCRM(crm.crm_id)}
                    leftIcon={isActive ? <CheckCircle className="w-3.5 h-3.5" /> : undefined}
                  >
                    {isActive ? 'Active CRM' : 'Set as Active'}
                  </Button>

                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => navigate(`/crms/${crm.crm_id}`)}
                    rightIcon={<ArrowRight className="w-3.5 h-3.5" />}
                  >
                    Details
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};
