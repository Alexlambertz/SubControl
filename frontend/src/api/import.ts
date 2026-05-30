/**
 * External-source import API.
 */

import { post } from './client'

export interface WallosImportRequest {
  url: string
  api_key: string
  bucket_id: string
  skip_inactive?: boolean
}

export interface ExternalImportResult {
  imported: number
  skipped: number
  failed: Array<{ name: string; error: string }>
}

export const importApi = {
  fromWallos: (body: WallosImportRequest) =>
    post<ExternalImportResult>('/import/wallos', body),
}
