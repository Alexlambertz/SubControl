/**
 * "Find Insurances" wizard — scans a bucket's subscriptions with AI to flag
 * ones that look like insurance policies, then lets the user pick which to
 * migrate (convert) into proper insurance records. Nothing is created or
 * deleted until the user explicitly clicks "Migrate selected".
 */

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Sparkles, ShieldCheck, CheckCircle, AlertCircle, X } from 'lucide-react'
import { bucketsApi } from '../../api/buckets'
import { aiImportApi } from '../../api/aiImport'
import CurrencyDisplay from '../../components/CurrencyDisplay'
import IntervalBadge from '../../components/IntervalBadge'
import type { InsuranceCandidate } from '../../types'

interface Row extends InsuranceCandidate {
  selected: boolean
  insurer: string
  category: string
}

const CONFIDENCE_STYLE: Record<string, string> = {
  high: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  medium: 'bg-amber-50 text-amber-700 border-amber-200',
  low: 'bg-gray-50 text-gray-500 border-gray-200',
}

export default function FindInsurancesPanel() {
  const qc = useQueryClient()
  const [bucketId, setBucketId] = useState('')
  const [scanning, setScanning] = useState(false)
  const [rows, setRows] = useState<Row[] | null>(null)
  const [error, setError] = useState('')
  const [migrating, setMigrating] = useState(false)
  const [result, setResult] = useState<{ migrated: number; failed: string[] } | null>(null)

  const { data: buckets = [] } = useQuery({
    queryKey: ['buckets'],
    queryFn: bucketsApi.list,
  })

  const handleScan = async () => {
    if (!bucketId) { setError('Please select a bucket first.'); return }
    setScanning(true)
    setError('')
    setResult(null)
    setRows(null)
    try {
      const candidates = await aiImportApi.detectInsuranceCandidates(bucketId)
      setRows(
        candidates.map((c) => ({
          ...c,
          selected: c.confidence === 'high',
          insurer: c.suggested_insurer,
          category: c.suggested_category,
        })),
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Scan failed')
    } finally {
      setScanning(false)
    }
  }

  const updateRow = (id: string, patch: Partial<Row>) => {
    setRows((prev) => prev?.map((r) => (r.subscription_id === id ? { ...r, ...patch } : r)) ?? null)
  }

  const selectedRows = rows?.filter((r) => r.selected) ?? []

  const handleMigrate = async () => {
    if (!bucketId || selectedRows.length === 0) return
    setMigrating(true)
    const failed: string[] = []
    let migrated = 0
    for (const row of selectedRows) {
      try {
        await aiImportApi.migrateToInsurance(bucketId, row.subscription_id, {
          insurer: row.insurer,
          category_name: row.category || undefined,
        })
        migrated++
      } catch (e) {
        failed.push(`${row.name}: ${e instanceof Error ? e.message : 'failed'}`)
      }
    }
    setMigrating(false)
    setResult({ migrated, failed })
    setRows((prev) => prev?.filter((r) => !selectedRows.some((s) => s.subscription_id === r.subscription_id)) ?? null)
    qc.invalidateQueries({ queryKey: ['subscriptions', bucketId] })
    qc.invalidateQueries({ queryKey: ['insurances', bucketId] })
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <p className="text-sm text-gray-500">
        AI scans a bucket's subscriptions and flags ones that look like insurance
        policies. Review the suggestions below, adjust the insurer/category if
        needed, then choose which ones to migrate — nothing changes until you
        confirm.
      </p>

      <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Bucket to scan <span className="text-red-500">*</span>
          </label>
          <div className="flex gap-3">
            <select
              value={bucketId}
              onChange={(e) => { setBucketId(e.target.value); setRows(null); setResult(null) }}
              className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none bg-white"
            >
              <option value="">Select a bucket…</option>
              {buckets.map((b) => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>
            <button
              onClick={handleScan}
              disabled={!bucketId || scanning}
              className="flex items-center gap-2 bg-blue-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition shrink-0"
            >
              <Sparkles size={15} />
              {scanning ? 'Scanning…' : 'Scan for insurances'}
            </button>
          </div>
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}
      </div>

      {rows && rows.length === 0 && (
        <div className="bg-white rounded-2xl border border-gray-200 py-10 text-center">
          <p className="text-gray-400 text-sm">No insurance-like subscriptions found in this bucket.</p>
        </div>
      )}

      {rows && rows.length > 0 && (
        <div className="bg-white rounded-2xl border border-gray-200 divide-y divide-gray-100">
          {rows.map((row) => (
            <div key={row.subscription_id} className="flex items-start gap-3 px-4 py-3">
              <input
                type="checkbox"
                checked={row.selected}
                onChange={(e) => updateRow(row.subscription_id, { selected: e.target.checked })}
                className="mt-1.5 shrink-0"
              />
              <div className="flex-1 min-w-0 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-medium text-gray-800 truncate">{row.name}</p>
                    <p className="text-xs text-gray-400">{row.provider_name ?? 'no provider'}</p>
                  </div>
                  <div className="text-right shrink-0 ml-2">
                    <CurrencyDisplay amount={row.amount} currency={row.currency} className="font-semibold text-gray-800 text-sm" />
                    <div className="mt-0.5"><IntervalBadge interval={row.recurring_interval} /></div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <span className={`text-xs px-2 py-0.5 rounded-full border ${CONFIDENCE_STYLE[row.confidence]}`}>
                    {row.confidence} confidence
                  </span>
                  {row.reason && <span className="text-xs text-gray-400">{row.reason}</span>}
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <input
                    value={row.insurer}
                    onChange={(e) => updateRow(row.subscription_id, { insurer: e.target.value })}
                    placeholder="Insurer"
                    className="border border-gray-200 rounded-lg px-2.5 py-1.5 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                  />
                  <input
                    value={row.category}
                    onChange={(e) => updateRow(row.subscription_id, { category: e.target.value })}
                    placeholder="Category"
                    className="border border-gray-200 rounded-lg px-2.5 py-1.5 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                  />
                </div>
              </div>
            </div>
          ))}

          <div className="px-4 py-3 flex justify-end">
            <button
              onClick={handleMigrate}
              disabled={selectedRows.length === 0 || migrating}
              className="flex items-center gap-2 bg-blue-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition"
            >
              <ShieldCheck size={15} />
              {migrating ? 'Migrating…' : `Migrate ${selectedRows.length} selected`}
            </button>
          </div>
        </div>
      )}

      {result && (
        <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-3">
          <h3 className="text-sm font-semibold text-gray-800">Migration result</h3>
          <div className="flex items-center gap-1.5 text-sm text-green-700">
            <CheckCircle size={16} className="text-green-500" />
            <strong>{result.migrated}</strong> migrated to insurances
          </div>
          {result.failed.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5 text-sm text-red-700">
                <AlertCircle size={16} className="text-red-500" />
                <strong>{result.failed.length}</strong> failed
              </div>
              {result.failed.map((f, i) => (
                <p key={i} className="text-xs text-red-600 pl-6">{f}</p>
              ))}
            </div>
          )}
          <button
            onClick={() => setResult(null)}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600"
          >
            <X size={12} /> Dismiss
          </button>
        </div>
      )}
    </div>
  )
}
