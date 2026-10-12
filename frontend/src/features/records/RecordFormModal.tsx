import React, { useState, useEffect } from 'react';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { CRMEntity, CRMRecord, CRMField } from '@/types/crm';
import { api } from '@/services/api';
import { useToast } from '@/context/ToastContext';

export interface RecordFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  crmId: string;
  entity: CRMEntity;
  record?: CRMRecord | null;
  onSaved: () => void;
}

export const RecordFormModal: React.FC<RecordFormModalProps> = ({
  isOpen,
  onClose,
  crmId,
  entity,
  record,
  onSaved,
}) => {
  const { success, error: toastError } = useToast();
  const [formData, setFormData] = useState<Record<string, unknown>>({});
  const [source, setSource] = useState<string>('Manual');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const isEditing = Boolean(record);

  useEffect(() => {
    if (record) {
      setFormData({ ...record.data });
      setSource(record.source || 'Manual');
    } else {
      const initial: Record<string, unknown> = {};
      entity.fields.forEach((f) => {
        if (f.type === 'boolean') initial[f.name] = false;
        else if (f.type === 'select' && f.options?.length) initial[f.name] = f.options[0];
        else initial[f.name] = '';
      });
      setFormData(initial);
      setSource('Manual');
    }
    setErrors({});
  }, [record, entity, isOpen]);

  const handleChange = (fieldName: string, value: unknown) => {
    setFormData((prev) => ({ ...prev, [fieldName]: value }));
    if (errors[fieldName]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[fieldName];
        return next;
      });
    }
  };

  const validate = (): boolean => {
    const errs: Record<string, string> = {};
    entity.fields.forEach((field) => {
      const val = formData[field.name];
      if (field.required) {
        if (val === undefined || val === null || val === '') {
          errs[field.name] = `${field.label} is required.`;
        }
      }
      if (val && field.type === 'email') {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(String(val))) {
          errs[field.name] = 'Invalid email format.';
        }
      }
      if (val && field.type === 'number') {
        if (isNaN(Number(val))) {
          errs[field.name] = 'Must be a valid number.';
        }
      }
    });

    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setIsSubmitting(true);
    try {
      // Coerce numeric types properly
      const cleanedData: Record<string, unknown> = {};
      entity.fields.forEach((f) => {
        const v = formData[f.name];
        if (f.type === 'number' && v !== '' && v !== undefined) {
          cleanedData[f.name] = Number(v);
        } else if (f.type === 'boolean') {
          cleanedData[f.name] = Boolean(v);
        } else if (v !== '' && v !== undefined) {
          cleanedData[f.name] = v;
        }
      });

      if (isEditing && record) {
        await api.updateRecord(crmId, entity.name, record.id, cleanedData);
        success(`Updated ${entity.label} record successfully!`);
      } else {
        await api.createRecord(crmId, entity.name, cleanedData, source);
        success(`Created ${entity.label} record successfully!`);
      }
      onSaved();
      onClose();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to save record.';
      toastError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderFieldInput = (field: CRMField) => {
    const val = formData[field.name];
    const errorMsg = errors[field.name];

    switch (field.type) {
      case 'textarea':
        return (
          <div key={field.name}>
            <label className="block text-xs font-semibold text-slate-700 mb-1.5 uppercase tracking-wider">
              {field.label} {field.required && <span className="text-rose-500">*</span>}
            </label>
            <textarea
              rows={3}
              value={String(val ?? '')}
              onChange={(e) => handleChange(field.name, e.target.value)}
              className={`block w-full rounded-lg border text-sm py-2 px-3 focus:outline-none ${
                errorMsg
                  ? 'border-rose-400 focus:border-rose-500 bg-rose-50/20'
                  : 'border-slate-300 focus:border-aura-cyan focus:ring-1 focus:ring-aura-cyan'
              }`}
            />
            {errorMsg && <p className="mt-1 text-xs text-rose-600">{errorMsg}</p>}
          </div>
        );

      case 'select':
        return (
          <div key={field.name}>
            <Select
              label={field.label}
              required={field.required}
              options={field.options || []}
              value={String(val ?? field.options?.[0] ?? '')}
              onChange={(e) => handleChange(field.name, e.target.value)}
              error={errorMsg}
            />
          </div>
        );

      case 'boolean':
        return (
          <div key={field.name} className="flex items-center gap-3 pt-2">
            <input
              type="checkbox"
              id={`field-${field.name}`}
              checked={Boolean(val)}
              onChange={(e) => handleChange(field.name, e.target.checked)}
              className="w-4 h-4 rounded text-aura-cyan focus:ring-aura-cyan border-slate-300"
            />
            <label
              htmlFor={`field-${field.name}`}
              className="text-xs font-medium text-slate-700 cursor-pointer select-none"
            >
              {field.label} {field.required && <span className="text-rose-500">*</span>}
            </label>
          </div>
        );

      case 'number':
        return (
          <div key={field.name}>
            <Input
              label={field.label}
              type="number"
              required={field.required}
              value={val !== undefined ? String(val) : ''}
              onChange={(e) => handleChange(field.name, e.target.value)}
              error={errorMsg}
            />
          </div>
        );

      case 'date':
        return (
          <div key={field.name}>
            <Input
              label={field.label}
              type="date"
              required={field.required}
              value={String(val ?? '')}
              onChange={(e) => handleChange(field.name, e.target.value)}
              error={errorMsg}
            />
          </div>
        );

      case 'email':
        return (
          <div key={field.name}>
            <Input
              label={field.label}
              type="email"
              required={field.required}
              value={String(val ?? '')}
              onChange={(e) => handleChange(field.name, e.target.value)}
              placeholder="e.g. contact@example.com"
              error={errorMsg}
            />
          </div>
        );

      case 'phone':
        return (
          <div key={field.name}>
            <Input
              label={field.label}
              type="tel"
              required={field.required}
              value={String(val ?? '')}
              onChange={(e) => handleChange(field.name, e.target.value)}
              placeholder="e.g. +1-555-0199"
              error={errorMsg}
            />
          </div>
        );

      case 'text':
      default:
        return (
          <div key={field.name}>
            <Input
              label={field.label}
              type="text"
              required={field.required}
              value={String(val ?? '')}
              onChange={(e) => handleChange(field.name, e.target.value)}
              error={errorMsg}
            />
          </div>
        );
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? `Edit ${entity.label} Record` : `Create New ${entity.label}`}
      description={`Fields dynamically configured per ${entity.label} schema definition.`}
      maxWidth="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Dynamic Fields */}
        <div className="space-y-3 max-h-[60vh] overflow-y-auto px-1">
          {entity.fields.map((field) => renderFieldInput(field))}

          {!isEditing && (
            <div className="pt-2 border-t border-slate-100">
              <Input
                label="Acquisition Source Tag"
                value={source}
                onChange={(e) => setSource(e.target.value)}
                placeholder="e.g. Manual, Inbound, Conference"
              />
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-100">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" size="sm" isLoading={isSubmitting}>
            {isEditing ? 'Save Changes' : 'Create Record'}
          </Button>
        </div>
      </form>
    </Modal>
  );
};
