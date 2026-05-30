/**
 * Settings page — configure the AI endpoint, model, and API key.
 * Also provides maintenance utilities (e.g. logo regeneration per bucket).
 */

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, Eye, EyeOff, RefreshCw } from 'lucide-react'
import { settingsApi } from '../api/settings'
import { bucketsApi } from '../api/buckets'
import { subscriptionsApi } from '../api/subscriptions'

export default function Settings() {
  const qc = useQueryClient()

  // ── AI settings ───────────────────────────────────────────────────────────
  const { data: settings = [] } = useQuery({
    queryKey: ['settings'],
    queryFn: settingsApi.list,
  })

  const [aiUrl, setAiUrl] = useState('')
  const [aiModel, setAiModel] = useState('')
  const [aiKey, setAiKey] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    const get = (key: string) => settings.find((s) => s.key === key)?.value ?? ''
    setAiUrl(get('ai_api_url'))
    setAiModel(get('ai_model'))
    setAiKey(get('ai_api_key'))
  }, [settings])

  const saveMut = useMutation({
    mutationFn: async () => {
      await settingsApi.update('ai_api_url', aiUrl)
      await settingsApi.update('ai_model', aiModel)
      await settingsApi.update('ai_api_key', aiKey)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  // ── Logo maintenance ──────────────────────────────────────────────────────
  const { data: buckets = [] } = useQuery({
    queryKey: ['buckets'],
    queryFn: bucketsApi.list,
  })

  const [logoBucketId, setLogoBucketId] = useState('')
  const [logoMsg, setLogoMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)

  // Pre-select first bucket once loaded
  useEffect(() => {
    if (!logoBucketId && buckets.length > 0) {
      setLogoBucketId(buckets[0].id)
    }
  }, [buckets, logoBucketId])

  const logoMut = useMutation({
    mutationFn: () => subscriptionsApi.refreshLogos(logoBucketId),
    onSuccess: (data) => {
      setLogoMsg({
        type: 'ok',
        text: `Logo refresh started for ${data.subscriptions} subscription${data.subscriptions !== 1 ? 's' : ''}.`,
      })
      setTimeout(() => setLogoMsg(null), 4000)
    },
    onError: (err: Error) => {
      setLogoMsg({ type: 'err', text: err.message })
    },
  })

  return (
    <div className="max-w-lg space-y-6">
      {/* ── AI Chat configuration ─────────────────────────────────────────── */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="text-base font-semibold text-gray-800 mb-5">
          AI Chat configuration
        </h2>

        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            saveMut.mutate()
          }}
        >
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              API endpoint URL
            </label>
            <input
              value={aiUrl}
              onChange={(e) => setAiUrl(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
              placeholder="https://api.openai.com/v1"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Model
            </label>
            <input
              value={aiModel}
              onChange={(e) => setAiModel(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
              placeholder="gpt-4o"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              API key
            </label>
            <div className="relative">
              <input
                type={showKey ? 'text' : 'password'}
                value={aiKey}
                onChange={(e) => setAiKey(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 pr-10 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                placeholder="sk-…"
              />
              <button
                type="button"
                onClick={() => setShowKey((s) => !s)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <button
              type="submit"
              disabled={saveMut.isPending}
              className="flex items-center gap-2 bg-blue-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition"
            >
              <Save size={15} />
              {saveMut.isPending ? 'Saving…' : 'Save settings'}
            </button>
            {saved && (
              <span className="text-sm text-green-600">✓ Saved</span>
            )}
          </div>
        </form>
      </div>

      {/* ── Logo maintenance ─────────────────────────────────────────────── */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="text-base font-semibold text-gray-800 mb-1">
          Logo maintenance
        </h2>
        <p className="text-sm text-gray-500 mb-5">
          Re-fetch provider logos for all subscriptions in a bucket. Logos are
          also refreshed automatically when importing from CSV.
        </p>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Bucket
            </label>
            <select
              value={logoBucketId}
              onChange={(e) => setLogoBucketId(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
            >
              {buckets.map((b) => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => logoMut.mutate()}
              disabled={logoMut.isPending || !logoBucketId}
              className="flex items-center gap-2 bg-blue-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition"
            >
              <RefreshCw size={15} className={logoMut.isPending ? 'animate-spin' : ''} />
              {logoMut.isPending ? 'Starting…' : 'Regenerate logos'}
            </button>
            {logoMsg && (
              <span className={`text-sm ${logoMsg.type === 'ok' ? 'text-green-600' : 'text-red-500'}`}>
                {logoMsg.type === 'ok' ? '✓ ' : '✗ '}{logoMsg.text}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
