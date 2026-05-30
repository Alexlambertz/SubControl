import { get } from './client'
import type { SearchResponse } from '../types'

export const searchApi = {
  search: (q: string) =>
    get<SearchResponse>('/search', { q }),
}
