import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Eye,
  Newspaper,
  RefreshCw,
  Loader2,
  AlertCircle,
  TrendingUp,
  Activity,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  fetchMonitorHits,
  type MonitorHit,
} from '@/services/watchlist'
import { cn } from '@/lib/utils'

type SortKey = 'live_count' | 'cached_count' | 'event_count' | 'ai_score'

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'live_count', label: '实时命中' },
  { key: 'cached_count', label: '物化命中' },
  { key: 'event_count', label: '今日事件' },
  { key: 'ai_score', label: 'AI 评分' },
]

const MARKET_LABEL: Record<string, string> = {
  cn: 'A股',
  hk: '港股',
  us: '美股',
}

/**
 * NIC-D2 Watchlist Monitor：自选股今日命中新闻数列表。
 * 数据源：/api/watchlist/monitor-hits（实时 news.articles 命中统计 + 物化 today_news_count 对照）。
 */
export function WatchlistMonitorTab() {
  const [sort, setSort] = useState<SortKey>('live_count')

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['news', 'watchlist', 'monitor-hits', sort],
    queryFn: () => fetchMonitorHits({ sort }),
  })

  return (
    <div className="space-y-4">
      {/* 头部 */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Eye className="size-4 text-primary" strokeWidth={1.8} />
          <h2 className="text-sm font-semibold text-foreground">Watchlist Monitor · 今日命中</h2>
          {data && (
            <Badge variant="secondary" className="text-[11px]">
              {data.total} 只标的
            </Badge>
          )}
          {data && data.stale > 0 && (
            <Badge variant="secondary" className="text-[11px] text-amber-600">
              <AlertCircle className="mr-1 size-3" />
              {data.stale} 只实时与物化不一致
            </Badge>
          )}
        </div>
        <Button variant="ghost" size="sm" onClick={() => refetch()} disabled={isFetching}>
          {isFetching ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}
          刷新
        </Button>
      </div>

      {/* 排序切换 */}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-muted-foreground">排序：</span>
        {SORT_OPTIONS.map((opt) => (
          <button
            key={opt.key}
            onClick={() => setSort(opt.key)}
            className={cn(
              'rounded-full border px-2.5 py-1 text-xs transition-colors',
              sort === opt.key
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border text-muted-foreground hover:bg-muted'
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12 rounded-lg" />
          ))}
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed p-8 text-center">
          <AlertCircle className="size-8 text-muted-foreground/50" />
          <p className="text-sm font-medium text-foreground">加载失败</p>
          <p className="text-xs text-muted-foreground">无法获取自选股命中统计。</p>
        </div>
      ) : data && data.items.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed p-8 text-center">
          <Newspaper className="size-8 text-muted-foreground/50" />
          <p className="text-sm font-medium text-foreground">暂无自选股</p>
          <p className="text-xs text-muted-foreground">请先在自选股列表中添加标的并启用监控。</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
                <th className="px-3 py-2 font-medium">标的</th>
                <th className="px-3 py-2 text-right font-medium">实时命中</th>
                <th className="px-3 py-2 text-right font-medium">物化命中</th>
                <th className="px-3 py-2 text-right font-medium">今日事件</th>
                <th className="px-3 py-2 text-right font-medium">AI 评分</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((item) => (
                <MonitorRow key={item.stock_code} item={item} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function MonitorRow({ item }: { item: MonitorHit }) {
  const stale = item.live_count !== item.cached_count
  return (
    <tr className="border-b last:border-0 hover:bg-muted/40">
      <td className="px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="font-medium text-foreground">{item.stock_name ?? item.stock_code}</span>
          <span className="text-xs text-muted-foreground">{item.stock_code}</span>
          {item.market && (
            <Badge variant="outline" className="text-[10px]">
              {MARKET_LABEL[item.market] ?? item.market}
            </Badge>
          )}
        </div>
      </td>
      <td className="px-3 py-2 text-right">
        <span className="inline-flex items-center gap-1 font-semibold text-primary">
          <Newspaper className="size-3.5" />
          {item.live_count}
        </span>
        {stale && (
          <span className="ml-1 text-[10px] text-amber-500" title="实时统计与物化计数不一致">
            *
          </span>
        )}
      </td>
      <td className="px-3 py-2 text-right text-muted-foreground">{item.cached_count}</td>
      <td className="px-3 py-2 text-right">
        <span className="inline-flex items-center gap-1 text-muted-foreground">
          <Activity className="size-3.5" />
          {item.event_count}
        </span>
      </td>
      <td className="px-3 py-2 text-right">
        <span className="inline-flex items-center gap-1 text-muted-foreground">
          <TrendingUp className="size-3.5" />
          {item.ai_score.toFixed(1)}
        </span>
      </td>
    </tr>
  )
}