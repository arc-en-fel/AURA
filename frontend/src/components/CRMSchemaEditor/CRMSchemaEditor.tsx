import React, { useState, useMemo } from 'react';
import { Loader2, AlertCircle } from 'lucide-react';
import { CRMConfiguration } from '@/types/crm';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { validateCRMConfiguration } from '@/utils/crmValidation';
import { FieldsEditor } from './FieldsEditor';
import { StagesEditor } from './StagesEditor';
import { MetadataEditor } from './MetadataEditor';

export interface CRMSchemaEditorProps {
  crm: CRMConfiguration;
  onSave: (updatedConfig: CRMConfiguration) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
}

type EditorTab = 'fields' | 'stages' | 'metadata';

export const CRMSchemaEditor: React.FC<CRMSchemaEditorProps> = ({
  crm,
  onSave,
  onCancel,
  isLoading = false,
}) => {
  const [activeTab, setActiveTab] = useState<EditorTab>('fields');
  const [editingConfig, setEditingConfig] = useState<CRMConfiguration>(crm);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Validate configuration in real-time
  const validation = useMemo(() => {
    return validateCRMConfiguration(editingConfig);
  }, [editingConfig]);

  const handleSave = async () => {
    setError(null);

    if (!validation.valid) {
      setError(validation.errors.join('; '));
      return;
    }

    setIsSaving(true);
    try {
      await onSave(editingConfig);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to save CRM configuration';
      setError(message);
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    setEditingConfig(crm);
    setError(null);
    onCancel();
  };

  const hasChanges = JSON.stringify(editingConfig) !== JSON.stringify(crm);

  return (
    <Modal
      isOpen={true}
      onClose={handleCancel}
      title="Edit CRM Schema"
      description="Modify fields, stages, and metadata for this CRM"
      maxWidth="2xl"
      footer={
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleCancel} disabled={isSaving || isLoading}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSave}
            disabled={!hasChanges || !validation.valid || isSaving || isLoading}
            leftIcon={isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : undefined}
          >
            {isSaving ? 'Saving...' : 'Save Changes'}
          </Button>
        </div>
      }
    >
      <div className="space-y-6">
        {/* Error Alert */}
        {error && (
          <div className="rounded-lg bg-rose-50 border border-rose-200 p-4 flex gap-3">
            <AlertCircle className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-rose-900">Error</p>
              <p className="text-sm text-rose-700 mt-1">{error}</p>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 border-b border-slate-200">
          {(['fields', 'stages', 'metadata'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm font-semibold uppercase tracking-wider transition-colors border-b-2 -mb-px ${
                activeTab === tab
                  ? 'text-aura-navy border-aura-cyan'
                  : 'text-slate-500 border-transparent hover:text-slate-700'
              }`}
            >
              {tab === 'fields' && 'Fields'}
              {tab === 'stages' && 'Pipeline Stages'}
              {tab === 'metadata' && 'Metadata'}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="space-y-4">
          {activeTab === 'fields' && (
            <FieldsEditor
              entities={editingConfig.entities}
              onEntitiesChange={(entities) =>
                setEditingConfig({ ...editingConfig, entities })
              }
            />
          )}

          {activeTab === 'stages' && (
            <StagesEditor
              stages={editingConfig.pipeline_stages || []}
              onStagesChange={(stages) =>
                setEditingConfig({ ...editingConfig, pipeline_stages: stages })
              }
            />
          )}

          {activeTab === 'metadata' && (
            <MetadataEditor
              name={editingConfig.name}
              industry={editingConfig.industry}
              onNameChange={(name) => setEditingConfig({ ...editingConfig, name })}
              onIndustryChange={(industry) =>
                setEditingConfig({ ...editingConfig, industry })
              }
            />
          )}
        </div>

        {/* Validation Status */}
        {!validation.valid && (
          <div className="rounded-lg bg-amber-50 border border-amber-200 p-4">
            <p className="text-xs font-semibold text-amber-900 uppercase">Validation Issues:</p>
            <ul className="mt-2 space-y-1">
              {validation.errors.map((error, idx) => (
                <li key={idx} className="text-xs text-amber-700">
                  • {error}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Modal>
  );
};
