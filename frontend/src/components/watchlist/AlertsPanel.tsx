import { CheckCheck, ExternalLink, BookOpen } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import { useWatchlistAlerts, useMarkAlertRead, useMarkAllAlertsRead, useTriggerStockResearch } from '@/hooks/useWatchlist'

const LEVEL_STYLE: Record<string, { bg: string; dot: string }> = {
  critical: { bg: 'border-red-300 dark:border-red-800', dot: 'bg-red-500' },
  important: { bg: 'border-amber-300 dark:border-amber-800', dot: 'bg-amber-500' },
  info: { bg: 'border-muted', dot: 'bg-blue-400' },
}

export function AlertsPanel() {
  const { data, isLoading } = useWatchlistAlerts({ limit: 20 })
  const markRead = useMarkAlertRead()
  const markAllRead = useMarkAllAlertsRead()
  const triggerResearch = useTriggerStockResearch()

  if (isLoading) {
    return (
      <Card>
        <CardHeader><Skeleton className="h-5 w-24" /></CardHeader>
        <CardContent className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </CardContent>
      </Card>
    )
  }

  const alerts = data?.items ?? []
  const unreadCount = alerts.filter((a) => !a.read).length

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-base">
          AI 告警
          {unreadCount > 0 && (
            <Badge variant="destructive" className="text-xs">{unreadCount} 未读</Badge>
          )}
        </CardTitle>
        {unreadCount > 0 && (
          <Button variant="ghost" size="sm" onClick={() => markAllRead.mutate()} disabled={markAllRead.isPending}>
            <CheckCheck className="mr-1 size-4" /> 全部已读
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-2">
        {alerts.length === 0 ? (
          <EmptyState title="暂无告警" description="监控系统运行后将自动推送重要告警" />
        ) : (
          alerts.map((a) => {
            const style = LEVEL_STYLE[a.level ?? 'info'] ?? LEVEL_STYLE.info
            return (
              <div
                key={a.id}
                className={`flex items-start gap-3 rounded-lg border p-3 transition-colors ${
                  !a.read ? style.bg : ''
                }`}
              >
                <div className={`mt-1.5 size-2 shrink-0 rounded-full ${style.dot}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={a.level === 'critical' ? 'destructive' : a.level === 'important' ? 'default' : 'secondary'}>
                      {a.level}
                    </Badge>
                    <span className="text-sm font-medium">{a.title}</span>
                    {a.stock_code && (
                      <span className="text-xs text-muted-foreground">{a.stock_code}</span>
                    )}
                  </div>
                  {a.content && (
                    <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{a.content}</p>
                  )}
                  <div className="mt-2 flex items-center gap-2">
                    {!a.read && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => markRead.mutate(a.id)}
                        disabled={markRead.isPending}
                      >
                        标记已读
                      </Button>
                    )}
                    <Button variant="ghost" size="sm" className="h-7 text-xs">
                      <ExternalLink className="mr-1 size-3" /> 查看
                    </Button>
                    {a.stock_code && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() =>
                          triggerResearch.mutate({
                            stockCode: a.stock_code!,
                            question: `对 ${a.title} 进行深度投研分析`,
                          })
                        }
                        disabled={triggerResearch.isPending}
                      >
                        <BookOpen className="mr-1 size-3" /> 加入研究
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            )
          })
        )}
      </CardContent>
    </Card>
  )
}
