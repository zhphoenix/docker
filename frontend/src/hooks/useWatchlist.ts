import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchOverview,
  fetchHistory,
  fetchSentimentTrend,
  fetchVolatility,
  fetchIndustrySignals,
  fetchWatchlist,
  fetchWatchEvents,
  fetchWebAlerts,
  fetchLatestReport,
  fetchConfig,
  fetchStockDetail,
  fetchStockSummary,
  generateStockSummary,
  fetchStockGraph,
  triggerStockResearch,
  runMonitoring,
  addWatchlist,
  updateWatchlist,
  deleteWatchlist,
  updateConfig,
  markAlertRead,
  markAllAlertsRead,
} from '@/services/watchlist'
import { fetchResearch } from '@/services/research'
import type {
  WatchlistItem,
  WatchlistOverview,
  HistoryResponse,
  WatchlistEvent,
  WebAlert,
  DailyReport,
  WatchlistConfig,
  StockDetail,
} from '@/services/watchlist'

// ─── Overview ──────────────────────────────────────────
export function useWatchlistOverview() {
  return useQuery<WatchlistOverview>({
    queryKey: ['watchlist', 'overview'],
    queryFn: fetchOverview,
    staleTime: 60_000,
  })
}

// ─── History ───────────────────────────────────────────
export function useWatchlistHistory(days = 30) {
  return useQuery<HistoryResponse>({
    queryKey: ['watchlist', 'history', days],
    queryFn: () => fetchHistory(days),
    staleTime: 5 * 60_000,
  })
}

// ─── Advanced AI Analytics (P4-3) ─────────────────────
export function useSentimentTrend(days = 14) {
  return useQuery({
    queryKey: ['watchlist', 'analytics', 'sentiment', days],
    queryFn: () => fetchSentimentTrend(days),
    staleTime: 5 * 60_000,
  })
}

export function useVolatility() {
  return useQuery({
    queryKey: ['watchlist', 'analytics', 'volatility'],
    queryFn: fetchVolatility,
    staleTime: 2 * 60_000,
  })
}

export function useIndustrySignals(days = 1) {
  return useQuery({
    queryKey: ['watchlist', 'analytics', 'industry', days],
    queryFn: () => fetchIndustrySignals(days),
    staleTime: 2 * 60_000,
  })
}

// ─── Watchlist Items ───────────────────────────────────
export function useWatchlistItems(params?: {
  group_name?: string
  tag?: string
  enabled?: boolean
}) {
  return useQuery<{ items: WatchlistItem[]; total: number }>({
    queryKey: ['watchlist', 'items', params],
    queryFn: () => fetchWatchlist(params),
  })
}

export function useAddWatchlist() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: addWatchlist,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['watchlist', 'items'] })
      qc.invalidateQueries({ queryKey: ['watchlist', 'overview'] })
    },
  })
}

export function useUpdateWatchlist() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<{ stock_name: string; market: string; industry: string; group_name: string; tags: string[]; enabled: boolean }> }) =>
      updateWatchlist(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['watchlist', 'items'] })
    },
  })
}

export function useDeleteWatchlist() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: deleteWatchlist,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['watchlist', 'items'] })
      qc.invalidateQueries({ queryKey: ['watchlist', 'overview'] })
    },
  })
}

// ─── Events ────────────────────────────────────────────
export function useWatchlistEvents(params?: {
  stock_code?: string
  importance?: number
  sentiment?: string
  limit?: number
}) {
  return useQuery<{ items: WatchlistEvent[]; total: number }>({
    queryKey: ['watchlist', 'events', params],
    queryFn: () => fetchWatchEvents(params),
  })
}

// ─── Alerts ────────────────────────────────────────────
export function useWatchlistAlerts(params?: {
  unread_only?: boolean
  limit?: number
}) {
  return useQuery<{ items: WebAlert[] }>({
    queryKey: ['watchlist', 'alerts', params],
    queryFn: () => fetchWebAlerts(params),
  })
}

export function useMarkAlertRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: markAlertRead,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['watchlist', 'alerts'] })
      qc.invalidateQueries({ queryKey: ['watchlist', 'overview'] })
    },
  })
}

export function useMarkAllAlertsRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: markAllAlertsRead,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['watchlist', 'alerts'] })
      qc.invalidateQueries({ queryKey: ['watchlist', 'overview'] })
    },
  })
}

// ─── Report ────────────────────────────────────────────
export function useWatchlistReport() {
  return useQuery<{ report: DailyReport | null }>({
    queryKey: ['watchlist', 'report'],
    queryFn: fetchLatestReport,
    staleTime: 5 * 60_000,
  })
}

// ─── Config ────────────────────────────────────────────
export function useWatchlistConfig() {
  return useQuery<WatchlistConfig>({
    queryKey: ['watchlist', 'config'],
    queryFn: fetchConfig,
  })
}

export function useUpdateWatchlistConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: updateConfig,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['watchlist', 'config'] })
    },
  })
}

// ─── Monitoring ────────────────────────────────────────
export function useRunMonitoring() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: runMonitoring,
    onSuccess: () => {
      // 监控完成后刷新相关数据
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ['watchlist'] })
      }, 30_000)
    },
  })
}

// ─── Stock Detail ──────────────────────────────────────
export function useStockDetail(stockCode: string | null) {
  return useQuery<StockDetail>({
    queryKey: ['watchlist', 'stock-detail', stockCode],
    queryFn: () => fetchStockDetail(stockCode!),
    enabled: !!stockCode,
    staleTime: 2 * 60_000,
  })
}

export function useStockSummary(stockCode: string | null) {
  return useQuery<{ summary: string }>({
    queryKey: ['watchlist', 'stock-summary', stockCode],
    queryFn: () => fetchStockSummary(stockCode!),
    enabled: !!stockCode,
    staleTime: 5 * 60_000,
  })
}

export function useGenerateStockSummary() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: generateStockSummary,
    onSuccess: (_data, stockCode) => {
      qc.invalidateQueries({ queryKey: ['watchlist', 'stock-summary', stockCode] })
    },
  })
}

export function useStockGraph(stockCode: string | null) {
  return useQuery({
    queryKey: ['watchlist', 'stock-graph', stockCode],
    queryFn: () => fetchStockGraph(stockCode!),
    enabled: !!stockCode,
    staleTime: 5 * 60_000,
  })
}

export function useTriggerStockResearch() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ stockCode, question }: { stockCode: string; question?: string }) =>
      triggerStockResearch(stockCode, question),
    onSuccess: (_data, { stockCode }) => {
      qc.invalidateQueries({ queryKey: ['watchlist', 'stock-research', stockCode] })
    },
  })
}

export function useStockResearchTasks(symbol: string | null) {
  return useQuery({
    queryKey: ['watchlist', 'stock-research', symbol],
    queryFn: () => fetchResearch({ symbol: symbol! }),
    enabled: !!symbol,
    staleTime: 30_000,
  })
}
