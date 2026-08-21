/**
 * Modal form for creating and editing subscriptions.
 */

import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { subscriptionsApi } from '../../api/subscriptions'
import { get } from '../../api/client'
import DateField from '../../components/DateField'
import type { Subscription, RecurringInterval } from '../../types'
import { INTERVAL_LABELS } from '../../types'

// Lazy-load providers/categories lists — must use authenticated client
async function fetchProviders(): Promise<{ id: number; name: string }[]> {
  const data = await get<{ id: number; name: string }[] | unknown>('/providers')
  return Array.isArray(data) ? data : []
}
async function fetchCategories(): Promise<{ id: number; name: string }[]> {
  const data = await get<{ id: number; name: string }[] | unknown>('/categories')
  return Array.isArray(data) ? data : []
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
