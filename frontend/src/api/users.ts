import { get, post, patch, del } from './client'
import type { User } from '../types'

export const usersApi = {
  me: () => get<User>('/auth/me'),
  login: () => post<User>('/auth/login'),
  list: () => get<User[]>('/users'),
  get: (id: string) => get<User>(`/users/${id}`),
  /** Returns the list of bucket IDs assigned to this user. */
  getBuckets: (id: string) => get<string[]>(`/users/${id}/buckets`),
  /** Toggle admin status. */
  setAdmin: (id: string, isAdmin: boolean) =>
    patch<User>(`/users/${id}`, { is_admin: isAdmin }),
  delete: (id: string) => del<void>(`/users/${id}`),
}
