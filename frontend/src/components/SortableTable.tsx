/**
 * A reusable table with sortable column headers.
 *
 * Usage:
 *   <SortableTable
 *     columns={[{ key: 'name', label: 'Name' }, ...]}
 *     data={rows}
 *     renderRow={(row) => <tr>...</tr>}
 *   />
 */

import React, { useMemo, useState } from 'react'
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react'

export interface Column<T> {
  key: keyof T | string
  label: string
  sortable?: boolean
  render?: (row: T) => React.ReactNode
}

interface Props<T> {
  columns: Column<T>[]
  data: T[]
  rowKey: (row: T) => string
  emptyMessage?: string
  defaultSort?: { key: string; dir: 'asc' | 'desc' }
}

type SortDir = 'asc' | 'desc' | null

export default function SortableTable<T>({
  columns,
  data,
  rowKey,
  emptyMessage = 'No data found.',
  defaultSort,
}: Props<T>) {
  const [sortKey, setSortKey] = useState<string | null>(defaultSort?.key ?? null)
  const [sortDir, setSortDir] = useState<SortDir>(defaultSort?.dir ?? null)

  const handleSort = (key: string) => {
    if (sortKey !== key) {
      setSortKey(key)
      setSortDir('asc')
    } else if (sortDir === 'asc') {
      setSortDir('desc')
    } else {
      setSortKey(null)
      setSortDir(null)
    }
  }

  const sorted = useMemo(
    () =>
      [...data].sort((a, b) => {
        if (!sortKey || !sortDir) return 0
        const av = (a as Record<string, unknown>)[sortKey] ?? ''
        const bv = (b as Record<string, unknown>)[sortKey] ?? ''
        const cmp = String(av).localeCompare(String(bv), undefined, { numeric: true })
        return sortDir === 'asc' ? cmp : -cmp
      }),
    [data, sortKey, sortDir],
  )

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            {columns.map((col) => (
              <th
                key={String(col.key)}
                className="px-4 py-3 text-left font-medium text-gray-500 uppercase tracking-wide text-xs select-none"
                onClick={() => col.sortable !== false && handleSort(String(col.key))}
                style={{ cursor: col.sortable === false ? 'default' : 'pointer' }}
              >
                <span className="inline-flex items-center gap-1">
                  {col.label}
                  {col.sortable !== false &&
                    (sortKey === String(col.key) ? (
                      sortDir === 'asc' ? (
                        <ChevronUp size={14} />
                      ) : (
                        <ChevronDown size={14} />
                      )
                    ) : (
                      <ChevronsUpDown size={14} className="text-gray-300" />
                    ))}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {sorted.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-4 py-8 text-center text-gray-400"
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            sorted.map((row) => (
              <tr key={rowKey(row)} className="hover:bg-gray-50 transition-colors">
                {columns.map((col) => (
                  <td key={String(col.key)} className="px-4 py-3 text-gray-700">
                    {col.render
                      ? col.render(row)
                      : String((row as Record<string, unknown>)[String(col.key)] ?? '')}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
