import React from 'react';
import { Input } from '@/components/ui/Input';

export interface MetadataEditorProps {
  name: string;
  industry: string;
  onNameChange: (name: string) => void;
  onIndustryChange: (industry: string) => void;
}

export const MetadataEditor: React.FC<MetadataEditorProps> = ({
  name,
  industry,
  onNameChange,
  onIndustryChange,
}) => {
  return (
    <div className="space-y-4">
      <Input
        label="CRM Name"
        placeholder="e.g., Sales Pipeline CRM"
        value={name}
        onChange={(e) => onNameChange(e.target.value)}
        required
      />

      <Input
        label="Industry"
        placeholder="e.g., technology, healthcare, real_estate"
        value={industry}
        onChange={(e) => onIndustryChange(e.target.value)}
        helperText="Optional: Used for AI-driven insights and recommendations"
      />

      <div className="rounded-lg bg-blue-50 border border-blue-200 p-4 text-xs text-blue-800 leading-relaxed">
        <p className="font-semibold mb-2">About CRM Metadata</p>
        <p>
          The CRM name is displayed to users. The industry is used for analytics, recommendations, and AI-generated insights.
        </p>
      </div>
    </div>
  );
};
