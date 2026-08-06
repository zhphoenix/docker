import { apiFetch } from './api-client'

// ─── SiYuan 展示层配置 ───────────────────────────────
// 知识图谱以 SiYuan 关系图作为展示层（PG 为唯一数据源 SoT）
export const SIYUAN_URL = import.meta.env.VITE_SIYUAN_URL || 'http://localhost:6806'

export const SIYUAN_GRAPH_GUIDE =
  '打开 SiYuan 后，点击顶部工具栏的「关系图」图标，即可查看基于实体文档链接生成的关联图谱。'

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

// ─── Knowledge Hub Stats ───────────────────────────────────

export interface KnowledgeStatsTask {
  id: string
  title: string
  task_type: string
  status: string
  progress: number
  created_at: string | null
}

export interface KnowledgeStatsUpdate {
  id: string
  market: string
  symbol: string
  company: string | null
  status: string
  chunk_count: number
  updated_at: string | null
}

export interface KnowledgeStats {
  documents: number
  chunks: number
  embedded: number
  entities: number
  facts: number
  task_queue: {
    pending: number
    running: number
    done: number
    failed: number
  }
  recent_tasks: KnowledgeStatsTask[]
  recent_updates: KnowledgeStatsUpdate[]
  quality: {
    avg_chunk_length: number | null
    embedding_coverage: number | null
    entity_confidence: number | null
  }
  collections: KnowledgeCollection[]
}

export function fetchKnowledgeStats(): Promise<KnowledgeStats> {
  return apiFetch<KnowledgeStats>('/api/knowledge/stats')
}

// ─── KOC-D1 Knowledge Analytics ────────────────────────────

export interface KnowledgeAnalytics {
  range_days: number
  growth: {
    entities: number
    relations: number
    facts: number
    events: number
    communities: number
  }
  coverage: {
    knowledge_coverage: number
    entity_fact_coverage: number
    entity_types: number
    embedding_coverage: number | null
  }
  usage: {
    runs: number
    runs_today: number
    top_agents: Array<{ agent_id: string; today: number; total: number }>
  }
  quality: {
    entity_confidence: number | null
    conflicts_open: number
    facts_verified: number
    facts_total: number
  }
  freshness: {
    last_entity_at: string | null
    last_fact_at: string | null
    last_event_at: string | null
    facts_expired: number
    new_entities: number
    new_facts: number
    new_events: number
  }
  trends: {
    range_days: number
    entities: Array<{ date: string; count: number }>
    facts: Array<{ date: string; count: number }>
    events: Array<{ date: string; count: number }>
  }
}

export function fetchKnowledgeAnalytics(rangeDays = 7): Promise<KnowledgeAnalytics> {
  return apiFetch<KnowledgeAnalytics>(`/api/knowledge/analytics?range_days=${rangeDays}`)
}

// ─── KOC-D2 Knowledge Insights ────────────────────────────

export interface KnowledgeInsightTopic {
  topic: string
  count: number
}

export interface InsightEntity {
  name: string
  source_count: number
  confidence?: number | null
  created_at?: string | null
}

export interface InsightConcept extends InsightEntity {
  entity_type: string
}

export interface InsightTypeCount {
  entity_type: string
  count: number
}

export interface InsightMention {
  name: string
  count: number
}

export interface InsightHeatPoint {
  date: string
  entities: number
  facts: number
}

export interface KnowledgeInsights {
  range_days: number
  limit: number
  hot_topics: KnowledgeInsightTopic[]
  trending_companies: InsightEntity[]
  trending_industries: InsightEntity[]
  emerging_concepts: InsightConcept[]
  top_growing: InsightTypeCount[]
  top_mentioned: InsightMention[]
  heatmap: InsightHeatPoint[]
}

export function fetchKnowledgeInsights(rangeDays = 7, limit = 10): Promise<KnowledgeInsights> {
  return apiFetch<KnowledgeInsights>(
    `/api/knowledge/insights?range_days=${rangeDays}&limit=${limit}`
  )
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
  min_confidence?: number
  min_source_count?: number
  limit?: number
}): Promise<EntitiesResponse> {
  const searchParams = new URLSearchParams()
  if (params?.name) searchParams.set('name', params.name)
  if (params?.entity_type) searchParams.set('entity_type', params.entity_type)
  if (params?.min_confidence != null) searchParams.set('min_confidence', String(params.min_confidence))
  if (params?.min_source_count != null) searchParams.set('min_source_count', String(params.min_source_count))
  if (params?.limit) searchParams.set('limit', String(params.limit))
  const qs = searchParams.toString()
  return apiFetch<EntitiesResponse>(`/api/knowledge/entities${qs ? `?${qs}` : ''}`)
}

export function fetchEntityDetail(entityId: string): Promise<KnowledgeEntity> {
  return apiFetch<KnowledgeEntity>(`/api/knowledge/entities/${entityId}`)
}

// ─── Entity Types（KOC-C1 类型统计卡） ────────────────────

export interface EntityTypeCount {
  entity_type: string
  count: number
}

export interface EntityTypesResponse {
  types: EntityTypeCount[]
  total: number
}

export function fetchEntityTypes(): Promise<EntityTypesResponse> {
  return apiFetch<EntityTypesResponse>('/api/knowledge/entities/types')
}

// ─── Graph ────────────────────────────────────────────────

export interface GraphEdge {
  source_entity: string
  target_entity: string
  source_name?: string | null
  target_name?: string | null
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

// ─── KOC-D3 Entity Timeline（Evolution） ───────────────────

export interface TimelineVersion {
  version: number
  created_by: string
  created_at: string | null
  content: Record<string, unknown>
}

export interface TimelineFact {
  id: string
  predicate: string
  object_value: unknown
  unit: string | null
  time_start: string | null
  time_end: string | null
  confidence: number | null
  verification_status: string | null
  created_at: string | null
}

export interface TimelineEvent {
  id: string
  event_type: string
  title: string
  description: string | null
  event_date: string | null
  created_at: string | null
}

export interface EntityTimeline {
  entity_id: string
  versions: TimelineVersion[]
  facts: TimelineFact[]
  events: TimelineEvent[]
}

export function fetchEntityTimeline(entityId: string): Promise<EntityTimeline> {
  return apiFetch<EntityTimeline>(`/api/knowledge/entities/${entityId}/timeline`)
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

// KOC-C2 统一搜索结果（Entity/Fact/Event/Document + 来源通道）
export interface UnifiedSearchItem {
  id: string
  source_channels: string[]
  score?: number | null
  // entity
  name?: string
  entity_type?: string
  description?: string | null
  // fact
  subject_name?: string
  predicate?: string
  object_value?: string
  time_start?: string | null
  // event
  title?: string
  event_type?: string | null
  event_date?: string | null
  // document
  document_type?: string | null
  source?: string | null
}

export interface UnifiedSearchResults {
  entities: UnifiedSearchItem[]
  facts: UnifiedSearchItem[]
  events: UnifiedSearchItem[]
  documents: UnifiedSearchItem[]
}

export interface HybridSearchResult {
  query: string
  source_channels?: {
    vector: boolean
    fulltext: boolean
    graph: boolean
  }
  results?: UnifiedSearchResults
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

// ─── GraphRAG Search ────────────────────────────────────

export interface GraphRAGEvidence {
  kind: string
  name?: string
  entity_type?: string
  description?: string
  subject?: string
  predicate?: string
  value?: string
  time_start?: string
  source_entity?: string
  target_entity?: string
  relation_type?: string
  depth?: number
}

export interface GraphRAGKeyFinding {
  finding: string
  cited_evidence: string[]
}

export interface GraphRAGResult {
  query: string
  fusion: {
    summary: string
    key_findings: GraphRAGKeyFinding[]
  }
  entity_ids_used: string[]
  evidence: {
    graph: GraphRAGEvidence[]
    vector: GraphRAGEvidence[]
  }
  degraded: boolean
}

export function graphragSearch(params: {
  query: string
  entity_name?: string
  limit?: number
}): Promise<GraphRAGResult> {
  return apiFetch<GraphRAGResult>('/api/knowledge/search/rag', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

// ─── Ingest ─────────────────────────────────────────────

export interface IngestResponse {
  status: string
  message: string
  found: number
  collection: string
  task_id?: string
}

export function triggerIngest(
  path: string,
  collection?: string
): Promise<IngestResponse> {
  return apiFetch<IngestResponse>('/api/knowledge/ingest', {
    method: 'POST',
    body: JSON.stringify({ path, collection: collection || 'documents_cn' }),
  })
}

// ─── Knowledge Extraction ───────────────────────────────

export interface ExtractionResponse {
  task_id: string
  status: string
  document_count: number
}

export function triggerExtraction(documentIds: string[], rawTexts?: Record<string, string>): Promise<ExtractionResponse> {
  return apiFetch<ExtractionResponse>('/api/knowledge/extract', {
    method: 'POST',
    body: JSON.stringify({ document_ids: documentIds, raw_texts: rawTexts || {} }),
  })
}

// ─── MinIO Ingest ───────────────────────────────────────

export interface MinioIngestResponse {
  status: string
  task_id?: string
  async_mode?: boolean
  registered?: Record<string, unknown>
  pipeline_task_id?: string | null
}

export function triggerIngestMinio(params: {
  bucket?: string
  prefix?: string
  market?: string
  trigger?: boolean
}): Promise<MinioIngestResponse> {
  return apiFetch<MinioIngestResponse>('/api/knowledge/ingest-minio', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

// ─── Directory Browse ──────────────────────────────────

export interface BrowseDirsResponse {
  current_path: string
  parent_path: string | null
  can_go_up: boolean
  directories: Array<{ name: string; path: string }>
  total: number
}

export function fetchBrowseDirs(path?: string): Promise<BrowseDirsResponse> {
  const searchParams = new URLSearchParams()
  if (path) searchParams.set('path', path)
  const qs = searchParams.toString()
  return apiFetch<BrowseDirsResponse>(`/api/knowledge/browse-dirs${qs ? `?${qs}` : ''}`)
}

// ─── Path Mapping ──────────────────────────────────────

export interface PathMappingInfo {
  description: string
  examples: {
    windows: string
    wsl: string
    container: string
  }
  volume_mounts: Array<{ host_path: string; container_path: string }>
  tip: string
}

export function fetchPathMapping(): Promise<PathMappingInfo> {
  return apiFetch<PathMappingInfo>('/api/knowledge/path-mapping')
}

// ─── Knowledge Governance (KOC-B2) ──────────────────────

export interface GovernanceSummary {
  duplicate_entity: number
  value_mismatch: number
  low_confidence: number
  stale_fact: number
  sync_conflict: number
  total: number
}

export interface GovernanceSummaryResponse {
  summary: GovernanceSummary
}

export interface GovernanceItem {
  id: string
  conflict_type: string
  entity_id: string | null
  entity_name: string | null
  entity_type: string | null
  fact_a: string | null
  fact_b: string | null
  resolution: string | null
  resolution_obj: Record<string, unknown>
  created_at: string | null
}

export interface GovernanceItemsResponse {
  items: GovernanceItem[]
  total: number
}

export interface ResolveResult {
  status: string
  message: string
  conflict_id: string
}

export function fetchGovernanceSummary(): Promise<GovernanceSummaryResponse> {
  return apiFetch<GovernanceSummaryResponse>('/api/knowledge/governance/summary')
}

export function fetchGovernanceItems(
  conflictType?: string,
  limit = 50
): Promise<GovernanceItemsResponse> {
  const searchParams = new URLSearchParams()
  if (conflictType) searchParams.set('conflict_type', conflictType)
  searchParams.set('limit', String(limit))
  return apiFetch<GovernanceItemsResponse>(
    `/api/knowledge/governance/items?${searchParams.toString()}`
  )
}

export function resolveGovernanceItem(
  conflictId: string,
  action: 'merge' | 'keep' | 'dismiss',
  note = ''
): Promise<ResolveResult> {
  return apiFetch<ResolveResult>(`/api/knowledge/governance/${conflictId}/resolve`, {
    method: 'POST',
    body: JSON.stringify({ action, note }),
  })
}
