import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Clock,
  Loader2,
  CheckCircle2,
  XCircle,
  RefreshCw,
  RotateCcw,
  Inbox,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  fetchIntelligenceQueue,
  retryAgentPackage,
  type NewsQueueItem,
  type QueueState,
} from '@/services/news'
import { cn } from '@/lib/utils'

const STATE_META: Record<
  QueueState,
  { label: string; icon: typeof Clock; color: string; badge: string }
> = {
  waiting: {
    label: 'Waiting',
    icon: Inbox,
    color: 'text-slate-500',
    badge: 'bg-slate-500/15 text-slate-600',
  },
  processing: {
    label: 'Processing',
    icon: Loader2,
    color: 'text-blue-500',
    badge: 'bg-blue-500/15 text-blue-600',
  },
  published: {
    label: 'Published',
    icon: CheckCircle2,
    color: 'text-green-500',
    badge: 'bg-green-500/15 text-green-600',
  },
  failed: {
    label: 'Failed',
    icon: XCircle,
    color: 'text-red-500',
    badge: 'bg-red-500/15 text-red-600',
  },
}

const STATE_ORDER: QueueState[] = ['waiting', 'processing', 'published', 'failed']

export function IntelligenceQueueTab() {
  const [stateFilter, setStateFilter] = useState<QueueState | ''>('')
  const queryClient = useQueryClient()

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['news-intelligence-queue', stateFilter],
    queryFn: () =>
      fetchIntelligenceQueue({ days: 7, limit: 50, state: stateFilter }),
  })

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['news-intelligence-queue'] })
  }

  const retryMutation = useMutation({
    mutationFn: (packageId: string) => retryAgentPackage(packageId),
    onSuccess: () => {
      setTimeout(refresh, 800)
    },
  })

  const summary = data?.summary ?? {
    waiting: 0,
    processing: 0,
    published: 0,
    failed: 0,
  }

  return (
    <div className="space-y-4">
      {/* 四态状态卡片 */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {STATE_ORDER.map((s) => {
          const meta = STATE_META[s]
          const Icon = meta.icon
          const active = stateFilter === s
          return (
            <button
              key={s}
              onClick={() => setStateFilter(active ? '' : s)}
              className={cn(
                'group rounded-xl border p-4 text-left transition-colors',
                active
                  ? 'border-primary/50 bg-primary/5'
                  : 'border-border bg-card hover:border-primary/30'
              )}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Icon className={cn('size-4', meta.color)} />
                  <span className="text-sm font-medium">{meta.label}</span>
                </div>
                <span className="text-2xl font-bold tabular-nums">
                  {data ? summary[s] : '–'}
                </span>
              </div>
              <p className="mt-1 text-[10px] text-muted-foreground">
                {s === 'waiting' && '已采集 · 未进入发布链路'}
                {s === 'processing' && 'Package 生成中 · 待发布'}
                {s === 'published' && '已发布 / 已被 KOC 消费'}
                {s === 'failed' && '发布失败 · 可重试'}
              </p>
            </button>
          )
        })}
      </div>

      {/* 列表头 */}
      <div className="flex items-center justify-between">
        <div className="text-xs text-muted-foreground">
          {stateFilter
            ? `筛选：${STATE_META[stateFilter].label}（${data?.total ?? 0} 条）`
            : `近 7 天 · 共 ${data?.total ?? 0} 条记录`}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => refetch()}
          className="gap-1.5"
        >
          <RefreshCw className={cn('size-3.5', isFetching && 'animate-spin')} />
          刷新
        </Button>
      </div>

      {/* 明细列表 */}
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-xl" />
          ))}
        </div>
      ) : isError ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <p className="text-sm text-destructive">查询失败，请检查后端服务</p>
            <p className="mt-1 text-xs text-muted-foreground">
              确认 LangGraph Agent 服务已启动（端口 8100）
            </p>
          </CardContent>
        </Card>
      ) : data && data.items.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <p className="text-sm text-muted-foreground">暂无队列记录</p>
            <p className="mt-1 text-xs text-muted-foreground">
              新闻采集后会自动进入发布链路
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {data.items.map((item) => (
            <QueueRow
              key={item.article_id + (item.package_id ?? '')}
              item={item}
              onRetry={(pid) => retryMutation.mutate(pid)}
              retrying={retryMutation.isPending && retryMutation.variables === item.package_id}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function QueueRow({
  item,
  onRetry,
  retrying,
}: {
  item: NewsQueueItem
  onRetry: (packageId: string) => void
  retrying: boolean
}) {
  const meta = STATE_META[item.state]
  const Icon = meta.icon

  return (
    <Card className="transition-shadow duration-200 hover:shadow-[var(--shadow-soft)]">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <Icon className={cn('size-3.5 shrink-0', meta.color)} />
              <h3 className="truncate text-sm font-medium text-foreground">
                {item.title ?? '（无标题）'}
              </h3>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Badge variant="secondary" className={cn('text-[10px]', meta.badge)}>
                {meta.label}
              </Badge>
              {item.importance_score != null && (
                <Badge variant="outline" className="text-[10px]">
                  重要度: {item.importance_score.toFixed(2)}
                </Badge>
              )}
              {item.source_name && (
                <span className="text-[10px] text-muted-foreground">
                  {item.source_name}
                </span>
              )}
              {item.package_id && (
                <span className="text-[10px] text-muted-foreground">
                  pkg {item.package_id.slice(0, 8)}
                  {item.retry_count > 0 && ` · 重试 ${item.retry_count} 次`}
                </span>
              )}
              {item.published_at && (
                <span className="ml-auto text-[10px] text-muted-foreground">
                  {new Date(item.published_at).toLocaleDateString('zh-CN', {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </span>
              )}
            </div>
            {item.state === 'failed' && item.error && (
              <p className="mt-2 rounded-md bg-red-500/10 px-2.5 py-1.5 text-[11px] text-red-600">
                失败原因：{item.error}
              </p>
            )}
          </div>

          {item.state === 'failed' && item.package_id && (
            <Button
              size="sm"
              variant="outline"
              className="shrink-0 gap-1.5 border-red-500/40 text-red-600 hover:bg-red-500/10"
              onClick={() => onRetry(item.package_id!)}
              disabled={retrying}
            >
              {retrying ? (
                <RefreshCw className="size-3.5 animate-spin" />
              ) : (
                <RotateCcw className="size-3.5" />
              )}
              {retrying ? '重试中' : '重试'}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}