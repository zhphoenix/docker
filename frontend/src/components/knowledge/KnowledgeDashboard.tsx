import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  Boxes,
  Network,
  Lightbulb,
  RefreshCw,
  ListChecks,
  Hourglass,
  Loader2,
  CircleCheck,
  CircleX,
  Activity,
  Gauge,
  Database,
  ChevronRight,
  Cpu,
  PencilLine,
  Share2,
  CalendarClock,
  Users,
  Percent,
  TrendingUp,
  Sparkles,
  Scale,
  Clock3,
  Flame,
  Building2,
  Zap,
  BarChart3,
  MessageSquareQuote,
} from 'lucide-react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Progress } from '@/components/ui/progress'
import { EmptyState } from '@/components/common/EmptyState'
import {
  fetchKnowledgeAnalytics,
  fetchKnowledgeInsights,
  fetchKnowledgeStats,
  type KnowledgeAnalytics,
  type KnowledgeInsights,
} from '@/services/knowledge'
import { fetchHealth } from '@/services/health'
import { cn } from '@/lib/utils'

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.05 } },
}

const item = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.25 } },
}

function formatNumber(n: number): string {
  return n.toLocaleString('zh-CN')
}

function formatTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const TASK_TYPE_LABELS: Record<string, string> = {
  knowledge_extraction: '知识提取',
  doc_pipeline: '文档 Pipeline',
  batch_embed: '批量向量化',
  approval: 'Inbox 审核',
  're-embed': '重新向量化',
}

const STATUS_VARIANTS: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'outline',
  running: 'secondary',
  done: 'default',
  failed: 'destructive',
}

const DOC_STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  indexed: '已索引',
  indexing: '索引中',
  failed: '失败',
}

interface KnowledgeDashboardProps {
  onNavigateToTasks?: (taskId?: string) => void
}

export function KnowledgeDashboard({ onNavigateToTasks }: KnowledgeDashboardProps) {
  const queryClient = useQueryClient()
  const [analyticsRange, setAnalyticsRange] = useState(7)

  const statsQuery = useQuery({
    queryKey: ['knowledge-stats'],
    queryFn: fetchKnowledgeStats,
    retry: 1,
  })

  // KOC-D1: Analytics 五维 + 趋势（7/30/90 天切换）
  const analyticsQuery = useQuery({
    queryKey: ['knowledge-analytics', analyticsRange],
    queryFn: () => fetchKnowledgeAnalytics(analyticsRange),
    retry: 1,
  })

  // KOC-D2: Insights 运营洞察（Hot Topics / Trending / Emerging Concepts）
  const insightsQuery = useQuery({
    queryKey: ['knowledge-insights'],
    queryFn: () => fetchKnowledgeInsights(7, 10),
    retry: 1,
  })

  // 服务状态：独立缓存键 ['dashboard-health']，避免与 StatusBar 的 ['health'] 轮询共享被动刷新
  const healthQuery = useQuery({
    queryKey: ['dashboard-health'],
    queryFn: fetchHealth,
    staleTime: Infinity,
    refetchInterval: false,
    refetchOnWindowFocus: false,
    retry: 1,
  })

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ['knowledge-stats'] })
    queryClient.invalidateQueries({ queryKey: ['knowledge-analytics'] })
    queryClient.invalidateQueries({ queryKey: ['knowledge-insights'] })
    healthQuery.refetch()
  }

  const stats = statsQuery.data
  const analytics = analyticsQuery.data
  const services = healthQuery.data?.services ?? {}
  const coreUp =
    services['qdrant'] === 'up' && services['postgres'] === 'up'
  // KOC-F5: SiYuan 渲染链路（容器 + Sync adapter 均可用 → 正常）
  const renderLinkUp =
    services['siyuan'] === 'up' && (services['siyuan_adapter'] ?? 'up') === 'up'

  // 设计 §15 首页统计：Entities / Relationships / Facts / Events / Communities / Coverage
  const statCards = [
    { label: 'Entities', value: analytics?.growth.entities ?? 0, icon: Network, color: 'text-violet-500' },
    { label: 'Relationships', value: analytics?.growth.relations ?? 0, icon: Share2, color: 'text-sky-500' },
    { label: 'Facts', value: analytics?.growth.facts ?? 0, icon: Lightbulb, color: 'text-amber-500' },
    { label: 'Events', value: analytics?.growth.events ?? 0, icon: CalendarClock, color: 'text-rose-500' },
    { label: 'Communities', value: analytics?.growth.communities ?? 0, icon: Users, color: 'text-pink-500' },
    {
      label: 'Coverage',
      value: analytics ? `${analytics.coverage.knowledge_coverage}%` : '—',
      icon: Percent,
      color: 'text-emerald-500',
    },
  ]

  const queue = stats?.task_queue ?? { pending: 0, running: 0, done: 0, failed: 0 }
  const quality = stats?.quality ?? { avg_chunk_length: null, embedding_coverage: null, entity_confidence: null }

  return (
    <div className="space-y-6">
      {/* Toolbar */}
      <div className="flex justify-end">
        <Button
          variant="outline"
          size="sm"
          className="gap-2"
          onClick={handleRefresh}
          disabled={statsQuery.isFetching}
        >
          <RefreshCw className={cn('size-3.5', statsQuery.isFetching && 'animate-spin')} />
          刷新
        </Button>
      </div>

      {statsQuery.isLoading || analyticsQuery.isLoading ? (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <Card key={i}>
                <CardContent className="p-5">
                  <Skeleton className="h-4 w-16" />
                  <Skeleton className="mt-3 h-8 w-20" />
                </CardContent>
              </Card>
            ))}
          </div>
          <Card>
            <CardContent className="space-y-3 p-6">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </CardContent>
          </Card>
        </div>
      ) : statsQuery.isError ? (
        <EmptyState
          icon={Database}
          title="无法加载知识库统计"
          description="无法连接到后端服务，请确认 LangGraph 服务已启动（端口 8100）"
          action={{ label: '重试', onClick: () => statsQuery.refetch() }}
        />
      ) : (
        <motion.div
          variants={container}
          initial="hidden"
          animate="show"
          className="space-y-6"
        >
          {/* 顶部统计卡（设计 §15） */}
          <motion.div
            variants={item}
            className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6"
          >
            {statCards.map((s) => (
              <Card key={s.label}>
                <CardContent className="p-5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-muted-foreground">{s.label}</span>
                    <s.icon className={cn('size-4', s.color)} strokeWidth={1.8} />
                  </div>
                  <div className="mt-2 text-2xl font-bold tabular-nums text-foreground">
                    {typeof s.value === 'number' ? formatNumber(s.value) : s.value}
                  </div>
                </CardContent>
              </Card>
            ))}
          </motion.div>

          {/* KOC-D1 Analytics：知识增长趋势 + 五维指标 */}
          {analytics && (
            <motion.div variants={item}>
              <AnalyticsSection
                analytics={analytics}
                range={analyticsRange}
                onRangeChange={setAnalyticsRange}
              />
            </motion.div>
          )}

          {/* KOC-D2 Insights：运营洞察（设计 §7） */}
          {insightsQuery.data && (
            <motion.div variants={item}>
              <InsightsSection insights={insightsQuery.data} />
            </motion.div>
          )}

          {/* 处理队列 + 服务状态 + 知识质量 */}
          <motion.div
            variants={item}
            className="grid grid-cols-1 gap-4 lg:grid-cols-3"
          >
            {/* 处理队列 */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ListChecks className="size-4 text-primary" strokeWidth={1.8} />
                  处理队列
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <QueueItem
                  icon={Loader2}
                  label="Running"
                  value={queue.running}
                  className="border-primary/30 bg-primary/5 text-primary"
                  animate={queue.running > 0}
                />
                <QueueItem
                  icon={Hourglass}
                  label="Pending"
                  value={queue.pending}
                  className="border-muted-foreground/30 bg-muted/50 text-muted-foreground"
                />
                <QueueItem
                  icon={CircleCheck}
                  label="Done"
                  value={queue.done}
                  className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600"
                />
                <QueueItem
                  icon={CircleX}
                  label="Failed"
                  value={queue.failed}
                  className="border-destructive/30 bg-destructive/10 text-destructive"
                />
              </CardContent>
            </Card>

            {/* 服务状态 */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Activity className="size-4 text-primary" strokeWidth={1.8} />
                  服务状态
                  <Badge
                    variant={healthQuery.data?.status === 'healthy' ? 'default' : 'secondary'}
                    className="ml-auto"
                  >
                    {healthQuery.data?.status ?? '检测中'}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                {healthQuery.isLoading ? (
                  <div className="space-y-2">
                    {[1, 2, 3, 4].map((i) => (
                      <Skeleton key={i} className="h-6 w-full" />
                    ))}
                  </div>
                ) : Object.keys(services).length === 0 ? (
                  <p className="text-xs text-muted-foreground">暂无服务信息</p>
                ) : (
                  <div className="space-y-3">
                    {/* KOC-F5: SiYuan 渲染链路（容器 + Sync adapter） */}
                    <div className="rounded-lg border px-3 py-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-foreground">
                          SiYuan 渲染链路
                        </span>
                        <Badge
                          variant={renderLinkUp ? 'default' : 'destructive'}
                          className="px-1.5 py-0 text-[9px]"
                        >
                          {renderLinkUp ? '正常' : '异常'}
                        </Badge>
                      </div>
                      <div className="mt-2 grid grid-cols-2 gap-2">
                        <div className="flex items-center gap-2 rounded-md bg-muted/50 px-2 py-1.5">
                          <span
                            className={cn(
                              'size-2 shrink-0 rounded-full',
                              services['siyuan'] === 'up' ? 'bg-emerald-500' : 'bg-destructive'
                            )}
                          />
                          <span className="truncate text-xs text-foreground">容器</span>
                          <span className="ml-auto text-[10px] text-muted-foreground">
                            {services['siyuan'] ?? '?'}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 rounded-md bg-muted/50 px-2 py-1.5">
                          <span
                            className={cn(
                              'size-2 shrink-0 rounded-full',
                              services['siyuan_adapter'] === 'up'
                                ? 'bg-emerald-500'
                                : 'bg-destructive'
                            )}
                          />
                          <span className="truncate text-xs text-foreground">Sync Adapter</span>
                          <span className="ml-auto text-[10px] text-muted-foreground">
                            {services['siyuan_adapter'] ?? '?'}
                          </span>
                        </div>
                      </div>
                    </div>
                    {/* 其他服务 */}
                    <div className="grid grid-cols-2 gap-2">
                      {Object.entries(services)
                        .filter(([name]) => name !== 'siyuan' && name !== 'siyuan_adapter')
                        .map(([name, state]) => (
                          <div
                            key={name}
                            className="flex items-center gap-2 rounded-md bg-muted/50 px-2 py-1.5"
                          >
                            <span
                              className={cn(
                                'size-2 shrink-0 rounded-full',
                                state === 'up' ? 'bg-emerald-500' : 'bg-destructive'
                              )}
                            />
                            <span className="truncate text-xs text-foreground">{name}</span>
                          </div>
                        ))}
                    </div>
                  </div>
                )}
                {!coreUp && Object.keys(services).length > 0 && (
                  <p className="mt-3 text-[11px] text-destructive">
                    核心服务（qdrant / postgres）不可用，功能可能受限
                  </p>
                )}
              </CardContent>
            </Card>

            {/* 知识质量 */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Gauge className="size-4 text-primary" strokeWidth={1.8} />
                  知识质量
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <QualityMetric
                  label="Chunk 平均长度"
                  value={quality.avg_chunk_length != null ? `${formatNumber(quality.avg_chunk_length)} tokens` : '—'}
                  icon={Boxes}
                />
                <QualityMetric
                  label="Embedding 覆盖率"
                  value={quality.embedding_coverage != null ? `${quality.embedding_coverage}%` : '—'}
                  icon={Cpu}
                  progress={quality.embedding_coverage}
                />
                <QualityMetric
                  label="实体置信度"
                  value={quality.entity_confidence != null ? `${quality.entity_confidence}%` : '—'}
                  icon={Gauge}
                  progress={quality.entity_confidence}
                />
              </CardContent>
            </Card>
          </motion.div>

          {/* 最近任务 + 最近更新 */}
          <motion.div
            variants={item}
            className="grid grid-cols-1 gap-4 lg:grid-cols-2"
          >
            {/* 最近任务 */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ListChecks className="size-4 text-primary" strokeWidth={1.8} />
                  最近任务
                </CardTitle>
              </CardHeader>
              <CardContent>
                {stats?.recent_tasks.length === 0 ? (
                  <p className="py-6 text-center text-xs text-muted-foreground">
                    暂无处理任务
                  </p>
                ) : (
                  <div className="space-y-2">
                    {stats?.recent_tasks.map((task) => (
                      <button
                        key={task.id}
                        type="button"
                        onClick={() => onNavigateToTasks?.(task.id)}
                        className="flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left transition-colors hover:bg-muted/50"
                        title="点击跳转到处理详情定位该任务"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium text-foreground">
                            {task.title}
                          </div>
                          <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                            <Badge variant="outline" className="px-1.5 py-0 text-[9px]">
                              {TASK_TYPE_LABELS[task.task_type] ?? task.task_type}
                            </Badge>
                            <span>{formatTime(task.created_at)}</span>
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          <div className="w-16">
                            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                              <div
                                className={cn(
                                  'h-full rounded-full',
                                  task.status === 'failed' ? 'bg-destructive' : 'bg-primary',
                                  task.status === 'running' && 'animate-pulse'
                                )}
                                style={{ width: `${Math.max(0, Math.min(100, task.progress))}%` }}
                              />
                            </div>
                          </div>
                          <Badge
                            variant={STATUS_VARIANTS[task.status] ?? 'outline'}
                            className="px-1.5 py-0 text-[9px]"
                          >
                            {task.status}
                          </Badge>
                          <ChevronRight className="size-3.5 text-muted-foreground" />
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* 最近更新 */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <PencilLine className="size-4 text-primary" strokeWidth={1.8} />
                  最近更新
                </CardTitle>
              </CardHeader>
              <CardContent>
                {stats?.recent_updates.length === 0 ? (
                  <p className="py-6 text-center text-xs text-muted-foreground">
                    暂无文档更新
                  </p>
                ) : (
                  <div className="space-y-2">
                    {stats?.recent_updates.map((doc) => (
                      <div
                        key={doc.id}
                        className="flex items-center gap-3 rounded-lg border px-3 py-2"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium text-foreground">
                            {doc.company || doc.symbol}
                          </div>
                          <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                            <Badge variant="outline" className="px-1.5 py-0 text-[9px]">
                              {doc.market?.toUpperCase()}
                            </Badge>
                            <span>{doc.symbol}</span>
                            <span>·</span>
                            <span>{formatTime(doc.updated_at)}</span>
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          <Badge
                            variant={doc.status === 'failed' ? 'destructive' : 'secondary'}
                            className="px-1.5 py-0 text-[9px]"
                          >
                            {DOC_STATUS_LABELS[doc.status] ?? doc.status}
                          </Badge>
                          <span className="text-[11px] tabular-nums text-muted-foreground">
                            {doc.chunk_count} chunks
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>

          {/* Collections 概览 */}
          <motion.div variants={item}>
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Database className="size-4 text-primary" strokeWidth={1.8} />
                  Collections 概览
                </CardTitle>
              </CardHeader>
              <CardContent>
                {stats?.collections.length === 0 ? (
                  <p className="py-6 text-center text-xs text-muted-foreground">
                    暂无知识集合
                  </p>
                ) : (
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {stats?.collections.map((coll) => {
                      const pct =
                        coll.chunk_count > 0
                          ? Math.round((coll.embedded_count / coll.chunk_count) * 100)
                          : 0
                      return (
                        <button
                          key={coll.id}
                          type="button"
                          onClick={() => onNavigateToTasks?.()}
                          className="rounded-lg border p-3 text-left transition-colors hover:bg-muted/50"
                          title="点击进入处理详情"
                        >
                          <div className="flex items-center justify-between">
                            <span className="truncate text-sm font-medium text-foreground">
                              {coll.name}
                            </span>
                            {coll.domain && (
                              <Badge variant="secondary" className="text-[9px]">
                                {coll.domain}
                              </Badge>
                            )}
                          </div>
                          <div className="mt-2 flex items-center justify-between text-[11px] text-muted-foreground">
                            <span>
                              向量化 {formatNumber(coll.embedded_count)}/{formatNumber(coll.chunk_count)}
                            </span>
                            <span className="tabular-nums">{pct}%</span>
                          </div>
                          <Progress value={pct} className="mt-1.5 h-1.5" />
                        </button>
                      )
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>
        </motion.div>
      )}
    </div>
  )
}

function QueueItem({
  icon: Icon,
  label,
  value,
  className,
  animate,
}: {
  icon: typeof Loader2
  label: string
  value: number
  className?: string
  animate?: boolean
}) {
  return (
    <div
      className={cn(
        'flex items-center justify-between rounded-lg border px-3 py-2',
        className
      )}
    >
      <span className="flex items-center gap-2 text-sm font-medium">
        <Icon className={cn('size-4', animate && 'animate-spin')} strokeWidth={1.8} />
        {label}
      </span>
      <span className="text-lg font-bold tabular-nums">{formatNumber(value)}</span>
    </div>
  )
}

function QualityMetric({
  label,
  value,
  icon: Icon,
  progress,
}: {
  label: string
  value: string
  icon: typeof Boxes
  progress?: number | null
}) {
  return (
    <div>
      <div className="flex items-center justify-between text-xs">
        <span className="flex items-center gap-1.5 text-muted-foreground">
          <Icon className="size-3.5" strokeWidth={1.8} />
          {label}
        </span>
        <span className="font-medium tabular-nums text-foreground">{value}</span>
      </div>
      {progress != null && <Progress value={progress} className="mt-1.5 h-1.5" />}
    </div>
  )
}

/* ---------- KOC-D1 Analytics 区块 ---------- */

const ANALYTICS_RANGES = [
  { value: 7, label: '7 天' },
  { value: 30, label: '30 天' },
  { value: 90, label: '90 天' },
]

function TrendLineChart({ analytics }: { analytics: KnowledgeAnalytics }) {
  const data = useMemo(() => {
    const dates = new Set<string>()
    for (const key of ['entities', 'facts', 'events'] as const) {
      for (const p of analytics.trends[key]) dates.add(p.date)
    }
    return [...dates]
      .sort()
      .map((date) => {
        const find = (arr: Array<{ date: string; count: number }>) =>
          arr.find((p) => p.date === date)?.count ?? 0
        return {
          date: date.slice(5), // MM-DD
          entities: find(analytics.trends.entities),
          facts: find(analytics.trends.facts),
          events: find(analytics.trends.events),
        }
      })
  }, [analytics])

  if (data.length === 0) {
    return (
      <p className="py-10 text-center text-xs text-muted-foreground">
        所选区间内暂无新增知识
      </p>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="date" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
        <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} allowDecimals={false} />
        <Tooltip
          contentStyle={{ fontSize: 12, borderRadius: 8 }}
          labelStyle={{ fontWeight: 600 }}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Line type="monotone" dataKey="entities" name="实体" stroke="#8b5cf6" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="facts" name="事实" stroke="#f59e0b" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="events" name="事件" stroke="#f43f5e" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}

function AnalyticsSection({
  analytics,
  range,
  onRangeChange,
}: {
  analytics: KnowledgeAnalytics
  range: number
  onRangeChange: (r: number) => void
}) {
  const { growth, coverage, usage, quality, freshness } = analytics
  const totalAssets =
    growth.entities + growth.relations + growth.facts + growth.events

  const dimensions = [
    {
      label: 'Knowledge Growth',
      value: formatNumber(totalAssets),
      unit: '资产',
      icon: TrendingUp,
      color: 'text-violet-500',
      detail: `${formatNumber(growth.entities)} 实体 · ${formatNumber(growth.relations)} 关系 · ${formatNumber(growth.facts)} 事实`,
    },
    {
      label: 'Knowledge Coverage',
      value: `${coverage.knowledge_coverage}%`,
      unit: '实体-事实覆盖',
      icon: Percent,
      color: 'text-emerald-500',
      detail: `${coverage.entity_types} 实体类型 · 向量化 ${coverage.embedding_coverage ?? '—'}%`,
    },
    {
      label: 'Knowledge Usage',
      value: formatNumber(usage.runs),
      unit: `次 / ${range} 天`,
      icon: Sparkles,
      color: 'text-sky-500',
      detail: `今日 ${usage.runs_today} · 榜首 ${usage.top_agents[0]?.agent_id ?? '—'}`,
    },
    {
      label: 'Knowledge Quality',
      value: quality.entity_confidence != null ? `${quality.entity_confidence}%` : '—',
      unit: '实体置信度',
      icon: Scale,
      color: 'text-amber-500',
      detail: `冲突 ${quality.conflicts_open} · 已核验 ${quality.facts_verified}/${quality.facts_total}`,
    },
    {
      label: 'Knowledge Freshness',
      value: freshness.last_entity_at ? formatTime(freshness.last_entity_at) : '—',
      unit: '最后入库',
      icon: Clock3,
      color: 'text-rose-500',
      detail: `过期事实 ${freshness.facts_expired} · 区间新增 ${formatNumber(freshness.new_entities + freshness.new_facts + freshness.new_events)}`,
    },
  ]

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      {/* 增长趋势图 */}
      <Card className="lg:col-span-2">
        <CardHeader className="pb-2">
          <CardTitle className="flex flex-wrap items-center gap-2">
            <TrendingUp className="size-4 text-primary" strokeWidth={1.8} />
            知识增长趋势
            <div className="ml-auto flex items-center gap-1">
              {ANALYTICS_RANGES.map((r) => (
                <Button
                  key={r.value}
                  variant={range === r.value ? 'default' : 'outline'}
                  size="sm"
                  className="h-6 px-2 text-[11px]"
                  onClick={() => onRangeChange(r.value)}
                >
                  {r.label}
                </Button>
              ))}
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <TrendLineChart analytics={analytics} />
        </CardContent>
      </Card>

      {/* 五维指标 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2">
            <Gauge className="size-4 text-primary" strokeWidth={1.8} />
            五维运营指标
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {dimensions.map((d) => (
            <div key={d.label} className="rounded-lg border p-2.5">
              <div className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <d.icon className={cn('size-3.5', d.color)} strokeWidth={1.8} />
                  {d.label}
                </span>
                <span className="font-semibold tabular-nums text-foreground">
                  {d.value}
                  <span className="ml-1 text-[10px] font-normal text-muted-foreground">
                    {d.unit}
                  </span>
                </span>
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground">{d.detail}</p>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}

/* ---------- KOC-D2 Insights 区块 ---------- */

function InsightRankRow({
  rank,
  name,
  meta,
  count,
}: {
  rank?: number
  name: string
  meta?: string
  count: number
}) {
  return (
    <div className="flex items-center gap-2.5 rounded-lg border px-2.5 py-1.5">
      {rank != null && (
        <span className="w-5 shrink-0 text-center text-[11px] font-bold tabular-nums text-muted-foreground">
          {rank}
        </span>
      )}
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-medium text-foreground" title={name}>
          {name}
        </div>
        {meta && <div className="truncate text-[10px] text-muted-foreground">{meta}</div>}
      </div>
      <span className="shrink-0 text-[11px] font-semibold tabular-nums text-foreground">
        {count}
      </span>
    </div>
  )
}

function InsightsSection({ insights }: { insights: KnowledgeInsights }) {
  const { hot_topics, trending_companies, emerging_concepts, top_growing, top_mentioned, heatmap } =
    insights

  // 热点关键词标签：count 分级控制字号与颜色强度
  const maxHot = Math.max(1, ...hot_topics.map((t) => t.count))
  const growingMax = Math.max(1, ...top_growing.map((g) => g.count))
  const heatData = useMemo(
    () =>
      heatmap.map((p) => ({
        date: p.date.slice(5),
        entities: p.entities,
        facts: p.facts,
      })),
    [heatmap]
  )

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      {/* Hot Topics：今日热点话题（NIC-D1 数据源） */}
      <Card className="lg:col-span-2">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2">
            <Flame className="size-4 text-orange-500" strokeWidth={1.8} />
            Today&apos;s Hot Topics
            <Badge variant="secondary" className="ml-auto text-[9px]">
              近 {insights.range_days} 天入库共现
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {hot_topics.length === 0 ? (
            <p className="py-6 text-center text-xs text-muted-foreground">
              近期无新增知识入库
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {hot_topics.map((t) => {
                const level = Math.ceil((t.count / maxHot) * 3) // 1..3
                return (
                  <span
                    key={t.topic}
                    className={cn(
                      'rounded-full border px-2.5 py-1 font-medium',
                      level >= 3
                        ? 'border-orange-400/40 bg-orange-500/10 text-orange-600 text-sm'
                        : level === 2
                          ? 'border-amber-400/40 bg-amber-500/10 text-amber-600 text-xs'
                          : 'border-muted-foreground/20 bg-muted/40 text-muted-foreground text-xs'
                    )}
                    title={`出现 ${t.count} 次`}
                  >
                    {t.topic}
                    <span className="ml-1.5 text-[10px] opacity-70">{t.count}</span>
                  </span>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Trending Companies */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2">
            <Building2 className="size-4 text-sky-500" strokeWidth={1.8} />
            Trending Companies
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5">
          {trending_companies.length === 0 ? (
            <p className="py-4 text-center text-xs text-muted-foreground">暂无数据</p>
          ) : (
            trending_companies.map((c, i) => (
              <InsightRankRow
                key={c.name}
                rank={i + 1}
                name={c.name}
                meta={`来源 ${c.source_count} 处`}
                count={c.source_count}
              />
            ))
          )}
        </CardContent>
      </Card>

      {/* Emerging Concepts */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2">
            <Zap className="size-4 text-violet-500" strokeWidth={1.8} />
            Emerging Concepts
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5">
          {emerging_concepts.length === 0 ? (
            <p className="py-4 text-center text-xs text-muted-foreground">暂无数据</p>
          ) : (
            emerging_concepts.map((c) => (
              <InsightRankRow
                key={c.name}
                name={c.name}
                meta={`${c.entity_type} · 置信 ${c.confidence != null ? `${Math.round(c.confidence * 100)}%` : '—'}`}
                count={c.source_count}
              />
            ))
          )}
        </CardContent>
      </Card>

      {/* Top Growing Knowledge */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="size-4 text-emerald-500" strokeWidth={1.8} />
            Top Growing Knowledge
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {top_growing.length === 0 ? (
            <p className="py-4 text-center text-xs text-muted-foreground">暂无数据</p>
          ) : (
            top_growing.map((g) => (
              <div key={g.entity_type}>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-foreground">{g.entity_type}</span>
                  <span className="tabular-nums text-muted-foreground">
                    {g.count} 新增
                  </span>
                </div>
                <Progress
                  value={(g.count / growingMax) * 100}
                  className="mt-1 h-1.5"
                />
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {/* Top Mentioned Companies */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2">
            <MessageSquareQuote className="size-4 text-rose-500" strokeWidth={1.8} />
            Top Mentioned
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5">
          {top_mentioned.length === 0 ? (
            <p className="py-4 text-center text-xs text-muted-foreground">暂无事实提及</p>
          ) : (
            top_mentioned.map((m, i) => (
              <InsightRankRow
                key={m.name}
                rank={i + 1}
                name={m.name}
                meta="事实提及"
                count={m.count}
              />
            ))
          )}
        </CardContent>
      </Card>

      {/* Knowledge Heatmap：近 7 天新增热度 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2">
            <BarChart3 className="size-4 text-amber-500" strokeWidth={1.8} />
            Knowledge Heatmap
          </CardTitle>
        </CardHeader>
        <CardContent>
          {heatData.length === 0 ? (
            <p className="py-4 text-center text-xs text-muted-foreground">暂无入库记录</p>
          ) : (
            <div className="flex h-24 items-end gap-1.5">
              {heatData.map((p) => {
                const h = Math.max(4, (p.entities / Math.max(1, ...heatData.map((x) => x.entities))) * 100)
                return (
                  <div key={p.date} className="flex h-full flex-1 flex-col items-center justify-end gap-1">
                    <div
                      className="w-full rounded-t bg-gradient-to-t from-amber-500/70 to-amber-400"
                      style={{ height: `${h}%` }}
                      title={`${p.date} 新增实体 ${p.entities}`}
                    />
                    <span className="text-[9px] text-muted-foreground">{p.date}</span>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}