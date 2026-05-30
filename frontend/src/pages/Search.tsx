/**
 * Global search results page — /search?q=<query>
 *
 * Clicking a subscription row opens the edit modal directly here so the user
 * can edit successive results without leaving the page.  A separate icon
 * navigates to the bucket's subscription list.
 */

import { useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FolderOpen, CreditCard, SearchX, Pencil, ExternalLink } from 'lucide-react'
import { searchApi } from '../api/search'
import { subscriptionsApi } from '../api/subscriptions'
import type { SearchResultBucket, SearchResultSubscription } from '../types'
import CurrencyDisplay from '../components/CurrencyDisplay'
import ProviderLogo from '../components/ProviderLogo'
import SubscriptionForm from './Subscriptions/SubscriptionForm'

// ---------------------------------------------------------------------------
// Cost helpers — mirrors the backend _FACTORS dict in dashboard.py
// ---------------------------------------------------------------------------

const MONTHLY_FACTORS: Record<string, number> = {
  daily: 30,
  weekly: 365 / 12 / 7,   // ≈ 4.333
  monthly: 1,
  quarterly: 1 / 3,
  'half-year': 1 / 6,
  yearly: 1 / 12,
}

function toMonthly(amount: number, interval: string) {
  return amount * (MONTHLY_FACTORS[interval] ?? 1)
}

function toYearly(amount: number, interval: string) {
  return toMonthly(amount, interval) * 12
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/** State that drives the edit modal — bucket + subscription IDs. */
interface EditTarget { bucketId: string; subId: string }

export default function Search() {
  const [searchParams] = useSearchParams()
  const qc = useQueryClient()
  const q = searchParams.get('q') ?? ''

  const [editTarget, setEditTarget] = useState<EditTarget | null>(null)

  // ── Search results ────────────────────────────────────────────────────────
  const { data, isLoading } = useQuery({
    queryKey: ['search', q],
    queryFn: () => searchApi.search(q),
    enabled: q.length > 0,
  })

  const buckets = (data?.results.filter((r) => r.type === 'bucket') ?? []) as SearchResultBucket[]
  const subscriptions = (data?.results.filter((r) => r.type === 'subscription') ?? []) as SearchResultSubscription[]
  const total = buckets.length + subscriptions.length

  // ── Full subscription fetch for the edit form ─────────────────────────────
  const { data: editSub, isLoading: editLoading } = useQuery({
    queryKey: ['subscription', editTarget?.bucketId, editTarget?.subId],
    queryFn: () => subscriptionsApi.get(editTarget!.bucketId, editTarget!.subId),
    enabled: !!editTarget,
  })

  // ── Cost totals ───────────────────────────────────────────────────────────
  const totalMonthly = subscriptions.reduce(
    (acc, s) => acc + toMonthly(s.amount, s.recurring_interval), 0
  )
  const totalYearly = totalMonthly * 12

  // ── Helpers ───────────────────────────────────────────────────────────────
  const openEdit = (s: SearchResultSubscription) =>
    setEditTarget({ bucketId: s.bucket_id, subId: s.id })

  const closeEdit = () => setEditTarget(null)

  const handleSaved = () => {
    qc.invalidateQueries({ queryKey: ['search', q] })
    closeEdit()
  }

  // ── Empty-query splash ────────────────────────────────────────────────────
  if (!q) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-gray-400">
        <SearchX size={48} className="mb-4 opacity-40" />
        <p className="text-sm">Enter a search term in the bar above.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Summary line */}
      <p className="text-sm text-gray-500">
        {isLoading ? (
          'Searching…'
        ) : (
          <>
            <span className="font-medium text-gray-800">{total}</span>{' '}
            result{total !== 1 ? 's' : ''} for{' '}
            <span className="font-medium text-gray-800">"{q}"</span>
          </>
        )}
      </p>

      {!isLoading && total === 0 && (
        <div className="bg-white rounded-2xl border border-gray-200 py-16 text-center">
          <SearchX size={36} className="mx-auto text-gray-300 mb-3" />
          <p className="text-sm text-gray-500">No results found for <strong>"{q}"</strong>.</p>
          <p className="text-xs text-gray-400 mt-1">Try a shorter or different search term.</p>
        </div>
      )}

      {/* ── Buckets ─────────────────────────────────────────────────────── */}
      {buckets.length > 0 && (
        <section>
          <h2 className="flex items-center gap-2 text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
            <FolderOpen size={14} />
            Buckets
            <span className="bg-gray-100 text-gray-600 rounded-full px-2 py-0.5 text-xs font-medium">
              {buckets.length}
            </span>
          </h2>
          <div className="bg-white rounded-2xl border border-gray-200 divide-y divide-gray-100">
            {buckets.map((b) => (
              <Link
                key={b.id}
                to={`/buckets/${b.id}/subscriptions`}
                className="flex items-center justify-between px-5 py-4 hover:bg-gray-50 transition group"
              >
                <div className="flex items-center gap-3">
                  <div className="bg-blue-50 rounded-lg p-2">
                    <FolderOpen size={18} className="text-blue-500" />
                  </div>
                  <span className="font-medium text-gray-800">{b.name}</span>
                </div>
                <ExternalLink size={15} className="text-gray-300 group-hover:text-blue-500 transition" />
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* ── Subscriptions ────────────────────────────────────────────────── */}
      {subscriptions.length > 0 && (
        <section>
          <h2 className="flex items-center gap-2 text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
            <CreditCard size={14} />
            Subscriptions
            <span className="bg-gray-100 text-gray-600 rounded-full px-2 py-0.5 text-xs font-medium">
              {subscriptions.length}
            </span>
          </h2>

          <div className="bg-white rounded-2xl border border-gray-200 divide-y divide-gray-100">
            {subscriptions.map((s) => {
              const monthly = toMonthly(s.amount, s.recurring_interval)
              const yearly  = toYearly(s.amount, s.recurring_interval)
              const isEditing = editTarget?.subId === s.id

              return (
                <div
                  key={s.id}
                  className={`flex items-center gap-4 px-5 py-4 hover:bg-gray-50 transition cursor-pointer group ${
                    isEditing ? 'bg-blue-50' : ''
                  }`}
                  onClick={() => openEdit(s)}
                >
                  <ProviderLogo name={s.provider_name} imageUrl={s.image_url} size={40} />

                  {/* Name + metadata */}
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-gray-800 truncate">{s.name}</p>
                    <div className="flex flex-wrap items-center gap-2 mt-0.5">
                      {s.provider_name && (
                        <span className="text-xs text-gray-500">{s.provider_name}</span>
                      )}
                      {s.category_name && (
                        <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                          {s.category_name}
                        </span>
                      )}
                      <span className="text-xs text-gray-400">in</span>
                      <span className="text-xs text-blue-600 font-medium">{s.bucket_name}</span>
                    </div>
                  </div>

                  {/* Monthly + yearly cost */}
                  <div className="text-right shrink-0 space-y-0.5">
                    <div className="text-sm font-semibold text-gray-800">
                      <CurrencyDisplay amount={monthly} currency={s.currency} /><span className="text-xs font-normal text-gray-400">/mo</span>
                    </div>
                    <div className="text-xs text-gray-400">
                      <CurrencyDisplay amount={yearly} currency={s.currency} /><span>/yr</span>
                    </div>
                  </div>

                  {/* Actions — stop propagation so row click doesn't double-fire */}
                  <div
                    className="flex items-center gap-1 shrink-0"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      onClick={() => openEdit(s)}
                      className="p-1.5 text-gray-400 hover:text-blue-600 rounded transition"
                      title="Edit"
                    >
                      <Pencil size={15} />
                    </button>
                    <Link
                      to={`/buckets/${s.bucket_id}/subscriptions`}
                      className="p-1.5 text-gray-400 hover:text-blue-600 rounded transition"
                      title="Go to bucket"
                    >
                      <ExternalLink size={15} />
                    </Link>
                  </div>
                </div>
              )
            })}

            {/* ── Totals footer ─────────────────────────────────────────── */}
            {subscriptions.length > 1 && (
              <div className="flex items-center justify-between px-5 py-3 bg-gray-50 rounded-b-2xl">
                <span className="text-xs font-medium text-gray-500">
                  Total · {subscriptions.length} subscriptions
                </span>
                <div className="flex items-center gap-4">
                  <span className="text-sm font-semibold text-gray-800">
                    <CurrencyDisplay amount={totalMonthly} currency="EUR" />
                    <span className="text-xs font-normal text-gray-400">/mo</span>
                  </span>
                  <span className="text-sm font-semibold text-gray-700">
                    <CurrencyDisplay amount={totalYearly} currency="EUR" />
                    <span className="text-xs font-normal text-gray-400">/yr</span>
                  </span>
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {/* ── Edit modal ───────────────────────────────────────────────────── */}
      {editTarget && !editLoading && editSub && (
        <SubscriptionForm
          bucketId={editTarget.bucketId}
          subscription={editSub}
          onClose={closeEdit}
          onSaved={handleSaved}
        />
      )}
    </div>
  )
}
