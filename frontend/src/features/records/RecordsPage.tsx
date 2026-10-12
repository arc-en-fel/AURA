import React, { useState, useEffect, useCallback } from 'react';
import {
  Database,
  Plus,
  FileSpreadsheet,
  Search,
  Trash2,
  Edit2,
  ChevronLeft,
  ChevronRight,
  Layers,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import { useCRM } from '@/context/CRMContext';
import { CRMRecord } from '@/types/crm';
import { api } from '@/services/api';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { TableSkeleton } from '@/components/ui/LoadingSkeleton';
import { Modal } from '@/components/ui/Modal';
import { useToast } from '@/context/ToastContext';
import { RecordFormModal } from './RecordFormModal';
import { CSVImportModal } from './CSVImportModal';
import { useNavigate } from 'react-router-dom';

export const RecordsPage: React.FC = () => {
  const { activeCRM, activeEntity, setActiveEntityByName } = useCRM();
  const { success, error: toastError } = useToast();
  const navigate = useNavigate();

  const [records, setRecords] = useState<CRMRecord[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [page, setPage] = useState<number>(0);
  const [pageSize] = useState<number>(20);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [searchTerm, setSearchTerm] = useState<string>('');

  // Modals state
  const [isFormModalOpen, setIsFormModalOpen] = useState(false);
  const [editingRecord, setEditingRecord] = useState<CRMRecord | null>(null);
  const [isCSVModalOpen, setIsCSVModalOpen] = useState(false);
  const [deletingRecord, setDeletingRecord] = useState<CRMRecord | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [viewingRecord, setViewingRecord] = useState<CRMRecord | null>(null);

  const fetchRecords = useCallback(async () => {
    if (!activeCRM || !activeEntity) return;
    setIsLoading(true);
    try {
      const res = await api.listRecords(
        activeCRM.crm_id,
        activeEntity.name,
        pageSize,
        page * pageSize
      );
      setRecords(res.items);
      setTotal(res.total);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch records';
      toastError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [activeCRM, activeEntity, page, pageSize, toastError]);

  useEffect(() => {
    fetchRecords();
  }, [fetchRecords]);

  // Reset page when switching entity
  const handleEntitySwitch = (entityName: string) => {
    setActiveEntityByName(entityName);
    setPage(0);
  };

  const handleDeleteRecord = async () => {
    if (!activeCRM || !activeEntity || !deletingRecord) return;
    setIsDeleting(true);
    try {
      await api.deleteRecord(activeCRM.crm_id, activeEntity.name, deletingRecord.id);
      success('Record soft-deleted successfully.');
      setDeletingRecord(null);
      fetchRecords();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to delete record';
      toastError(msg);
    } finally {
      setIsDeleting(false);
    }
  };

  if (!activeCRM) {
    return (
      <EmptyState
        icon={<Database className="w-6 h-6" />}
        title="No Active CRM Selected"
        description="Select or generate a CRM first to manage its dynamic records."
        actionLabel="Go to My CRMs"
        onAction={() => navigate('/crms')}
      />
    );
  }

  if (!activeEntity) {
    return (
      <EmptyState
        icon={<Layers className="w-6 h-6" />}
        title="No Entities Defined"
        description="This CRM does not have any entities configured."
        actionLabel="View CRM Details"
        onAction={() => navigate(`/crms/${activeCRM.crm_id}`)}
      />
    );
  }

  // Filter records by search term across all data values
  const filteredRecords = records.filter((r) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return Object.values(r.data).some((val) =>
      String(val || '').toLowerCase().includes(term)
    );
  });

  const renderCellContent = (value: unknown, type: string) => {
    if (value === null || value === undefined || value === '') {
      return <span className="text-slate-300">—</span>;
    }

    if (type === 'boolean') {
      return value ? (
        <CheckCircle2 className="w-4 h-4 text-emerald-500" />
      ) : (
        <XCircle className="w-4 h-4 text-slate-300" />
      );
    }

    if (type === 'email') {
      return (
        <a
          href={`mailto:${String(value)}`}
          className="text-aura-cyan hover:underline font-medium"
          onClick={(e) => e.stopPropagation()}
        >
          {String(value)}
        </a>
      );
    }

    if (type === 'phone') {
      return (
        <a
          href={`tel:${String(value)}`}
          className="text-slate-700 hover:text-aura-navy font-mono text-[11px]"
          onClick={(e) => e.stopPropagation()}
        >
          {String(value)}
        </a>
      );
    }

    if (type === 'number') {
      return <span className="font-mono text-slate-800">{Number(value).toLocaleString()}</span>;
    }

    if (type === 'select') {
      return (
        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
          {String(value)}
        </span>
      );
    }

    return <span className="truncate max-w-[200px] inline-block">{String(value)}</span>;
  };

  return (
    <div className="space-y-5">
      {/* Entity Selector Tabs & Action Row */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        {/* Dynamic Entity Tabs */}
        <div className="flex items-center gap-1.5 p-1 bg-slate-200/70 rounded-xl overflow-x-auto max-w-full">
          {activeCRM.configuration.entities.map((entity) => (
            <button
              key={entity.name}
              onClick={() => handleEntitySwitch(entity.name)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all whitespace-nowrap ${
                activeEntity.name === entity.name
                  ? 'bg-white text-aura-navy shadow-sm'
                  : 'text-slate-600 hover:text-aura-navy hover:bg-white/50'
              }`}
            >
              {entity.label}
            </button>
          ))}
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsCSVModalOpen(true)}
            leftIcon={<FileSpreadsheet className="w-4 h-4 text-emerald-600" />}
          >
            Import CSV
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              setEditingRecord(null);
              setIsFormModalOpen(true);
            }}
            leftIcon={<Plus className="w-4 h-4 text-aura-cyan" />}
          >
            New {activeEntity.label}
          </Button>
        </div>
      </div>

      {/* Search and Table Container */}
      <Card className="overflow-hidden border-slate-200 shadow-card">
        {/* Table Toolbar */}
        <div className="p-3.5 bg-slate-50/60 border-b border-slate-200 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2 flex-1 max-w-sm">
            <Search className="w-4 h-4 text-slate-400" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder={`Search in ${activeEntity.label} records...`}
              className="w-full text-xs bg-transparent outline-none placeholder-slate-400"
            />
          </div>

          <div className="text-xs text-slate-500 font-medium">
            Showing <span className="font-bold text-aura-navy">{filteredRecords.length}</span> of{' '}
            <span className="font-bold text-aura-navy">{total}</span> records
          </div>
        </div>

        {/* Dynamic Table */}
        {isLoading ? (
          <TableSkeleton rows={5} cols={activeEntity.fields.length + 1} />
        ) : filteredRecords.length === 0 ? (
          <div className="p-10 text-center space-y-3">
            <Database className="w-8 h-8 text-slate-300 mx-auto" />
            <h4 className="text-sm font-bold text-aura-navy">
              No {activeEntity.label} Records Yet
            </h4>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              Get started by adding records manually or importing a batch of records from a CSV file.
            </p>
            <div className="flex justify-center gap-2 pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsCSVModalOpen(true)}
                leftIcon={<FileSpreadsheet className="w-4 h-4" />}
              >
                Import CSV
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  setEditingRecord(null);
                  setIsFormModalOpen(true);
                }}
                leftIcon={<Plus className="w-4 h-4" />}
              >
                Add Record
              </Button>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                <tr>
                  {activeEntity.fields.map((f) => (
                    <th key={f.name} className="py-3 px-4 whitespace-nowrap">
                      {f.label}
                    </th>
                  ))}
                  <th className="py-3 px-4 whitespace-nowrap">Source</th>
                  <th className="py-3 px-4 whitespace-nowrap text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {filteredRecords.map((record) => (
                  <tr
                    key={record.id}
                    onClick={() => setViewingRecord(record)}
                    className="hover:bg-slate-50/70 transition-colors cursor-pointer group"
                  >
                    {activeEntity.fields.map((f) => (
                      <td key={f.name} className="py-3 px-4 text-aura-charcoal">
                        {renderCellContent(record.data[f.name], f.type)}
                      </td>
                    ))}

                    <td className="py-3 px-4 text-slate-400 text-[11px]">
                      {record.source || 'Manual'}
                    </td>

                    <td className="py-3 px-4 text-right whitespace-nowrap">
                      <div
                        className="flex items-center justify-end gap-1 opacity-70 group-hover:opacity-100 transition-opacity"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          onClick={() => {
                            setEditingRecord(record);
                            setIsFormModalOpen(true);
                          }}
                          className="p-1 rounded text-slate-400 hover:text-aura-cyan hover:bg-slate-100 transition-colors"
                          title="Edit Record"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => setDeletingRecord(record)}
                          className="p-1 rounded text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                          title="Delete Record"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Bar */}
        {total > pageSize && (
          <div className="p-3 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500">
            <span>
              Page {page + 1} of {Math.ceil(total / pageSize)}
            </span>
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
                leftIcon={<ChevronLeft className="w-3.5 h-3.5" />}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={(page + 1) * pageSize >= total}
                onClick={() => setPage((p) => p + 1)}
                rightIcon={<ChevronRight className="w-3.5 h-3.5" />}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Record Details Drawer / Modal */}
      {viewingRecord && (
        <Modal
          isOpen={Boolean(viewingRecord)}
          onClose={() => setViewingRecord(null)}
          title={`${activeEntity.label} Details`}
          description={`ID: ${viewingRecord.id}`}
        >
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 pb-3 border-b border-slate-100 text-xs">
              <div>
                <span className="text-[10px] text-slate-400 font-bold uppercase">Created At</span>
                <p className="font-semibold">{new Date(viewingRecord.created_at).toLocaleString()}</p>
              </div>
              <div>
                <span className="text-[10px] text-slate-400 font-bold uppercase">Source</span>
                <p className="font-semibold">{viewingRecord.source || 'Manual'}</p>
              </div>
            </div>

            <div className="space-y-3">
              {activeEntity.fields.map((f) => (
                <div key={f.name} className="p-2.5 rounded-lg bg-slate-50 text-xs">
                  <span className="text-[10px] uppercase font-bold text-slate-400">
                    {f.label} ({f.type})
                  </span>
                  <div className="mt-1 font-medium text-aura-charcoal">
                    {renderCellContent(viewingRecord.data[f.name], f.type)}
                  </div>
                </div>
              ))}
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setEditingRecord(viewingRecord);
                  setViewingRecord(null);
                  setIsFormModalOpen(true);
                }}
                leftIcon={<Edit2 className="w-3.5 h-3.5" />}
              >
                Edit Record
              </Button>
              <Button variant="primary" size="sm" onClick={() => setViewingRecord(null)}>
                Close
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Delete Confirmation Dialog */}
      {deletingRecord && (
        <Modal
          isOpen={Boolean(deletingRecord)}
          onClose={() => setDeletingRecord(null)}
          title="Confirm Record Deletion"
          description="Are you sure you want to soft-delete this record? This action will set deleted_at and preserve audit history."
        >
          <div className="flex justify-end gap-2 pt-4">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDeletingRecord(null)}
              disabled={isDeleting}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={handleDeleteRecord}
              isLoading={isDeleting}
            >
              Confirm Soft Delete
            </Button>
          </div>
        </Modal>
      )}

      {/* Create / Edit Form Modal */}
      {isFormModalOpen && (
        <RecordFormModal
          isOpen={isFormModalOpen}
          onClose={() => setIsFormModalOpen(false)}
          crmId={activeCRM.crm_id}
          entity={activeEntity}
          record={editingRecord}
          onSaved={fetchRecords}
        />
      )}

      {/* CSV Import Modal */}
      {isCSVModalOpen && (
        <CSVImportModal
          isOpen={isCSVModalOpen}
          onClose={() => setIsCSVModalOpen(false)}
          crmId={activeCRM.crm_id}
          entity={activeEntity}
          onSuccess={fetchRecords}
        />
      )}
    </div>
  );
};
