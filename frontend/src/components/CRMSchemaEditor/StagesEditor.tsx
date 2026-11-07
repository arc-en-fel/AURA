import React, { useState } from 'react';
import { Plus, Trash2, GripVertical, Edit2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';

export interface StagesEditorProps {
  stages: string[];
  onStagesChange: (stages: string[]) => void;
}

export const StagesEditor: React.FC<StagesEditorProps> = ({ stages, onStagesChange }) => {
  const [showAddStage, setShowAddStage] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [draggedFrom, setDraggedFrom] = useState<number | null>(null);
  const [newStageName, setNewStageName] = useState('');
  const [newStageError, setNewStageError] = useState<string | null>(null);

  const addStage = () => {
    setNewStageError(null);

    if (!newStageName.trim()) {
      setNewStageError('Stage name cannot be empty');
      return;
    }

    if (stages.some((s) => s.toLowerCase() === newStageName.trim().toLowerCase())) {
      setNewStageError('A stage with this name already exists');
      return;
    }

    onStagesChange([...stages, newStageName.trim()]);
    setNewStageName('');
    setShowAddStage(false);
  };

  const updateStage = (index: number, newName: string) => {
    if (!newName.trim()) {
      setNewStageError('Stage name cannot be empty');
      return;
    }

    if (stages.some((s, i) => i !== index && s.toLowerCase() === newName.trim().toLowerCase())) {
      setNewStageError('A stage with this name already exists');
      return;
    }

    const updated = [...stages];
    updated[index] = newName.trim();
    onStagesChange(updated);
    setEditingIndex(null);
    setNewStageName('');
    setNewStageError(null);
  };

  const deleteStage = (index: number) => {
    if (!window.confirm('Delete this stage? This action cannot be undone.')) return;
    const updated = stages.filter((_, i) => i !== index);
    onStagesChange(updated);
  };

  const moveStage = (fromIndex: number, toIndex: number) => {
    if (fromIndex === toIndex) return;
    const updated = [...stages];
    const [removed] = updated.splice(fromIndex, 1);
    updated.splice(toIndex, 0, removed);
    onStagesChange(updated);
    setDraggedFrom(null);
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-600">
          {stages.length === 0
            ? 'No pipeline stages configured. Add one to get started.'
            : `${stages.length} stage${stages.length !== 1 ? 's' : ''} configured`}
        </p>
        <Button
          size="sm"
          variant="primary"
          onClick={() => setShowAddStage(true)}
          leftIcon={<Plus className="w-4 h-4" />}
        >
          Add Stage
        </Button>
      </div>

      {/* Stages List */}
      <div className="space-y-2">
        {stages.map((stage, index) => (
          <div
            key={`${stage}-${index}`}
            draggable
            onDragStart={() => setDraggedFrom(index)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => {
              if (draggedFrom !== null && draggedFrom !== index) {
                moveStage(draggedFrom, index);
              }
            }}
            className={`flex items-center gap-3 p-3 rounded-lg border transition-colors ${
              draggedFrom === index
                ? 'bg-blue-50 border-aura-cyan'
                : 'bg-white border-slate-200 hover:border-slate-300'
            }`}
          >
            <GripVertical className="w-4 h-4 text-slate-400 cursor-move flex-shrink-0" />
            <span className="flex-1 font-semibold text-aura-navy">{stage}</span>
            <div className="flex gap-1">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setEditingIndex(index);
                  setNewStageName(stage);
                  setNewStageError(null);
                }}
                leftIcon={<Edit2 className="w-3.5 h-3.5" />}
              />
              <Button
                size="sm"
                variant="ghost"
                onClick={() => deleteStage(index)}
                leftIcon={<Trash2 className="w-3.5 h-3.5 text-rose-500" />}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Add Stage Modal */}
      {showAddStage && (
        <Modal
          isOpen={true}
          onClose={() => {
            setShowAddStage(false);
            setNewStageName('');
            setNewStageError(null);
          }}
          title="Add Pipeline Stage"
          description="Create a new stage for your CRM pipeline"
          maxWidth="sm"
          footer={
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => {
                  setShowAddStage(false);
                  setNewStageName('');
                  setNewStageError(null);
                }}
              >
                Cancel
              </Button>
              <Button variant="primary" onClick={addStage}>
                Add Stage
              </Button>
            </div>
          }
        >
          <div className="space-y-4">
            <Input
              label="Stage Name"
              placeholder="e.g., In Progress"
              value={newStageName}
              onChange={(e) => setNewStageName(e.target.value)}
              error={newStageError || undefined}
              required
            />
          </div>
        </Modal>
      )}

      {/* Edit Stage Modal */}
      {editingIndex !== null && (
        <Modal
          isOpen={true}
          onClose={() => {
            setEditingIndex(null);
            setNewStageName('');
            setNewStageError(null);
          }}
          title="Edit Pipeline Stage"
          description={`Currently: ${stages[editingIndex]}`}
          maxWidth="sm"
          footer={
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => {
                  setEditingIndex(null);
                  setNewStageName('');
                  setNewStageError(null);
                }}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={() => updateStage(editingIndex, newStageName)}
              >
                Save Changes
              </Button>
            </div>
          }
        >
          <div className="space-y-4">
            <Input
              label="Stage Name"
              placeholder="e.g., In Progress"
              value={newStageName}
              onChange={(e) => {
                setNewStageName(e.target.value);
                setNewStageError(null);
              }}
              error={newStageError || undefined}
              required
            />
          </div>
        </Modal>
      )}
    </div>
  );
};
