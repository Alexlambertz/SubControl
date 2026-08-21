import { post, postFormData } from './client'
import type {
  InsuranceCandidate,
  MigrateToInsurancePayload,
  ExtractedRecord,
  Insurance,
} from '../types'

export const aiImportApi = {
  detectInsuranceCandidates: (bucketId: string) =>
    post<{ candidates: InsuranceCandidate[] }>(
      `/buckets/${bucketId}/insurances/detect-candidates`,
    ).then((r) => r.candidates),

  migrateToInsurance: (bucketId: string, subId: string, data: MigrateToInsurancePayload) =>
    post<Insurance>(
      `/buckets/${bucketId}/subscriptions/${subId}/migrate-to-insurance`,
      data,
    ),

  extractFromDocument: (bucketId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return postFormData<{ records: ExtractedRecord[] }>(
      `/buckets/${bucketId}/ai-import/extract`,
      form,
    ).then((r) => r.records)
  },
}
