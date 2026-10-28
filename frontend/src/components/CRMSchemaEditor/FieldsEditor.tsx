import React, { useState } from 'react';
import { Plus, Edit2, Trash2, GripVertical } from 'lucide-react';
import { CRMEntity, CRMField } from '@/types/crm';
import { Button } from '@/components/ui/Button';
import { AddFieldForm } from './AddFieldForm';
import { FieldEditModal } from './FieldEditModal';
import { getFieldTypeLabel } from '@/utils/crmValidation';

export interface FieldsEditorProps {
  entities: CRMEntity[];
  onEntitiesChange: (entities: CRMEntity[]) => void;
}

export const FieldsEditor: React.FC<FieldsEditorProps> = ({ entities, onEntitiesChange }) => {
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingField, setEditingField] = useState<{
    entityIndex: number;
    fieldIndex: number;
    field: CRMField;
  } | null>(null);
  const [draggedFrom, setDraggedFrom] = useState<{
    entityIndex: number;
    fieldIndex: number;
  } | null>(null);

  const addField = (entityIndex: number, newField: CRMField) => {
    const updated = [...entities];
    updated[entityIndex].fields.push(newField);
    onEntitiesChange(updated);
    setShowAddForm(false);
  };

  const updateField = (entityIndex: number, fieldIndex: number, updatedField: CRMField) => {
    const updated = [...entities];
    updated[entityIndex].fields[fieldIndex] = updatedField;
    onEntitiesChange(updated);
    setEditingField(null);
  };

  const deleteField = (entityIndex: number, fieldIndex: number) => {
    if (!window.confirm('Delete this field? This action cannot be undone.')) return;
    const updated = [...entities];
    updated[entityIndex].fields.splice(fieldIndex, 1);
    onEntitiesChange(updated);
  };

  const moveField = (
    entityIndex: number,
    fromIndex: number,
    toIndex: number
  ) => {
    if (fromIndex === toIndex) return;
    const updated = [...entities];
    const [removed] = updated[entityIndex].fields.splice(fromIndex, 1);
    updated[entityIndex].fields.splice(toIndex, 0, removed);
    onEntitiesChange(updated);
    setDraggedFrom(null);
  };

  if (entities.length === 0) {
    return (
      <div className="text-center py-8 text-slate-500">
        <p>No entities configured yet.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {entities.map((entity, entityIndex) => (
        <div
          key={entity.name}
          className="border border-slate-200 rounded-lg p-4 bg-slate-50/50"
        >
          {/* Entity Header */}
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-bold text-aura-navy">{entity.label}</h3>
              <p className="text-xs text-slate-500 font-mono mt-1">Entity: {entity.name}</p>
            </div>
            <Button
              size="sm"
              variant="primary"
              onClick={() => setShowAddForm(true)}
              leftIcon={<Plus className="w-4 h-4" />}
            >
              Add Field
            </Button>
          </div>

          {/* Fields List */}
          <div className="space-y-2">
            {entity.fields.length === 0 ? (
              <p className="text-xs text-slate-400 italic">No fields. Add one with the button above.</p>
            ) : (
              entity.fields.map((field, fieldIndex) => (
                <div
                  key={field.name}
                  draggable
                  onDragStart={() => setDraggedFrom({ entityIndex, fieldIndex })}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => {
                    if (draggedFrom?.entityIndex === entityIndex && draggedFrom.fieldIndex !== fieldIndex) {
                      moveField(entityIndex, draggedFrom.fieldIndex, fieldIndex);
                    }
                  }}
                  className={`flex items-center gap-3 p-3 rounded-lg border transition-colors ${
                    draggedFrom?.entityIndex === entityIndex && draggedFrom.fieldIndex === fieldIndex
                      ? 'bg-blue-50 border-aura-cyan'
                      : 'bg-white border-slate-200 hover:border-slate-300'
                  }`}
                >
                  <GripVertical className="w-4 h-4 text-slate-400 cursor-move" />

                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-aura-navy">{field.label}</p>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-mono">
                        {field.name}
                      </span>
                      <span className="text-xs bg-aura-cyan/10 text-aura-cyan px-2 py-0.5 rounded font-medium">
                        {getFieldTypeLabel(field.type)}
                      </span>
                      {field.required && (
                        <span className="text-xs bg-rose-100 text-rose-700 px-2 py-0.5 rounded font-semibold">
                          Required
                        </span>
                      )}
                      {field.options && field.options.length > 0 && (
                        <span className="text-xs text-slate-600">
                          {field.options.length} option{field.options.length !== 1 ? 's' : ''}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setEditingField({ entityIndex, fieldIndex, field })}
                      leftIcon={<Edit2 className="w-3.5 h-3.5" />}
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => deleteField(entityIndex, fieldIndex)}
                      leftIcon={<Trash2 className="w-3.5 h-3.5 text-rose-500" />}
                    />
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      ))}

      {/* Add Field Form Modal */}
      {showAddForm && (
        <AddFieldForm
          onAdd={(newField) => addField(0, newField)} // Add to first entity for MVP
          onCancel={() => setShowAddForm(false)}
          existingFieldNames={entities[0]?.fields.map((f) => f.name) || []}
        />
      )}

      {/* Edit Field Modal */}
      {editingField && (
        <FieldEditModal
          field={editingField.field}
          onSave={(updated) =>
            updateField(editingField.entityIndex, editingField.fieldIndex, updated)
          }
          onCancel={() => setEditingField(null)}
          existingFieldNames={entities[editingField.entityIndex].fields
            .filter((f) => f.name !== editingField.field.name)
            .map((f) => f.name)}
        />
      )}
    </div>
  );
};
