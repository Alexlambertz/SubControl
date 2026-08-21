/**
 * Insurance list page — shown after selecting a bucket's "Insurances" tab.
 * Provides CRUD, mirroring SubscriptionList's structure (without duplicate
 * detection, which doesn't apply here).
 */

import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Pencil, Shield, Paperclip } from 'lucide-react'
import { insurancesApi } from '../../api/insurances'
import { bucketsApi } from '../../api/buckets'
import IntervalBadge from '../../components/IntervalBadge'
import CurrencyDisplay from '../../components/CurrencyDisplay'
import ConfirmDialog from '../../components/ConfirmDialog'
import BucketTabs from '../../components/BucketTabs'
import InsuranceForm from './InsuranceForm'
import type { Insurance } from '../../types'

export default function InsuranceList() {
  const { bucketId } = useParams<{ bucketId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [showForm, setShowForm] = useState(false)
  const [editInsurance, setEditInsurance] = useState<Insurance | null>(null)
  const [deleteInsurance, setDeleteInsurance] = useState<Insurance | null>(null)

  const { data: bucket } = useQuery({
    queryKey: ['bucket', bucketId],
    queryFn: () => bucketsApi.get(bucketId!),
    enabled: !!bucketId,
  })

  const { data: insurances = [], isLoading } = useQuery({
    queryKey: ['insurances', bucketId],
    queryFn: () => insurancesApi.list(bucketId!),
    enabled: !!bucketId,
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => insurancesApi.delete(bucketId!, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['insurances', bucketId] })
      setDeleteInsurance(null)
    },
  })

  const closeForm = () => {
    qc.invalidateQueries({ queryKey: ['insurances', bucketId] })
    setShowForm(false)
    setEditInsurance(null)
  }

  if (!bucketId) return null

  return (
    <div className="space-y-5">
      {/* ── Breadcrumb + action bar ────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <button onClick={() => navigate('/buckets')} className="hover:text-blue-600 transition">
            Buckets
          </button>
          <span>/</span>
          <span className="font-medium text-gray-800">{bucket?.name ?? '…'}</span>
        </div>

        <BucketTabs bucketId={bucketId} />

        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-2 bg-blue-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-blue-700 transition"
          >
            <Plus size={15} />
            Add insurance
          </button>
        </div>
      </div>

      {/* ── Insurance list ─────────────────────────────────────────────────── */}
      {isLoading ? (
        <div className="text-gray-400 text-center py-12">Loading…</div>
      ) : insurances.length === 0 ? (
        <div className="bg-white rounded-2xl border border-gray-200 py-12 text-center">
          <p className="text-gray-400 text-sm">No insurances in this bucket yet.</p>
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-gray-200 divide-y divide-gray-100">
          {insurances.map((ins) => {
            const endDateExpired =
              ins.end_date != null && ins.end_date <= new Date().toISOString().slice(0, 10)

            return (
              <div
                key={ins.id}
                onClick={() => setEditInsurance(ins)}
                className="flex items-start gap-3 px-4 py-3 hover:bg-gray-50 transition cursor-pointer"
              >
                {/* Icon */}
                <div className="shrink-0 mt-0.5 w-[38px] h-[38px] rounded-lg bg-blue-50 flex items-center justify-center">
                  <Shield size={18} className="text-blue-500" />
                </div>

                <div className="flex-1 min-w-0">
                  {/* Row 1 — Name + Amount */}
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-medium text-gray-800 truncate leading-snug">{ins.name}</p>
                    <div className="text-right shrink-0 ml-2">
                      <CurrencyDisplay
                        amount={ins.amount}
                        currency={ins.currency}
                        className="font-semibold text-gray-800 text-sm"
                      />
                      <p className="text-xs text-gray-400 mt-0.5 whitespace-nowrap">
                        {ins.recurring_date ?? '—'}
                      </p>
                    </div>
                  </div>

                  {/* Row 2 — Meta badges + action buttons */}
                  <div
                    className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 mt-1.5"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-xs text-gray-500">{ins.insurer}</span>
                      {ins.category_name && (
                        <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                          {ins.category_name}
                        </span>
                      )}
                      {ins.end_date && (
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full border ${
                            endDateExpired
                              ? 'bg-amber-50 text-amber-600 border-amber-200'
                              : 'bg-blue-50 text-blue-600 border-blue-200'
                          }`}
                        >
                          {endDateExpired ? 'Ended' : 'Ends'} {ins.end_date}
                        </span>
                      )}
                      {ins.attachments.length > 0 && (
                        <span className="inline-flex items-center gap-1 text-xs text-gray-500">
                          <Paperclip size={11} />
                          {ins.attachments.length}
                        </span>
                      )}
                      <IntervalBadge interval={ins.recurring_interval} />
                    </div>

                    <div className="flex items-center gap-0.5 shrink-0">
                      <button
                        onClick={(e) => { e.stopPropagation(); setEditInsurance(ins) }}
                        className="p-1.5 text-gray-400 hover:text-blue-600 rounded transition"
                        title="Edit"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); setDeleteInsurance(ins) }}
                        className="p-1.5 text-gray-400 hover:text-red-600 rounded transition"
                        title="Delete"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* ── Modals ────────────────────────────────────────────────────────── */}
      {(showForm || editInsurance) && (
        <InsuranceForm
          bucketId={bucketId}
          insurance={editInsurance ?? undefined}
          onClose={closeForm}
          onSaved={closeForm}
        />
      )}

      {deleteInsurance && (
        <ConfirmDialog
          title="Delete insurance"
          message={`Delete "${deleteInsurance.name}"? This also removes its attachments. This cannot be undone.`}
          confirmLabel="Delete"
          onConfirm={() => deleteMut.mutate(deleteInsurance.id)}
          onCancel={() => setDeleteInsurance(null)}
        />
      )}
    </div>
  )
}
