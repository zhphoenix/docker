import { apiFetch } from './api-client'

// ─── Collection ───────────────────────────────────────────

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

// ─── Entity ───────────────────────────────────────────────

export interface KnowledgeEntity {
  id: string
  name: string
  entity_type: string
  description: string | null
  canonical_name: string | null
  confidence: number | null
  source_count: number
  aliases?: string[]
  properties?: Record<string, unknown>
}

export interface EntitiesResponse {
  entities: KnowledgeEntity[]
  total: number
}

export function fetchEntities(params?: {
  name?: string
  entity_type?: string
  limit?: number
}): Promise<EntitiesResponse> {
  const searchParams = new URLSearchParams()
  if (params?.name) searchParams.set('name', params.name)
  if (params?.entity_type) searchParams.set('entity_type', params.entity_type)
  if (params?.limit) searchParams.set('limit', String(params.limit))
  const qs = searchParams.toString()
  return apiFetch<EntitiesResponse>(`/api/knowledge/entities${qs ? `?${qs}` : ''}`)
}

export function fetchEntityDetail(entityId: string): Promise<KnowledgeEntity> {
  return apiFetch<KnowledgeEntity>(`/api/knowledge/entities/${entityId}`)
}

// ─── Graph ────────────────────────────────────────────────

export interface GraphEdge {
  source_entity: string
  target_entity: string
  relation_type: string
  depth: number
}

export interface NeighborsResponse {
  entity_id: string
  depth: number
  neighbors: GraphEdge[]
  total: number
}

export function fetchEntityNeighbors(
  entityId: string,
  depth = 1
): Promise<NeighborsResponse> {
  return apiFetch<NeighborsResponse>(
    `/api/knowledge/entities/${entityId}/neighbors?depth=${depth}`
  )
}

// ─── Facts ────────────────────────────────────────────────

export interface KnowledgeFact {
  id: string
  predicate: string
  object_value: unknown
  unit: string | null
  time_start: string | null
  time_end: string | null
  confidence: number | null
  verification_status?: string | null
}

export interface FactsResponse {
  facts: KnowledgeFact[]
  total: number
}

export function fetchFacts(
  subject: string,
  predicate?: string
): Promise<FactsResponse> {
  const searchParams = new URLSearchParams({ subject })
  if (predicate) searchParams.set('predicate', predicate)
  return apiFetch<FactsResponse>(`/api/knowledge/facts?${searchParams.toString()}`)
}

// ─── Hybrid Search ────────────────────────────────────────

export interface VectorSearchResults {
  entities: Array<{ id: string; score: number; payload: Record<string, unknown> }>
  facts: Array<{ id: string; score: number; payload: Record<string, unknown> }>
}

export interface HybridSearchResult {
  query: string
  graph_results: GraphEdge[]
  vector_results: VectorSearchResults
  entity_ids_used: string[]
}

export function searchKnowledge(params: {
  query: string
  entity_name?: string
  limit?: number
}): Promise<HybridSearchResult> {
  return apiFetch<HybridSearchResult>('/api/knowledge/search', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}
