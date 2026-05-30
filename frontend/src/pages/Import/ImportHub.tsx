/**
 * Import Hub — tabbed page for all subscription import sources.
 *
 * Adding a new importer:
 *   1. Create its component in this directory.
 *   2. Add an entry to the TABS array below.
 */

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Globe, Upload, CheckCircle, AlertCircle } from 'lucide-react'
import { bucketsApi } from '../../api/buckets'
import { subscriptionsApi } from '../../api/subscriptions'
import WallosImport from './WallosImport'
import type { ImportResult } from '../../types'

// ---------------------------------------------------------------------------
// Tab definition — extend here for future importers
// ---------------------------------------------------------------------------

const TABS = [
  { id: 'csv',    label: 'CSV',    icon: FileText },
  { id: 'wallos', label: 'WallOS', icon: Globe },
] as const

type TabId = (typeof TABS)[number]['id']

// ---------------------------------------------------------------------------
// Inline CSV import panel (standalone variant — no modal wrapper)
// ---------------------------------------------------------------------------

function CsvImportPanel() {
  const qc = useQueryClient()
  const [bucketId, setBucketId] = useState('')
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState('')

  const { data: buckets = [] } = useQuery({
    queryKey: ['buckets'],
    queryFn: bucketsApi.list,
  })

  const handleFile = async (file: File) => {
    if (!bucketId) {
      setError('Please select a bucket first.')
      return
    }
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const res = await subscriptionsApi.importCsv(bucketId, file)
      setResult(res)
      if (res.imported > 0) {
        qc.invalidateQueries({ queryKey: ['subscriptions', bucketId] })
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Import failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6 max-w-xl">
      <p className="text-sm text-gray-500">
        Upload a CSV file to bulk-import subscriptions into a bucket. Providers and
        categories are created automatically.
      </p>

      <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
        {/* Bucket selector */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Import into bucket <span className="text-red-500">*</span>
          </label>
          <select
            value={bucketId}
            onChange={(e) => setBucketId(e.target.value)}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none bg-white"
          >
            <option value="">Select a bucket…</option>
            {buckets.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </div>

        {/* Drop zone */}
        <div
          className={`border-2 border-dashed rounded-xl p-8 text-center transition ${
            bucketId
              ? dragging
                ? 'border-blue-400 bg-blue-50 cursor-pointer'
                : 'border-gray-200 hover:border-blue-300 cursor-pointer'
              : 'border-gray-100 opacity-50 cursor-not-allowed'
          }`}
          onDragOver={(e) => {
            if (!bucketId) return
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            if (!bucketId) return
            const file = e.dataTransfer.files[0]
            if (file) handleFile(file)
          }}
          onClick={() => {
            if (!bucketId) return
            document.getElementById('csv-file-input')?.click()
          }}
        >
          <Upload className="mx-auto text-gray-400 mb-2" size={32} />
          <p className="text-sm text-gray-600">
            Drop a CSV file here, or{' '}
            <span className="text-blue-600 font-medium">browse</span>
          </p>
          <p className="text-xs text-gray-400 mt-1">
            Columns: name, provider, recurring_interval, recurring_date, amount,
            currency, category
          </p>
        </div>

        <input
          id="csv-file-input"
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) handleFile(file)
            // Reset so the same file can be re-selected
            e.target.value = ''
          }}
        />

        {loading && (
          <p className="text-sm text-gray-500 text-center">Importing…</p>
        )}
        {error && <p className="text-sm text-red-500">{error}</p>}
      </div>

      {/* Results */}
      {result && (
        <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
          <h3 className="text-sm font-semibold text-gray-800">Import result</h3>

          <div className="flex items-center gap-1.5 text-sm text-green-700">
            <CheckCircle size={16} className="text-green-500" />
            <strong>{result.imported}</strong>&nbsp;subscription
            {result.imported !== 1 ? 's' : ''} imported
          </div>

          {result.failed.length > 0 && (
            <>
              <div className="flex items-center gap-1.5 text-sm text-red-700">
                <AlertCircle size={16} className="text-red-500" />
                <strong>{result.failed.length}</strong> row
                {result.failed.length !== 1 ? 's' : ''} failed
              </div>
              <div className="border border-red-100 rounded-lg divide-y divide-red-50 text-xs">
                {result.failed.map(({ row, error: e }) => (
                  <div key={row} className="px-3 py-2 flex gap-3">
                    <span className="text-gray-400 shrink-0">Row {row + 1}</span>
                    <span className="text-red-600">{e}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hub
// ---------------------------------------------------------------------------

export default function ImportHub() {
  const [activeTab, setActiveTab] = useState<TabId>('csv')

  return (
    <div className="space-y-6">
      {/* Tab bar */}
      <div className="flex gap-1 bg-gray-100 rounded-xl p-1 w-fit">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition ${
              activeTab === id
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            <Icon size={15} />
            {label}
          </button>
        ))}
      </div>

      {/* Panel */}
      {activeTab === 'csv'    && <CsvImportPanel />}
      {activeTab === 'wallos' && <WallosImport />}
    </div>
  )
}
