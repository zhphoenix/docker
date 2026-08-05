import { apiFetch } from './api-client'

// ─── Types ─────────────────────────────────────────────

export interface WatchlistItem {
  id: string
  stock_code: string
  stock_name: string | null
  market: string | null
  industry: string | null
  group_name: string | null
  tags: string[]
  enabled: boolean
  created_at: string | null
}

export interface WatchlistConfig {
  schedule_time: string | null
  auto_enabled: boolean
  webhook_url: string | null
  updated_at: string | null
}

export interface WatchlistEvent {
  id: string
  stock_code: string
  stock_name: string | null
  news_id: string | null
  event_id: string | null
  importance: number
  sentiment: string | null
  confidence: string | null
  impact_horizon: string | null
  summary: string | null
  source_type: string | null
  article_title: string | null
  article_url: string | null
  source_name: string | null
  event_time: string | null
  created_at: string | null
}

export interface DailyReport {
  id: string
  report_date: string | null
  title: string | null
  summary: string | null
  content: string | null
  created_at: string | null
}

export interface WebAlert {
  id: string
  stock_code: string | null
  title: string
  content: string | null
  level: string | null
  event_id: string | null
  delivered: boolean
  read: boolean
  created_at: string | null
}

export interface GroupInfo {
  group_name: string | null
  cnt: number
}

export interface CompanyLookup {
  market: string | null
  symbol: string
  company_name: string | null
  exchange: string | null
  industry: string | null
}

// ─── Watchlist CRUD ────────────────────────────────────

export function fetchWatchlist(params?: {
  group_name?: string
  tag?: string
  enabled?: boolean
}): Promise<{ items: WatchlistItem[]; total: number }> {
  const searchParams = new URLSearchParams()
  if (params?.group_name) searchParams.set('group_name', params.group_name)
  if (params?.tag) searchParams.set('tag', params.tag)
  if (params?.enabled !== undefined)
    searchParams.set('enabled', String(params.enabled))
  const qs = searchParams.toString()
  return apiFetch(`/api/watchlist${qs ? `?${qs}` : ''}`)
}

export function addWatchlist(data: {
  stock_code: string
  stock_name?: string
  market?: string
  industry?: string
  group_name?: string
  tags?: string[]
}): Promise<WatchlistItem> {
  return apiFetch('/api/watchlist', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateWatchlist(
  id: string,
  data: Partial<{
    stock_name: string
    market: string
    industry: string
    group_name: string
    tags: string[]
    enabled: boolean
  }>
): Promise<WatchlistItem> {
  return apiFetch(`/api/watchlist/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function deleteWatchlist(id: string): Promise<{ deleted: string }> {
  return apiFetch(`/api/watchlist/${id}`, { method: 'DELETE' })
}

export function fetchGroups(): Promise<{ items: GroupInfo[] }> {
  return apiFetch('/api/watchlist/groups')
}

export function lookupStock(params: {
  code?: string
  name?: string
  market?: string
}): Promise<{ item: CompanyLookup | null }> {
  const searchParams = new URLSearchParams()
  if (params.code) searchParams.set('code', params.code)
  if (params.name) searchParams.set('name', params.name)
  if (params.market) searchParams.set('market', params.market)
  return apiFetch(`/api/watchlist/lookup?${searchParams.toString()}`)
}

export function createGroup(
  group_name: string
): Promise<{ group_name: string }> {
  return apiFetch('/api/watchlist/groups', {
    method: 'POST',
    body: JSON.stringify({ group_name }),
  })
}

// ─── Monitoring ────────────────────────────────────────

export function runMonitoring(): Promise<{ status: string; message: string }> {
  return apiFetch('/api/watchlist/run', { method: 'POST' })
}

// ─── Config ────────────────────────────────────────────

export function fetchConfig(): Promise<WatchlistConfig> {
  return apiFetch('/api/watchlist/config')
}

export function updateConfig(data: {
  schedule_time?: string
  auto_enabled?: boolean
  webhook_url?: string | null
}): Promise<WatchlistConfig> {
  return apiFetch('/api/watchlist/config', {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

// ─── Reports ───────────────────────────────────────────

export function fetchReports(
  limit?: number
): Promise<{ items: DailyReport[] }> {
  const qs = limit ? `?limit=${limit}` : ''
  return apiFetch(`/api/watchlist/reports${qs}`)
}

export function fetchLatestReport(): Promise<{ report: DailyReport | null }> {
  return apiFetch('/api/watchlist/reports/latest')
}

// ─── Events ────────────────────────────────────────────

export function fetchWatchEvents(params?: {
  stock_code?: string
  importance?: number
  sentiment?: string
  limit?: number
}): Promise<{ items: WatchlistEvent[]; total: number }> {
  const searchParams = new URLSearchParams()
  if (params?.stock_code) searchParams.set('stock_code', params.stock_code)
  if (params?.importance !== undefined)
    searchParams.set('importance', String(params.importance))
  if (params?.sentiment) searchParams.set('sentiment', params.sentiment)
  if (params?.limit) searchParams.set('limit', String(params.limit))
  const qs = searchParams.toString()
  return apiFetch(`/api/watchlist/events${qs ? `?${qs}` : ''}`)
}

// ─── Alerts ────────────────────────────────────────────

export function fetchWebAlerts(params?: {
  unread_only?: boolean
  limit?: number
}): Promise<{ items: WebAlert[] }> {
  const searchParams = new URLSearchParams()
  if (params?.unread_only) searchParams.set('unread_only', 'true')
  if (params?.limit) searchParams.set('limit', String(params.limit))
  const qs = searchParams.toString()
  return apiFetch(`/api/watchlist/alerts${qs ? `?${qs}` : ''}`)
}

export function markAlertRead(id: string): Promise<{ ok: boolean }> {
  return apiFetch(`/api/watchlist/alerts/${id}/read`, { method: 'POST' })
}