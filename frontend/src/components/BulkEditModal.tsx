/**
 * Generic bulk-edit modal: the caller supplies a field config, the user
 * checks which field(s) to overwrite and enters one value per checked
 * field, and on submit only the checked fields are sent — applied
 * identically to every record passed in by the caller.
 */

import { useState } from 'react'
import { X, Pencil, Eraser } from 'lucide-react'

export interface BulkEditField {
  key: string
  label: string
  type: 'text' | 'number' | 'date' | 'select'
  options?: { value: string; label: string }[]
  /** Set false for fields that must always hold a value (e.g. Name, Amount). */
  nullable?: boolean
}

type UpdateValue = string | number | null

interface Props {
  count: number
  fields: BulkEditField[]
  onApply: (update: Record<string, UpdateValue>) => Promise<void>
  onCancel: () => void
}

const INPUT_CLS =
  'w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 outline-none disabled:bg-gray-50 disabled:text-gray-400'

export default function BulkEditModal({ count, fields, onApply, onCancel }: Props) {
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [values, setValues] = useState<Record<string, string>>({})
  const [cleared, setCleared] = useState<Set<string>>(new Set())
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState('')

  const toggle = (key: string) => {
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const setValue = (key: string, value: string) => {
    setValues((prev) => ({ ...prev, [key]: value }))
    // Typing a value cancels a pending "clear" for this field.
    setCleared((prev) => {
      if (!prev.has(key)) return prev
      const next = new Set(prev)
      next.delete(key)
      return next
    })
  }

  const toggleCleared = (key: string) => {
    setCleared((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
    setValues((prev) => ({ ...prev, [key]: '' }))
  }

  const handleApply = async () => {
    setError('')
    const update: Record<string, UpdateValue> = {}
    for (const field of fields) {
      if (!checked.has(field.key)) continue
      if (cleared.has(field.key)) {
        update[field.key] = null
        continue
      }
      const raw = values[field.key] ?? ''
      if (field.type === 'number') {
        const n = parseFloat(raw)
        if (Number.isNaN(n)) {
          setError(`Enter a valid number for "${field.label}"`)
          return
        }
        update[field.key] = n
      } else {
        if (raw === '') {
          setError(
            field.nullable === false
              ? `Enter a value for "${field.label}"`
              : `Enter a value for "${field.label}", or use Clear`,
          )
          return
        }
        update[field.key] = raw
      }
    }
    if (Object.keys(update).length === 0) {
      setError('Check at least one field to apply')
      return
    }
    setApplying(true)
    try {
      await onApply(update)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Bulk update failed')
    } finally {
      setApplying(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onCancel} />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 p-6 overflow-y-auto max-h-[90vh]">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <Pencil size={17} className="text-blue-600" />
            Edit {count} selected
          </h2>
          <button onClick={onCancel} className="text-gray-400 hover:text-gray-600 transition">
            <X size={20} />
          </button>
        </div>
        <p className="text-xs text-gray-400 mb-4">
          Check a field to overwrite it on all {count} selected records.
        </p>

        <div className="space-y-3">
          {fields.map((field) => {
            const isChecked = checked.has(field.key)
            const isCleared = cleared.has(field.key)
            const isNullable = field.nullable !== false
            return (
              <div key={field.key} className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={isChecked}
                  onChange={() => toggle(field.key)}
                  className="shrink-0"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-0.5">
                    <label className="block text-xs font-medium text-gray-500">
                      {field.label}
                    </label>
                    {isChecked && isNullable && (
                      <button
                        type="button"
                        onClick={() => toggleCleared(field.key)}
                        className={`flex items-center gap-1 text-xs px-1.5 py-0.5 rounded transition ${
                          isCleared
                            ? 'bg-red-50 text-red-600'
                            : 'text-gray-400 hover:text-red-500 hover:bg-red-50'
                        }`}
                        title="Clear this field on all selected records"
                      >
                        <Eraser size={11} />
                        {isCleared ? 'Clearing' : 'Clear'}
                      </button>
                    )}
                  </div>
                  {field.type === 'select' ? (
                    <select
                      value={values[field.key] ?? ''}
                      onChange={(e) => setValue(field.key, e.target.value)}
                      disabled={!isChecked || isCleared}
                      className={INPUT_CLS}
                    >
                      <option value="">—</option>
                      {field.options?.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type={field.type === 'date' ? 'date' : field.type === 'number' ? 'number' : 'text'}
                      value={values[field.key] ?? ''}
                      onChange={(e) => setValue(field.key, e.target.value)}
                      disabled={!isChecked || isCleared}
                      className={INPUT_CLS}
                      placeholder={
                        isCleared ? 'Will be cleared' : isChecked ? undefined : 'Check to edit'
                      }
                    />
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {error && <p className="text-sm text-red-500 mt-4">{error}</p>}

        <div className="flex justify-end gap-2 mt-6">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-sm rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 transition"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleApply}
            disabled={applying || checked.size === 0}
            className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition"
          >
            {applying ? 'Applying…' : `Apply to ${count}`}
          </button>
        </div>
      </div>
    </div>
  )
}
