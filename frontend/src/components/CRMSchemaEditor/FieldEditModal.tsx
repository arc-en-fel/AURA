import React, { useState } from 'react';
import { CRMField, FieldType } from '@/types/crm';
import { Modal } from '@/components/ui/Modal';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Button } from '@/components/ui/Button';
import { validateField, getFieldTypeLabel, isValidFieldType } from '@/utils/crmValidation';
import { AlertCircle } from 'lucide-react';

export interface FieldEditModalProps {
  field: CRMField;
  onSave: (updated: CRMField) => void;
  onCancel: () => void;
  existingFieldNames?: string[];
}

const FIELD_TYPES: FieldType[] = [
  'text',
  'textarea',
  'email',
  'number',
  'date',
  'datetime',
  'boolean',
  'select',
  'multi_select',
  'phone',
  'url',
];

export const FieldEditModal: React.FC<FieldEditModalProps> = ({
  field,
  onSave,
  onCancel,
}: FieldEditModalProps) => {
  const [label, setLabel] = useState(field.label);
  const [fieldType, setFieldType] = useState<FieldType>(field.type);
  const [required, setRequired] = useState(field.required);
  const [optionsText, setOptionsText] = useState(field.options?.join('\n') || '');
  const [errors, setErrors] = useState<string[]>([]);

  const handleSubmit = () => {
    setErrors([]);

    // Validate label
    if (!label.trim()) {
      setErrors(['Field label is required']);
      return;
    }

    // Parse options for select/multi_select
    let options: string[] | undefined;
    if (fieldType === 'select' || fieldType === 'multi_select') {
      if (!optionsText.trim()) {
        setErrors(['Select fields require at least one option']);
        return;
      }
      options = optionsText
        .split('\n')
        .map((o) => o.trim())
        .filter((o) => o.length > 0);

      if (options.length === 0) {
        setErrors(['Select fields require at least one option']);
        return;
      }

      // Check for duplicates
      if (new Set(options).size !== options.length) {
        setErrors(['Options must be unique']);
        return;
      }
    }

    const updated: CRMField = {
      ...field,
      label: label.trim(),
      type: fieldType,
      required,
      options,
    };

    const validation = validateField(updated);
    if (!validation.valid) {
      setErrors(validation.errors);
      return;
    }

    onSave(updated);
  };

  const isSelectType = fieldType === 'select' || fieldType === 'multi_select';

  return (
    <Modal
      isOpen={true}
      onClose={onCancel}
      title="Edit Field"
      description={`Editing field: ${field.name}`}
      maxWidth="md"
      footer={
        <div className="flex gap-2">
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleSubmit}>
            Save Changes
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {/* Error Alert */}
        {errors.length > 0 && (
          <div className="rounded-lg bg-rose-50 border border-rose-200 p-4 flex gap-3">
            <AlertCircle className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-rose-900">Validation Errors</p>
              <ul className="mt-2 space-y-1">
                {errors.map((error, idx) => (
                  <li key={idx} className="text-xs text-rose-700">
                    • {error}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {/* Field Label */}
        <Input
          label="Field Label"
          placeholder="e.g., Customer Name"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          required
        />

        {/* Machine Name (read-only) */}
        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1.5 uppercase tracking-wider">
            Machine Name
          </label>
          <div className="block w-full rounded-lg border border-slate-300 text-sm py-2 px-3 bg-slate-50 text-slate-600 font-mono">
            {field.name}
          </div>
          <p className="mt-1 text-xs text-slate-500">Machine names cannot be changed.</p>
        </div>

        {/* Field Type */}
        <Select
          label="Field Type"
          options={FIELD_TYPES.map((type) => ({
            value: type,
            label: getFieldTypeLabel(type),
          }))}
          value={fieldType}
          onChange={(e) => {
            const newType = e.target.value;
            if (isValidFieldType(newType)) {
              setFieldType(newType);
            }
          }}
          required
        />

        {/* Required Checkbox */}
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            id="required"
            checked={required}
            onChange={(e) => setRequired(e.target.checked)}
            className="w-4 h-4 rounded border-slate-300 text-aura-cyan focus:ring-2 focus:ring-aura-cyan/20"
          />
          <label htmlFor="required" className="text-sm font-medium text-slate-700">
            Make this field required
          </label>
        </div>

        {/* Options for Select Fields */}
        {isSelectType && (
          <div>
            <label htmlFor="options" className="block text-xs font-semibold text-slate-700 mb-1.5 uppercase tracking-wider">
              Options (one per line)
            </label>
            <textarea
              id="options"
              value={optionsText}
              onChange={(e) => setOptionsText(e.target.value)}
              placeholder="Option 1&#10;Option 2&#10;Option 3"
              className="w-full rounded-lg border border-slate-300 text-sm py-2 px-3 focus:border-aura-cyan focus:ring-2 focus:ring-aura-cyan/20 transition-colors"
              rows={4}
            />
            <p className="mt-1 text-xs text-slate-500">
              Enter each option on a new line. Duplicates will be rejected.
            </p>
          </div>
        )}
      </div>
    </Modal>
  );
};
