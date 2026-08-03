import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  FileText,
  Boxes,
  ScanLine,
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
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Progress } from '@/components/ui/progress'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchKnowledgeStats } from '@/services/knowledge'
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
  reindex: '重新索引',
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

  const statsQuery = useQuery({
    queryKey: ['knowledge-stats'],
    queryFn: fetchKnowledgeStats,
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
    healthQuery.refetch()
  }

  const stats = statsQuery.data
  const services = healthQuery.data?.services ?? {}
  const coreUp =
    services['qdrant'] === 'up' && services['postgres'] === 'up'

  const statCards = [
    { label: 'Documents', value: stats?.documents ?? 0, icon: FileText, color: 'text-primary' },
    { label: 'Chunks', value: stats?.chunks ?? 0, icon: Boxes, color: 'text-sky-500' },
    { label: 'Embedded', value: stats?.embedded ?? 0, icon: ScanLine, color: 'text-emerald-500' },
    { label: 'Entities', value: stats?.entities ?? 0, icon: Network, color: 'text-violet-500' },
    { label: 'Facts', value: stats?.facts ?? 0, icon: Lightbulb, color: 'text-amber-500' },
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

      {statsQuery.isLoading ? (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {[1, 2, 3, 4, 5].map((i) => (
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
          {/* 顶部统计卡 */}
          <motion.div
            variants={item}
            className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5"
          >
            {statCards.map((s) => (
              <Card key={s.label}>
                <CardContent className="p-5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-muted-foreground">{s.label}</span>
                    <s.icon className={cn('size-4', s.color)} strokeWidth={1.8} />
                  </div>
                  <div className="mt-2 text-2xl font-bold tabular-nums text-foreground">
                    {formatNumber(s.value)}
                  </div>
                </CardContent>
              </Card>
            ))}
          </motion.div>

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
                  <div className="grid grid-cols-2 gap-2">
                    {Object.entries(services).map(([name, state]) => (
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