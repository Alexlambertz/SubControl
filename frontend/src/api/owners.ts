import { get, post } from './client'
import type { Owner } from '../types'

export const ownersApi = {
  list: (bucketId: string) => get<Owner[]>(`/buckets/${bucketId}/owners`),
  create: (bucketId: string, name: string) =>
    post<Owner>(`/buckets/${bucketId}/owners`, { name }),
}
