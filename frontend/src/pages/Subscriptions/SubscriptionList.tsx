/**
 * Subscription list page — shown after selecting a bucket.
 * Provides CRUD, CSV import, and duplicate detection with auto-resolve.
 */

import { useState, useMemo, useEffect } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Pencil, Upload, AlertTriangle, CopyX, ListChecks, X, User } from 'lucide-react'
import { subscriptionsApi } from '../../api/subscriptions'
import { bucketsApi } from '../../api/buckets'
import { pickLoser, type ResolveStrategy } from '../../utils/duplicates'
import ProviderLogo from '../../components/ProviderLogo'
import IntervalBadge from '../../components/IntervalBadge'
import CurrencyDisplay from '../../components/CurrencyDisplay'
import ConfirmDialog from '../../components/ConfirmDialog'
import DuplicatesPanel from '../../components/DuplicatesPanel'
import BucketTabs from '../../components/BucketTabs'
import BulkEditModal, { type BulkEditField } from '../../components/BulkEditModal'
import ListFilterBar from '../../components/ListFilterBar'
import SubscriptionForm from './SubscriptionForm'
import CsvImport from './CsvImport'
import type { Subscription } from '../../types'
import { INTERVAL_LABELS } from '../../types'

const BULK_FIELDS: BulkEditField[] = [
  { key: 'name', label: 'Name', type: 'text', nullable: false },
  { key: 'provider_name', label: 'Provider', type: 'text', nullable: false },
  {
    key: 'recurring_interval',
    label: 'Billing interval',
    type: 'select',
    options: Object.entries(INTERVAL_LABELS).map(([value, label]) => ({ value, label })),
    nullable: false,
  },
  { key: 'recurring_date', label: 'Last payment date', type: 'date' },
  { key: 'end_date', label: 'End date', type: 'date' },
  { key: 'amount', label: 'Amount', type: 'number', nullable: false },
  { key: 'currency', label: 'Currency', type: 'text', nullable: false },
  { key: 'category_name', label: 'Category', type: 'text' },
  { key: 'owner_name', label: 'Owner', type: 'text' },
]

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

  /** Bulk-edit "select mode" — checkboxes replace click-to-edit on rows. */
  const [selectMode, setSelectMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [showBulkEdit, setShowBulkEdit] = useState(false)

  /** Pending batch auto-resolve — set to trigger the batch confirm dialog. */
  const [autoResolve, setAutoResolve] = useState<AutoResolveState | null>(null)
  const [isResolving, setIsResolving] = useState(false)

  /** List filters — search matches Name/Provider; selects are exact-match AND. */
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [ownerFilter, setOwnerFilter] = useState('')
  const [intervalFilter, setIntervalFilter] = useState('')

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

  // ── Filters ───────────────────────────────────────────────────────────────
  // Option lists are derived from what's actually in the bucket, so a filter
  // never offers a value that would return zero results.
  const categoryOptions = useMemo(
    () => [...new Set(subs.map((s) => s.category_name).filter((v): v is string => !!v))].sort(),
    [subs],
  )
  const ownerOptions = useMemo(
    () => [...new Set(subs.map((s) => s.owner_name).filter((v): v is string => !!v))].sort(),
    [subs],
  )
  const intervalOptions = useMemo(
    () => [...new Set(subs.map((s) => s.recurring_interval))].sort(),
    [subs],
  )

  const filteredSubs = useMemo(() => {
    const q = search.trim().toLowerCase()
    return subs.filter((s) => {
      if (q && !s.name.toLowerCase().includes(q) && !s.provider_name?.toLowerCase().includes(q)) {
        return false
      }
      if (categoryFilter && s.category_name !== categoryFilter) return false
      if (ownerFilter && s.owner_name !== ownerFilter) return false
      if (intervalFilter && s.recurring_interval !== intervalFilter) return false
      return true
    })
  }, [subs, search, categoryFilter, ownerFilter, intervalFilter])

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

  const toggleSelected = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const exitSelectMode = () => {
    setSelectMode(false)
    setSelectedIds(new Set())
  }

  const handleBulkApply = async (update: Record<string, string | number | null>) => {
    if (!bucketId) return
    await subscriptionsApi.bulkUpdate(bucketId, [...selectedIds], update)
    qc.invalidateQueries({ queryKey: ['subscriptions', bucketId] })
    setShowBulkEdit(false)
    exitSelectMode()
  }

  // ── Duplicate detection ───────────────────────────────────────────────────
  const duplicateGroups = useMemo(() => {
    const eligible = subs.filter((s) => !s.ignore_duplicate)
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
  }, [subs])

  // O(1) membership lookup per row instead of re-scanning duplicateGroups
  // for every subscription on every render.
  const duplicateIds = useMemo(
    () => new Set(duplicateGroups.flatMap((g) => g.subscriptions.map((s) => s.id))),
    [duplicateGroups],
  )

  // Auto-close the panel when all groups are resolved
  useEffect(() => {
    if (duplicateGroups.length === 0) setShowDuplicates(false)
  }, [duplicateGroups.length])

  // ── Duplicate action handlers ─────────────────────────────────────────────
  /**
   * Persisted server-side (subscriptions.ignore_duplicate) rather than in
   * localStorage — survives clearing browser data and is shared across
   * devices/users of the bucket.
   */
  const handleMarkUnique = (id: string) => {
    if (!bucketId) return
    subscriptionsApi
      .setIgnoreDuplicate(bucketId, id, true)
      .then(() => qc.invalidateQueries({ queryKey: ['subscriptions', bucketId] }))
  }

  const ignoredCount = subs.filter((s) => s.ignore_duplicate).length

  /** Un-ignore every subscription currently excluded from duplicate detection. */
  const handleResetMarks = async () => {
    if (!bucketId) return
    const ignored = subs.filter((s) => s.ignore_duplicate)
    await Promise.all(
      ignored.map((s) => subscriptionsApi.setIgnoreDuplicate(bucketId, s.id, false)),
    )
    qc.invalidateQueries({ queryKey: ['subscriptions', bucketId] })
  }

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

        <BucketTabs bucketId={bucketId} />

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
            onClick={() => (selectMode ? exitSelectMode() : setSelectMode(true))}
            className={`flex items-center gap-2 text-sm px-3 py-2 rounded-lg border transition ${
              selectMode
                ? 'bg-blue-50 border-blue-300 text-blue-700'
                : 'border-gray-200 text-gray-700 hover:bg-gray-50'
            }`}
          >
            <ListChecks size={15} />
            {selectMode ? 'Cancel select' : 'Select'}
          </button>
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

      {/* ── Filters ───────────────────────────────────────────────────────── */}
      <ListFilterBar
        search={search}
        onSearchChange={setSearch}
        searchPlaceholder="Search name or provider…"
        selects={[
          { key: 'category', label: 'Category', value: categoryFilter, options: categoryOptions, onChange: setCategoryFilter },
          { key: 'owner', label: 'Owner', value: ownerFilter, options: ownerOptions, onChange: setOwnerFilter },
          { key: 'interval', label: 'Interval', value: intervalFilter, options: intervalOptions, onChange: setIntervalFilter },
        ]}
      />

      {/* ── Bulk-select bar ──────────────────────────────────────────────── */}
      {selectMode && (
        <div className="flex items-center justify-between gap-3 bg-blue-50 border border-blue-200 rounded-xl px-4 py-2.5">
          <span className="text-sm text-blue-800">
            {selectedIds.size} selected
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowBulkEdit(true)}
              disabled={selectedIds.size === 0}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition"
            >
              <Pencil size={13} />
              Edit selected
            </button>
            <button
              onClick={exitSelectMode}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 transition"
            >
              <X size={13} />
              Cancel
            </button>
          </div>
        </div>
      )}

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
            {ignoredCount > 0 && (
              <button
                onClick={handleResetMarks}
                className="text-xs text-amber-600 hover:text-amber-800 underline underline-offset-2 transition"
              >
                Reset marks ({ignoredCount})
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
      ) : filteredSubs.length === 0 ? (
        <div className="bg-white rounded-2xl border border-gray-200 py-12 text-center">
          <p className="text-gray-400 text-sm">No subscriptions match your filters.</p>
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-gray-200 divide-y divide-gray-100">
          {filteredSubs.map((sub) => {
            const isDuplicateCandidate = duplicateIds.has(sub.id)
            const isMarkedUnique = sub.ignore_duplicate
            const endDateExpired =
              sub.end_date != null &&
              sub.end_date <= new Date().toISOString().slice(0, 10)

            return (
              <div
                key={sub.id}
                onClick={() => (selectMode ? toggleSelected(sub.id) : setEditSub(sub))}
                className={`flex items-start gap-3 px-4 py-3 hover:bg-gray-50 transition cursor-pointer${
                  isDuplicateCandidate ? ' border-l-2 border-l-amber-300' : ''
                }`}
              >
                {/* Checkbox (select mode) or logo */}
                {selectMode ? (
                  <input
                    type="checkbox"
                    checked={selectedIds.has(sub.id)}
                    onChange={() => toggleSelected(sub.id)}
                    onClick={(e) => e.stopPropagation()}
                    className="shrink-0 mt-2.5"
                  />
                ) : (
                  <div className="shrink-0 mt-0.5">
                    <ProviderLogo name={sub.provider_name} imageUrl={sub.image_url} size={38} />
                  </div>
                )}

                {/* All text content */}
                <div className="flex-1 min-w-0">
                  {/* Row 1 — Name + Amount */}
                  <div className="flex items-start justify-between gap-2">
                    {/* Name + "kept" badge */}
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <p className="font-medium text-gray-800 truncate leading-snug">
                          {sub.name}
                        </p>
                        {isMarkedUnique && (
                          <span
                            className="text-xs text-emerald-600 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded-full shrink-0"
                            title="Marked as intentional — excluded from duplicate detection"
                          >
                            ✓ kept
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Amount — always top-right, never shrinks away */}
                    <div className="text-right shrink-0 ml-2">
                      <CurrencyDisplay
                        amount={sub.amount}
                        currency={sub.currency}
                        className="font-semibold text-gray-800 text-sm"
                      />
                      <p className="text-xs text-gray-400 mt-0.5 whitespace-nowrap">
                        {sub.recurring_date ?? '—'}
                      </p>
                    </div>
                  </div>

                  {/* Row 2 — Meta badges + interval + action buttons */}
                  <div
                    className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 mt-1.5"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {/* Left: provider / category / end-date / interval */}
                    <div className="flex flex-wrap items-center gap-1.5">
                      {sub.provider_name && (
                        <span className="text-xs text-gray-500">{sub.provider_name}</span>
                      )}
                      {sub.category_name && (
                        <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                          {sub.category_name}
                        </span>
                      )}
                      {sub.owner_name && (
                        <span className="inline-flex items-center gap-1 text-xs bg-violet-50 text-violet-600 px-2 py-0.5 rounded-full">
                          <User size={11} />
                          {sub.owner_name}
                        </span>
                      )}
                      {sub.end_date && (
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full border ${
                            endDateExpired
                              ? 'bg-amber-50 text-amber-600 border-amber-200'
                              : 'bg-blue-50 text-blue-600 border-blue-200'
                          }`}
                        >
                          {endDateExpired ? 'Ended' : 'Ends'} {sub.end_date}
                        </span>
                      )}
                      <IntervalBadge interval={sub.recurring_interval} />
                    </div>

                    {/* Right: edit / delete */}
                    <div className="flex items-center gap-0.5 shrink-0">
                      <button
                        onClick={(e) => { e.stopPropagation(); setEditSub(sub) }}
                        className="p-1.5 text-gray-400 hover:text-blue-600 rounded transition"
                        title="Edit"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); setDeleteSub(sub) }}
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

      {showBulkEdit && (
        <BulkEditModal
          count={selectedIds.size}
          fields={BULK_FIELDS}
          onApply={handleBulkApply}
          onCancel={() => setShowBulkEdit(false)}
        />
      )}
    </div>
  )
}
