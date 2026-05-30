/**
 * Dashboard page — monthly spend summary + yearly real-cost overview.
 */

import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  AreaChart, Area, CartesianGrid, ReferenceLine,
} from 'recharts'
import { TrendingUp, Filter, X, CalendarDays } from 'lucide-react'
import { dashboardApi } from '../api/dashboard'
import { bucketsApi } from '../api/buckets'
import CurrencyDisplay from '../components/CurrencyDisplay'
import MonthPicker from '../components/MonthPicker'

const COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
  '#8b5cf6', '#ec4899', '#14b8a6', '#f97316',
]

const fmtEur = (v: number) =>
  new Intl.NumberFormat(undefined, { style: 'currency', currency: 'EUR' }).format(v)

export default function Dashboard() {
  const [mode, setMode] = useState<'average' | 'real'>('average')
  const [month, setMonth] = useState(() => {
    const now = new Date()
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  })
  const [bucketId, setBucketId] = useState<string>('')
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)

  const year = parseInt(month.slice(0, 4), 10)

  // Clear category filter when main controls change
  const handleModeChange = useCallback((m: 'average' | 'real') => {
    setMode(m); setSelectedCategory(null)
  }, [])
  const handleMonthChange = useCallback((m: string) => {
    setMonth(m); setSelectedCategory(null)
  }, [])
  const handleBucketChange = useCallback((id: string) => {
    setBucketId(id); setSelectedCategory(null)
  }, [])

  // ── Data fetching ─────────────────────────────────────────────────────────
  const { data: buckets = [] } = useQuery({
    queryKey: ['buckets'],
    queryFn: bucketsApi.list,
  })

  const { data: summary, isLoading } = useQuery({
    queryKey: ['dashboard', mode, month, bucketId],
    queryFn: () =>
      dashboardApi.getSummary({ mode, month, bucket_id: bucketId || undefined }),
  })

  const { data: yearly, isLoading: yearlyLoading } = useQuery({
    queryKey: ['dashboard-yearly', year, bucketId],
    queryFn: () =>
      dashboardApi.getYearlySummary({ year, bucket_id: bucketId || undefined }),
  })

  // Label of the selected month for the reference line ("Jan", "Feb", …)
  const selectedMonthLabel = yearly?.months.find((m) => m.month === month)?.label

  return (
    <div className="space-y-6">
      {/* ── Controls ──────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex rounded-lg overflow-hidden border border-gray-200 bg-white">
          {(['average', 'real'] as const).map((m) => (
            <button
              key={m}
              onClick={() => handleModeChange(m)}
              className={`px-4 py-2 text-sm font-medium capitalize transition ${
                mode === m ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              {m === 'average' ? 'Average monthly' : 'Real monthly'}
            </button>
          ))}
        </div>

        <MonthPicker value={month} onChange={handleMonthChange} />

        <div className="flex items-center gap-2">
          <Filter size={16} className="text-gray-400" />
          <select
            value={bucketId}
            onChange={(e) => handleBucketChange(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none bg-white"
          >
            <option value="">All buckets</option>
            {buckets.map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="text-gray-400 py-12 text-center">Loading…</div>
      ) : summary ? (
        <>
          {/* ── Total card ──────────────────────────────────────────────── */}
          <div className="bg-white rounded-2xl border border-gray-200 p-6 flex items-center gap-4">
            <div className="bg-blue-50 rounded-xl p-3">
              <TrendingUp size={28} className="text-blue-600" />
            </div>
            <div>
              <p className="text-sm text-gray-500 mb-0.5">Total monthly spend</p>
              <p className="text-3xl font-bold text-gray-900">
                <CurrencyDisplay amount={summary.total_monthly} currency="EUR" />
              </p>
            </div>
          </div>

          {/* ── Yearly overview chart ────────────────────────────────────── */}
          <div className="bg-white rounded-2xl border border-gray-200 p-6">
            <div className="flex items-center gap-2 mb-1">
              <CalendarDays size={16} className="text-blue-500" />
              <h2 className="text-base font-semibold text-gray-800">
                Real costs · {year}
              </h2>
            </div>
            <p className="text-xs text-gray-400 mb-5">
              Actual payments due each month based on billing cycles.
            </p>

            {yearlyLoading ? (
              <div className="h-48 flex items-center justify-center text-gray-300 text-sm">
                Loading…
              </div>
            ) : yearly ? (
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart
                  data={yearly.months}
                  margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
                >
                  <defs>
                    <linearGradient id="yearGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>

                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />

                  <XAxis
                    dataKey="label"
                    axisLine={false}
                    tickLine={false}
                    tick={(props: unknown) => {
                      const { x, y, payload } = props as { x: number; y: number; payload: { value: string } }
                      const targetMonth = yearly.months.find((mo) => mo.label === payload.value)?.month
                      const isSelected = payload.value === selectedMonthLabel
                      return (
                        <text
                          x={x} y={y} dy={12}
                          textAnchor="middle"
                          fontSize={12}
                          fill={isSelected ? '#2563eb' : '#9ca3af'}
                          fontWeight={isSelected ? 600 : 400}
                          style={{ cursor: 'pointer', userSelect: 'none' }}
                          onClick={() => targetMonth && handleMonthChange(targetMonth)}
                        >
                          {payload.value}
                        </text>
                      )
                    }}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: '#9ca3af' }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v: number) =>
                      v === 0 ? '0' : v >= 1000 ? `€${(v / 1000).toFixed(1)}k` : `€${v}`
                    }
                    width={48}
                  />

                  <Tooltip
                    formatter={(value) => [fmtEur(Number(value)), 'Total']}
                    contentStyle={{
                      borderRadius: '10px',
                      border: '1px solid #e5e7eb',
                      fontSize: 13,
                    }}
                  />

                  {/* Vertical marker for the currently selected month */}
                  {selectedMonthLabel && (
                    <ReferenceLine
                      x={selectedMonthLabel}
                      stroke="#2563eb"
                      strokeWidth={1.5}
                      strokeDasharray="4 3"
                    />
                  )}

                  <Area
                    type="monotone"
                    dataKey="total"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    fill="url(#yearGradient)"
                    dot={(props: unknown) => {
                      const { cx, cy, payload } = props as { cx: number; cy: number; payload: { month: string; label: string } }
                      const isSelected = payload.label === selectedMonthLabel
                      return (
                        <g
                          key={payload.month}
                          style={{ cursor: 'pointer' }}
                          onClick={() => handleMonthChange(payload.month)}
                        >
                          {/* Transparent hit area */}
                          <circle cx={cx} cy={cy} r={14} fill="transparent" />
                          <circle
                            cx={cx} cy={cy}
                            r={isSelected ? 5 : 3}
                            fill={isSelected ? '#2563eb' : '#3b82f6'}
                            stroke="#fff"
                            strokeWidth={isSelected ? 2 : 1}
                          />
                        </g>
                      )
                    }}
                    activeDot={{ r: 6, fill: '#2563eb', stroke: '#fff', strokeWidth: 2 }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : null}
          </div>

          {/* ── Category breakdown chart ─────────────────────────────────── */}
          {summary.by_category.length > 0 && (
            <div className="bg-white rounded-2xl border border-gray-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-base font-semibold text-gray-800">By category</h2>
                {selectedCategory && (
                  <button
                    onClick={() => setSelectedCategory(null)}
                    className="flex items-center gap-1 text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded-full px-3 py-1 hover:bg-blue-100 transition"
                  >
                    {selectedCategory}
                    <X size={12} />
                  </button>
                )}
              </div>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart
                  data={summary.by_category}
                  layout="vertical"
                  style={{ cursor: 'pointer' }}
                >
                  <XAxis type="number" tick={{ fontSize: 12 }} />
                  <YAxis
                    dataKey="category"
                    type="category"
                    width={120}
                    tick={({ x, y, payload }) => (
                      <text
                        x={x}
                        y={y}
                        dy={4}
                        textAnchor="end"
                        fontSize={12}
                        fill={payload.value === selectedCategory ? '#2563eb' : '#6b7280'}
                        fontWeight={payload.value === selectedCategory ? 600 : 400}
                        style={{ cursor: 'pointer' }}
                        onClick={() =>
                          setSelectedCategory(
                            selectedCategory === payload.value ? null : payload.value,
                          )
                        }
                      >
                        {payload.value}
                      </text>
                    )}
                  />
                  <Tooltip
                    formatter={(value) => fmtEur(Number(value))}
                  />
                  <Bar
                    dataKey="total"
                    radius={[0, 6, 6, 0]}
                    onClick={(data: unknown) => {
                      const cat = (data as { category?: string })?.category
                      if (cat) setSelectedCategory(selectedCategory === cat ? null : cat)
                    }}
                  >
                    {summary.by_category.map((entry, i) => (
                      <Cell
                        key={i}
                        fill={COLORS[i % COLORS.length]}
                        opacity={
                          selectedCategory === null || selectedCategory === entry.category
                            ? 1
                            : 0.3
                        }
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* ── Subscription table ───────────────────────────────────────── */}
          {summary.subscriptions.length > 0 &&
            (() => {
              const visible = selectedCategory
                ? summary.subscriptions.filter((s) => s.category === selectedCategory)
                : summary.subscriptions
              return visible.length > 0 ? (
                <div className="bg-white rounded-2xl border border-gray-200 p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-base font-semibold text-gray-800">
                      Subscriptions
                      {selectedCategory && (
                        <span className="ml-2 text-sm font-normal text-gray-400">
                          — {selectedCategory}
                        </span>
                      )}
                    </h2>
                  </div>
                  <div className="overflow-x-auto">
                  <table className="min-w-full text-sm divide-y divide-gray-100">
                    <thead>
                      <tr className="text-gray-500 text-xs uppercase">
                        <th className="text-left py-2 pr-4">Name</th>
                        <th className="text-right py-2">Monthly amount</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {visible.map((s, i) => (
                        <tr key={i}>
                          <td className="py-2 pr-4 text-gray-700">{s.name}</td>
                          <td className="py-2 text-right font-medium">
                            <CurrencyDisplay amount={s.monthly_amount} currency={s.currency} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  </div>
                </div>
              ) : null
            })()}
        </>
      ) : null}
    </div>
  )
}
