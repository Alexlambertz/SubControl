/**
 * Collapsible filter panel shared by the Subscriptions and Insurances list
 * pages — a text search plus a caller-supplied set of dropdown filters
 * (Category, Owner, Interval), all combined with AND semantics.
 */

import { useState } from 'react'
import { Filter, ChevronDown, ChevronUp, X, Search } from 'lucide-react'

export interface FilterSelect {
  key: string
  label: string
  value: string
  options: string[]
  onChange: (value: string) => void
}

interface Props {
  search: string
  onSearchChange: (value: string) => void
  searchPlaceholder: string
  selects: FilterSelect[]
}

const SELECT_CLS =
  'w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 outline-none'

export default function ListFilterBar({
  search,
  onSearchChange,
  searchPlaceholder,
  selects,
}: Props) {
  const [expanded, setExpanded] = useState(false)

  const activeCount =
    (search.trim() ? 1 : 0) + selects.filter((s) => s.value !== '').length

  const clearAll = () => {
    onSearchChange('')
    selects.forEach((s) => s.onChange(''))
  }

  return (
    <div>
      <button
        onClick={() => setExpanded((v) => !v)}
        className={`flex items-center gap-2 text-sm px-3 py-2 rounded-lg border transition ${
          activeCount > 0
            ? 'bg-blue-50 border-blue-300 text-blue-700'
            : 'border-gray-200 text-gray-700 hover:bg-gray-50'
        }`}
      >
        <Filter size={15} />
        Filters
        {activeCount > 0 && (
          <span className="bg-blue-600 text-white text-xs w-4.5 h-4.5 min-w-[18px] rounded-full flex items-center justify-center">
            {activeCount}
          </span>
        )}
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {expanded && (
        <div className="mt-2 bg-white border border-gray-200 rounded-xl p-3 flex flex-wrap items-end gap-3">
          <div className="min-w-[180px] flex-1">
            <label className="block text-xs font-medium text-gray-500 mb-1">Search</label>
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                value={search}
                onChange={(e) => onSearchChange(e.target.value)}
                placeholder={searchPlaceholder}
                className={`${SELECT_CLS} pl-8`}
              />
            </div>
          </div>

          {selects.map((s) => (
            <div key={s.key} className="min-w-[140px]">
              <label className="block text-xs font-medium text-gray-500 mb-1">{s.label}</label>
              <select
                value={s.value}
                onChange={(e) => s.onChange(e.target.value)}
                className={SELECT_CLS}
              >
                <option value="">All</option>
                {s.options.map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
            </div>
          ))}

          {activeCount > 0 && (
            <button
              onClick={clearAll}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 px-2 py-1.5 transition"
            >
              <X size={13} />
              Clear
            </button>
          )}
        </div>
      )}
    </div>
  )
}
