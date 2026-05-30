/**
 * Small badge showing the billing interval in human-readable form.
 */


import { Clock } from 'lucide-react'
import type { RecurringInterval } from '../types'
import { INTERVAL_LABELS } from '../types'

interface Props {
  interval: RecurringInterval
}

export default function IntervalBadge({ interval }: Props) {
  return (
    <span className="inline-flex items-center gap-1 text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full font-medium">
      <Clock size={11} />
      {INTERVAL_LABELS[interval] ?? interval}
    </span>
  )
}
