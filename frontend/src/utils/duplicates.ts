/**
 * Utilities for duplicate-subscription detection and auto-resolution.
 */

import type { Subscription } from '../types'

export type ResolveStrategy = 'newer' | 'pricier'

/**
 * Given exactly two subscriptions, return the one that should be DELETED.
 *
 * 'newer'   → keep the more recently created; tie-break: keep pricier.
 * 'pricier' → keep the higher-priced; tie-break: keep newer.
 */
export function pickLoser(
  [a, b]: [Subscription, Subscription],
  strategy: ResolveStrategy,
): Subscription {
  if (strategy === 'newer') {
    const ta = new Date(a.created_at).getTime()
    const tb = new Date(b.created_at).getTime()
    if (ta !== tb) return ta < tb ? a : b          // delete the older one
    return a.amount <= b.amount ? a : b            // tie: delete the cheaper
  } else {
    // 'pricier': keep the more expensive, delete the cheaper
    if (a.amount !== b.amount) return a.amount < b.amount ? a : b
    const ta = new Date(a.created_at).getTime()   // tie: delete the older
    const tb = new Date(b.created_at).getTime()
    return ta <= tb ? a : b
  }
}
