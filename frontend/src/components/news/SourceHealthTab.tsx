import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Activity, AlertTriangle, CheckCircle2, CircleOff, Clock, Database, GitCompareArrows, Gauge, Power, Radio } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { fetchSourceHealth, setNewsSourceEnabled, type SourceHealth } from '@/services/news'

const STATUS_META: Record<
  SourceHealth['status'],
  { label: string; className: string; dot: string }
> = {
  healthy: { label: '健康', className: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400', dot: 'bg-emerald-400' },
  degraded: { label: '降级', className: 'border-amber-500/30 bg-amber-500/10 text-amber-400', dot: 'bg-amber-400' },
  error: { label: '异常', className: 'border-red-500/30 bg-red-500/10 text-red-400', dot: 'bg-red-400' },
  disabled: { label: '已停用', className: 'border-muted bg-muted/40 text-muted-foreground', dot: 'bg-muted-foreground' },
  no_data: { label: '无数据', className: 'border-sky-500/30 bg-sky-500/10 text-sky-400', dot: 'bg-sky-400' },
}

function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—'
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`
}

function Stat({ icon: Icon, label, value, tone }: {
  icon: typeof Clock
  label: string
  value: string | number
  tone?: 'good' | 'bad' | 'normal'
}) {
  const color =
    tone === 'good' ? 'text-emerald-400'
    : tone === 'bad' ? 'text-red-400'
    : 'text-foreground'
  return (
    <div className="flex items-center gap-2">
      <Icon className={`size-4 ${tone === 'bad' ? 'text-red-400' : 'text-muted-foreground'}`} />
      <div>
        <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className={`text-sm font-semibold ${color}`}>{value}</p>
      </div>
    </div>
  )
}

function SourceCard({ source, onToggle, toggling }: {
  source: SourceHealth
  onToggle: (source: SourceHealth) => void
  toggling: boolean
}) {
  const meta = STATUS_META[source.status]
  const successRate =
    source.total_runs > 0
      ? Math.round((source.success_count / source.total_runs) * 100)
      : null
  const lastSuccess = source.total_runs > 0 && source.last_success !== false

  return (
    <Card className={`transition-shadow hover:shadow-[var(--shadow-soft)] ${source.status === 'error' ? 'border-red-500/40' : ''}`}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className={`size-2 shrink-0 rounded-full ${meta.dot}`} />
              <h3 className="min-w-0 truncate text-sm font-semibold text-foreground">
                {source.name}
              </h3>
            </div>
            <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
              {source.source_id} · {source.source_type}
            </p>
          </div>
          <Badge variant="outline" className={`shrink-0 ${meta.className}`}>
            {meta.label}
          </Badge>
        </div>

        {source.status === 'error' && source.last_error && (
          <div className="mt-3 flex items-start gap-2 rounded-md bg-red-500/10 px-2.5 py-2 text-xs text-red-300">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
            <span className="min-w-0 break-words">{source.last_error}</span>
          </div>
        )}

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat
            icon={Clock}
            label="Latency"
            value={formatMs(source.last_latency_ms)}
            tone={source.last_latency_ms && source.last_latency_ms > 10000 ? 'bad' : 'normal'}
          />
          <Stat
            icon={AlertTriangle}
            label="Errors"
            value={source.failed_count}
            tone={source.failed_count > 0 ? 'bad' : 'good'}
          />
          <Stat
            icon={Database}
            label="Articles"
            value={source.total_stored}
            tone="normal"
          />
          <Stat
            icon={GitCompareArrows}
            label="Duplicates"
            value={source.total_duplicates}
            tone={source.total_duplicates > source.total_stored && source.total_duplicates > 0 ? 'bad' : 'normal'}
          />
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border/60 pt-2.5 text-[11px] text-muted-foreground">
          <span>成功率 <b className="text-foreground">{successRate ?? '—'}%</b></span>
          <span>采集 <b className="text-foreground">{source.total_runs}</b> 次</span>
          <span>平均延迟 <b className="text-foreground">{formatMs(source.avg_latency_ms)}</b></span>
          <span>累计错误 <b className={source.error_count ? 'text-red-400' : 'text-foreground'}>{source.error_count ?? 0}</b></span>
          {source.last_collected_at && (
            <span className="ml-auto">
              最近采集 {new Date(source.last_collected_at).toLocaleString('zh-CN')}
            </span>
          )}
          {source.total_runs > 0 && !lastSuccess && (
            <span className="text-red-400">最近一次失败</span>
          )}
        </div>

        {/* 启停联动（NIC-C3） */}
        <div className="mt-3 flex items-center justify-end border-t border-border/60 pt-2.5">
          <button
            onClick={() => onToggle(source)}
            disabled={toggling}
            className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
              source.enabled
                ? 'border-red-500/30 bg-red-500/10 text-red-400 hover:bg-red-500/20'
                : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20'
            }`}
          >
            <Power className="size-3.5" />
            {source.enabled ? '停用' : '启用'}
          </button>
        </div>
      </CardContent>
    </Card>
  )
}

export function SourceHealthTab() {
  const queryClient = useQueryClient()
  const { data, isLoading, isError, refetch, isRefetching } = useQuery({
    queryKey: ['source-health'],
    queryFn: () => fetchSourceHealth(30),
  })

  const toggleMutation = useMutation({
    mutationFn: ({ source, enabled }: { source: SourceHealth; enabled: boolean }) =>
      setNewsSourceEnabled(source.source_id, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['source-health'] })
    },
  })

  const handleToggle = (source: SourceHealth) => {
    toggleMutation.mutate({ source, enabled: !source.enabled })
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-32 w-full rounded-xl" />
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <Card>
        <CardContent className="py-10 text-center">
          <p className="text-sm text-destructive">Source Health 加载失败，请检查后端服务</p>
        </CardContent>
      </Card>
    )
  }

  const coveragePct = Math.round((data?.coverage ?? 0) * 100)
  const statusCounts = (data?.sources ?? []).reduce<Record<string, number>>(
    (acc, s) => {
      acc[s.status] = (acc[s.status] ?? 0) + 1
      return acc
    },
    {}
  )

  return (
    <div className="space-y-4">
      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2">
              <Gauge className="size-4 text-primary" />
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground">覆盖率</p>
            </div>
            <p className="mt-1 text-2xl font-bold text-foreground">{coveragePct}%</p>
            <p className="text-[11px] text-muted-foreground">
              健康源 {data?.healthy_sources ?? 0} / 启用 {data?.enabled_sources ?? 0}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2">
              <Radio className="size-4 text-primary" />
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground">源总数</p>
            </div>
            <p className="mt-1 text-2xl font-bold text-foreground">{data?.total_sources ?? 0}</p>
            <p className="text-[11px] text-muted-foreground">统计范围 {data?.days ?? 30} 天</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="size-4 text-emerald-400" />
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground">健康</p>
            </div>
            <p className="mt-1 text-2xl font-bold text-emerald-400">{statusCounts.healthy ?? 0}</p>
            <p className="text-[11px] text-muted-foreground">含降级 {statusCounts.degraded ?? 0}</p>
          </CardContent>
        </Card>
        <Card className={statusCounts.error ? 'border-red-500/40' : ''}>
          <CardContent className="p-4">
            <div className="flex items-center gap-2">
              <CircleOff className={`size-4 ${statusCounts.error ? 'text-red-400' : 'text-muted-foreground'}`} />
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground">异常</p>
            </div>
            <p className={`mt-1 text-2xl font-bold ${statusCounts.error ? 'text-red-400' : 'text-foreground'}`}>
              {statusCounts.error ?? 0}
            </p>
            <p className="text-[11px] text-muted-foreground">无数据 {statusCounts.no_data ?? 0} · 停用 {statusCounts.disabled ?? 0}</p>
          </CardContent>
        </Card>
      </div>

      {/* Action bar */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          按源展示 Latency / Errors / Articles / Duplicates 四项采集指标
        </p>
        <button
          onClick={() => refetch()}
          disabled={isRefetching}
          className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
        >
          <Activity className={`size-3.5 ${isRefetching ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>

      {/* Source cards */}
      {!data?.sources.length ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-sm text-muted-foreground">暂无新闻源健康数据</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3">
          {data.sources.map((s) => (
            <SourceCard
              key={s.source_id}
              source={s}
              onToggle={handleToggle}
              toggling={toggleMutation.isPending}
            />
          ))}
        </div>
      )}
    </div>
  )
}