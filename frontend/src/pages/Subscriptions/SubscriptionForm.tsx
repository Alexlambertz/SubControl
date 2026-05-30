/**
 * Modal form for creating and editing subscriptions.
 */

import { useState, useRef } from 'react'
import type { ReactNode } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { subscriptionsApi } from '../../api/subscriptions'
import type { Subscription, RecurringInterval } from '../../types'
import { INTERVAL_LABELS } from '../../types'

// Lazy-load providers/categories lists
async function fetchProviders() {
  const res = await fetch('/api/providers')
  return res.json() as Promise<{ id: number; name: string }[]>
}
async function fetchCategories() {
  const res = await fetch('/api/categories')
  return res.json() as Promise<{ id: number; name: string }[]>
}

const INPUT_CLS =
  'w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 outline-none'

interface Props {
  bucketId: string
  subscription?: Subscription
  onClose: () => void
  onSaved: () => void
}

export default function SubscriptionForm({
  bucketId,
  subscription,
  onClose,
  onSaved,
}: Props) {
  const isEdit = !!subscription

  const [name, setName] = useState(subscription?.name ?? '')
  const [providerName, setProviderName] = useState(subscription?.provider_name ?? '')
  const [interval, setInterval] = useState<RecurringInterval>(
    subscription?.recurring_interval ?? 'monthly'
  )
  const [recurringDate, setRecurringDate] = useState(
    subscription?.recurring_date ?? ''
  )
  const [endDate, setEndDate] = useState(subscription?.end_date ?? '')
  const [amount, setAmount] = useState(String(subscription?.amount ?? ''))
  const [currency, setCurrency] = useState(subscription?.currency ?? 'EUR')
  const [categoryName, setCategoryName] = useState(
    subscription?.category_name ?? ''
  )
  const [error, setError] = useState('')

  const { data: providers = [] } = useQuery({
    queryKey: ['providers'],
    queryFn: fetchProviders,
  })

  const { data: categories = [] } = useQuery({
    queryKey: ['categories'],
    queryFn: fetchCategories,
  })

  const saveMut = useMutation({
    mutationFn: () => {
      const data = {
        name,
        provider_name: providerName,
        recurring_interval: interval,
        recurring_date: recurringDate || undefined,
        end_date: endDate || undefined,
        amount: parseFloat(amount),
        currency,
        category_name: categoryName || undefined,
      }
      return isEdit
        ? subscriptionsApi.update(bucketId, subscription!.id, data)
        : subscriptionsApi.create(bucketId, data)
    },
    onSuccess: onSaved,
    onError: (e: Error) => setError(e.message),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-lg mx-4 p-6 overflow-y-auto max-h-[90vh]">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-gray-900">
            {isEdit ? 'Edit subscription' : 'Add subscription'}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition"
          >
            <X size={20} />
          </button>
        </div>

        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            if (!name.trim()) {
              setError('Name is required')
              return
            }
            saveMut.mutate()
          }}
        >
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Name *
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={INPUT_CLS}
              placeholder="e.g. Netflix Premium"
            />
          </div>

          {/* Provider */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Provider *
            </label>
            <input
              list="providers-list"
              value={providerName}
              onChange={(e) => setProviderName(e.target.value)}
              className={INPUT_CLS}
              placeholder="e.g. Netflix"
            />
            <datalist id="providers-list">
              {providers.map((p) => (
                <option key={p.id} value={p.name} />
              ))}
            </datalist>
          </div>

          {/* Billing interval */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Billing interval *
            </label>
            <select
              value={interval}
              onChange={(e) => setInterval(e.target.value as RecurringInterval)}
              className={INPUT_CLS}
            >
              {(Object.entries(INTERVAL_LABELS) as [RecurringInterval, string][]).map(
                ([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                )
              )}
            </select>
          </div>

          {/* Last payment date + End date row */}
          <div className="grid grid-cols-2 gap-3">
            <DateField
              label="Last payment date"
              value={recurringDate}
              onChange={setRecurringDate}
            />
            <DateField
              label={
                <>
                  End date{' '}
                  <span className="text-gray-400 font-normal">(optional)</span>
                </>
              }
              value={endDate}
              onChange={setEndDate}
            />
          </div>

          {/* Amount + Currency row */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Amount *
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className={INPUT_CLS}
                placeholder="9.99"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Currency
              </label>
              <input
                value={currency}
                onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                maxLength={3}
                className={INPUT_CLS}
                placeholder="EUR"
              />
            </div>
          </div>

          {/* Category */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Category
            </label>
            <div className="relative">
              <input
                list="categories-list"
                value={categoryName}
                onChange={(e) => setCategoryName(e.target.value)}
                className={INPUT_CLS}
                placeholder="e.g. Streaming"
              />
              {categoryName && (
                <button
                  type="button"
                  onClick={() => setCategoryName('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-gray-400 hover:text-gray-600 transition"
                  title="Clear category"
                >
                  <X size={14} />
                </button>
              )}
            </div>
            <datalist id="categories-list">
              {categories.map((c) => (
                <option key={c.id} value={c.name} />
              ))}
            </datalist>
          </div>

          {error && (
            <p className="text-sm text-red-500">{error}</p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saveMut.isPending}
              className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {saveMut.isPending ? 'Saving…' : isEdit ? 'Save changes' : 'Add'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// DateField — segmented DD / MM / YYYY input with auto-advance and clear
// ---------------------------------------------------------------------------

interface DateFieldProps {
  label: ReactNode
  value: string          // ISO "YYYY-MM-DD" or ""
  onChange: (v: string) => void
}

/**
 * Splits an ISO date string into { dd, mm, yyyy } display parts.
 * Returns empty strings when the value is blank.
 */
function splitIso(iso: string): { dd: string; mm: string; yyyy: string } {
  if (!iso || iso.length < 10) return { dd: '', mm: '', yyyy: '' }
  const [yyyy, mm, dd] = iso.split('-')
  return { dd, mm, yyyy }
}

function DateField({ label, value, onChange }: DateFieldProps) {
  const { dd: initDd, mm: initMm, yyyy: initYyyy } = splitIso(value)
  const [dd, setDd] = useState(initDd)
  const [mm, setMm] = useState(initMm)
  const [yyyy, setYyyy] = useState(initYyyy)

  const mmRef = useRef<HTMLInputElement>(null)
  const yyyyRef = useRef<HTMLInputElement>(null)

  /** Emit change only when all three parts form a valid date. */
  const emit = (nextDd: string, nextMm: string, nextYyyy: string) => {
    if (nextDd.length === 2 && nextMm.length === 2 && nextYyyy.length === 4) {
      const iso = `${nextYyyy}-${nextMm}-${nextDd}`
      // Basic sanity check — avoid emitting obviously bad dates
      const d = new Date(iso)
      if (!isNaN(d.getTime())) {
        onChange(iso)
        return
      }
    }
    // Partial / invalid → clear the external value
    if (value !== '') onChange('')
  }

  const handleClear = () => {
    setDd(''); setMm(''); setYyyy('')
    onChange('')
  }

  const SEG = 'w-8 text-center border-0 outline-none bg-transparent text-sm text-gray-900 placeholder-gray-400 focus:text-blue-600'
  const hasValue = dd || mm || yyyy

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label}
      </label>
      <div className="flex items-center gap-1.5">
        {/* Segmented input pill */}
        <div className="flex-1 flex items-center border border-gray-200 rounded-lg px-2 py-2 bg-white focus-within:ring-2 focus-within:ring-blue-500">
          {/* Day */}
          <input
            type="text"
            inputMode="numeric"
            maxLength={2}
            placeholder="DD"
            value={dd}
            className={SEG}
            onChange={(e) => {
              const v = e.target.value.replace(/\D/g, '').slice(0, 2)
              setDd(v)
              emit(v, mm, yyyy)
              if (v.length === 2) mmRef.current?.focus()
            }}
            onKeyDown={(e) => {
              if (e.key === 'Backspace' && dd === '') {
                // nothing to do — already at first segment
              }
            }}
          />
          <span className="text-gray-300 select-none">.</span>
          {/* Month */}
          <input
            ref={mmRef}
            type="text"
            inputMode="numeric"
            maxLength={2}
            placeholder="MM"
            value={mm}
            className={SEG}
            onChange={(e) => {
              const v = e.target.value.replace(/\D/g, '').slice(0, 2)
              setMm(v)
              emit(dd, v, yyyy)
              if (v.length === 2) yyyyRef.current?.focus()
            }}
            onKeyDown={(e) => {
              if (e.key === 'Backspace' && mm === '') {
                // Let browser handle — focus would naturally go back
              }
            }}
          />
          <span className="text-gray-300 select-none">.</span>
          {/* Year */}
          <input
            ref={yyyyRef}
            type="text"
            inputMode="numeric"
            maxLength={4}
            placeholder="YYYY"
            value={yyyy}
            className="w-12 text-center border-0 outline-none bg-transparent text-sm text-gray-900 placeholder-gray-400 focus:text-blue-600"
            onChange={(e) => {
              const v = e.target.value.replace(/\D/g, '').slice(0, 4)
              setYyyy(v)
              emit(dd, mm, v)
            }}
          />
        </div>

        {/* Clear button / spacer */}
        {hasValue ? (
          <button
            type="button"
            onClick={handleClear}
            className="shrink-0 p-1.5 text-gray-400 hover:text-red-500 rounded-lg hover:bg-red-50 transition"
            title="Clear date"
          >
            <X size={14} />
          </button>
        ) : (
          <span className="shrink-0 w-7" />
        )}
      </div>
    </div>
  )
}
