/**
 * Dashboard page — monthly spend summary + yearly real-cost overview.
 */

import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  AreaChart, Area, CartesianGrid, ReferenceLine,
} from 'recharts'
import { TrendingUp, Filter, X, CalendarDays, Shield } from 'lucide-react'
import { dashboardApi } from '../api/dashboard'
import { bucketsApi } from '../api/buckets'
import CurrencyDisplay from '../components/CurrencyDisplay'
import MonthPicker from '../components/MonthPicker'
import IntervalBadge from '../components/IntervalBadge'
import SortableTable, { type Column } from '../components/SortableTable'
import type { SubscriptionSummaryItem } from '../types'

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
            <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <CalendarDays size={16} className="text-blue-500" />
                <h2 className="text-base font-semibold text-gray-800">
                  Real costs · {year}
                </h2>
              </div>
              <div className="flex items-center gap-3 text-xs">
                <span className="inline-flex items-center gap-1.5 text-gray-500">
                  <span className="w-2 h-2 rounded-full bg-blue-500" />
                  Baseline
                </span>
                <span className="inline-flex items-center gap-1.5 text-gray-500">
                  <span className="w-2 h-2 rounded-full bg-amber-500" />
                  On top
                </span>
              </div>
            </div>
            <p className="text-xs text-gray-400 mb-5">
              Baseline is recurring monthly spend; on-top is non-monthly charges landing that month.
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
                    <linearGradient id="baselineGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.05} />
                    </linearGradient>
                    <linearGradient id="onTopGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#f59e0b" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#f59e0b" stopOpacity={0.05} />
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
                    formatter={(value, name) => [
                      fmtEur(Number(value)),
                      name === 'baseline' ? 'Baseline' : name === 'on_top' ? 'On top' : 'Total',
                    ]}
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
                    dataKey="baseline"
                    stackId="1"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    fill="url(#baselineGradient)"
                    activeDot={{ r: 5, fill: '#2563eb', stroke: '#fff', strokeWidth: 2 }}
                  />
                  <Area
                    type="monotone"
                    dataKey="on_top"
                    stackId="1"
                    stroke="#f59e0b"
                    strokeWidth={2}
                    fill="url(#onTopGradient)"
                    activeDot={{ r: 5, fill: '#d97706', stroke: '#fff', strokeWidth: 2 }}
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
              if (visible.length === 0) return null

              const baselineTotal = visible
                .filter((s) => s.is_baseline)
                .reduce((sum, s) => sum + s.monthly_amount, 0)
              const onTopTotal = visible
                .filter((s) => !s.is_baseline)
                .reduce((sum, s) => sum + s.monthly_amount, 0)

              const columns: Column<SubscriptionSummaryItem>[] = [
                {
                  key: 'name',
                  label: 'Name',
                  render: (s) => (
                    <span className="inline-flex items-center gap-1.5">
                      {s.kind === 'insurance' && (
                        <Shield size={13} className="text-blue-400 shrink-0" />
                      )}
                      {s.name}
                    </span>
                  ),
                },
                {
                  key: 'recurring_interval',
                  label: 'Interval',
                  render: (s) => <IntervalBadge interval={s.recurring_interval} />,
                },
                {
                  key: 'is_baseline',
                  label: 'Type',
                  render: (s) => (
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full border ${
                        s.is_baseline
                          ? 'bg-blue-50 text-blue-600 border-blue-200'
                          : 'bg-amber-50 text-amber-600 border-amber-200'
                      }`}
                    >
                      {s.is_baseline ? 'Baseline' : 'On top'}
                    </span>
                  ),
                },
                {
                  key: 'monthly_amount',
                  label: 'Monthly amount',
                  render: (s) => (
                    <span className="font-medium">
                      <CurrencyDisplay amount={s.monthly_amount} currency={s.currency} />
                    </span>
                  ),
                },
              ]

              return (
                <div className="bg-white rounded-2xl border border-gray-200 p-6">
                  <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
                    <h2 className="text-base font-semibold text-gray-800">
                      Subscriptions
                      {selectedCategory && (
                        <span className="ml-2 text-sm font-normal text-gray-400">
                          — {selectedCategory}
                        </span>
                      )}
                    </h2>
                    <div className="flex items-center gap-3 text-xs">
                      <span className="inline-flex items-center gap-1.5 text-gray-500">
                        <span className="w-2 h-2 rounded-full bg-blue-500" />
                        Baseline: {fmtEur(baselineTotal)}
                      </span>
                      <span className="inline-flex items-center gap-1.5 text-gray-500">
                        <span className="w-2 h-2 rounded-full bg-amber-500" />
                        On top: {fmtEur(onTopTotal)}
                      </span>
                    </div>
                  </div>
                  <SortableTable
                    columns={columns}
                    data={visible}
                    rowKey={(s) => `${s.kind}:${s.name}:${s.category}:${s.monthly_amount}`}
                    defaultSort={{ key: 'name', dir: 'asc' }}
                  />
                </div>
              )
            })()}
        </>
      ) : null}
    </div>
  )
}
