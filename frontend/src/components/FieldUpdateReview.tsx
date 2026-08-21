/**
 * Field-by-field review UI for AI-suggested updates derived from an
 * uploaded attachment (see FindInsurancesPanel/AiDocumentImportPanel for
 * the sibling "propose new record" flow — this one proposes edits to an
 * *existing* subscription/insurance instead).
 *
 * Every field shown here already passed the backend's "actually differs
 * from the current value" filter, so all rows start pre-checked — the user
 * deselects what they don't want rather than opting in field by field.
 */

import { useState } from 'react'
import { Sparkles, Check, X } from 'lucide-react'

type UpdateValue = string | number | null

interface Props {
  updates: Record<string, UpdateValue>
  currentValues: Record<string, unknown>
  fieldLabels: Record<string, string>
  onApply: (selected: Record<string, UpdateValue>) => void | Promise<void>
  onDismiss: () => void
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—'
  return String(v)
}

export default function FieldUpdateReview({
  updates,
  currentValues,
  fieldLabels,
  onApply,
  onDismiss,
}: Props) {
  const fields = Object.keys(updates)
  const [selected, setSelected] = useState<Set<string>>(new Set(fields))
  const [applying, setApplying] = useState(false)

  const toggle = (field: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(field)) next.delete(field)
      else next.add(field)
      return next
    })
  }

  const handleApply = async () => {
    const chosen: Record<string, UpdateValue> = {}
    for (const field of fields) {
      if (selected.has(field)) chosen[field] = updates[field]
    }
    setApplying(true)
    try {
      await onApply(chosen)
    } finally {
      setApplying(false)
    }
  }

  if (fields.length === 0) return null

  return (
    <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles size={15} className="text-blue-600" />
        <h3 className="text-sm font-semibold text-blue-900">
          This document suggests {fields.length} update{fields.length !== 1 ? 's' : ''}
        </h3>
      </div>

      <ul className="divide-y divide-blue-100 border border-blue-100 rounded-lg overflow-hidden bg-white">
        {fields.map((field) => (
          <li key={field} className="flex items-center gap-3 px-3 py-2 text-sm">
            <input
              type="checkbox"
              checked={selected.has(field)}
              onChange={() => toggle(field)}
              className="shrink-0"
            />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-gray-500">
                {fieldLabels[field] ?? field}
              </p>
              <p className="text-gray-700 truncate">
                <span className="text-gray-400">{formatValue(currentValues[field])}</span>
                {' → '}
                <span className="font-medium text-blue-700">{formatValue(updates[field])}</span>
              </p>
            </div>
          </li>
        ))}
      </ul>

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onDismiss}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 transition"
        >
          <X size={13} />
          Dismiss
        </button>
        <button
          type="button"
          onClick={handleApply}
          disabled={selected.size === 0 || applying}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition"
        >
          <Check size={13} />
          {applying ? 'Applying…' : `Apply ${selected.size} selected`}
        </button>
      </div>
    </div>
  )
}
