/**
 * Modal form for creating and editing insurances, including an attachments
 * panel (policy conditions documents) once the insurance has been saved.
 */

import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Paperclip, Upload, Download, Trash2, FileText } from 'lucide-react'
import { insurancesApi } from '../../api/insurances'
import { get } from '../../api/client'
import DateField from '../../components/DateField'
import type { Insurance, InsuranceAttachment, RecurringInterval } from '../../types'
import { INTERVAL_LABELS } from '../../types'

async function fetchCategories(): Promise<{ id: number; name: string }[]> {
  const data = await get<{ id: number; name: string }[] | unknown>('/categories')
  return Array.isArray(data) ? data : []
}

const INPUT_CLS =
  'w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 outline-none'

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

interface Props {
  bucketId: string
  insurance?: Insurance
  onClose: () => void
  onSaved: () => void
}

export default function InsuranceForm({ bucketId, insurance, onClose, onSaved }: Props) {
  const isEdit = !!insurance
  const qc = useQueryClient()

  const [name, setName] = useState(insurance?.name ?? '')
  const [insurer, setInsurer] = useState(insurance?.insurer ?? '')
  const [policyNumber, setPolicyNumber] = useState(insurance?.policy_number ?? '')
  const [interval, setInterval] = useState<RecurringInterval>(
    insurance?.recurring_interval ?? 'yearly',
  )
  const [recurringDate, setRecurringDate] = useState(insurance?.recurring_date ?? '')
  const [endDate, setEndDate] = useState(insurance?.end_date ?? '')
  const [amount, setAmount] = useState(String(insurance?.amount ?? ''))
  const [currency, setCurrency] = useState(insurance?.currency ?? 'EUR')
  const [categoryName, setCategoryName] = useState(insurance?.category_name ?? '')
  const [notes, setNotes] = useState(insurance?.notes ?? '')
  const [error, setError] = useState('')

  // Attachments — only manageable once the insurance exists (edit mode).
  const [attachments, setAttachments] = useState<InsuranceAttachment[]>(
    insurance?.attachments ?? [],
  )
  const [savedInsuranceId, setSavedInsuranceId] = useState<string | null>(
    insurance?.id ?? null,
  )
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [attachError, setAttachError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: categories = [] } = useQuery({
    queryKey: ['categories'],
    queryFn: fetchCategories,
  })

  const saveMut = useMutation({
    mutationFn: () => {
      const data = {
        name,
        insurer,
        policy_number: policyNumber || undefined,
        recurring_interval: interval,
        recurring_date: recurringDate || undefined,
        end_date: endDate || undefined,
        amount: parseFloat(amount),
        currency,
        category_name: categoryName || undefined,
        notes: notes || undefined,
      }
      return isEdit
        ? insurancesApi.update(bucketId, insurance!.id, data)
        : insurancesApi.create(bucketId, data)
    },
    onSuccess: (saved) => {
      // Keep the form open after saving so the attachments panel unlocks —
      // the user closes explicitly via the Done/Cancel button below.
      setSavedInsuranceId(saved.id)
      setError('')
      qc.invalidateQueries({ queryKey: ['insurances', bucketId] })
    },
    onError: (e: Error) => setError(e.message),
  })

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0 || !savedInsuranceId) return
    setAttachError('')
    setUploading(true)
    try {
      for (const file of Array.from(files)) {
        const attachment = await insurancesApi.uploadAttachment(
          bucketId,
          savedInsuranceId,
          file,
        )
        setAttachments((prev) => [...prev, attachment])
      }
      qc.invalidateQueries({ queryKey: ['insurances', bucketId] })
    } catch (e) {
      setAttachError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const handleDeleteAttachment = async (attachmentId: string) => {
    if (!savedInsuranceId) return
    await insurancesApi.deleteAttachment(bucketId, savedInsuranceId, attachmentId)
    setAttachments((prev) => prev.filter((a) => a.id !== attachmentId))
    qc.invalidateQueries({ queryKey: ['insurances', bucketId] })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-lg mx-4 p-6 overflow-y-auto max-h-[90vh]">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-gray-900">
            {isEdit ? 'Edit insurance' : 'Add insurance'}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition">
            <X size={20} />
          </button>
        </div>

        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            if (!name.trim()) { setError('Name is required'); return }
            if (!insurer.trim()) { setError('Insurer is required'); return }
            saveMut.mutate()
          }}
        >
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Name *</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={INPUT_CLS}
              placeholder="e.g. Household contents"
            />
          </div>

          {/* Insurer */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Insurer *</label>
            <input
              value={insurer}
              onChange={(e) => setInsurer(e.target.value)}
              className={INPUT_CLS}
              placeholder="e.g. Allianz"
            />
          </div>

          {/* Policy number */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Policy number
            </label>
            <input
              value={policyNumber}
              onChange={(e) => setPolicyNumber(e.target.value)}
              className={INPUT_CLS}
              placeholder="e.g. POL-123456"
            />
          </div>

          {/* Billing interval */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Premium interval *
            </label>
            <select
              value={interval}
              onChange={(e) => setInterval(e.target.value as RecurringInterval)}
              className={INPUT_CLS}
            >
              {(Object.entries(INTERVAL_LABELS) as [RecurringInterval, string][]).map(
                ([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ),
              )}
            </select>
          </div>

          {/* Last payment date + End date row */}
          <div className="grid grid-cols-2 gap-3">
            <DateField label="Last payment date" value={recurringDate} onChange={setRecurringDate} />
            <DateField
              label={<>End date <span className="text-gray-400 font-normal">(optional)</span></>}
              value={endDate}
              onChange={setEndDate}
            />
          </div>

          {/* Amount + Currency row */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Amount *</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className={INPUT_CLS}
                placeholder="120.00"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Currency</label>
              <input
                value={currency}
                onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                maxLength={3}
                className={INPUT_CLS}
                placeholder="EUR"
              />
            </div>
          </div>

          {/* Category */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
            <div className="relative">
              <input
                list="insurance-categories-list"
                value={categoryName}
                onChange={(e) => setCategoryName(e.target.value)}
                className={INPUT_CLS}
                placeholder="e.g. Health"
              />
              {categoryName && (
                <button
                  type="button"
                  onClick={() => setCategoryName('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-gray-400 hover:text-gray-600 transition"
                  title="Clear category"
                >
                  <X size={14} />
                </button>
              )}
            </div>
            <datalist id="insurance-categories-list">
              {categories.map((c) => <option key={c.id} value={c.name} />)}
            </datalist>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className={INPUT_CLS}
              rows={2}
              placeholder="Optional notes…"
            />
          </div>

          {error && <p className="text-sm text-red-500">{error}</p>}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={savedInsuranceId ? onSaved : onClose}
              className="px-4 py-2 text-sm rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50"
            >
              {savedInsuranceId ? 'Done' : 'Cancel'}
            </button>
            <button
              type="submit"
              disabled={saveMut.isPending}
              className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {saveMut.isPending ? 'Saving…' : savedInsuranceId ? 'Save changes' : 'Add insurance'}
            </button>
          </div>
        </form>

        {/* ── Attachments ─────────────────────────────────────────────────── */}
        <div className="mt-6 pt-5 border-t border-gray-100">
          <div className="flex items-center gap-2 mb-3">
            <Paperclip size={15} className="text-gray-400" />
            <h3 className="text-sm font-semibold text-gray-700">
              Policy documents
            </h3>
          </div>

          {!savedInsuranceId ? (
            <p className="text-xs text-gray-400">
              Save the insurance first to attach policy documents.
            </p>
          ) : (
            <div className="space-y-3">
              {attachments.length > 0 && (
                <ul className="divide-y divide-gray-100 border border-gray-100 rounded-lg overflow-hidden">
                  {attachments.map((a) => (
                    <li key={a.id} className="flex items-center gap-2 px-3 py-2 text-sm">
                      <FileText size={15} className="text-gray-400 shrink-0" />
                      <span className="flex-1 min-w-0 truncate text-gray-700">{a.filename}</span>
                      <span className="text-xs text-gray-400 shrink-0">{formatSize(a.size_bytes)}</span>
                      <button
                        type="button"
                        onClick={() =>
                          insurancesApi.downloadAttachment(
                            bucketId, savedInsuranceId, a.id, a.filename,
                          )
                        }
                        className="p-1 text-gray-400 hover:text-blue-600 rounded transition shrink-0"
                        title="Download"
                      >
                        <Download size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteAttachment(a.id)}
                        className="p-1 text-gray-400 hover:text-red-600 rounded transition shrink-0"
                        title="Delete"
                      >
                        <Trash2 size={14} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <div
                onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault()
                  setDragging(false)
                  handleFiles(e.dataTransfer.files)
                }}
                onClick={() => fileInputRef.current?.click()}
                className={`flex flex-col items-center justify-center gap-1.5 border-2 border-dashed rounded-lg py-5 text-center cursor-pointer transition ${
                  dragging ? 'border-blue-400 bg-blue-50' : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <Upload size={18} className="text-gray-400" />
                <p className="text-xs text-gray-500">
                  {uploading ? 'Uploading…' : 'Drop a file here, or click to browse'}
                </p>
                <p className="text-xs text-gray-400">PDF, image, or Word document · max 20 MB</p>
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  accept=".pdf,.png,.jpg,.jpeg,.doc,.docx"
                  multiple
                  onChange={(e) => handleFiles(e.target.files)}
                />
              </div>

              {attachError && <p className="text-xs text-red-500">{attachError}</p>}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
