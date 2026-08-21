import { get, post, put, del, postFormData, getBlob } from './client'
import type { Insurance, AttachmentUploadResult, HistoryEntry } from '../types'

export interface InsurancePayload {
  name: string
  insurer: string
  policy_number?: string | null
  recurring_interval: string
  recurring_date?: string | null
  end_date?: string | null
  amount: number
  currency?: string
  category_name?: string | null
  notes?: string | null
}

export const insurancesApi = {
  list: (bucketId: string) =>
    get<Insurance[]>(`/buckets/${bucketId}/insurances`),
  get: (bucketId: string, insuranceId: string) =>
    get<Insurance>(`/buckets/${bucketId}/insurances/${insuranceId}`),
  create: (bucketId: string, data: InsurancePayload) =>
    post<Insurance>(`/buckets/${bucketId}/insurances`, data),
  update: (bucketId: string, insuranceId: string, data: Partial<InsurancePayload>) =>
    put<Insurance>(`/buckets/${bucketId}/insurances/${insuranceId}`, data),
  delete: (bucketId: string, insuranceId: string) =>
    del<void>(`/buckets/${bucketId}/insurances/${insuranceId}`),

  uploadAttachment: (bucketId: string, insuranceId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return postFormData<AttachmentUploadResult>(
      `/buckets/${bucketId}/insurances/${insuranceId}/attachments`,
      form,
    )
  },

  downloadAttachment: async (
    bucketId: string,
    insuranceId: string,
    attachmentId: string,
    filename: string,
  ): Promise<void> => {
    const blob = await getBlob(
      `/buckets/${bucketId}/insurances/${insuranceId}/attachments/${attachmentId}`,
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

  deleteAttachment: (bucketId: string, insuranceId: string, attachmentId: string) =>
    del<void>(`/buckets/${bucketId}/insurances/${insuranceId}/attachments/${attachmentId}`),

  getHistory: (bucketId: string, insuranceId: string) =>
    get<HistoryEntry[]>(`/buckets/${bucketId}/insurances/${insuranceId}/history`),
}
