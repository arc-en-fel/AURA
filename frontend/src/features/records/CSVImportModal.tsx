import React, { useState } from 'react';
import { Upload, FileSpreadsheet, AlertCircle, CheckCircle2, X } from 'lucide-react';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { CRMEntity, ImportResult } from '@/types/crm';
import { api } from '@/services/api';

export interface CSVImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  crmId: string;
  entity: CRMEntity;
  onSuccess: () => void;
}

export const CSVImportModal: React.FC<CSVImportModalProps> = ({
  isOpen,
  onClose,
  crmId,
  entity,
  onSuccess,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [previewRows, setPreviewRows] = useState<string[][]>([]);
  const [headers, setHeaders] = useState<string[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    setResult(null);
    const selected = e.target.files?.[0];
    if (!selected) return;

    if (!selected.name.endsWith('.csv')) {
      setError('Please select a valid .csv file.');
      return;
    }

    setFile(selected);

    // Read and parse preview lines
    try {
      const text = await selected.text();
      const lines = text.split('\n').filter((l) => l.trim().length > 0);
      if (lines.length > 0) {
        const headerRow = lines[0].split(',').map((h) => h.trim());
        setHeaders(headerRow);
        const dataRows = lines
          .slice(1, 6)
          .map((row) => row.split(',').map((c) => c.trim()));
        setPreviewRows(dataRows);
      }
    } catch {
      setError('Could not parse CSV preview.');
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setIsUploading(true);
    setError(null);
    try {
      const res = await api.importCSV(crmId, entity.name, file);
      setResult(res);
      onSuccess();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Import failed.';
      setError(msg);
    } finally {
      setIsUploading(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setHeaders([]);
    setPreviewRows([]);
    setResult(null);
    setError(null);
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Import CSV into ${entity.label}`}
      description={`Upload a CSV file matching the schema of ${entity.label} (${entity.fields.length} dynamic fields).`}
      maxWidth="xl"
    >
      <div className="space-y-4">
        {/* Template helper */}
        <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-600">
          <span className="font-bold text-aura-navy">Expected CSV column headers:</span>{' '}
          <code className="text-aura-deep font-mono">
            {entity.fields.map((f) => f.name).join(', ')}
          </code>
        </div>

        {/* File Picker */}
        {!file && !result && (
          <div className="border-2 border-dashed border-slate-300 rounded-xl p-8 text-center hover:border-aura-cyan transition-colors bg-white">
            <Upload className="w-8 h-8 text-slate-400 mx-auto mb-3" />
            <p className="text-sm font-semibold text-aura-navy mb-1">
              Select or drop a CSV dataset
            </p>
            <p className="text-xs text-slate-400 mb-4">
              Supports standard UTF-8 CSV up to 5MB and 10,000 rows
            </p>
            <label className="cursor-pointer">
              <span className="inline-flex items-center px-4 py-2 rounded-lg bg-aura-navy text-white text-xs font-semibold hover:bg-aura-deep transition-colors">
                Browse Files
              </span>
              <input
                type="file"
                accept=".csv"
                onChange={handleFileChange}
                className="hidden"
              />
            </label>
          </div>
        )}

        {/* Preview Table */}
        {file && !result && (
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 bg-slate-100 rounded-lg text-xs">
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
                <span className="font-bold text-aura-navy">{file.name}</span>
                <span className="text-slate-400">({(file.size / 1024).toFixed(1)} KB)</span>
              </div>
              <button
                onClick={handleReset}
                className="text-slate-500 hover:text-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {headers.length > 0 && (
              <div>
                <p className="text-[11px] font-bold text-slate-500 mb-1.5 uppercase">
                  Data Preview (First {previewRows.length} rows):
                </p>
                <div className="max-h-48 overflow-auto border border-slate-200 rounded-lg text-xs">
                  <table className="w-full text-left">
                    <thead className="bg-slate-50 text-[10px] uppercase font-bold text-slate-500 sticky top-0">
                      <tr>
                        {headers.map((h, i) => (
                          <th key={i} className="py-2 px-3 border-b border-slate-200">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {previewRows.map((r, rIdx) => (
                        <tr key={rIdx} className="hover:bg-slate-50">
                          {r.map((cell, cIdx) => (
                            <td key={cIdx} className="py-2 px-3 text-slate-700">
                              {cell}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={handleReset}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleUpload}
                isLoading={isUploading}
              >
                Confirm & Import Records
              </Button>
            </div>
          </div>
        )}

        {/* Error Feedback */}
        {error && (
          <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-700 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
            <div>
              <p className="font-bold">Import Failure</p>
              <p>{error}</p>
            </div>
          </div>
        )}

        {/* Success / Summary Feedback */}
        {result && (
          <div className="space-y-4">
            <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-900 space-y-2">
              <div className="flex items-center gap-2 font-bold text-sm text-emerald-800">
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                Import Summary
              </div>
              <div className="grid grid-cols-2 gap-2 pt-2 text-xs">
                <div>
                  <span className="text-emerald-700 font-medium">Successfully Created:</span>{' '}
                  <span className="font-bold text-base text-emerald-900">{result.created}</span>
                </div>
                <div>
                  <span className="text-amber-700 font-medium">Skipped Rows:</span>{' '}
                  <span className="font-bold text-base text-amber-900">{result.skipped}</span>
                </div>
              </div>
            </div>

            {/* Row validation errors if any */}
            {result.errors && result.errors.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-bold text-rose-700">
                  Validation Errors ({result.errors.length}):
                </p>
                <div className="max-h-40 overflow-y-auto border border-rose-200 rounded-lg p-2 bg-rose-50/50 space-y-1.5 text-xs text-rose-800">
                  {result.errors.map((err, i) => (
                    <div key={i} className="flex gap-2">
                      <span className="font-mono font-bold">Row {err.row}:</span>
                      <span>[{err.code}] {err.message}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="primary" size="sm" onClick={onClose}>
                Done
              </Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
};
