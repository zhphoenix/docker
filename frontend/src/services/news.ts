import { apiFetch } from './api-client'

// ─── Types ─────────────────────────────────────────────

export interface NewsArticle {
  id: string
  title: string
  summary: string | null
  content?: string
  url: string | null
  category: string | null
  language: string | null
  published_at: string | null
  collected_at: string | null
  status: string | null
  source_name: string | null
  importance: string | null
  entities?: NewsEntity[]
  events?: NewsEvent[]
}

export interface NewsEntity {
  id: string
  name: string
  entity_type: string
  description: string | null
  confidence: number | null
}

export interface NewsEvent {
  id: string
  event_type: string
  title: string
  summary: string | null
  event_time: string | null
  impact_score: number | null
  impact_direction: string | null
  market?: string | null
  sector?: string | null
  confidence?: number | null
  created_at?: string | null
  article_title?: string | null
}

export interface NewsSource {
  id: string
  source_id: string
  name: string
  source_type: string
  category: string | null
  market: string | null
  priority: number | null
  enabled: boolean
  created_at: string | null
}

export interface SourceHealth {
  source_id: string
  name: string
  source_type: string
  category: string[] | null
  market: string[] | null
  priority: string | null
  enabled: boolean
  last_latency_ms: number | null
  last_success: boolean | null
  last_error: string | null
  error_count: number | null
  last_collected_at: string | null
  total_runs: number
  success_count: number
  failed_count: number
  avg_latency_ms: number
  total_articles: number
  total_stored: number
  total_duplicates: number
  status: 'disabled' | 'no_data' | 'healthy' | 'degraded' | 'error'
}

export interface SourceHealthResponse {
  sources: SourceHealth[]
  coverage: number
  total_sources: number
  enabled_sources: number
  healthy_sources: number
  days: number
}

export interface NewsListResponse {
  articles: NewsArticle[]
  total: number
  limit: number
  offset: number
}

export interface NewsFeedArticle {
  id: string
  title: string
  summary: string | null
  url: string | null
  category: string | null
  language: string | null
  importance_score: number | null
  tier: number | null
  published_at: string | null
  collected_at: string | null
  status: string | null
  source_name: string | null
}

export interface NewsFeedHotTopic {
  name: string
  mentions: number
}

export interface NewsFeed {
  hours: number
  breaking: NewsFeedArticle[]
  high_impact: NewsFeedArticle[]
  hot_topics: NewsFeedHotTopic[]
  summary: {
    breaking: number
    high_impact: number
    hot_topics: number
  }
}

export type QueueState = 'waiting' | 'processing' | 'published' | 'failed'

export interface NewsQueueItem {
  article_id: string
  title: string | null
  source_name: string | null
  published_at: string | null
  importance_score: number | null
  package_id: string | null
  package_status: string | null
  retry_count: number
  state: QueueState
  error: string | null
}

export interface NewsIntelligenceQueue {
  days: number
  summary: Record<QueueState, number>
  items: NewsQueueItem[]
  total: number
}

export interface EventListResponse {
  events: NewsEvent[]
  total: number
}

export interface EventImpact {
  id: string
  event_type: string
  title: string
  summary: string | null
  event_time: string | null
  impact_score: number | null
  impact_direction: string | null
  market: string | null
  sector: string | null
  confidence: number | null
  article_title: string | null
  article_category: string | null
}

export interface CoreEvent {
  id: string
  event_type: string
  title: string
  description: string | null
  event_date: string | null
  entities: string[]
  company_count: number
  impact: { score?: number; direction?: string; duration?: string } | null
  confidence: number | null
  created_at: string | null
}

export interface EventMonitorResponse {
  source: string
  days: number
  today_new: number
  window_total: number
  avg_score: number | null
  direction: { positive: number; negative: number; neutral: number }
  affected_companies: string[]
  company_mentions: Array<{ company: string; event_count: number }>
  events: CoreEvent[]
  total: number
}

export interface TopImpactEvent {
  id: string
  event_type: string
  title: string
  description: string | null
  event_date: string | null
  companies: string[]
  company_count: number
  impact: { score?: number; direction?: string; duration?: string } | null
  score: number | null
  stars: number
  confidence: number | null
}

export interface TopImpactResponse {
  source: string
  days: number
  items: TopImpactEvent[]
  total: number
}

export interface EventTimelineResponse {
  source: string
  entity_name: string
  days: number
  items: TopImpactEvent[]
  total: number
}

export interface ImpactAnalysis {
  entity_name: string
  days?: number
  total_events: number
  positive_count: number
  negative_count: number
  neutral_count: number
  avg_impact_score: number
  events: Array<{
    entity_name: string
    entity_type: string | null
    event_type: string | null
    event_title: string | null
    impact_score: number | null
    impact_direction: string | null
    event_time: string | null
    article_title: string | null
    published_at: string | null
  }>
  message?: string
}

export interface TimelineItem {
  title: string
  category: string | null
  published_at: string | null
  url: string | null
  importance: string | null
  source_name: string | null
}

export interface TimelineResponse {
  entity_name: string
  items: TimelineItem[]
  total: number
}

// ─── API Functions ─────────────────────────────────────

export function fetchNewsArticles(params?: {
  keyword?: string
  category?: string
  days?: number
  limit?: number
  offset?: number
}): Promise<NewsListResponse> {
  const searchParams = new URLSearchParams()
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  if (params?.category) searchParams.set('category', params.category)
  if (params?.days) searchParams.set('days', String(params.days))
  if (params?.limit) searchParams.set('limit', String(params.limit))
  if (params?.offset) searchParams.set('offset', String(params.offset))
  const qs = searchParams.toString()
  return apiFetch<NewsListResponse>(`/api/news/articles${qs ? `?${qs}` : ''}`)
}

export function fetchNewsFeed(params?: {
  hours?: number
  limit?: number
}): Promise<NewsFeed> {
  const searchParams = new URLSearchParams()
  if (params?.hours) searchParams.set('hours', String(params.hours))
  if (params?.limit) searchParams.set('limit', String(params.limit))
  const qs = searchParams.toString()
  return apiFetch<NewsFeed>(`/api/news/feed${qs ? `?${qs}` : ''}`)
}

export function fetchIntelligenceQueue(params?: {
  days?: number
  limit?: number
  state?: QueueState | ''
}): Promise<NewsIntelligenceQueue> {
  const searchParams = new URLSearchParams()
  if (params?.days) searchParams.set('days', String(params.days))
  if (params?.limit) searchParams.set('limit', String(params.limit))
  if (params?.state) searchParams.set('state', params.state)
  const qs = searchParams.toString()
  return apiFetch<NewsIntelligenceQueue>(
    `/api/news/intelligence-queue${qs ? `?${qs}` : ''}`
  )
}

/** 重投失败 Package（failed → draft，复用 DP-D1 Re-Publish 端点） */
export function retryAgentPackage(
  packageId: string
): Promise<{ status: string; message: string; package_id: string }> {
  return apiFetch(`/api/knowledge/packages/${packageId}/retry`, {
    method: 'POST',
  })
}

export function fetchNewsArticle(id: string): Promise<NewsArticle> {
  return apiFetch<NewsArticle>(`/api/news/articles/${id}`)
}

export function fetchNewsEvents(params?: {
  event_type?: string
  entity_name?: string
  days?: number
  limit?: number
}): Promise<EventListResponse> {
  const searchParams = new URLSearchParams()
  if (params?.event_type) searchParams.set('event_type', params.event_type)
  if (params?.entity_name) searchParams.set('entity_name', params.entity_name)
  if (params?.days) searchParams.set('days', String(params.days))
  if (params?.limit) searchParams.set('limit', String(params.limit))
  const qs = searchParams.toString()
  return apiFetch<EventListResponse>(`/api/news/events${qs ? `?${qs}` : ''}`)
}

export function fetchEventImpact(id: string): Promise<EventImpact> {
  return apiFetch<EventImpact>(`/api/news/events/${id}/impact`)
}

/** NIC-B1 Event Monitor：读 core.events（KOC 侧聚合端点） */
export function fetchEventMonitor(params?: {
  event_type?: string
  company?: string
  days?: number
  limit?: number
}): Promise<EventMonitorResponse> {
  const searchParams = new URLSearchParams()
  if (params?.event_type) searchParams.set('event_type', params.event_type)
  if (params?.company) searchParams.set('company', params.company)
  if (params?.days) searchParams.set('days', String(params.days))
  if (params?.limit) searchParams.set('limit', String(params.limit))
  const qs = searchParams.toString()
  return apiFetch<EventMonitorResponse>(
    `/api/knowledge/events/monitor${qs ? `?${qs}` : ''}`
  )
}

/** NIC-B2 Top Impact Events：KOC 分析结果（core.events），星级=影响评分 */
export function fetchTopImpactEvents(params?: {
  company?: string
  days?: number
  limit?: number
}): Promise<TopImpactResponse> {
  const searchParams = new URLSearchParams()
  if (params?.company) searchParams.set('company', params.company)
  if (params?.days) searchParams.set('days', String(params.days))
  if (params?.limit) searchParams.set('limit', String(params.limit))
  const qs = searchParams.toString()
  return apiFetch<TopImpactResponse>(
    `/api/knowledge/events/top-impact${qs ? `?${qs}` : ''}`
  )
}

/** NIC-B3 事件时间线：读 core.events（Timeline 与 Event Monitor 同源） */
export function fetchKnowledgeEventsTimeline(params?: {
  entity_name?: string
  days?: number
  limit?: number
}): Promise<EventTimelineResponse> {
  const searchParams = new URLSearchParams()
  if (params?.entity_name) searchParams.set('entity_name', params.entity_name)
  if (params?.days) searchParams.set('days', String(params.days))
  if (params?.limit) searchParams.set('limit', String(params.limit))
  const qs = searchParams.toString()
  return apiFetch<EventTimelineResponse>(
    `/api/knowledge/events/timeline${qs ? `?${qs}` : ''}`
  )
}

export function fetchNewsImpact(
  entityName: string,
  days?: number
): Promise<ImpactAnalysis> {
  const searchParams = new URLSearchParams({ entity_name: entityName })
  if (days) searchParams.set('days', String(days))
  return apiFetch<ImpactAnalysis>(`/api/news/impact?${searchParams.toString()}`)
}

export function fetchNewsTimeline(
  entityName: string,
  days?: number,
  limit?: number
): Promise<TimelineResponse> {
  const searchParams = new URLSearchParams({ entity_name: entityName })
  if (days) searchParams.set('days', String(days))
  if (limit) searchParams.set('limit', String(limit))
  return apiFetch<TimelineResponse>(`/api/news/timeline?${searchParams.toString()}`)
}

export function fetchNewsSources(enabledOnly?: boolean): Promise<{
  sources: NewsSource[]
  total: number
}> {
  const searchParams = new URLSearchParams()
  if (enabledOnly !== undefined)
    searchParams.set('enabled_only', String(enabledOnly))
  const qs = searchParams.toString()
  return apiFetch<{ sources: NewsSource[]; total: number }>(
    `/api/news/sources${qs ? `?${qs}` : ''}`
  )
}

export function fetchSourceHealth(days?: number): Promise<SourceHealthResponse> {
  const searchParams = new URLSearchParams()
  if (days) searchParams.set('days', String(days))
  const qs = searchParams.toString()
  return apiFetch<SourceHealthResponse>(
    `/api/news/sources/health${qs ? `?${qs}` : ''}`
  )
}

export function setNewsSourceEnabled(
  sourceId: string,
  enabled: boolean
): Promise<{ source_id: string; enabled: boolean; status: string; message: string }> {
  return apiFetch(`/api/news/sources/${encodeURIComponent(sourceId)}/enabled`, {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  })
}

export interface CollectResponse {
  status: string
  message: string
}

export function triggerNewsCollect(keyword: string): Promise<CollectResponse> {
  return apiFetch<CollectResponse>('/api/news/collect', {
    method: 'POST',
    body: JSON.stringify({ keyword, priority: 'high' }),
  })
}
