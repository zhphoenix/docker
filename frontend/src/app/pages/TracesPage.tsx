import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  ChevronRight,
  Loader2,
  Network,
  RefreshCw,
  ScrollText,
  TriangleAlert,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import {
  fetchCollabTraces,
  fetchTraceChain,
  type CollabTraceItem,
  type TraceChainRun,
} from '@/services/agents'
import { cn } from '@/lib/utils'

function fmtDuration(ms: number | null): string {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1000) return `${ms} ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} s`
  return `${(ms / 60000).toFixed(1)} min`
}

function fmtFull(ts: string | null): string {
  if (!ts) return '—'
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function shortId(id: string): string {
  return id.length > 8 ? `${id.slice(0, 8)}…` : id
}

const STATUS_DOT: Record<string, string> = {
  completed: 'bg-emerald-500',
  success: 'bg-emerald-500',
  failed: 'bg-destructive',
  running: 'bg-sky-500',
}

/* ---------- 单条调用链详情（横向 Agent 顺序 + 各 run 时间线） ---------- */

function ChainDetail({ traceId }: { traceId: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['trace-chain', traceId],
    queryFn: () => fetchTraceChain(traceId),
    enabled: !!traceId,
    retry: 1,
    refetchInterval: 8000,
  })

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-3 text-xs text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" /> 加载调用链…
      </div>
    )
  }
  if (isError || !data) {
    return (
      <div className="flex items-center gap-2 py-3 text-xs text-destructive">
        <TriangleAlert className="size-3.5" /> 调用链加载失败
      </div>
    )
  }

  const runs = data.runs ?? []
  return (
    <div className="space-y-4">
      {/* 横向调用链顺序 */}
      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border bg-muted/30 p-3">
        {data.chain.map((s, i) => (
          <span key={s.agent_id} className="flex items-center gap-1.5">
            <Badge variant="outline">{s.display_name}</Badge>
            {i < data.chain.length - 1 && <ArrowRight className="size-3 text-muted-foreground" />}
          </span>
        ))}
      </div>

      {/* 各 Agent 运行详情 */}
      {runs.length === 0 ? (
        <p className="text-xs text-muted-foreground">该调用链暂无运行记录</p>
      ) : (
        runs.map((run: TraceChainRun, i: number) => (
          <div key={run.run_id} className="rounded-lg border p-3">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge>{run.display_name}</Badge>
              <Badge variant="outline">{run.task_kind}</Badge>
              <span className={cn('size-1.5 rounded-full', STATUS_DOT[run.status] ?? 'bg-muted-foreground/50')} />
              <span className="text-muted-foreground">{fmtFull(run.created_at)}</span>
              <span className="ml-auto font-medium">
                耗时 {fmtDuration(run.duration_ms)}
              </span>
            </div>
            {run.question && (
              <p className="mt-1.5 text-xs text-muted-foreground break-all">{run.question}</p>
            )}
            {run.status === 'failed' && (
              <p className="mt-2 rounded bg-destructive/5 p-2 text-xs text-destructive font-mono break-all">
                {run.error ?? '未知错误'}
              </p>
            )}

            {/* 节点级时间线 */}
            {run.timeline.length > 0 && (
              <ol className="relative mt-3 space-y-2 pl-4 before:absolute before:inset-y-0 before:left-1.5 before:w-px before:bg-border">
                {run.timeline.map((t, j) => (
                  <li key={j} className="relative">
                    <span
                      className={cn(
                        'absolute -left-4 top-1.5 size-2 rounded-full ring-2 ring-background',
                        t.status === 'failed' ? 'bg-destructive' : 'bg-emerald-500'
                      )}
                    />
                    <div className="flex items-center gap-2 text-xs">
                      <span className="font-medium text-foreground">{t.node}</span>
                      {t.duration_ms !== null && t.duration_ms !== undefined && (
                        <span className="text-muted-foreground">{fmtDuration(t.duration_ms)}</span>
                      )}
                    </div>
                    {t.detail && (
                      <p className="mt-0.5 text-xs text-muted-foreground break-all">{t.detail}</p>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </div>
        ))
      )}
      <p className="text-right text-[11px] text-muted-foreground" key={runs.length}>
        {runs.length} 个 Agent 运行 · 自动刷新
      </p>
    </div>
  )
}

/* ---------- 调用链列表行 ---------- */

function TraceRow({ item, open, onToggle }: { item: CollabTraceItem; open: boolean; onToggle: () => void }) {
  return (
    <div className="rounded-lg border">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-3 p-3 text-left transition-colors hover:bg-muted/30"
      >
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Network className="size-4 text-primary" strokeWidth={1.8} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-medium text-foreground">{shortId(item.trace_id)}</span>
            <Badge
              variant="outline"
              className={cn(
                'text-[10px]',
                item.status === 'failed' && 'border-destructive/40 text-destructive'
              )}
            >
              {item.status === 'failed' ? '失败' : '完成'}
            </Badge>
            {item.failed_runs > 0 && (
              <span className="text-[11px] text-destructive">{item.failed_runs} 失败</span>
            )}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
            <span>{item.agents} 个 Agent</span>
            <span>{item.runs} 次运行</span>
            <span>总耗时 {fmtDuration(item.total_duration_ms)}</span>
            <span>{fmtFull(item.started_at)}</span>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {item.steps.map((s, i) => (
              <span key={s.agent_id} className="flex items-center gap-1.5">
                <Badge variant="secondary" className="text-[10px]">
                  {s.display_name}
                </Badge>
                {i < item.steps.length - 1 && (
                  <ArrowRight className="size-2.5 text-muted-foreground" />
                )}
              </span>
            ))}
          </div>
        </div>
        {open ? (
          <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
        )}
      </button>
      {open && (
        <div className="border-t bg-muted/20 p-3">
          <ChainDetail traceId={item.trace_id} />
        </div>
      )}
    </div>
  )
}

/* ---------- 页面 ---------- */

export default function TracesPage() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [expanded, setExpanded] = useState<string | null>(null)

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['collab-traces', page],
    queryFn: () => fetchCollabTraces(page, 20),
    retry: 1,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / 20))

  const toggle = (traceId: string) => {
    setExpanded((cur) => (cur === traceId ? null : traceId))
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate('/agents')}>
            <ArrowLeft className="size-4" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold text-foreground">协同调用链</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              跨 Agent 协同监控：一次任务中多个 Agent 的衔接追踪（如 News → Knowledge Ingestion）
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" className="gap-2" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={cn('size-3.5', isFetching && 'animate-spin')} />
          刷新
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <ScrollText className="size-4 text-muted-foreground" /> 跨 Agent 调用链
            {total > 0 && (
              <Badge variant="secondary" className="text-[10px]">
                {total}
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {isLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-24 w-full" />
              ))}
            </div>
          ) : isError ? (
            <EmptyState icon={Network} title="无法加载调用链" description="traces 端点不可用" />
          ) : items.length === 0 ? (
            <EmptyState
              icon={Network}
              title="暂无跨 Agent 调用链"
              description="运行一次新闻入库等协同任务后，将在此按 trace 聚合展示"
            />
          ) : (
            items.map((item) => (
              <TraceRow
                key={item.trace_id}
                item={item}
                open={expanded === item.trace_id}
                onToggle={() => toggle(item.trace_id)}
              />
            ))
          )}

          {items.length > 0 && (
            <div className="flex items-center justify-between pt-2 text-xs text-muted-foreground">
              <span>
                共 {total} 条 · 第 {page} / {totalPages} 页
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  上一页
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                >
                  下一页
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}