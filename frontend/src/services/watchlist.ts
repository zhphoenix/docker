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
  item_type: string
  enabled: boolean
  ai_score: number
  last_event_at: string | null
  today_event_count: number
  today_news_count: number
  created_at: string | null
}

export interface WatchlistOverview {
  today: string
  monitored_stocks: number
  today_events: number
  high_risk_events: number
  ai_reports: number
  unread_alerts: number
  yesterday_events: number
}

export interface HistoryStat {
  date: string
  total_stocks: number
  total_events: number
  high_priority_events: number
  total_alerts: number
  critical_alerts: number
  ai_reports_generated: number
}

export interface HistoryResponse {
  stats: HistoryStat[]
  source: string
}

export interface StockDetail {
  stock_code: string
  stock_name: string | null
  market: string | null
  industry: string | null
  ai_score: number
  today_stats: {
    news_count: number
    announcement_count: number
    research_count: number
    industry_news_count: number
    competitor_news_count: number
  }
  ai_summary: string | null
  recent_events: WatchlistEvent[]
}

export interface WatchlistConfig {
  schedule_time: string | null
  auto_enabled: boolean
  webhook_url: string | null
  monitoring_scopes: string[]
  ai_summary_enabled: boolean
  daily_report_enabled: boolean
  email_enabled: boolean
  email_address: string | null
  update_frequency: string
  alert_threshold: number
  notification_channels: string[]
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

export interface SentimentPoint {
  date: string
  bullish: number
  bearish: number
  neutral: number
}

export interface VolatilityItem {
  stock_code: string
  stock_name: string | null
  market: string | null
  industry: string | null
  price: number | null
  change: number | null
  change_pct: number
  data_source: string | null
  events: Array<{
    importance: number
    sentiment: string | null
    summary: string | null
    source_type: string | null
  }>
}

export interface IndustrySignal {
  industry: string
  stocks: Array<{
    stock_code: string
    stock_name: string | null
    event_cnt: number
  }>
  total_events: number
  max_importance: number
  stock_count: number
  is_industry_signal: boolean
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
  item_type?: string
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
    item_type: string
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
  monitoring_scopes?: string[]
  ai_summary_enabled?: boolean
  daily_report_enabled?: boolean
  email_enabled?: boolean
  email_address?: string | null
  update_frequency?: string
  alert_threshold?: number
  notification_channels?: string[]
}): Promise<WatchlistConfig> {
  return apiFetch('/api/watchlist/config', {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function fetchOverview(): Promise<WatchlistOverview> {
  return apiFetch('/api/watchlist/overview')
}

export function fetchHistory(days?: number): Promise<HistoryResponse> {
  const qs = days ? `?days=${days}` : ''
  return apiFetch(`/api/watchlist/history${qs}`)
}

// ─── Advanced AI Analytics (P4-3) ─────────────────────

export function fetchSentimentTrend(days?: number): Promise<{
  items: SentimentPoint[]
  days: number
}> {
  const qs = days ? `?days=${days}` : ''
  return apiFetch(`/api/watchlist/analytics/sentiment${qs}`)
}

export function fetchVolatility(): Promise<{ items: VolatilityItem[] }> {
  return apiFetch('/api/watchlist/analytics/volatility')
}

export function fetchIndustrySignals(days?: number): Promise<{
  items: IndustrySignal[]
}> {
  const qs = days ? `?days=${days}` : ''
  return apiFetch(`/api/watchlist/analytics/industry${qs}`)
}

export function fetchStockDetail(stockCode: string): Promise<StockDetail> {
  return apiFetch(`/api/watchlist/stocks/${encodeURIComponent(stockCode)}/detail`)
}

export function fetchStockSummary(
  stockCode: string
): Promise<{ summary: string }> {
  return apiFetch(
    `/api/watchlist/stocks/${encodeURIComponent(stockCode)}/summary`
  )
}

export function generateStockSummary(
  stockCode: string
): Promise<{ summary: string }> {
  return apiFetch(
    `/api/watchlist/stocks/${encodeURIComponent(stockCode)}/summary`,
    { method: 'POST' }
  )
}

export function fetchStockGraph(stockCode: string): Promise<{
  nodes: Array<{ id: string; label: string; type: string }>
  edges: Array<{ source: string; target: string; label?: string }>
}> {
  return apiFetch(
    `/api/watchlist/stocks/${encodeURIComponent(stockCode)}/graph`
  )
}

export function triggerStockResearch(
  stockCode: string,
  question?: string
): Promise<{ task_id: string; status: string }> {
  return apiFetch(
    `/api/watchlist/stocks/${encodeURIComponent(stockCode)}/research`,
    {
      method: 'POST',
      body: JSON.stringify({ question }),
    }
  )
}

export function markAllAlertsRead(): Promise<{ ok: boolean }> {
  return apiFetch('/api/watchlist/alerts/read-all', { method: 'POST' })
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

export async function exportReport(reportId: string): Promise<Blob> {
  const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
  const response = await fetch(`${API_BASE}/api/watchlist/reports/${reportId}/export`)
  if (!response.ok) {
    throw new Error(`导出失败：HTTP ${response.status}`)
  }
  return response.blob()
}

export async function exportReportPdf(reportId: string): Promise<Blob> {
  const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
  const response = await fetch(
    `${API_BASE}/api/watchlist/reports/${reportId}/export?format=pdf`
  )
  if (!response.ok) {
    throw new Error(`PDF 导出失败：HTTP ${response.status}`)
  }
  return response.blob()
}

export function emailReport(
  reportId: string,
  to: string
): Promise<{ ok: boolean; to: string; subject: string }> {
  return apiFetch(`/api/watchlist/reports/${reportId}/email`, {
    method: 'POST',
    body: JSON.stringify({ to }),
  })
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