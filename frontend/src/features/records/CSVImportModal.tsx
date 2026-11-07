import React, { useState } from 'react';
import {
  Upload,
  FileSpreadsheet,
  AlertCircle,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  RefreshCw,
  X,
} from 'lucide-react';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { CRMEntity, ImportResult } from '@/types/crm';
import { api } from '@/services/api';
import {
  parseCSV,
  resolveCSVHeaders,
  findUnmatchedEnumValues,
  CSVResolutionResult,
  UnmatchedEnumValue,
} from '@/utils/csvResolver';

export interface CSVImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  crmId: string;
  entity: CRMEntity;
  pipelineStages?: string[];
  onSuccess: () => void;
}

export const CSVImportModal: React.FC<CSVImportModalProps> = ({
  isOpen,
  onClose,
  crmId,
  entity,
  pipelineStages = [],
  onSuccess,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [previewRows, setPreviewRows] = useState<string[][]>([]);
  const [allDataRows, setAllDataRows] = useState<string[][]>([]);
  const [headers, setHeaders] = useState<string[]>([]);
  const [resolution, setResolution] = useState<CSVResolutionResult | null>(null);
  const [unmatchedEnums, setUnmatchedEnums] = useState<UnmatchedEnumValue[]>([]);
  const [valueMappings, setValueMappings] = useState<Record<string, Record<string, string>>>({});
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRetryMode, setIsRetryMode] = useState(false);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    setResult(null);
    setResolution(null);
    setUnmatchedEnums([]);
    setValueMappings({});
    setIsRetryMode(false);

    const selected = e.target.files?.[0];
    if (!selected) return;

    if (!selected.name.endsWith('.csv')) {
      setError('Please select a valid .csv file.');
      return;
    }

    setFile(selected);

    // Read and parse preview lines using robust CSV parser
    try {
      const text = await selected.text();
      const parsed = parseCSV(text);
      if (parsed.error) {
        setError(parsed.error);
        return;
      }

      setHeaders(parsed.headers);
      setAllDataRows(parsed.rows);
      setPreviewRows(parsed.rows.slice(0, 5));

      // Universal schema-driven header resolution
      const res = resolveCSVHeaders(parsed.headers, entity.fields, entity.label);
      setResolution(res);

      if (!res.isValid && res.errors.length > 0) {
        setError(res.errors[0]);
        return;
      }

      // Pre-flight scan for unmatched enum / status values
      const unmatched = findUnmatchedEnumValues(
        parsed.rows,
        res.indexMap,
        entity.fields,
        pipelineStages
      );
      setUnmatchedEnums(unmatched);
    } catch {
      setError('Could not parse CSV preview.');
    }
  };

  const handleMappingChange = (fieldName: string, rawVal: string, targetVal: string) => {
    setValueMappings((prev) => {
      const fieldMap = { ...(prev[fieldName] || {}) };
      if (!targetVal) {
        delete fieldMap[rawVal];
      } else {
        fieldMap[rawVal] = targetVal;
      }
      return {
        ...prev,
        [fieldName]: fieldMap,
      };
    });
  };

  const handleUpload = async (mappingsToUse?: Record<string, Record<string, string>>) => {
    if (!file) return;
    if (resolution && !resolution.isValid) {
      setError(resolution.errors[0] || 'Cannot import CSV with invalid headers.');
      return;
    }

    setIsUploading(true);
    setError(null);
    try {
      const mappings = mappingsToUse || valueMappings;
      const res = await api.importCSV(crmId, entity.name, file, mappings, true);
      setResult(res);
      setIsRetryMode(false);
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
    setAllDataRows([]);
    setResolution(null);
    setUnmatchedEnums([]);
    setValueMappings({});
    setResult(null);
    setError(null);
    setIsRetryMode(false);
  };

  const handleOpenRetryMapping = () => {
    setIsRetryMode(true);
    setResult(null);
  };

  const totalUnmatchedRows = unmatchedEnums.reduce((acc, u) => acc + u.count, 0);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Import CSV into ${entity.label}`}
      description={`Upload a CSV file matching the schema of ${entity.label} (${entity.fields.length} dynamic fields).`}
      maxWidth="2xl"
    >
      <div className="space-y-4">
        {/* Template helper */}
        <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-600 space-y-1.5">
          <div className="flex items-center gap-1.5 font-bold text-aura-navy">
            <span>Accepted Column Headers:</span>
            <span className="font-normal text-[11px] text-slate-500">
              (Display labels, canonical field names, case & space variations)
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5 pt-0.5">
            {entity.fields.map((f) => (
              <span
                key={f.name}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-white border border-slate-200 text-[11px] font-mono text-aura-navy"
                title={`Canonical: ${f.name} | Type: ${f.type}${f.required ? ' | Required' : ''}`}
              >
                <span className="font-sans font-semibold text-slate-700">{f.label}</span>
                <span className="text-slate-400">({f.name})</span>
                {f.required && <span className="text-rose-500 font-bold">*</span>}
              </span>
            ))}
          </div>
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

        {/* Interactive Enum / Status Value Mapping Step */}
        {file && !result && (unmatchedEnums.length > 0 || isRetryMode) && (
          <div className="p-4 bg-amber-50/70 border border-amber-200 rounded-xl space-y-3">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2 text-amber-900 font-bold text-sm">
                <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                <span>Workflow Status & Value Mapping Required</span>
              </div>
              <span className="text-[11px] font-semibold text-amber-800 bg-amber-100 px-2 py-0.5 rounded">
                {totalUnmatchedRows} rows affected
              </span>
            </div>
            <p className="text-xs text-amber-800 leading-relaxed">
              The CSV contains values that do not match the configured options in your CRM schema.
              Explicitly map each value to a permitted destination option, or choose to skip those rows.
            </p>

            <div className="space-y-2 pt-1">
              {unmatchedEnums.map((item, idx) => {
                const currentVal = valueMappings[item.fieldName]?.[item.rawValue] || '';
                return (
                  <div
                    key={idx}
                    className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-2.5 bg-white border border-amber-200 rounded-lg text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-500 font-sans text-[11px]">
                        {item.fieldLabel}:
                      </span>
                      <span className="px-2 py-0.5 bg-rose-50 text-rose-700 border border-rose-200 rounded font-mono font-bold text-[11px]">
                        "{item.rawValue}"
                      </span>
                      <span className="text-[10px] text-slate-400 font-medium">
                        ({item.count} {item.count === 1 ? 'row' : 'rows'})
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <ArrowRight className="w-3.5 h-3.5 text-slate-400 hidden sm:block" />
                      <select
                        value={currentVal}
                        onChange={(e) =>
                          handleMappingChange(item.fieldName, item.rawValue, e.target.value)
                        }
                        className="px-2.5 py-1 text-xs border border-slate-300 rounded-md bg-white text-slate-800 font-medium focus:outline-none focus:ring-1 focus:ring-aura-cyan"
                      >
                        <option value="">-- Choose destination option --</option>
                        {item.allowedOptions.map((opt) => (
                          <option key={opt} value={opt}>
                            {opt}
                          </option>
                        ))}
                        <option value="__SKIP__">⛔ Skip rows with this value</option>
                      </select>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1 border-t border-amber-200/60">
              <span>
                Need separate stages? You can configure new stages in Workflow Settings.
              </span>
            </div>
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
                <span className="text-slate-400">• {allDataRows.length} total rows</span>
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
                <div className="flex items-center justify-between mb-1.5">
                  <p className="text-[11px] font-bold text-slate-500 uppercase">
                    Data Preview (First {previewRows.length} rows):
                  </p>
                  {resolution?.isValid && (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                      <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                      All {headers.length} columns resolved
                    </span>
                  )}
                </div>
                <div className="max-h-52 overflow-auto border border-slate-200 rounded-lg text-xs">
                  <table className="w-full text-left">
                    <thead className="bg-slate-50 text-[10px] uppercase font-bold text-slate-600 sticky top-0 border-b border-slate-200">
                      <tr>
                        {headers.map((h, i) => {
                          const resItem = resolution?.resolutions[i];
                          const isMatched = resItem?.status === 'matched';
                          const isUnknown = resItem?.status === 'unknown';
                          const isDup = resItem?.status === 'duplicate';
                          const isAmb = resItem?.status === 'ambiguous';

                          return (
                            <th
                              key={i}
                              className={`py-2 px-3 border-r last:border-r-0 border-slate-200 ${isUnknown || isDup || isAmb ? 'bg-rose-50/70' : ''
                                }`}
                            >
                              <div className="font-mono text-slate-800 text-[11px]">{h}</div>
                              {isMatched && (
                                <div className="text-[9px] text-emerald-700 font-sans font-semibold normal-case mt-0.5 flex items-center gap-0.5">
                                  <span>✓</span>
                                  <span>{resItem.displayLabel}</span>
                                  <span className="text-slate-400 font-mono">({resItem.canonicalName})</span>
                                </div>
                              )}
                              {isUnknown && (
                                <div className="text-[9px] text-rose-600 font-sans font-semibold normal-case mt-0.5">
                                  ✕ Unknown column
                                </div>
                              )}
                              {isDup && (
                                <div className="text-[9px] text-amber-700 font-sans font-semibold normal-case mt-0.5">
                                  ⚠ Duplicate mapping
                                </div>
                              )}
                              {isAmb && (
                                <div className="text-[9px] text-purple-700 font-sans font-semibold normal-case mt-0.5">
                                  ⚠ Ambiguous
                                </div>
                              )}
                            </th>
                          );
                        })}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {previewRows.map((r, rIdx) => (
                        <tr key={rIdx} className="hover:bg-slate-50">
                          {r.map((cell, cIdx) => {
                            const colField = resolution?.indexMap[cIdx];
                            const mappedVal = colField ? valueMappings[colField]?.[cell] : null;

                            return (
                              <td
                                key={cIdx}
                                className="py-2 px-3 text-slate-700 border-r last:border-r-0 border-slate-100 font-mono text-[11px]"
                              >
                                {cell}
                                {mappedVal && (
                                  <span className="ml-1 text-[9px] text-emerald-600 font-sans font-bold">
                                    → {mappedVal === '__SKIP__' ? 'SKIP' : mappedVal}
                                  </span>
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Missing required fields warning */}
            {resolution?.warnings && resolution.warnings.length > 0 && (
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-800 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                <div className="space-y-0.5">
                  <p className="font-bold">Missing Required Fields Notice</p>
                  {resolution.warnings.map((w, idx) => (
                    <p key={idx}>{w}</p>
                  ))}
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
                onClick={() => handleUpload()}
                isLoading={isUploading}
                disabled={resolution ? !resolution.isValid : false}
              >
                {unmatchedEnums.length > 0 && Object.keys(valueMappings).length === 0
                  ? 'Confirm & Import Records (with unmapped rows)'
                  : 'Confirm & Import Records'}
              </Button>
            </div>
          </div>
        )}

        {/* Error Feedback */}
        {error && (
          <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-700 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
            <div>
              <p className="font-bold">Validation Issue</p>
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
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 text-xs">
                <div>
                  <span className="text-emerald-700 font-medium">Successfully Created:</span>{' '}
                  <span className="font-bold text-base text-emerald-900 block">{result.created}</span>
                </div>
                <div>
                  <span className="text-blue-700 font-medium">Preserved (Duplicates):</span>{' '}
                  <span className="font-bold text-base text-blue-900 block">{result.duplicate || 0}</span>
                </div>
                <div>
                  <span className="text-amber-700 font-medium">Skipped Rows:</span>{' '}
                  <span className="font-bold text-base text-amber-900 block">{result.skipped}</span>
                </div>
                <div>
                  <span className="text-slate-600 font-medium">Total CSV Rows:</span>{' '}
                  <span className="font-bold text-base text-slate-800 block">
                    {result.total_rows || (result.created + (result.duplicate || 0) + result.skipped)}
                  </span>
                </div>
              </div>
            </div>

            {/* Row validation errors if any */}
            {result.errors && result.errors.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-bold text-rose-700">
                    Row-Level Errors ({result.errors.length}):
                  </p>
                  {result.errors.some((e) => e.code === 'INVALID_OPTION') && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleOpenRetryMapping}
                      className="text-xs text-aura-navy border-aura-cyan hover:bg-aura-cyan/10"
                    >
                      <RefreshCw className="w-3 h-3 mr-1" />
                      Resolve Status Mappings & Retry Failed Rows ({result.skipped})
                    </Button>
                  )}
                </div>
                <div className="max-h-40 overflow-y-auto border border-rose-200 rounded-lg p-2 bg-rose-50/50 space-y-1.5 text-xs text-rose-800">
                  {result.errors.map((err, i) => (
                    <div key={i} className="flex gap-2">
                      <span className="font-mono font-bold">Row {err.row}:</span>
                      <span>
                        [{err.code}] {err.message}
                      </span>
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
