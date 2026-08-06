import { TrendingUp, TrendingDown } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import { useVolatility } from '@/hooks/useWatchlist'

export function VolatilityAlert() {
  const { data, isLoading } = useVolatility()
  const items = data?.items ?? []

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-base">异常波动解释</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : items.length === 0 ? (
          <EmptyState
            title="暂无异常波动"
            description="|涨跌幅| > 3% 时自动关联当日事件解释原因"
          />
        ) : (
          <div className="space-y-3">
            {items.map((it) => {
              const up = it.change_pct > 0
              return (
                <div key={it.stock_code} className="rounded-lg border p-3">
                  <div className="flex items-center justify-between">
                    <div className="flex min-w-0 items-center gap-2">
                      {up ? (
                        <TrendingUp className="size-4 shrink-0 text-green-600" />
                      ) : (
                        <TrendingDown className="size-4 shrink-0 text-red-600" />
                      )}
                      <span className="truncate font-semibold">
                        {it.stock_name || it.stock_code}
                      </span>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {it.stock_code}
                      </span>
                    </div>
                    <span
                      className={`shrink-0 text-sm font-bold tabular-nums ${
                        up ? 'text-green-600' : 'text-red-600'
                      }`}
                    >
                      {up ? '+' : ''}
                      {it.change_pct}%
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {it.industry ? `行业：${it.industry}` : '数据源：'}
                    {it.data_source ? ` · ${it.data_source}` : ''}
                  </div>
                  {(it.events?.length ?? 0) > 0 ? (
                    <ul className="mt-2 space-y-1">
                      {it.events.slice(0, 3).map((ev, i) => (
                        <li
                          key={i}
                          className="flex gap-1.5 text-xs text-muted-foreground"
                        >
                          <span className="shrink-0 rounded bg-muted px-1">
                            {ev.source_type || '事件'}
                          </span>
                          <span className="line-clamp-2">{ev.summary || ''}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-2 text-xs text-muted-foreground">
                      暂无当日关联事件，可能为市场整体波动。
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}