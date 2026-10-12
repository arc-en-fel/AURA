import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Sparkles,
  ArrowRight,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Database,
  Type,
  Hash,
  Mail,
  Calendar,
  ToggleLeft,
  ListFilter,
  Save,
  Lightbulb,
} from 'lucide-react';
import { api } from '@/services/api';
import { CRMConfiguration, FieldType } from '@/types/crm';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { useToast } from '@/context/ToastContext';
import { useCRM } from '@/context/CRMContext';

export const CRMGeneratorPage: React.FC = () => {
  const navigate = useNavigate();
  const { success, error: toastError } = useToast();
  const { refreshCRMs, selectCRM } = useCRM();

  const [prompt, setPrompt] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draftConfig, setDraftConfig] = useState<CRMConfiguration | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);

  const examplePrompts = [
    {
      title: 'B2B SaaS Sales CRM',
      prompt:
        'Create a B2B SaaS CRM to track enterprise leads, deals, lead sources, demo follow-up dates, deal values, and subscription tier stages.',
    },
    {
      title: 'Real Estate Brokerage CRM',
      prompt:
        'Create a luxury real estate CRM to manage property buyer leads, listings, site visits, budgets, location preferences, and escrow stages.',
    },
    {
      title: 'Healthcare & Patient Clinic',
      prompt:
        'Create a healthcare clinic CRM to track patients, appointments, primary phone, blood groups, triage status, and consultation stages.',
    },
  ];

  const handleGenerate = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setError(null);

    if (prompt.trim().length < 10) {
      setError('Please provide a detailed prompt (at least 10 characters).');
      return;
    }

    setIsGenerating(true);
    try {
      const response = await api.generateCRM(prompt);
      setDraftConfig(response.configuration);
      setWarnings(response.warnings || []);
      success('Draft CRM configuration generated successfully! Please review before saving.');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'CRM generation failed.';
      setError(msg);
      toastError(msg);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSaveCRM = async () => {
    if (!draftConfig) return;
    setIsSaving(true);
    try {
      const saved = await api.saveCRM(draftConfig);
      await refreshCRMs();
      await selectCRM(saved.crm_id);
      success(`CRM "${saved.name}" persisted and activated!`);
      navigate(`/crms/${saved.crm_id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to save CRM.';
      setError(msg);
      toastError(msg);
    } finally {
      setIsSaving(false);
    }
  };

  const getFieldTypeIcon = (type: FieldType) => {
    switch (type) {
      case 'text':
      case 'textarea':
        return <Type className="w-3 h-3 text-slate-500" />;
      case 'number':
        return <Hash className="w-3 h-3 text-blue-500" />;
      case 'email':
        return <Mail className="w-3 h-3 text-indigo-500" />;
      case 'date':
        return <Calendar className="w-3 h-3 text-amber-500" />;
      case 'boolean':
        return <ToggleLeft className="w-3 h-3 text-purple-500" />;
      case 'select':
        return <ListFilter className="w-3 h-3 text-cyan-500" />;
      default:
        return <Type className="w-3 h-3 text-slate-400" />;
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Title & Introduction */}
      <div>
        <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-cyan-50 border border-cyan-200 text-aura-cyan text-[11px] font-bold uppercase tracking-wider mb-2">
          <Sparkles className="w-3.5 h-3.5" />
          Autonomous CRM Synthesis
        </div>
        <h2 className="text-xl sm:text-2xl font-extrabold text-aura-navy">
          Generate Custom CRM Architecture
        </h2>
        <p className="text-xs sm:text-sm text-slate-500 mt-1">
          Describe your business model and data tracking needs in natural language. AURA synthesizes schema definitions, dynamic entities, field validation rules, and pipeline stages.
        </p>
      </div>

      {/* Prompt Editor Card */}
      <Card className="p-6 border-slate-200 space-y-4">
        <form onSubmit={handleGenerate} className="space-y-4">
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">
              Natural Language CRM Specification
            </label>
            <textarea
              rows={4}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g. Create a sales CRM to manage leads, customers, sales representatives, follow-up dates, deal values, and lead stages..."
              className="w-full text-xs sm:text-sm p-4 rounded-xl border border-slate-300 focus:border-aura-cyan focus:ring-2 focus:ring-aura-cyan/20 outline-none leading-relaxed placeholder-slate-400"
            />
          </div>

          {/* Example Prompt Chips */}
          <div>
            <p className="text-[11px] font-bold uppercase text-slate-400 tracking-wider mb-2 flex items-center gap-1.5">
              <Lightbulb className="w-3.5 h-3.5 text-amber-500" />
              Example Prompts (Click to Use):
            </p>
            <div className="flex flex-wrap gap-2">
              {examplePrompts.map((ex, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setPrompt(ex.prompt)}
                  className="text-left text-xs px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 hover:bg-white hover:border-aura-cyan text-slate-700 transition-colors"
                >
                  <span className="font-semibold text-aura-deep">{ex.title}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Action Row */}
          <div className="flex items-center justify-between pt-2">
            <span className="text-[11px] text-slate-400">
              Generating produces a draft proposal. It is not saved until you review and confirm.
            </span>
            <Button
              type="submit"
              variant="primary"
              isLoading={isGenerating}
              leftIcon={<Sparkles className="w-4 h-4 text-aura-cyan" />}
            >
              Generate CRM Architecture
            </Button>
          </div>
        </form>

        {error && (
          <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">Generation Error</p>
              <p>{error}</p>
            </div>
          </div>
        )}

        {warnings.length > 0 && (
          <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-800 space-y-1">
            <p className="font-bold">Architectural Warnings:</p>
            {warnings.map((w, idx) => (
              <p key={idx}>• {w}</p>
            ))}
          </div>
        )}
      </Card>

      {/* Generated Draft Preview Workspace */}
      {draftConfig && (
        <div className="space-y-5 animate-fade-in">
          <div className="flex items-center justify-between pb-2 border-b border-slate-200">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold uppercase tracking-wider text-amber-600 bg-amber-50 border border-amber-200 px-2.5 py-0.5 rounded-full">
                  Draft Proposal
                </span>
                <span className="text-xs text-slate-400">• Ready for validation & save</span>
              </div>
              <h3 className="text-lg font-bold text-aura-navy mt-1">
                {draftConfig.name}
              </h3>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleGenerate()}
                isLoading={isGenerating}
                leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
              >
                Regenerate
              </Button>
              <Button
                variant="yellow"
                size="sm"
                onClick={handleSaveCRM}
                isLoading={isSaving}
                leftIcon={<Save className="w-4 h-4" />}
                rightIcon={<ArrowRight className="w-4 h-4" />}
              >
                Save & Activate CRM
              </Button>
            </div>
          </div>

          {/* Schema Metadata Card */}
          <Card className="p-5 space-y-4 border-aura-cyan/40 shadow-card">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pb-4 border-b border-slate-100">
              <div>
                <label className="text-[10px] uppercase font-bold text-slate-400">
                  CRM Name
                </label>
                <input
                  type="text"
                  value={draftConfig.name}
                  onChange={(e) =>
                    setDraftConfig({ ...draftConfig, name: e.target.value })
                  }
                  className="mt-1 w-full text-sm font-bold text-aura-navy border-b border-slate-200 focus:border-aura-cyan outline-none py-1"
                />
              </div>
              <div>
                <label className="text-[10px] uppercase font-bold text-slate-400">
                  Target Industry
                </label>
                <input
                  type="text"
                  value={draftConfig.industry}
                  onChange={(e) =>
                    setDraftConfig({ ...draftConfig, industry: e.target.value })
                  }
                  className="mt-1 w-full text-sm font-semibold text-aura-charcoal border-b border-slate-200 focus:border-aura-cyan outline-none py-1"
                />
              </div>
              <div>
                <label className="text-[10px] uppercase font-bold text-slate-400">
                  Schema Spec Version
                </label>
                <p className="mt-1 text-sm font-mono text-slate-600">
                  {draftConfig.schema_version}
                </p>
              </div>
            </div>

            {/* Pipeline Stages */}
            {draftConfig.pipeline_stages.length > 0 && (
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                  Generated Pipeline Stages
                </h4>
                <div className="flex flex-wrap gap-2">
                  {draftConfig.pipeline_stages.map((stg, i) => (
                    <span
                      key={i}
                      className="px-3 py-1 rounded-lg bg-slate-100 border border-slate-200 text-xs font-semibold text-aura-navy"
                    >
                      {stg}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Entities & Fields Breakdown */}
            <div className="space-y-4 pt-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Generated Entities ({draftConfig.entities.length})
              </h4>

              <div className="space-y-4">
                {draftConfig.entities.map((ent, idx) => (
                  <div
                    key={idx}
                    className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Database className="w-4 h-4 text-aura-cyan" />
                        <span className="font-bold text-sm text-aura-navy">
                          {ent.label}
                        </span>
                        <code className="text-xs text-slate-400">({ent.name})</code>
                      </div>
                      <span className="text-xs text-slate-500 font-medium">
                        {ent.fields.length} dynamic fields
                      </span>
                    </div>

                    {/* Fields List */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                      {ent.fields.map((fld, fIdx) => (
                        <div
                          key={fIdx}
                          className="p-2.5 rounded-lg bg-white border border-slate-200/80 shadow-2xs text-xs space-y-1"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-aura-charcoal">
                              {fld.label}
                            </span>
                            {fld.required && (
                              <span className="text-[10px] text-rose-600 font-bold">
                                Req
                              </span>
                            )}
                          </div>
                          <div className="flex items-center justify-between text-slate-400 text-[11px]">
                            <span className="font-mono">{fld.name}</span>
                            <span className="inline-flex items-center gap-1 uppercase text-[10px] font-bold text-slate-500">
                              {getFieldTypeIcon(fld.type)}
                              {fld.type}
                            </span>
                          </div>
                          {fld.options && fld.options.length > 0 && (
                            <p className="text-[10px] text-slate-500 truncate pt-0.5">
                              Options: {fld.options.join(', ')}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Final Confirmation Banner */}
            <div className="pt-4 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-4">
              <div className="flex items-center gap-2 text-xs text-emerald-700">
                <CheckCircle className="w-4 h-4 text-emerald-500 shrink-0" />
                <span>
                  Configuration adheres strictly to AURA JSON Schema v1.0 specifications.
                </span>
              </div>
              <Button
                variant="yellow"
                onClick={handleSaveCRM}
                isLoading={isSaving}
                leftIcon={<Save className="w-4 h-4" />}
              >
                Save & Activate CRM
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
};
