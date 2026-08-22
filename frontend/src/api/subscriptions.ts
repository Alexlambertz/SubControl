import { get, post, put, patch, del, postFormData, getBlob } from './client'
import type { Subscription, ImportResult, AttachmentUploadResult, HistoryEntry } from '../types'

export interface SubscriptionPayload {
  name: string
  provider_name: string
  recurring_interval: string
  recurring_date?: string | null
  end_date?: string | null
  amount: number
  currency?: string
  category_name?: string | null
  owner_name?: string | null
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

  refreshLogos: (bucketId: string) =>
    post<{ status: string; subscriptions: number }>(
      `/buckets/${bucketId}/subscriptions/refresh-logos`
    ),

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

  uploadAttachment: (bucketId: string, subId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return postFormData<AttachmentUploadResult>(
      `/buckets/${bucketId}/subscriptions/${subId}/attachments`,
      form,
    )
  },

  downloadAttachment: async (
    bucketId: string,
    subId: string,
    attachmentId: string,
    filename: string,
  ): Promise<void> => {
    const blob = await getBlob(
      `/buckets/${bucketId}/subscriptions/${subId}/attachments/${attachmentId}`,
    )
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },

  deleteAttachment: (bucketId: string, subId: string, attachmentId: string) =>
    del<void>(`/buckets/${bucketId}/subscriptions/${subId}/attachments/${attachmentId}`),

  getHistory: (bucketId: string, subId: string) =>
    get<HistoryEntry[]>(`/buckets/${bucketId}/subscriptions/${subId}/history`),

  bulkUpdate: (bucketId: string, ids: string[], update: Partial<SubscriptionPayload>) =>
    patch<{ updated: number }>(`/buckets/${bucketId}/subscriptions/bulk`, { ids, update }),
}
