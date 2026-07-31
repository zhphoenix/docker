import { apiFetch } from './api-client'

export interface KnowledgeCollection {
  id: string
  name: string
  description: string | null
  vector_size: number
  distance: string | null
  domain: string | null
  chunk_count: number
  embedded_count: number
  qdrant_points: number | null
}

export interface KnowledgeCollectionsResponse {
  collections: KnowledgeCollection[]
  total: number
}

export function fetchKnowledgeCollections(): Promise<KnowledgeCollectionsResponse> {
  return apiFetch<KnowledgeCollectionsResponse>('/api/knowledge/collections')
}
