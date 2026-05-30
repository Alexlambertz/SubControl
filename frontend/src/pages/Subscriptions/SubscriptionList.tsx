/**
 * Subscription list page — shown after selecting a bucket.
 * Provides CRUD, CSV import, and duplicate detection with auto-resolve.
 */

import { useState, useMemo, useEffect } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Pencil, Upload, AlertTriangle, CopyX } from 'lucide-react'
import { subscriptionsApi } from '../../api/subscriptions'
import { bucketsApi } from '../../api/buckets'
import { pickLoser, type ResolveStrategy } from '../../utils/duplicates'
import ProviderLogo from '../../components/ProviderLogo'
import IntervalBadge from '../../components/IntervalBadge'
import CurrencyDisplay from '../../components/CurrencyDisplay'
import ConfirmDialog from '../../components/ConfirmDialog'
import DuplicatesPanel from '../../components/DuplicatesPanel'
import SubscriptionForm from './SubscriptionForm'
import CsvImport from './CsvImport'
import type { Subscription } from '../../types'

/** localStorage key for IDs that the user has explicitly kept (non-duplicate) */
const markedKey = (bucketId: string) => `subcontrol_marked_unique_${bucketId}`

interface AutoResolveState {
  losers: Subscription[]
  strategy: ResolveStrategy
}

export default function SubscriptionList() {
  const { bucketId } = useParams<{ bucketId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const qc = useQueryClient()

  // ── UI state ──────────────────────────────────────────────────────────────
  const [showForm, setShowForm] = useState(false)
  const [editSub, setEditSub] = useState<Subscription | null>(null)
  const [deleteSub, setDeleteSub] = useState<Subscription | null>(null)
  const [showImport, setShowImport] = useState(false)
  const [showDuplicates, setShowDuplicates] = useState(false)

  /** Pending batch auto-resolve — set to trigger the batch confirm dialog. */
  const [autoResolve, setAutoResolve] = useState<AutoResolveState | null>(null)
  const [isResolving, setIsResolving] = useState(false)

  /** IDs the user has marked as intentional (excluded from duplicate grouping) */
  const [markedUniqueIds, setMarkedUniqueIds] = useState<Set<string>>(() => {
    if (!bucketId) return new Set()
    try {
      const raw = localStorage.getItem(markedKey(bucketId))
      return raw ? new Set(JSON.parse(raw) as string[]) : new Set()
    } catch {
      return new Set()
    }
  })

  // Persist marked IDs to localStorage whenever they change
  useEffect(() => {
    if (!bucketId) return
    try {
      localStorage.setItem(markedKey(bucketId), JSON.stringify([...markedUniqueIds]))
    } catch {
      // ignore (private browsing etc.)
    }
  }, [markedUniqueIds, bucketId])

  // ── Data fetching ─────────────────────────────────────────────────────────
  const { data: bucket } = useQuery({
    queryKey: ['bucket', bucketId],
    queryFn: () => bucketsApi.get(bucketId!),
    enabled: !!bucketId,
  })

  const { data: subs = [], isLoading } = useQuery({
    queryKey: ['subscriptions', bucketId],
    queryFn: () => subscriptionsApi.list(bucketId!),
    enabled: !!bucketId,
  })

  // When navigated from the search page with a specific subscription ID,
  // open its edit modal once the list has loaded.
  useEffect(() => {
    const targetId = (location.state as { openSubscriptionId?: string } | null)?.openSubscriptionId
    if (!targetId || isLoading || subs.length === 0) return
    const match = subs.find((s) => s.id === targetId)
    if (match) {
      setEditSub(match)
      // Clear the state so back-navigation doesn't reopen the modal
      navigate(location.pathname, { replace: true, state: null })
    }
  }, [location.state, subs, isLoading]) // eslint-disable-line react-hooks/exhaustive-deps

  const deleteMut = useMutation({
    mutationFn: (id: string) => subscriptionsApi.delete(bucketId!, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subscriptions', bucketId] })
      setDeleteSub(null)
    },
  })

  // ── Duplicate detection ───────────────────────────────────────────────────
  const duplicateGroups = useMemo(() => {
    const eligible = subs.filter((s) => !markedUniqueIds.has(s.id))
    const byName = new Map<string, Subscription[]>()
    for (const sub of eligible) {
      const key = sub.name.toLowerCase().trim()
      const group = byName.get(key) ?? []
      group.push(sub)
      byName.set(key, group)
    }
    return [...byName.entries()]
      .filter(([, g]) => g.length > 1)
      .map(([key, subscriptions]) => ({ key, subscriptions }))
  }, [subs, markedUniqueIds])

  // Auto-close the panel when all groups are resolved
  useEffect(() => {
    if (duplicateGroups.length === 0) setShowDuplicates(false)
  }, [duplicateGroups.length])

  // ── Duplicate action handlers ─────────────────────────────────────────────
  const handleMarkUnique = (id: string) =>
    setMarkedUniqueIds((prev) => new Set([...prev, id]))

  /** Per-group auto-resolve: hand the loser to the existing single-confirm flow. */
  const handleAutoResolveGroup = (loser: Subscription) => setDeleteSub(loser)

  /** Global auto-resolve: compute all losers from 2-item groups, show batch confirm. */
  const handleAutoResolveAll = (strategy: ResolveStrategy) => {
    const twoItemGroups = duplicateGroups.filter((g) => g.subscriptions.length === 2)
    const losers = twoItemGroups.map((g) =>
      pickLoser(g.subscriptions as [Subscription, Subscription], strategy),
    )
    if (losers.length > 0) setAutoResolve({ losers, strategy })
  }

  /** Execute the batch delete after the user confirms. */
  const handleConfirmAutoResolve = async () => {
    if (!autoResolve || !bucketId) return
    const { losers } = autoResolve
    setAutoResolve(null)         // close the confirm dialog immediately
    setIsResolving(true)
    try {
      for (const sub of losers) {
        await subscriptionsApi.delete(bucketId, sub.id)
      }
    } finally {
      qc.invalidateQueries({ queryKey: ['subscriptions', bucketId] })
      setIsResolving(false)
    }
  }

  if (!bucketId) return null

  const hasDuplicates = duplicateGroups.length > 0

  return (
    <div className="space-y-5">
      {/* ── Breadcrumb + action bar ────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <button
            onClick={() => navigate('/buckets')}
            className="hover:text-blue-600 transition"
          >
            Buckets
          </button>
          <span>/</span>
          <span className="font-medium text-gray-800">{bucket?.name ?? '…'}</span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Duplicate indicator */}
          {hasDuplicates && (
            <button
              onClick={() => setShowDuplicates((v) => !v)}
              className={`flex items-center gap-1.5 text-sm px-3 py-2 rounded-lg border transition ${
                showDuplicates
                  ? 'bg-amber-100 border-amber-300 text-amber-800'
                  : 'bg-amber-50 border-amber-200 text-amber-700 hover:bg-amber-100'
              }`}
            >
              <AlertTriangle size={14} />
              {duplicateGroups.length} duplicate group{duplicateGroups.length !== 1 ? 's' : ''}
              <span className="text-xs opacity-60">{showDuplicates ? '▲' : '▼'}</span>
            </button>
          )}

          <button
            onClick={() => setShowImport(true)}
            className="flex items-center gap-2 border border-gray-200 text-gray-700 text-sm px-3 py-2 rounded-lg hover:bg-gray-50 transition"
          >
            <Upload size={15} />
            Import CSV
          </button>
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-2 bg-blue-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-blue-700 transition"
          >
            <Plus size={15} />
            Add subscription
          </button>
        </div>
      </div>

      {/* ── Duplicates panel ──────────────────────────────────────────────── */}
      {showDuplicates && hasDuplicates && (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <CopyX size={16} className="text-amber-600" />
              <span className="text-sm font-semibold text-amber-800">
                Duplicate subscriptions
              </span>
              {isResolving && (
                <span className="text-xs text-amber-600 animate-pulse">Resolving…</span>
              )}
            </div>
            {markedUniqueIds.size > 0 && (
              <button
                onClick={() => setMarkedUniqueIds(new Set())}
                className="text-xs text-amber-600 hover:text-amber-800 underline underline-offset-2 transition"
              >
                Reset marks ({markedUniqueIds.size})
              </button>
            )}
          </div>

          <DuplicatesPanel
            groups={duplicateGroups}
            onMarkUnique={handleMarkUnique}
            onAutoResolveGroup={handleAutoResolveGroup}
            onAutoResolveAll={handleAutoResolveAll}
            onDelete={(sub) => setDeleteSub(sub)}
          />
        </div>
      )}

      {/* ── Subscription list ─────────────────────────────────────────────── */}
      {isLoading ? (
        <div className="text-gray-400 text-center py-12">Loading…</div>
      ) : subs.length === 0 ? (
        <div className="bg-white rounded-2xl border border-gray-200 py-12 text-center">
          <p className="text-gray-400 text-sm">No subscriptions in this bucket yet.</p>
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-gray-200 divide-y divide-gray-100">
          {subs.map((sub) => {
            const isDuplicateCandidate = duplicateGroups.some((g) =>
              g.subscriptions.some((s) => s.id === sub.id),
            )
            const isMarkedUnique = markedUniqueIds.has(sub.id)

            return (
              <div
                key={sub.id}
                onClick={() => setEditSub(sub)}
                className={`flex items-center gap-4 px-5 py-4 hover:bg-gray-50 transition cursor-pointer ${
                  isDuplicateCandidate ? 'border-l-2 border-l-amber-300' : ''
                }`}
              >
                <ProviderLogo name={sub.provider_name} imageUrl={sub.image_url} size={40} />

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="font-medium text-gray-800 truncate">{sub.name}</p>
                    {isMarkedUnique && (
                      <span
                        className="text-xs text-emerald-600 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded-full shrink-0"
                        title="Marked as intentional — excluded from duplicate detection"
                      >
                        ✓ kept
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-2 mt-0.5">
                    {sub.provider_name && (
                      <span className="text-xs text-gray-500">{sub.provider_name}</span>
                    )}
                    {sub.category_name && (
                      <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                        {sub.category_name}
                      </span>
                    )}
                    {sub.end_date && (() => {
                      const expired = sub.end_date <= new Date().toISOString().slice(0, 10)
                      return (
                        <span className={`text-xs px-2 py-0.5 rounded-full border ${
                          expired
                            ? 'bg-amber-50 text-amber-600 border-amber-200'
                            : 'bg-blue-50 text-blue-600 border-blue-200'
                        }`}>
                          {expired ? 'Ended' : 'Ends'} {sub.end_date}
                        </span>
                      )
                    })()}
                  </div>
                </div>

                <IntervalBadge interval={sub.recurring_interval} />

                <div className="text-right shrink-0">
                  <CurrencyDisplay
                    amount={sub.amount}
                    currency={sub.currency}
                    className="font-semibold text-gray-800"
                  />
                  <p className="text-xs text-gray-400 mt-0.5">{sub.recurring_date ?? '—'}</p>
                </div>

                <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={() => setEditSub(sub)}
                    className="p-1.5 text-gray-400 hover:text-blue-600 rounded transition"
                    title="Edit"
                  >
                    <Pencil size={15} />
                  </button>
                  <button
                    onClick={() => setDeleteSub(sub)}
                    className="p-1.5 text-gray-400 hover:text-red-600 rounded transition"
                    title="Delete"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* ── Modals ────────────────────────────────────────────────────────── */}
      {(showForm || editSub) && (
        <SubscriptionForm
          bucketId={bucketId}
          subscription={editSub ?? undefined}
          onClose={() => { setShowForm(false); setEditSub(null) }}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ['subscriptions', bucketId] })
            setShowForm(false)
            setEditSub(null)
          }}
        />
      )}

      {showImport && (
        <CsvImport
          bucketId={bucketId}
          bucketName={bucket?.name ?? ''}
          onClose={() => setShowImport(false)}
          onImported={() => {
            qc.invalidateQueries({ queryKey: ['subscriptions', bucketId] })
            setShowImport(false)
          }}
        />
      )}

      {/* Single-entry delete confirm (also used for per-group auto-resolve) */}
      {deleteSub && (
        <ConfirmDialog
          title="Delete subscription"
          message={`Delete "${deleteSub.name}"? This cannot be undone.`}
          confirmLabel="Delete"
          onConfirm={() => deleteMut.mutate(deleteSub.id)}
          onCancel={() => setDeleteSub(null)}
        />
      )}

      {/* Batch auto-resolve confirm */}
      {autoResolve && (
        <ConfirmDialog
          title="Auto-resolve duplicates"
          message={`Delete ${autoResolve.losers.length} subscription${
            autoResolve.losers.length !== 1 ? 's' : ''
          }, keeping the ${
            autoResolve.strategy === 'newer'
              ? 'most recently created'
              : 'highest-priced'
          } entry in each pair? This cannot be undone.`}
          confirmLabel={`Delete ${autoResolve.losers.length}`}
          onConfirm={handleConfirmAutoResolve}
          onCancel={() => setAutoResolve(null)}
        />
      )}
    </div>
  )
}
