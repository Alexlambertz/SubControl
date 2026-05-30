import { get, put } from './client'
import type { AppSetting } from '../types'

export const settingsApi = {
  list: () => get<AppSetting[]>('/settings'),
  get: (key: string) => get<AppSetting>(`/settings/${key}`),
  update: (key: string, value: string) =>
    put<AppSetting>(`/settings/${key}`, { value }),
}
