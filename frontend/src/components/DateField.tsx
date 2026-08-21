/**
 * Segmented DD / MM / YYYY date input with auto-advance and clear.
 * Shared between SubscriptionForm and InsuranceForm.
 */

import { useState, useRef } from 'react'
import type { ReactNode } from 'react'
import { X } from 'lucide-react'

interface DateFieldProps {
  label: ReactNode
  value: string          // ISO "YYYY-MM-DD" or ""
  onChange: (v: string) => void
}

/**
 * Splits an ISO date string into { dd, mm, yyyy } display parts.
 * Returns empty strings when the value is blank.
 */
function splitIso(iso: string): { dd: string; mm: string; yyyy: string } {
  if (!iso || iso.length < 10) return { dd: '', mm: '', yyyy: '' }
  const [yyyy, mm, dd] = iso.split('-')
  return { dd, mm, yyyy }
}

export default function DateField({ label, value, onChange }: DateFieldProps) {
  const { dd: initDd, mm: initMm, yyyy: initYyyy } = splitIso(value)
  const [dd, setDd] = useState(initDd)
  const [mm, setMm] = useState(initMm)
  const [yyyy, setYyyy] = useState(initYyyy)

  const mmRef = useRef<HTMLInputElement>(null)
  const yyyyRef = useRef<HTMLInputElement>(null)

  /** Emit change only when all three parts form a valid date. */
  const emit = (nextDd: string, nextMm: string, nextYyyy: string) => {
    if (nextDd.length === 2 && nextMm.length === 2 && nextYyyy.length === 4) {
      const iso = `${nextYyyy}-${nextMm}-${nextDd}`
      // Basic sanity check — avoid emitting obviously bad dates
      const d = new Date(iso)
      if (!isNaN(d.getTime())) {
        onChange(iso)
        return
      }
    }
    // Partial / invalid → clear the external value
    if (value !== '') onChange('')
  }

  const handleClear = () => {
    setDd(''); setMm(''); setYyyy('')
    onChange('')
  }

  const SEG = 'w-8 text-center border-0 outline-none bg-transparent text-sm text-gray-900 placeholder-gray-400 focus:text-blue-600'
  const hasValue = dd || mm || yyyy

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label}
      </label>
      <div className="flex items-center gap-1.5">
        {/* Segmented input pill */}
        <div className="flex-1 flex items-center border border-gray-200 rounded-lg px-2 py-2 bg-white focus-within:ring-2 focus-within:ring-blue-500">
          {/* Day */}
          <input
            type="text"
            inputMode="numeric"
            maxLength={2}
            placeholder="DD"
            value={dd}
            className={SEG}
            onChange={(e) => {
              const v = e.target.value.replace(/\D/g, '').slice(0, 2)
              setDd(v)
              emit(v, mm, yyyy)
              if (v.length === 2) mmRef.current?.focus()
            }}
            onKeyDown={(e) => {
              if (e.key === 'Backspace' && dd === '') {
                // nothing to do — already at first segment
              }
            }}
          />
          <span className="text-gray-300 select-none">.</span>
          {/* Month */}
          <input
            ref={mmRef}
            type="text"
            inputMode="numeric"
            maxLength={2}
            placeholder="MM"
            value={mm}
            className={SEG}
            onChange={(e) => {
              const v = e.target.value.replace(/\D/g, '').slice(0, 2)
              setMm(v)
              emit(dd, v, yyyy)
              if (v.length === 2) yyyyRef.current?.focus()
            }}
            onKeyDown={(e) => {
              if (e.key === 'Backspace' && mm === '') {
                // Let browser handle — focus would naturally go back
              }
            }}
          />
          <span className="text-gray-300 select-none">.</span>
          {/* Year */}
          <input
            ref={yyyyRef}
            type="text"
            inputMode="numeric"
            maxLength={4}
            placeholder="YYYY"
            value={yyyy}
            className="w-12 text-center border-0 outline-none bg-transparent text-sm text-gray-900 placeholder-gray-400 focus:text-blue-600"
            onChange={(e) => {
              const v = e.target.value.replace(/\D/g, '').slice(0, 4)
              setYyyy(v)
              emit(dd, mm, v)
            }}
          />
        </div>

        {/* Clear button / spacer */}
        {hasValue ? (
          <button
            type="button"
            onClick={handleClear}
            className="shrink-0 p-1.5 text-gray-400 hover:text-red-500 rounded-lg hover:bg-red-50 transition"
            title="Clear date"
          >
            <X size={14} />
          </button>
        ) : (
          <span className="shrink-0 w-7" />
        )}
      </div>
    </div>
  )
}
