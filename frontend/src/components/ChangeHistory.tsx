/**
 * Read-only, collapsed-by-default log of field-level edits for a
 * subscription or insurance. Deliberately unobtrusive — a plain text
 * toggle rather than a prominent panel — since most users will never open
 * it. History is only fetched once the user actually expands the panel.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, ChevronDown, History as HistoryIcon } from 'lucide-react'
import type { HistoryEntry } from '../types'

interface Props {
  queryKey: unknown[]
  queryFn: () => Promise<HistoryEntry[]>
  fieldLabels: Record<string, string>
}

function formatValue(v: string | null): string {
  if (v === null || v === '') return '—'
  return v
}

function formatDate(value: string): string {
  // SQLite's datetime('now') yields "YYYY-MM-DD HH:MM:SS" in UTC with a
  // space separator, not a Date-parseable ISO string — normalize it.
  const iso = value.includes('T') ? value : `${value.replace(' ', 'T')}Z`
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function ChangeHistory({ queryKey, queryFn, fieldLabels }: Props) {
  const [expanded, setExpanded] = useState(false)

  const { data: entries = [], isLoading } = useQuery({
    queryKey,
    queryFn,
    enabled: expanded,
  })

  return (
    <div className="mt-6 pt-5 border-t border-gray-100">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 transition"
      >
        {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <HistoryIcon size={13} />
        History
      </button>

      {expanded && (
        <div className="mt-2">
          {isLoading ? (
            <p className="text-xs text-gray-400">Loading…</p>
          ) : entries.length === 0 ? (
            <p className="text-xs text-gray-400">No changes recorded yet.</p>
          ) : (
            <ul className="divide-y divide-gray-100 border border-gray-100 rounded-lg overflow-hidden">
              {entries.map((entry) => (
                <li key={entry.id} className="px-3 py-2 text-xs">
                  <p className="text-gray-500">
                    <span className="font-medium text-gray-600">
                      {fieldLabels[entry.field] ?? entry.field}
                    </span>
                    {': '}
                    <span className="text-gray-400">{formatValue(entry.old_value)}</span>
                    {' → '}
                    <span className="font-medium text-gray-700">
                      {formatValue(entry.new_value)}
                    </span>
                  </p>
                  <p className="text-gray-400 mt-0.5">
                    {entry.changed_by_username} · {formatDate(entry.changed_at)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
