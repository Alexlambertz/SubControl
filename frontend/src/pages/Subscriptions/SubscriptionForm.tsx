/**
 * Modal form for creating and editing subscriptions, including an
 * attachments panel (e.g. a signup confirmation or renewal letter) once
 * the subscription has been saved.
 */

import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Paperclip, Upload, Download, Trash2, FileText } from 'lucide-react'
import { subscriptionsApi } from '../../api/subscriptions'
import { ownersApi } from '../../api/owners'
import { get } from '../../api/client'
import DateField from '../../components/DateField'
import FieldUpdateReview from '../../components/FieldUpdateReview'
import ChangeHistory from '../../components/ChangeHistory'
import type { Attachment, Subscription, RecurringInterval } from '../../types'
import { INTERVAL_LABELS } from '../../types'

// Lazy-load providers/categories lists — must use authenticated client
async function fetchProviders(): Promise<{ id: number; name: string }[]> {
  const data = await get<{ id: number; name: string }[] | unknown>('/providers')
  return Array.isArray(data) ? data : []
}
async function fetchCategories(): Promise<{ id: number; name: string }[]> {
  const data = await get<{ id: number; name: string }[] | unknown>('/categories')
  return Array.isArray(data) ? data : []
}

const INPUT_CLS =
  'w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 outline-none'

const FIELD_LABELS: Record<string, string> = {
  name: 'Name',
  provider_name: 'Provider',
  recurring_interval: 'Billing interval',
  recurring_date: 'Last payment date',
  end_date: 'End date',
  amount: 'Amount',
  currency: 'Currency',
  category_name: 'Category',
  owner_name: 'Owner',
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

interface Props {
  bucketId: string
  subscription?: Subscription
  onClose: () => void
  onSaved: () => void
}

export default function SubscriptionForm({
  bucketId,
  subscription,
  onClose,
  onSaved,
}: Props) {
  const isEdit = !!subscription
  const qc = useQueryClient()

  const [name, setName] = useState(subscription?.name ?? '')
  const [providerName, setProviderName] = useState(subscription?.provider_name ?? '')
  const [interval, setInterval] = useState<RecurringInterval>(
    subscription?.recurring_interval ?? 'monthly'
  )
  const [recurringDate, setRecurringDate] = useState(
    subscription?.recurring_date ?? ''
  )
  const [endDate, setEndDate] = useState(subscription?.end_date ?? '')
  const [amount, setAmount] = useState(String(subscription?.amount ?? ''))
  const [currency, setCurrency] = useState(subscription?.currency ?? 'EUR')
  const [categoryName, setCategoryName] = useState(
    subscription?.category_name ?? ''
  )
  const [ownerName, setOwnerName] = useState(
    subscription?.owner_name ?? ''
  )
  const [error, setError] = useState('')

  // Attachments — only manageable once the subscription exists (edit mode);
  // a brand-new subscription is saved (and the modal closes) before it has
  // an id to attach files to.
  const [attachments, setAttachments] = useState<Attachment[]>(
    subscription?.attachments ?? [],
  )
  const subId = subscription?.id ?? null
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [attachError, setAttachError] = useState('')
  const [suggestedUpdates, setSuggestedUpdates] = useState<Record<string, string | number | null> | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: providers = [] } = useQuery({
    queryKey: ['providers'],
    queryFn: fetchProviders,
  })

  const { data: categories = [] } = useQuery({
    queryKey: ['categories'],
    queryFn: fetchCategories,
  })

  const { data: owners = [] } = useQuery({
    queryKey: ['owners', bucketId],
    queryFn: () => ownersApi.list(bucketId),
  })

  const saveMut = useMutation({
    mutationFn: () => {
      const data = {
        name,
        provider_name: providerName,
        recurring_interval: interval,
        // Explicit null (not undefined) so a cleared field is actually
        // cleared on update — omitting the key would be indistinguishable
        // from "leave this field alone" server-side.
        recurring_date: recurringDate || null,
        end_date: endDate || null,
        amount: parseFloat(amount),
        currency,
        category_name: categoryName || null,
        owner_name: ownerName || null,
      }
      return isEdit
        ? subscriptionsApi.update(bucketId, subscription!.id, data)
        : subscriptionsApi.create(bucketId, data)
    },
    onSuccess: onSaved,
    onError: (e: Error) => setError(e.message),
  })

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0 || !subId) return
    setAttachError('')
    setUploading(true)
    try {
      for (const file of Array.from(files)) {
        const result = await subscriptionsApi.uploadAttachment(bucketId, subId, file)
        setAttachments((prev) => [...prev, result.attachment])
        // Last upload's suggestions win if multiple files are dropped at once.
        setSuggestedUpdates(
          Object.keys(result.suggested_updates).length > 0 ? result.suggested_updates : null,
        )
      }
      qc.invalidateQueries({ queryKey: ['subscriptions', bucketId] })
    } catch (e) {
      setAttachError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const handleDeleteAttachment = async (attachmentId: string) => {
    if (!subId) return
    await subscriptionsApi.deleteAttachment(bucketId, subId, attachmentId)
    setAttachments((prev) => prev.filter((a) => a.id !== attachmentId))
    qc.invalidateQueries({ queryKey: ['subscriptions', bucketId] })
  }

  const currentFieldValues: Record<string, unknown> = {
    name, provider_name: providerName, recurring_interval: interval,
    recurring_date: recurringDate, end_date: endDate, amount, currency,
    category_name: categoryName, owner_name: ownerName,
  }

  const handleApplyUpdates = async (selected: Record<string, string | number | null>) => {
    if (!subId) return
    const updated = await subscriptionsApi.update(bucketId, subId, selected)
    if ('name' in selected) setName(updated.name)
    if ('provider_name' in selected) setProviderName(updated.provider_name ?? '')
    if ('recurring_interval' in selected) setInterval(updated.recurring_interval)
    if ('recurring_date' in selected) setRecurringDate(updated.recurring_date ?? '')
    if ('end_date' in selected) setEndDate(updated.end_date ?? '')
    if ('amount' in selected) setAmount(String(updated.amount))
    if ('currency' in selected) setCurrency(updated.currency)
    if ('category_name' in selected) setCategoryName(updated.category_name ?? '')
    if ('owner_name' in selected) setOwnerName(updated.owner_name ?? '')
    setSuggestedUpdates(null)
    qc.invalidateQueries({ queryKey: ['subscriptions', bucketId] })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-lg mx-4 p-6 overflow-y-auto max-h-[90vh]">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-gray-900">
            {isEdit ? 'Edit subscription' : 'Add subscription'}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition"
          >
            <X size={20} />
          </button>
        </div>

        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            if (!name.trim()) {
              setError('Name is required')
              return
            }
            saveMut.mutate()
          }}
        >
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Name *
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={INPUT_CLS}
              placeholder="e.g. Netflix Premium"
            />
          </div>

          {/* Provider */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Provider *
            </label>
            <input
              list="providers-list"
              value={providerName}
              onChange={(e) => setProviderName(e.target.value)}
              className={INPUT_CLS}
              placeholder="e.g. Netflix"
            />
            <datalist id="providers-list">
              {providers.map((p) => (
                <option key={p.id} value={p.name} />
              ))}
            </datalist>
          </div>

          {/* Billing interval */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Billing interval *
            </label>
            <select
              value={interval}
              onChange={(e) => setInterval(e.target.value as RecurringInterval)}
              className={INPUT_CLS}
            >
              {(Object.entries(INTERVAL_LABELS) as [RecurringInterval, string][]).map(
                ([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                )
              )}
            </select>
          </div>

          {/* Last payment date + End date row */}
          <div className="grid grid-cols-2 gap-3">
            <DateField
              label="Last payment date"
              value={recurringDate}
              onChange={setRecurringDate}
            />
            <DateField
              label={
                <>
                  End date{' '}
                  <span className="text-gray-400 font-normal">(optional)</span>
                </>
              }
              value={endDate}
              onChange={setEndDate}
            />
          </div>

          {/* Amount + Currency row */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Amount *
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className={INPUT_CLS}
                placeholder="9.99"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Currency
              </label>
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
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Category
            </label>
            <div className="relative">
              <input
                list="categories-list"
                value={categoryName}
                onChange={(e) => setCategoryName(e.target.value)}
                className={INPUT_CLS}
                placeholder="e.g. Streaming"
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
            <datalist id="categories-list">
              {categories.map((c) => (
                <option key={c.id} value={c.name} />
              ))}
            </datalist>
          </div>

          {/* Owner */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Owner
            </label>
            <div className="relative">
              <input
                list="owners-list"
                value={ownerName}
                onChange={(e) => setOwnerName(e.target.value)}
                className={INPUT_CLS}
                placeholder="e.g. Alex"
              />
              {ownerName && (
                <button
                  type="button"
                  onClick={() => setOwnerName('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-gray-400 hover:text-gray-600 transition"
                  title="Clear owner"
                >
                  <X size={14} />
                </button>
              )}
            </div>
            <datalist id="owners-list">
              {owners.map((o) => (
                <option key={o.id} value={o.name} />
              ))}
            </datalist>
          </div>

          {error && (
            <p className="text-sm text-red-500">{error}</p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saveMut.isPending}
              className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {saveMut.isPending ? 'Saving…' : isEdit ? 'Save changes' : 'Add'}
            </button>
          </div>
        </form>

        {/* ── Attachments ─────────────────────────────────────────────────── */}
        <div className="mt-6 pt-5 border-t border-gray-100">
          <div className="flex items-center gap-2 mb-3">
            <Paperclip size={15} className="text-gray-400" />
            <h3 className="text-sm font-semibold text-gray-700">
              Documents
            </h3>
          </div>

          {!subId ? (
            <p className="text-xs text-gray-400">
              Save the subscription first, then edit it again to attach documents.
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
                          subscriptionsApi.downloadAttachment(
                            bucketId, subId, a.id, a.filename,
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

              {suggestedUpdates && (
                <FieldUpdateReview
                  updates={suggestedUpdates}
                  currentValues={currentFieldValues}
                  fieldLabels={FIELD_LABELS}
                  onApply={handleApplyUpdates}
                  onDismiss={() => setSuggestedUpdates(null)}
                />
              )}
            </div>
          )}
        </div>

        {/* ── Change history ──────────────────────────────────────────────── */}
        {isEdit && subId && (
          <ChangeHistory
            queryKey={['subscription-history', bucketId, subId]}
            queryFn={() => subscriptionsApi.getHistory(bucketId, subId)}
            fieldLabels={FIELD_LABELS}
          />
        )}
      </div>
    </div>
  )
}
