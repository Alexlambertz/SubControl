/**
 * Shared TypeScript interfaces mirroring the Pydantic schemas from the backend.
 */

export interface Bucket {
  id: string
  name: string
  created_at: string
}

export interface User {
  id: string
  username: string
  is_admin: boolean
  last_login: string | null
  created_at: string
}

export type RecurringInterval =
  | 'daily'
  | 'weekly'
  | 'monthly'
  | 'quarterly'
  | 'half-year'
  | 'yearly'

export interface Attachment {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  uploaded_at: string
}

export interface AttachmentUploadResult {
  attachment: Attachment
  suggested_updates: Record<string, string | number | null>
}

export interface Subscription {
  id: string
  bucket_id: string
  name: string
  provider_name: string | null
  recurring_interval: RecurringInterval
  recurring_date: string | null
  end_date: string | null
  amount: number
  currency: string
  image_url: string | null
  category_name: string | null
  created_at: string
  updated_at: string
  attachments: Attachment[]
}

export interface Provider {
  id: number
  name: string
}

export interface Insurance {
  id: string
  bucket_id: string
  name: string
  insurer: string
  policy_number: string | null
  recurring_interval: RecurringInterval
  recurring_date: string | null
  end_date: string | null
  amount: number
  currency: string
  category_name: string | null
  notes: string | null
  created_at: string
  updated_at: string
  attachments: Attachment[]
}

export interface Category {
  id: number
  name: string
}

export interface SubscriptionSummaryItem {
  name: string
  monthly_amount: number
  currency: string
  category: string
  kind: 'subscription' | 'insurance'
}

export interface CategoryTotal {
  category: string
  total: number
}

export interface DashboardSummary {
  total_monthly: number
  subscriptions: SubscriptionSummaryItem[]
  by_category: CategoryTotal[]
}

export interface MonthTotal {
  /** "2025-01" */
  month: string
  /** "Jan" */
  label: string
  total: number
}

export interface YearlySummary {
  year: number
  months: MonthTotal[]
}

export interface AppSetting {
  key: string
  value: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ImportResult {
  imported: number
  failed: Array<{ row: number; error: string }>
}

// ---------------------------------------------------------------------------
// AI-assisted insurance discovery & document import
// ---------------------------------------------------------------------------

export type AiConfidence = 'high' | 'medium' | 'low'

export interface InsuranceCandidate {
  subscription_id: string
  name: string
  provider_name: string | null
  amount: number
  currency: string
  recurring_interval: RecurringInterval
  suggested_insurer: string
  suggested_category: string
  confidence: AiConfidence
  reason: string
}

export interface MigrateToInsurancePayload {
  insurer: string
  policy_number?: string
  category_name?: string
  notes?: string
}

export type ExtractedRecordType = 'subscription' | 'insurance'

export interface ExtractedRecordFields {
  name?: string
  provider_name?: string
  insurer?: string
  policy_number?: string
  recurring_interval?: string
  recurring_date?: string
  end_date?: string
  amount?: number
  currency?: string
  category_name?: string
  notes?: string
}

export interface ExtractedRecord {
  type: ExtractedRecordType
  confidence: AiConfidence
  fields: ExtractedRecordFields
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

export interface SearchResultBucket {
  type: 'bucket'
  id: string
  name: string
}

export interface SearchResultSubscription {
  type: 'subscription'
  id: string
  name: string
  amount: number
  currency: string
  recurring_interval: RecurringInterval
  bucket_id: string
  bucket_name: string
  provider_name: string | null
  category_name: string | null
  image_url: string | null
}

export type SearchResult = SearchResultBucket | SearchResultSubscription

export interface SearchResponse {
  query: string
  results: SearchResult[]
}

export interface HistoryEntry {
  id: string
  field: string
  old_value: string | null
  new_value: string | null
  changed_by_username: string
  changed_at: string
}

/** Intervals displayed with human-readable labels */
export const INTERVAL_LABELS: Record<RecurringInterval, string> = {
  daily: 'Daily',
  weekly: 'Weekly',
  monthly: 'Monthly',
  quarterly: 'Quarterly',
  'half-year': 'Half-yearly',
  yearly: 'Yearly',
}
