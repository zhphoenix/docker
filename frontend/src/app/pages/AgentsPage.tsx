import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Activity,
  Bot,
  CheckCircle2,
  Clock,
  Gauge,
  RefreshCw,
  ScrollText,
  Store,
  TrendingUp,
  TriangleAlert,
  Network,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import {
  fetchAgentLogs,
  fetchAgents,
  fetchAgentsSummary,
  type AgentInfo,
  type AgentSummaryItem,
  type LogEntry,
} from '@/services/agents'
import { cn } from '@/lib/utils'

const STATUS_META: Record<string, { label: string; dot: string }> = {
  active: { label: '运行中', dot: 'bg-success' },
  paused: { label: '已暂停', dot: 'bg-amber-500' },
  deprecated: { label: '已下线', dot: 'bg-muted-foreground/40' },
}

const LOG_LEVEL_DOT: Record<string, string> = {
  completed: 'bg-emerald-500',
  success: 'bg-emerald-500',
  failed: 'bg-destructive',
  running: 'bg-sky-500',
  info: 'bg-muted-foreground/50',
  error: 'bg-destructive',
  warning: 'bg-amber-500',
}

function formatLastActive(ts: string | null): string {
  if (!ts) return '从未运行'
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} 小时前`
  return `${Math.floor(hours / 24)} 天前`
}

function fmtTime(ts: string | null): string {
  if (!ts) return '—'
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/* ---------- 第 1 栏：Agent Registry 卡片 ---------- */

function AgentRegistryCard({ agent, onClick }: { agent: AgentInfo; onClick: () => void }) {
  const meta = STATUS_META[agent.status] ?? STATUS_META.active
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full rounded-lg border p-3 text-left transition-colors hover:border-primary/40 hover:bg-muted/30"
    >
      <div className="flex items-center gap-2">
        <div className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Bot className="size-3.5 text-primary" strokeWidth={1.8} />
        </div>
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">
          {agent.display_name || agent.name}
        </span>
        <span className={cn('size-2 shrink-0 rounded-full', meta.dot)} title={meta.label} />
      </div>
      {agent.description && (
        <p className="mt-1.5 line-clamp-1 text-xs text-muted-foreground">{agent.description}</p>
      )}
      <div className="mt-1.5 flex items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        <Badge variant={agent.source === 'builtin' ? 'default' : 'secondary'} className="text-[10px]">
          {agent.source === 'builtin' ? '内置' : '自定义'}
        </Badge>
        {agent.tools.length > 0 && (
          <span className="flex items-center gap-1">
            <Wrench className="size-3" strokeWidth={1.8} />
            {agent.tools.length}
          </span>
        )}
        <span className="flex items-center gap-1">
          <Clock className="size-3" strokeWidth={1.8} />
          {formatLastActive(agent.last_active_at)}
        </span>
      </div>
    </button>
  )
}

/* ---------- 第 2 栏：Runtime Metrics ---------- */

function MetricTile({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: LucideIcon
  label: string
  value: number | string
  accent: string
}) {
  return (
    <div className="rounded-lg border bg-muted/20 p-3">
      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <Icon className={cn('size-3', accent)} /> {label}
      </div>
      <p className={cn('mt-1 text-xl font-semibold', accent)}>{value}</p>
    </div>
  )
}

function AgentRunRow({
  item,
  onClick,
}: {
  item: AgentSummaryItem
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full rounded-md border p-2 text-left transition-colors hover:bg-muted/30"
    >
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="min-w-0 truncate font-medium text-foreground">{item.display_name}</span>
        <div className="flex shrink-0 items-center gap-2">
          {item.failed_today > 0 && <span className="text-destructive">{item.failed_today} 失败</span>}
          <span className="text-muted-foreground">{item.runs_today} 次</span>
        </div>
      </div>
      <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-emerald-500"
          style={{ width: `${Math.min(100, item.success_rate)}%` }}
        />
      </div>
    </button>
  )
}

/* ---------- 第 3 栏：Recent Logs ---------- */

function RecentLogRow({ log }: { log: LogEntry }) {
  const dot = LOG_LEVEL_DOT[log.level] ?? 'bg-muted-foreground/50'
  return (
    <div className="rounded-lg border p-2.5">
      <div className="flex items-center gap-2 text-xs">
        <span className={cn('size-1.5 shrink-0 rounded-full', dot)} />
        <span className="min-w-0 truncate font-medium text-foreground">{log.entity}</span>
        <span className="ml-auto shrink-0 whitespace-nowrap text-muted-foreground">
          {fmtTime(log.time)}
        </span>
      </div>
      <p className="mt-1 line-clamp-1 text-[11px] text-muted-foreground">{log.message}</p>
    </div>
  )
}

/* ---------- 页面：三栏布局（规范 §16） ---------- */

export default function AgentsPage() {
  const navigate = useNavigate()
  const agentsQuery = useQuery({ queryKey: ['agents'], queryFn: fetchAgents, retry: 1 })
  const summaryQuery = useQuery({
    queryKey: ['agents-summary'],
    queryFn: fetchAgentsSummary,
    retry: 1,
  })
  const logsQuery = useQuery({
    queryKey: ['recent-logs'],
    queryFn: () => fetchAgentLogs({ pageSize: 8 }),
    retry: 1,
  })

  const agents = agentsQuery.data?.agents ?? []
  const summary = summaryQuery.data
  const recentLogs = logsQuery.data?.items ?? []
  const isFetching =
    agentsQuery.isFetching || summaryQuery.isFetching || logsQuery.isFetching

  const refreshAll = () => {
    agentsQuery.refetch()
    summaryQuery.refetch()
    logsQuery.refetch()
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Agent Center</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Agent 注册表 · 运行指标 · 最近日志
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="gap-2" onClick={() => navigate('/agents/traces')}>
            <Network className="size-3.5" />
            协同调用链
          </Button>
          <Button variant="outline" size="sm" className="gap-2" onClick={() => navigate('/agents/marketplace')}>
            <Store className="size-3.5" />
            模板市场
          </Button>
          <Button variant="outline" size="sm" className="gap-2" onClick={refreshAll}>
            <RefreshCw className={cn('size-3.5', isFetching && 'animate-spin')} />
            刷新
          </Button>
        </div>
      </div>

      {/* 三栏：Agent Registry | Runtime Metrics | Recent Logs */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {/* 第 1 栏 Agent Registry */}
        <Card className="xl:col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Bot className="size-4 text-muted-foreground" /> Agent Registry
              {agents.length > 0 && (
                <Badge variant="secondary" className="text-[10px]">
                  {agents.length}
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="max-h-[620px] space-y-2 overflow-y-auto pr-1">
            {agentsQuery.isLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-20 w-full" />
                ))}
              </div>
            ) : agentsQuery.isError ? (
              <EmptyState icon={Bot} title="无法加载" description="Agent 列表不可用" />
            ) : agents.length === 0 ? (
              <EmptyState icon={Bot} title="暂无 Agent" description="尚未注册任何 Agent" />
            ) : (
              agents.map((agent) => (
                <AgentRegistryCard
                  key={agent.id}
                  agent={agent}
                  onClick={() => navigate(`/agents/${agent.id}`)}
                />
              ))
            )}
          </CardContent>
        </Card>

        {/* 第 2 栏 Runtime Metrics */}
        <Card className="xl:col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Gauge className="size-4 text-muted-foreground" /> Runtime Metrics
              <span className="text-[10px] font-normal text-muted-foreground">今日</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {summaryQuery.isLoading ? (
              <div className="grid grid-cols-2 gap-2">
                {[1, 2, 3, 4].map((i) => (
                  <Skeleton key={i} className="h-16 w-full" />
                ))}
              </div>
            ) : summaryQuery.isError || !summary ? (
              <EmptyState icon={Gauge} title="指标不可用" description="summary 端点不可用" />
            ) : (
              <>
                <div className="grid grid-cols-2 gap-2">
                  <MetricTile
                    icon={Activity}
                    label="今日运行"
                    value={summary.total.runs_today}
                    accent="text-primary"
                  />
                  <MetricTile
                    icon={CheckCircle2}
                    label="成功"
                    value={summary.total.success_today}
                    accent="text-emerald-500"
                  />
                  <MetricTile
                    icon={TriangleAlert}
                    label="失败"
                    value={summary.total.failed_today}
                    accent="text-destructive"
                  />
                  <MetricTile
                    icon={TrendingUp}
                    label="成功率"
                    value={`${summary.total.success_rate}%`}
                    accent="text-sky-500"
                  />
                </div>

                <div>
                  <p className="mb-2 text-xs text-muted-foreground">各 Agent 今日运行</p>
                  <div className="space-y-1.5">
                    {summary.agents.filter((a) => a.runs_today > 0).length === 0 ? (
                      <p className="text-xs text-muted-foreground">今日暂无运行记录</p>
                    ) : (
                      summary.agents
                        .filter((a) => a.runs_today > 0)
                        .sort((a, b) => b.runs_today - a.runs_today)
                        .slice(0, 6)
                        .map((a) => (
                          <AgentRunRow
                            key={a.agent_id}
                            item={a}
                            onClick={() => navigate(`/agents/${a.agent_id}`)}
                          />
                        ))
                    )}
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* 第 3 栏 Recent Logs */}
        <Card className="xl:col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <ScrollText className="size-4 text-muted-foreground" /> Recent Logs
            </CardTitle>
          </CardHeader>
          <CardContent className="max-h-[620px] space-y-2 overflow-y-auto pr-1">
            {logsQuery.isLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-14 w-full" />
                ))}
              </div>
            ) : logsQuery.isError ? (
              <EmptyState icon={ScrollText} title="日志不可用" description="logs 端点不可用" />
            ) : recentLogs.length === 0 ? (
              <EmptyState icon={ScrollText} title="暂无日志" description="Agent 运行后在此展示" />
            ) : (
              recentLogs.map((log, i) => (
                <RecentLogRow key={`${log.run_id ?? log.task_id}-${i}`} log={log} />
              ))
            )}
          </CardContent>
        </Card>
      </div>

      {/* Footer note */}
      <p className="text-center text-xs text-muted-foreground">
        点击 Agent 卡片进入详情页 · 更多管理能力将在后续开放
      </p>
    </div>
  )
}