/**
 * Wallos import form — connects to a self-hosted Wallos instance and
 * imports its subscriptions into a chosen SubControl bucket.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle, AlertCircle, Loader2 } from 'lucide-react'
import { importApi } from '../../api/import'
import { bucketsApi } from '../../api/buckets'
import type { ExternalImportResult } from '../../api/import'

export default function WallosImport() {
  const [url, setUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [bucketId, setBucketId] = useState('')
  const [skipInactive, setSkipInactive] = useState(true)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ExternalImportResult | null>(null)
  const [error, setError] = useState('')

  const { data: buckets = [] } = useQuery({
    queryKey: ['buckets'],
    queryFn: bucketsApi.list,
  })

  const handleImport = async () => {
    const trimmedUrl = url.trim()
    const trimmedKey = apiKey.trim()

    if (!trimmedUrl || !trimmedKey || !bucketId) {
      setError('Please fill in all required fields.')
      return
    }

    setLoading(true)
    setError('')
    setResult(null)

    try {
      const res = await importApi.fromWallos({
        url: trimmedUrl,
        api_key: trimmedKey,
        bucket_id: bucketId,
        skip_inactive: skipInactive,
      })
      setResult(res)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Import failed'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6 max-w-xl">
      <p className="text-sm text-gray-500">
        Connect to your{' '}
        <a
          href="https://github.com/ellite/Wallos"
          target="_blank"
          rel="noreferrer"
          className="text-blue-600 hover:underline"
        >
          Wallos
        </a>{' '}
        instance to import all your subscriptions into a SubControl bucket.
      </p>

      {/* Form */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
        {/* URL */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Wallos URL <span className="text-red-500">*</span>
          </label>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://wallos.example.com"
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
          />
        </div>

        {/* API key */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            API key <span className="text-red-500">*</span>
          </label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="Your Wallos API token"
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
          />
          <p className="text-xs text-gray-400 mt-1">
            Found in Wallos → Settings → API.
          </p>
        </div>

        {/* Target bucket */}
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

        {/* Skip inactive toggle */}
        <label className="flex items-center gap-3 cursor-pointer select-none">
          <div
            role="checkbox"
            aria-checked={skipInactive}
            onClick={() => setSkipInactive((v) => !v)}
            className={`relative w-10 h-6 rounded-full transition-colors ${
              skipInactive ? 'bg-blue-600' : 'bg-gray-200'
            }`}
          >
            <div
              className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform ${
                skipInactive ? 'translate-x-5' : 'translate-x-1'
              }`}
            />
          </div>
          <span className="text-sm text-gray-700">Skip inactive subscriptions</span>
        </label>

        {error && (
          <p className="text-sm text-red-500 flex items-center gap-2">
            <AlertCircle size={14} /> {error}
          </p>
        )}

        <button
          onClick={handleImport}
          disabled={loading || !url.trim() || !apiKey.trim() || !bucketId}
          className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 disabled:opacity-40 transition"
        >
          {loading ? (
            <>
              <Loader2 size={16} className="animate-spin" /> Importing…
            </>
          ) : (
            'Import from Wallos'
          )}
        </button>
      </div>

      {/* Results */}
      {result && (
        <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
          <h3 className="text-sm font-semibold text-gray-800">Import result</h3>

          <div className="flex flex-wrap gap-4 text-sm">
            <div className="flex items-center gap-1.5 text-green-700">
              <CheckCircle size={16} className="text-green-500" />
              <span>
                <strong>{result.imported}</strong> imported
              </span>
            </div>
            {result.skipped > 0 && (
              <div className="text-gray-500">
                <strong>{result.skipped}</strong> skipped (inactive)
              </div>
            )}
            {result.failed.length > 0 && (
              <div className="flex items-center gap-1.5 text-red-700">
                <AlertCircle size={16} className="text-red-500" />
                <strong>{result.failed.length}</strong> failed
              </div>
            )}
          </div>

          {result.failed.length > 0 && (
            <div className="border border-red-100 rounded-lg divide-y divide-red-50 text-xs">
              {result.failed.map(({ name, error: e }, i) => (
                <div key={i} className="px-3 py-2 flex gap-3">
                  <span className="text-gray-500 shrink-0 font-medium">{name}</span>
                  <span className="text-red-600">{e}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
