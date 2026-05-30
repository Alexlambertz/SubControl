import { get, post, put, del, postFormData, getBlob } from './client'
import type { Subscription, ImportResult } from '../types'

export interface SubscriptionPayload {
  name: string
  provider_name: string
  recurring_interval: string
  recurring_date?: string
  end_date?: string
  amount: number
  currency?: string
  category_name?: string
}

export const subscriptionsApi = {
  list: (bucketId: string) =>
    get<Subscription[]>(`/buckets/${bucketId}/subscriptions`),
  get: (bucketId: string, subId: string) =>
    get<Subscription>(`/buckets/${bucketId}/subscriptions/${subId}`),
  create: (bucketId: string, data: SubscriptionPayload) =>
    post<Subscription>(`/buckets/${bucketId}/subscriptions`, data),
  update: (bucketId: string, subId: string, data: Partial<SubscriptionPayload>) =>
    put<Subscription>(`/buckets/${bucketId}/subscriptions/${subId}`, data),
  delete: (bucketId: string, subId: string) =>
    del<void>(`/buckets/${bucketId}/subscriptions/${subId}`),
  importCsv: (bucketId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return postFormData<ImportResult>(
      `/buckets/${bucketId}/subscriptions/import`,
      form
    )
  },

  exportCsv: async (bucketId: string, bucketName: string): Promise<void> => {
    const blob = await getBlob(`/buckets/${bucketId}/subscriptions/export`)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${bucketName.replace(/\s+/g, '_')}_subscriptions.csv`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
}
