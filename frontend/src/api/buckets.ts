import { get, post, put, del } from './client'
import type { Bucket } from '../types'

export const bucketsApi = {
  list: () => get<Bucket[]>('/buckets'),
  get: (id: string) => get<Bucket>(`/buckets/${id}`),
  create: (name: string) => post<Bucket>('/buckets', { name }),
  update: (id: string, name: string) => put<Bucket>(`/buckets/${id}`, { name }),
  delete: (id: string) => del<void>(`/buckets/${id}`),
  assignUser: (bucketId: string, userId: string) =>
    post<{ user_id: string; bucket_id: string }>(`/buckets/${bucketId}/users/${userId}`),
  removeUser: (bucketId: string, userId: string) =>
    del<{ user_id: string; bucket_id: string }>(`/buckets/${bucketId}/users/${userId}`),
}
