import { useState, useCallback } from 'react'
import { Star, Loader2 } from 'lucide-react'
import { TodayOverview } from '@/components/watchlist/TodayOverview'
import { TodayTimeline } from '@/components/watchlist/TodayTimeline'
import { AlertsPanel } from '@/components/watchlist/AlertsPanel'
import { WatchlistGrid } from '@/components/watchlist/WatchlistGrid'
import { LifecycleFlow } from '@/components/watchlist/LifecycleFlow'
import { StockDetailDrawer } from '@/components/watchlist/StockDetailDrawer'
import { MonitoringConfig } from '@/components/watchlist/MonitoringConfig'
import { DailyReport } from '@/components/watchlist/DailyReport'
import { HistoryPanel } from '@/components/watchlist/HistoryPanel'
import { SentimentTrend } from '@/components/watchlist/SentimentTrend'
import { VolatilityAlert } from '@/components/watchlist/VolatilityAlert'
import { IndustrySignal } from '@/components/watchlist/IndustrySignal'
import { useRunMonitoring } from '@/hooks/useWatchlist'
import type { WatchlistItem } from '@/services/watchlist'

export default function WatchlistPage() {
  const [filterGroup, setFilterGroup] = useState('')
  const [filterEnabled, setFilterEnabled] = useState('')
  const runMonitor = useRunMonitoring()

  // Stock Detail Drawer
  const [detailStock, setDetailStock] = useState<WatchlistItem | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)

  const handleStockClick = useCallback((item: WatchlistItem) => {
    setDetailStock(item)
    setDetailOpen(true)
  }, [])

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-xl bg-primary/10">
            <Star className="size-5 text-primary" strokeWidth={1.8} />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">
              Watchlist Intelligence Center
            </h1>
            <p className="text-sm text-muted-foreground">
              自选股监控 · 新闻 · 公告 · 财报 · 行业 · 风险 · AI 分析
            </p>
          </div>
        </div>
        {runMonitor.isPending && (
          <div className="flex items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 px-4 py-2 text-sm">
            <Loader2 className="size-4 animate-spin text-primary" />
            采集中…
          </div>
        )}
      </div>

      {/* ─────────── ① Today Overview ─────────── */}
      <TodayOverview />

      {/* ─────────── ② Timeline + Alerts ─────────── */}
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <TodayTimeline
            onEventClick={(ev) => {
              // Find the stock item and open its detail
              setDetailStock({
                id: '',
                stock_code: ev.stock_code,
                stock_name: ev.stock_name,
                market: null,
                industry: null,
                group_name: null,
                tags: [],
                enabled: true,
                ai_score: 0,
                last_event_at: null,
                today_event_count: 0,
                today_news_count: 0,
                created_at: null,
              })
              setDetailOpen(true)
            }}
          />
        </div>
        <div>
          <AlertsPanel />
        </div>
      </div>

      {/* ─────────── ④ Watchlist ─────────── */}
      <WatchlistGrid
        filterGroup={filterGroup}
        filterEnabled={filterEnabled}
        onFilterGroupChange={setFilterGroup}
        onFilterEnabledChange={setFilterEnabled}
        onStockClick={handleStockClick}
      />

      {/* ─────────── 生命周期可视化 ─────────── */}
      <LifecycleFlow isRunning={runMonitor.isPending} />

      {/* ─────────── ⑤ Config + ⑥ Report ─────────── */}
      <div className="grid gap-4 lg:grid-cols-2">
        <MonitoringConfig />
        <DailyReport />
      </div>

      {/* ─────────── ⑦ History ─────────── */}
      <HistoryPanel />

      {/* ─────────── ⑧ 高级 AI 分析（P4-3）─────────── */}
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <SentimentTrend />
        </div>
        <div>
          <IndustrySignal />
        </div>
      </div>
      <VolatilityAlert />

      {/* Stock Detail Drawer */}
      <StockDetailDrawer
        stock={detailStock}
        open={detailOpen}
        onOpenChange={setDetailOpen}
      />
    </div>
  )
}
