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

export interface NewsListResponse {
  articles: NewsArticle[]
  total: number
  limit: number
  offset: number
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
