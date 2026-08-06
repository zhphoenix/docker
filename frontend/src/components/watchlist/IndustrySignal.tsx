import { Factory, AlertTriangle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import { useIndustrySignals } from '@/hooks/useWatchlist'

export function IndustrySignal() {
  const { data, isLoading } = useIndustrySignals(1)
  const items = data?.items ?? []

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-base">行业影响分析</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : items.length === 0 ? (
          <EmptyState
            title="暂无行业数据"
            description="同行业多只股票出现事件时标记行业级信号"
          />
        ) : (
          <div className="space-y-3">
            {items.map((it) => (
              <div key={it.industry} className="rounded-lg border p-3">
                <div className="flex items-center justify-between">
                  <div className="flex min-w-0 items-center gap-2">
                    <Factory className="size-4 shrink-0 text-muted-foreground" />
                    <span className="truncate font-semibold">{it.industry}</span>
                    {it.is_industry_signal && (
                      <Badge variant="secondary" className="gap-1 shrink-0">
                        <AlertTriangle className="size-3" /> 行业级信号
                      </Badge>
                    )}
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {it.total_events} 事件 · {it.stock_count} 股
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {it.stocks.map((s) => (
                    <span
                      key={s.stock_code}
                      className="rounded-md bg-muted px-2 py-0.5 text-xs"
                    >
                      {s.stock_name || s.stock_code}{' '}
                      <span className="text-muted-foreground">({s.event_cnt})</span>
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}