import { get, post, del } from './client'
import type { User } from '../types'

export const usersApi = {
  me: () => get<User>('/auth/me'),
  login: () => post<User>('/auth/login'),
  list: () => get<User[]>('/users'),
  get: (id: string) => get<User>(`/users/${id}`),
  delete: (id: string) => del<void>(`/users/${id}`),
}
