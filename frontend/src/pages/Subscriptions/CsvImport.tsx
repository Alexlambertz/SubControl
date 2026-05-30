/**
 * CSV import / export modal.
 */

import { useRef, useState } from 'react'
import { Upload, Download, X, CheckCircle, AlertCircle } from 'lucide-react'
import { subscriptionsApi } from '../../api/subscriptions'
import type { ImportResult } from '../../types'

interface Props {
  bucketId: string
  bucketName: string
  onClose: () => void
  onImported: () => void
}

export default function CsvImport({ bucketId, bucketName, onClose, onImported }: Props) {
  const [dragging, setDragging] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = async (file: File) => {
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const res = await subscriptionsApi.importCsv(bucketId, file)
      setResult(res)
      if (res.imported > 0) onImported()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Import failed')
    } finally {
      setLoading(false)
    }
  }

  const handleExport = async () => {
    setExporting(true)
    setError('')
    try {
      await subscriptionsApi.exportCsv(bucketId, bucketName)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-lg mx-4 p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-gray-900">Import / Export</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        {/* ── Import section ────────────────────────────────────────────────── */}
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
          Import
        </p>

        <div
          className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition ${
            dragging ? 'border-blue-400 bg-blue-50' : 'border-gray-200 hover:border-blue-300'
          }`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            const file = e.dataTransfer.files[0]
            if (file) handleFile(file)
          }}
          onClick={() => inputRef.current?.click()}
        >
          <Upload className="mx-auto text-gray-400 mb-2" size={32} />
          <p className="text-sm text-gray-600">
            Drop a CSV file here, or{' '}
            <span className="text-blue-600 font-medium">browse</span>
          </p>
          <p className="text-xs text-gray-400 mt-1">
            Columns: name, provider, recurring_interval, recurring_date,
            end_date, amount, currency, category
          </p>
        </div>

        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) handleFile(file)
          }}
        />

        {loading && (
          <p className="mt-3 text-sm text-gray-500 text-center">Importing…</p>
        )}

        {error && (
          <p className="mt-3 text-sm text-red-500">{error}</p>
        )}

        {result && (
          <div className="mt-4 space-y-2">
            <div className="flex items-center gap-2 text-sm">
              <CheckCircle size={16} className="text-green-500" />
              <span className="font-medium text-green-700">
                {result.imported} subscription{result.imported !== 1 ? 's' : ''} imported
              </span>
            </div>
            {result.failed.length > 0 && (
              <div>
                <div className="flex items-center gap-2 text-sm mb-2">
                  <AlertCircle size={16} className="text-red-500" />
                  <span className="font-medium text-red-700">
                    {result.failed.length} row{result.failed.length !== 1 ? 's' : ''} failed
                  </span>
                </div>
                <div className="border border-red-100 rounded-lg divide-y divide-red-50 text-xs">
                  {result.failed.map(({ row, error: e }) => (
                    <div key={row} className="px-3 py-2 flex gap-3">
                      <span className="text-gray-400 shrink-0">Row {row + 1}</span>
                      <span className="text-red-600">{e}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── Export section ────────────────────────────────────────────────── */}
        <div className="mt-5 pt-4 border-t border-gray-100">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-3">
            Export
          </p>
          <button
            onClick={handleExport}
            disabled={exporting}
            className="flex items-center gap-2 w-full justify-center px-4 py-2.5 rounded-xl border border-gray-200 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition"
          >
            <Download size={16} className="text-gray-500" />
            {exporting ? 'Preparing download…' : 'Download CSV'}
          </button>
          <p className="text-xs text-gray-400 mt-1.5 text-center">
            Exports all subscriptions in this bucket
          </p>
        </div>

        <div className="mt-5 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
