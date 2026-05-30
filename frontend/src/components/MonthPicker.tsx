/**
 * MonthPicker — compact popover that lets the user pick a YYYY-MM value.
 *
 * Shows a year with 12 month buttons in a 4×3 grid plus prev/next year
 * navigation. Clicking outside closes the popover.
 */

import { useState, useRef, useEffect } from 'react'
import { ChevronLeft, ChevronRight, Calendar } from 'lucide-react'

interface Props {
  value: string          // "YYYY-MM"
  onChange: (value: string) => void
}

const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

export default function MonthPicker({ value, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const [year, month] = value.split('-').map(Number)
  const [pickerYear, setPickerYear] = useState(year)

  // Sync picker year when value changes externally
  useEffect(() => {
    setPickerYear(year)
  }, [year])

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const select = (m: number) => {
    onChange(`${pickerYear}-${String(m).padStart(2, '0')}`)
    setOpen(false)
  }

  const label = `${MONTHS[month - 1]} ${year}`

  return (
    <div ref={ref} className="relative">
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white hover:bg-gray-50 transition"
      >
        <Calendar size={15} className="text-gray-400" />
        {label}
      </button>

      {/* Popover */}
      {open && (
        <div className="absolute z-20 mt-1 left-0 bg-white border border-gray-200 rounded-xl shadow-lg p-3 w-52">
          {/* Year navigation */}
          <div className="flex items-center justify-between mb-2">
            <button
              type="button"
              onClick={() => setPickerYear((y) => y - 1)}
              className="p-1 hover:bg-gray-100 rounded transition"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="text-sm font-semibold text-gray-700">{pickerYear}</span>
            <button
              type="button"
              onClick={() => setPickerYear((y) => y + 1)}
              className="p-1 hover:bg-gray-100 rounded transition"
            >
              <ChevronRight size={16} />
            </button>
          </div>

          {/* Month grid */}
          <div className="grid grid-cols-4 gap-1">
            {MONTHS.map((name, i) => {
              const m = i + 1
              const isSelected = pickerYear === year && m === month
              return (
                <button
                  key={name}
                  type="button"
                  onClick={() => select(m)}
                  className={`text-xs py-1.5 rounded-lg transition ${
                    isSelected
                      ? 'bg-blue-600 text-white font-medium'
                      : 'hover:bg-gray-100 text-gray-700'
                  }`}
                >
                  {name}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
