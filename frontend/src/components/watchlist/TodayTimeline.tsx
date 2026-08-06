import { RefreshCw } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import { useWatchlistEvents } from '@/hooks/useWatchlist'
import type { WatchlistEvent } from '@/services/watchlist'

const STAR: Record<number, string> = { 5: '★★★★★', 4: '★★★★', 3: '★★★', 2: '★★', 1: '★' }

const SENTIMENT_COLOR: Record<string, string> = {
  bullish: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  bearish: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  neutral: 'bg-muted text-muted-foreground',
}

const IMPACT_HORIZON_LABEL: Record<string, string> = {
  short_term: '短期',
  mid_term: '中期',
  long_term: '长期',
}

interface Props {
  onEventClick?: (event: WatchlistEvent) => void
}

export function TodayTimeline({ onEventClick }: Props) {
  const { data, isLoading, refetch, isFetching } = useWatchlistEvents({ limit: 50 })

  if (isLoading) {
    return (
      <Card>
        <CardHeader><Skeleton className="h-5 w-28" /></CardHeader>
        <CardContent className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </CardContent>
      </Card>
    )
  }

  const events = data?.items ?? []

  // Group by importance
  const byImportance = (src: WatchlistEvent[]) => {
    const map: Record<number, WatchlistEvent[]> = {}
    for (const ev of src) {
      ;(map[ev.importance] ||= []).push(ev)
    }
    return Object.keys(map).map(Number).sort((a, b) => b - a)
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">今日重点（{events.length}）</CardTitle>
        <Button variant="ghost" size="sm" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={`mr-1 size-4 ${isFetching ? 'animate-spin' : ''}`} />
          刷新
        </Button>
      </CardHeader>
      <CardContent>
        {events.length === 0 ? (
          <EmptyState title="暂无事件" description="运行监控后，重要事件将出现在此处" />
        ) : (
          <div className="relative space-y-0 border-l-2 border-muted pl-4">
            {byImportance(events).flatMap((imp) =>
              events
                .filter((e) => e.importance === imp)
                .map((ev) => (
                  <div
                    key={ev.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => onEventClick?.(ev)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        onEventClick?.(ev)
                      }
                    }}
                    className={`relative mb-3 cursor-pointer rounded-lg border p-3 transition-colors hover:border-primary/40 hover:bg-muted/40 ${
                      ev.importance >= 4 ? 'border-red-200 dark:border-red-900/30' : ''
                    }`}
                  >
                    {/* Timeline dot */}
                    <div
                      className={`absolute -left-[22px] top-4 size-3 rounded-full border-2 border-background ${
                        ev.importance >= 4 ? 'bg-red-500' : ev.importance >= 3 ? 'bg-amber-500' : 'bg-muted-foreground'
                      }`}
                    />
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-semibold text-amber-600 dark:text-amber-400">
                        {STAR[ev.importance] ?? '★'}
                      </span>
                      <span className="text-sm font-medium">
                        {ev.stock_name || ev.stock_code}
                      </span>
                      {ev.sentiment && (
                        <Badge variant="outline" className={SENTIMENT_COLOR[ev.sentiment] ?? ''}>
                          {ev.sentiment}
                        </Badge>
                      )}
                      {ev.impact_horizon && (
                        <Badge variant="secondary" className="text-xs">
                          {IMPACT_HORIZON_LABEL[ev.impact_horizon] ?? ev.impact_horizon}
                        </Badge>
                      )}
                      {ev.event_time && (
                        <span className="ml-auto text-xs text-muted-foreground">
                          {new Date(ev.event_time).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      )}
                    </div>
                    {ev.summary && (
                      <p className="mt-1 line-clamp-2 text-sm text-foreground">{ev.summary}</p>
                    )}
                    {ev.source_name && (
                      <p className="mt-1 text-xs text-muted-foreground">
                        来源：{ev.source_name}
                        {ev.article_title ? ` · ${ev.article_title}` : ''}
                      </p>
                    )}
                  </div>
                ))
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
