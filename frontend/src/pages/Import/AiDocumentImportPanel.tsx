/**
 * "AI Document Import" wizard — upload a policy PDF or a photo/screenshot,
 * let the AI propose subscription/insurance records extracted from it, then
 * let the user review/edit and selectively create them. Nothing is created
 * until the user explicitly clicks "Create selected". When a proposed
 * insurance is confirmed, the original uploaded file is automatically
 * attached to it as the policy document.
 */

import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Upload, FileText, CheckCircle, AlertCircle, X, Plus } from 'lucide-react'
import { bucketsApi } from '../../api/buckets'
import { subscriptionsApi } from '../../api/subscriptions'
import { insurancesApi } from '../../api/insurances'
import { aiImportApi } from '../../api/aiImport'
import DateField from '../../components/DateField'
import { INTERVAL_LABELS } from '../../types'
import type { ExtractedRecord, ExtractedRecordFields, RecurringInterval } from '../../types'

interface Row {
  clientId: string
  type: ExtractedRecord['type']
  confidence: ExtractedRecord['confidence']
  selected: boolean
  fields: ExtractedRecordFields
}

const INPUT_CLS =
  'w-full border border-gray-200 rounded-lg px-2.5 py-1.5 text-xs text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 outline-none'

function toRow(r: ExtractedRecord, i: number): Row {
  return {
    clientId: `${i}-${r.fields.name ?? 'record'}`,
    type: r.type,
    confidence: r.confidence,
    selected: r.confidence !== 'low',
    fields: { currency: 'EUR', ...r.fields },
  }
}

export default function AiDocumentImportPanel() {
  const qc = useQueryClient()
  const [bucketId, setBucketId] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [rows, setRows] = useState<Row[] | null>(null)
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)
  const [result, setResult] = useState<{ created: number; failed: string[] } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: buckets = [] } = useQuery({
    queryKey: ['buckets'],
    queryFn: bucketsApi.list,
  })

  const handleFile = async (f: File) => {
    if (!bucketId) { setError('Please select a bucket first.'); return }
    setFile(f)
    setError('')
    setResult(null)
    setRows(null)
    setExtracting(true)
    try {
      const records = await aiImportApi.extractFromDocument(bucketId, f)
      setRows(records.map(toRow))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Extraction failed')
    } finally {
      setExtracting(false)
    }
  }

  const updateRow = (id: string, patch: Partial<Row>) => {
    setRows((prev) => prev?.map((r) => (r.clientId === id ? { ...r, ...patch } : r)) ?? null)
  }
  const updateFields = (id: string, patch: Partial<ExtractedRecordFields>) => {
    setRows(
      (prev) =>
        prev?.map((r) => (r.clientId === id ? { ...r, fields: { ...r.fields, ...patch } } : r)) ?? null,
    )
  }

  const selectedRows = rows?.filter((r) => r.selected) ?? []

  const handleCreate = async () => {
    if (!bucketId || selectedRows.length === 0) return
    setCreating(true)
    const failed: string[] = []
    let created = 0
    for (const row of selectedRows) {
      const f = row.fields
      try {
        if (row.type === 'subscription') {
          await subscriptionsApi.create(bucketId, {
            name: f.name ?? 'Untitled',
            provider_name: f.provider_name || f.name || 'Unknown',
            recurring_interval: f.recurring_interval || 'monthly',
            recurring_date: f.recurring_date || undefined,
            end_date: f.end_date || undefined,
            amount: f.amount ?? 0,
            currency: f.currency || 'EUR',
            category_name: f.category_name || undefined,
          })
        } else {
          const insurance = await insurancesApi.create(bucketId, {
            name: f.name ?? 'Untitled',
            insurer: f.insurer || f.provider_name || f.name || 'Unknown',
            policy_number: f.policy_number || undefined,
            recurring_interval: f.recurring_interval || 'monthly',
            recurring_date: f.recurring_date || undefined,
            end_date: f.end_date || undefined,
            amount: f.amount ?? 0,
            currency: f.currency || 'EUR',
            category_name: f.category_name || undefined,
            notes: f.notes || undefined,
          })
          if (file) {
            await insurancesApi.uploadAttachment(bucketId, insurance.id, file)
          }
        }
        created++
      } catch (e) {
        failed.push(`${f.name ?? 'record'}: ${e instanceof Error ? e.message : 'failed'}`)
      }
    }
    setCreating(false)
    setResult({ created, failed })
    setRows((prev) => prev?.filter((r) => !selectedRows.some((s) => s.clientId === r.clientId)) ?? null)
    qc.invalidateQueries({ queryKey: ['subscriptions', bucketId] })
    qc.invalidateQueries({ queryKey: ['insurances', bucketId] })
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <p className="text-sm text-gray-500">
        Upload a policy document, invoice, or screenshot of a confirmation
        email. AI extracts the billing details and proposes a subscription or
        insurance record — review and edit everything below, then confirm
        which ones to create.
      </p>

      <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Bucket <span className="text-red-500">*</span>
          </label>
          <select
            value={bucketId}
            onChange={(e) => { setBucketId(e.target.value); setRows(null); setResult(null) }}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none bg-white"
          >
            <option value="">Select a bucket…</option>
            {buckets.map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>
        </div>

        <div
          className={`border-2 border-dashed rounded-xl p-8 text-center transition ${
            bucketId
              ? dragging ? 'border-blue-400 bg-blue-50 cursor-pointer' : 'border-gray-200 hover:border-blue-300 cursor-pointer'
              : 'border-gray-100 opacity-50 cursor-not-allowed'
          }`}
          onDragOver={(e) => { if (!bucketId) return; e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault(); setDragging(false)
            if (!bucketId) return
            const f = e.dataTransfer.files[0]
            if (f) handleFile(f)
          }}
          onClick={() => { if (bucketId) fileInputRef.current?.click() }}
        >
          <Upload className="mx-auto text-gray-400 mb-2" size={32} />
          <p className="text-sm text-gray-600">
            {extracting ? 'Extracting…' : (
              <>Drop a document here, or <span className="text-blue-600 font-medium">browse</span></>
            )}
          </p>
          <p className="text-xs text-gray-400 mt-1">
            PDF (text or scanned), PNG, or JPG · max 20 MB
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) handleFile(f)
              e.target.value = ''
            }}
          />
        </div>

        {file && <p className="text-xs text-gray-400 flex items-center gap-1.5"><FileText size={13} /> {file.name}</p>}
        {error && <p className="text-sm text-red-500">{error}</p>}
      </div>

      {rows && rows.length === 0 && (
        <div className="bg-white rounded-2xl border border-gray-200 py-10 text-center">
          <p className="text-gray-400 text-sm">No records could be extracted from this document.</p>
        </div>
      )}

      {rows && rows.length > 0 && (
        <div className="space-y-4">
          {rows.map((row) => (
            <div key={row.clientId} className="bg-white rounded-2xl border border-gray-200 p-4 space-y-3">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={row.selected}
                    onChange={(e) => updateRow(row.clientId, { selected: e.target.checked })}
                  />
                  <select
                    value={row.type}
                    onChange={(e) => updateRow(row.clientId, { type: e.target.value as Row['type'] })}
                    className="text-xs font-medium border border-gray-200 rounded-lg px-2 py-1 bg-white"
                  >
                    <option value="subscription">Subscription</option>
                    <option value="insurance">Insurance</option>
                  </select>
                </label>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full border ${
                    row.confidence === 'high'
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      : row.confidence === 'medium'
                        ? 'bg-amber-50 text-amber-700 border-amber-200'
                        : 'bg-gray-50 text-gray-500 border-gray-200'
                  }`}
                >
                  {row.confidence} confidence
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <input
                  value={row.fields.name ?? ''}
                  onChange={(e) => updateFields(row.clientId, { name: e.target.value })}
                  placeholder="Name"
                  className={INPUT_CLS}
                />
                <input
                  value={(row.type === 'insurance' ? row.fields.insurer : row.fields.provider_name) ?? ''}
                  onChange={(e) =>
                    updateFields(
                      row.clientId,
                      row.type === 'insurance' ? { insurer: e.target.value } : { provider_name: e.target.value },
                    )
                  }
                  placeholder={row.type === 'insurance' ? 'Insurer' : 'Provider'}
                  className={INPUT_CLS}
                />

                {row.type === 'insurance' && (
                  <input
                    value={row.fields.policy_number ?? ''}
                    onChange={(e) => updateFields(row.clientId, { policy_number: e.target.value })}
                    placeholder="Policy number"
                    className={INPUT_CLS}
                  />
                )}

                <select
                  value={(row.fields.recurring_interval as RecurringInterval) || 'monthly'}
                  onChange={(e) => updateFields(row.clientId, { recurring_interval: e.target.value })}
                  className={INPUT_CLS}
                >
                  {(Object.entries(INTERVAL_LABELS) as [RecurringInterval, string][]).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>

                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={row.fields.amount ?? ''}
                  onChange={(e) => updateFields(row.clientId, { amount: parseFloat(e.target.value) || 0 })}
                  placeholder="Amount"
                  className={INPUT_CLS}
                />
                <input
                  value={row.fields.currency ?? 'EUR'}
                  onChange={(e) => updateFields(row.clientId, { currency: e.target.value.toUpperCase() })}
                  maxLength={3}
                  placeholder="Currency"
                  className={INPUT_CLS}
                />

                <input
                  value={row.fields.category_name ?? ''}
                  onChange={(e) => updateFields(row.clientId, { category_name: e.target.value })}
                  placeholder="Category"
                  className={INPUT_CLS}
                />

                <DateField
                  label="Last payment date"
                  value={row.fields.recurring_date ?? ''}
                  onChange={(v) => updateFields(row.clientId, { recurring_date: v })}
                />
              </div>
            </div>
          ))}

          <div className="flex justify-end">
            <button
              onClick={handleCreate}
              disabled={selectedRows.length === 0 || creating}
              className="flex items-center gap-2 bg-blue-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition"
            >
              <Plus size={15} />
              {creating ? 'Creating…' : `Create ${selectedRows.length} selected`}
            </button>
          </div>
        </div>
      )}

      {result && (
        <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-3">
          <h3 className="text-sm font-semibold text-gray-800">Import result</h3>
          <div className="flex items-center gap-1.5 text-sm text-green-700">
            <CheckCircle size={16} className="text-green-500" />
            <strong>{result.created}</strong> created
          </div>
          {result.failed.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5 text-sm text-red-700">
                <AlertCircle size={16} className="text-red-500" />
                <strong>{result.failed.length}</strong> failed
              </div>
              {result.failed.map((f, i) => (
                <p key={i} className="text-xs text-red-600 pl-6">{f}</p>
              ))}
            </div>
          )}
          <button
            onClick={() => setResult(null)}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600"
          >
            <X size={12} /> Dismiss
          </button>
        </div>
      )}
    </div>
  )
}
