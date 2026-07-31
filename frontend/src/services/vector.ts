import { apiFetch } from './api-client'

export interface VectorCollection {
  name: string
  points_count?: number
  vectors_count?: number
  indexed_vectors_count?: number
  status: string
  vector_size?: number | null
  distance?: string | null
}

export interface VectorCollectionsResponse {
  collections: VectorCollection[]
  total: number
  error: string | null
}

export function fetchVectorCollections(): Promise<VectorCollectionsResponse> {
  return apiFetch<VectorCollectionsResponse>('/api/vector/collections')
}
