/**
 * DuplicatesPanel — shows groups of potential duplicate subscriptions.
 *
 * Per entry:
 *   ✓ Keep  — marks as intentional (excluded from future detection).
 *   🗑 Delete — triggers the parent's delete-confirm flow.
 *
 * For 2-entry groups an "Auto-resolve" shortcut is available in the group
 * header that immediately picks the winner by strategy and hands the loser
 * to the parent.
 *
 * A "Resolve all" section at the top batch-resolves every 2-entry group.
 */

import { CheckCircle, Trash2, Zap } from 'lucide-react'
import type { Subscription } from '../types'
import { pickLoser, type ResolveStrategy } from '../utils/duplicates'
import ProviderLogo from './ProviderLogo'
import CurrencyDisplay from './CurrencyDisplay'
import IntervalBadge from './IntervalBadge'

export interface DuplicateGroup {
  /** Normalised (lowercase + trimmed) subscription name */
  key: string
  subscriptions: Subscription[]
}

interface Props {
  groups: DuplicateGroup[]
  onMarkUnique: (id: string) => void
  /** Triggered by per-group auto-resolve: parent should confirm-then-delete the loser. */
  onAutoResolveGroup: (loser: Subscription) => void
  /** Triggered by global auto-resolve: parent computes all losers and batch-confirms. */
  onAutoResolveAll: (strategy: ResolveStrategy) => void
  onDelete: (sub: Subscription) => void
}

/** Small pill button used for the two auto-resolve strategy choices. */
function StrategyButton({
  label,
  onClick,
}: {
  label: string
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1 text-xs text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-200 px-2 py-1 rounded-md transition whitespace-nowrap"
    >
      <Zap size={11} />
      {label}
    </button>
  )
}

export default function DuplicatesPanel({
  groups,
  onMarkUnique,
  onAutoResolveGroup,
  onAutoResolveAll,
  onDelete,
}: Props) {
  if (groups.length === 0) return null

  const twoItemGroups = groups.filter((g) => g.subscriptions.length === 2)

  return (
    <div className="space-y-3">
      {/* ── Global auto-resolve (only when 2-item groups exist) ─────────── */}
      {twoItemGroups.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap px-1">
          <span className="text-xs text-amber-700 font-medium">
            Auto-resolve {twoItemGroups.length} two-entry group
            {twoItemGroups.length !== 1 ? 's' : ''}:
          </span>
          <StrategyButton
            label="Keep newest"
            onClick={() => onAutoResolveAll('newer')}
          />
          <StrategyButton
            label="Keep priciest"
            onClick={() => onAutoResolveAll('pricier')}
          />
        </div>
      )}

      {/* ── Per-group ────────────────────────────────────────────────────── */}
      {groups.map((group) => {
        const isTwo = group.subscriptions.length === 2
        return (
          <div
            key={group.key}
            className="bg-white rounded-2xl border border-amber-200 overflow-hidden"
          >
            {/* Group header */}
            <div className="flex items-center gap-2 flex-wrap px-4 py-2.5 bg-amber-50 border-b border-amber-100">
              <span className="text-sm font-semibold text-amber-900 truncate">
                {group.subscriptions[0].name}
              </span>
              <span className="shrink-0 text-xs text-amber-700 bg-amber-200 px-1.5 py-0.5 rounded-full font-medium">
                ×{group.subscriptions.length}
              </span>

              {/* Per-group auto-resolve (2-item groups only) */}
              {isTwo && (
                <div className="flex items-center gap-1.5 ml-auto">
                  <StrategyButton
                    label="Keep newest"
                    onClick={() =>
                      onAutoResolveGroup(
                        pickLoser(
                          group.subscriptions as [Subscription, Subscription],
                          'newer',
                        ),
                      )
                    }
                  />
                  <StrategyButton
                    label="Keep priciest"
                    onClick={() =>
                      onAutoResolveGroup(
                        pickLoser(
                          group.subscriptions as [Subscription, Subscription],
                          'pricier',
                        ),
                      )
                    }
                  />
                </div>
              )}
            </div>

            {/* Rows */}
            <div className="divide-y divide-gray-100">
              {group.subscriptions.map((sub) => (
                <div
                  key={sub.id}
                  className="flex items-center gap-4 px-4 py-3 hover:bg-gray-50 transition"
                >
                  <ProviderLogo name={sub.provider_name} imageUrl={sub.image_url} size={36} />

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      {sub.provider_name && (
                        <span className="text-xs text-gray-500">{sub.provider_name}</span>
                      )}
                      {sub.category_name && (
                        <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                          {sub.category_name}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-400 mt-0.5">
                      Added {new Date(sub.created_at).toLocaleDateString()} ·{' '}
                      {sub.recurring_date ?? 'no payment date'}
                    </p>
                  </div>

                  <IntervalBadge interval={sub.recurring_interval} />

                  <CurrencyDisplay
                    amount={sub.amount}
                    currency={sub.currency}
                    className="font-semibold text-gray-700 text-sm shrink-0"
                  />

                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => onMarkUnique(sub.id)}
                      className="flex items-center gap-1 text-xs text-emerald-700 bg-emerald-50 hover:bg-emerald-100 px-2.5 py-1.5 rounded-lg transition"
                      title="Mark as intentional — exclude from duplicate detection"
                    >
                      <CheckCircle size={13} />
                      Keep
                    </button>
                    <button
                      onClick={() => onDelete(sub)}
                      className="p-1.5 text-gray-400 hover:text-red-600 rounded transition"
                      title="Delete this subscription"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
