import { get } from './client'
import type { DashboardSummary, YearlySummary } from '../types'

export const dashboardApi = {
  getSummary: (params: {
    mode?: 'average' | 'real'
    month?: string
    bucket_id?: string
    category_id?: number
  }) =>
    get<DashboardSummary>(
      '/dashboard',
      params as Record<string, string | number | boolean | undefined>,
    ),

  getYearlySummary: (params: { year: number; bucket_id?: string }) =>
    get<YearlySummary>(
      '/dashboard/yearly',
      params as Record<string, string | number | boolean | undefined>,
    ),
}
