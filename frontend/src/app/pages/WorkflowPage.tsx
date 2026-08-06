import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  GitBranch,
  RefreshCw,
  Plus,
  Check,
  X,
  Loader2,
  Trash2,
  Copy,
  Eye,
  RotateCcw,
  Ban,
  Activity,
  Server,
  CalendarClock,
  AlertTriangle,
  Clock,
  Boxes,
  Inbox,
  PackageCheck,
  Gauge,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { WindowedDialog } from '@/components/ui/windowed-dialog'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { EmptyState } from '@/components/common/EmptyState'
import {
  fetchTasks,
  fetchTaskDetail,
  fetchTaskLogs,
  fetchTaskStats,
  fetchWorkers,
  fetchSchedule,
  fetchPipelineStats,
  retryTask,
  cancelTask,
  deleteTask,
  cloneTask,
  triggerPipeline,
  triggerBatchEmbed,
} from '@/services/tasks'
import type { TaskInfo, TaskStatus, TaskLog, PipelineStats } from '@/services/tasks'
import { triggerExtraction } from '@/services/knowledge'
import { cn } from '@/lib/utils'

// ─── 状态与类型常量（与后端真实枚举对齐） ──────────────────
const STATUS_META: Record<TaskStatus, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  pending: { label: '待处理', variant: 'secondary' },
  running: { label: '运行中', variant: 'default' },
  done: { label: '已完成', variant: 'outline' },
  failed: { label: '失败', variant: 'destructive' },
}

const STATUS_OPTIONS: { value: TaskStatus; label: string }[] = [
  { value: 'pending', label: '待处理' },
  { value: 'running', label: '运行中' },
  { value: 'done', label: '已完成' },
  { value: 'failed', label: '失败' },
]

const TYPE_OPTIONS: { value: string; label: string; source: string }[] = [
  { value: 'doc_pipeline', label: '文档流水线', source: '文档中心' },
  { value: 'batch_embed', label: '批量向量化', source: '知识中台' },
  { value: 're-embed', label: '重新向量化', source: '文档中心' },
  { value: 'knowledge_extraction', label: '知识提取', source: '知识中台' },
  { value: 'approval', label: '审批', source: '系统' },
]

const TYPE_SOURCE: Record<string, string> = {
  doc_pipeline: '文档中心',
  batch_embed: '知识中台',
  're-embed': '文档中心',
  knowledge_extraction: '知识中台',
  approval: '系统',
}

// Pipeline 八阶段（真实后端阶段，DP-B1 对齐）
const STAGE_ORDER = ['acquire', 'routing', 'parse', 'chunk', 'extraction', 'embedding', 'package', 'publish']
const STAGE_LABELS: Record<string, string> = {
  acquire: '采集',
  routing: '路由',
  parse: '解析',
  chunk: '分块',
  extraction: '知识抽取',
  embedding: '向量化',
  package: '打包',
  publish: '发布',
}

function getStageState(task: TaskInfo, stage: string): 'done' | 'active' | 'pending' | 'failed' {
  if (task.status === 'done') return 'done'
  const currentIdx = STAGE_ORDER.indexOf(task.stage ?? '')
  const stageIdx = STAGE_ORDER.indexOf(stage)
  if (task.status === 'failed') {
    if (task.stage === stage) return 'failed'
    return stageIdx < currentIdx ? 'done' : 'pending'
  }
  if (currentIdx < 0) return 'pending'
  if (stageIdx < currentIdx) return 'done'
  if (stageIdx === currentIdx) return 'active'
  return 'pending'
}

function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatDuration(start: string | null, end: string | null): string {
  if (!start) return '—'
  const s = new Date(start).getTime()
  const e = end ? new Date(end).getTime() : Date.now()
  const sec = Math.max(0, Math.round((e - s) / 1000))
  if (sec < 60) return `${sec}s`
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${sec % 60}s`
  return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`
}

// ─── Pipeline 三阶段可视化 ────────────────────────────────
function PipelineVisual({ task }: { task: TaskInfo }) {
  return (
    <div className="flex items-center gap-1.5">
      {STAGE_ORDER.map((stage) => {
        const state = getStageState(task, stage)
        return (
          <div key={stage} className="flex items-center gap-1.5">
            <div
              className={cn(
                'flex h-5 items-center gap-1 rounded-md border px-1.5 text-[10px] font-medium',
                state === 'done' && 'border-primary/40 bg-primary/10 text-primary',
                state === 'active' && 'border-primary bg-primary text-primary-foreground',
                state === 'failed' && 'border-destructive bg-destructive/10 text-destructive',
                state === 'pending' && 'border-muted bg-muted/40 text-muted-foreground',
              )}
            >
              {state === 'done' ? (
                <Check className="size-2.5" />
              ) : state === 'active' ? (
                <Loader2 className="size-2.5 animate-spin" />
              ) : state === 'failed' ? (
                <X className="size-2.5" />
              ) : null}
              {STAGE_LABELS[stage]}
            </div>
            {stage !== 'publish' && (
              <div className="h-px w-3 bg-muted" />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ─── 新建任务表单 ─────────────────────────────────────────
type CreateType = 'doc_pipeline' | 'batch_embed' | 'knowledge_extraction'

function NewWorkflowDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onCreated: () => void
}) {
  const [type, setType] = useState<CreateType>('doc_pipeline')
  const [limit, setLimit] = useState('50')
  const [collection, setCollection] = useState('documents_cn')
  const [docIds, setDocIds] = useState('')

  const queryClient = useQueryClient()

  const pipelineMutation = useMutation({
    mutationFn: () => triggerPipeline({ limit: Number(limit) || 50, async_mode: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      queryClient.invalidateQueries({ queryKey: ['taskStats'] })
      onCreated()
    },
  })
  const batchMutation = useMutation({
    mutationFn: () => triggerBatchEmbed({ collection, batch_size: 64, limit: 0 }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      queryClient.invalidateQueries({ queryKey: ['taskStats'] })
      onCreated()
    },
  })
  const extractMutation = useMutation({
    mutationFn: () => triggerExtraction(docIds.split(',').map((s) => s.trim()).filter(Boolean)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      queryClient.invalidateQueries({ queryKey: ['taskStats'] })
      onCreated()
    },
  })

  const active = pipelineMutation.isPending || batchMutation.isPending || extractMutation.isPending

  const extractReady = type !== 'knowledge_extraction' || docIds.trim().length > 0

  const submit = () => {
    if (type === 'doc_pipeline') pipelineMutation.mutate()
    else if (type === 'batch_embed') batchMutation.mutate()
    else extractMutation.mutate()
  }

  return (
    <WindowedDialog
      open={open}
      onOpenChange={onOpenChange}
      title="创建任务"
      description="选择任务类型并配置参数，任务将进入后台队列由 Worker 执行"
      defaultWidth={480}
      defaultHeight={480}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={active}>
            取消
          </Button>
          <Button onClick={submit} disabled={active || !extractReady}>
            {active && <Loader2 className="mr-2 size-4 animate-spin" />}
            创建并入队
          </Button>
        </div>
      }
    >
      <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">任务类型</label>
            <Select value={type} onValueChange={(v) => setType(v as CreateType)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="doc_pipeline">文档流水线（Document Pipeline）</SelectItem>
                <SelectItem value="batch_embed">批量向量化（Batch Embed）</SelectItem>
                <SelectItem value="knowledge_extraction">知识提取（Knowledge Extraction）</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {type === 'doc_pipeline' && (
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">处理数量 Limit</label>
              <Input value={limit} onChange={(e) => setLimit(e.target.value)} placeholder="50" type="number" min={1} />
            </div>
          )}

          {type === 'batch_embed' && (
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Collection</label>
              <Select value={collection} onValueChange={(v) => setCollection(v ?? '')}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="documents_cn">documents_cn</SelectItem>
                  <SelectItem value="documents_hk">documents_hk</SelectItem>
                  <SelectItem value="documents_us">documents_us</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {type === 'knowledge_extraction' && (
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                文档 ID（逗号分隔，必填）
              </label>
              <Input value={docIds} onChange={(e) => setDocIds(e.target.value)} placeholder="doc_id_1, doc_id_2" />
              {docIds.trim().length === 0 && (
                <p className="text-xs text-destructive">至少填写一个文档 ID</p>
              )}
            </div>
          )}
        </div>
    </WindowedDialog>
  )
}

// ─── 任务详情 Dialog ──────────────────────────────────────
function TaskDetailDialog({
  task,
  onOpenChange,
}: {
  task: TaskInfo | null
  onOpenChange: (v: boolean) => void
}) {
  const detailQuery = useQuery({
    queryKey: ['taskDetail', task?.id],
    queryFn: () => fetchTaskDetail(task!.id),
    enabled: !!task,
  })
  const logsQuery = useQuery({
    queryKey: ['taskLogs', task?.id],
    queryFn: () => fetchTaskLogs(task!.id),
    enabled: !!task,
  })
  const statsQuery = useQuery({
    queryKey: ['taskStats'],
    queryFn: fetchTaskStats,
    enabled: !!task,
    refetchInterval: false,
  })

  const detail = detailQuery.data ?? task
  const logs: TaskLog[] = logsQuery.data?.logs ?? []

  return (
    <WindowedDialog
      open={!!task}
      onOpenChange={onOpenChange}
      title={detail?.title ?? '任务详情'}
      description={
        detail && (
          <span className="flex items-center gap-2">
            <Badge variant={STATUS_META[detail.status as TaskStatus]?.variant ?? 'outline'}>
              {STATUS_META[detail.status as TaskStatus]?.label ?? detail.status}
            </Badge>
            <span className="text-muted-foreground">{detail.task_type}</span>
            <span className="text-muted-foreground">来源 {TYPE_SOURCE[detail.task_type] ?? '—'}</span>
          </span>
        )
      }
      defaultWidth={720}
      defaultHeight={560}
    >
      <Tabs defaultValue="overview" className="w-full">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="overview">总览</TabsTrigger>
            <TabsTrigger value="pipeline">流水线</TabsTrigger>
            <TabsTrigger value="logs">日志</TabsTrigger>
            <TabsTrigger value="statistics">统计</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-4 pt-3">
            {detail ? (
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-xs text-muted-foreground">任务 ID</div>
                  <div className="mt-0.5 font-mono text-xs">{detail.id}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">创建时间</div>
                  <div className="mt-0.5">{formatDateTime(detail.created_at)}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">开始时间</div>
                  <div className="mt-0.5">{formatDateTime(detail.started_at)}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">完成时间</div>
                  <div className="mt-0.5">{formatDateTime(detail.finished_at)}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">进度</div>
                  <div className="mt-0.5 flex items-center gap-2">
                    <Progress value={Number(detail.progress ?? 0)} className="w-32" />
                    <span className="tabular-nums">{Math.round(Number(detail.progress ?? 0))}%</span>
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">当前阶段</div>
                  <div className="mt-0.5">{detail.stage || '—'}</div>
                </div>
                <div className="col-span-2">
                  <div className="text-xs text-muted-foreground">参数</div>
                  <pre className="mt-1 max-h-32 overflow-auto rounded-md bg-muted/40 p-2 text-xs">
                    {JSON.stringify(detail.params ?? {}, null, 2)}
                  </pre>
                </div>
                {detail.error_message && (
                  <div className="col-span-2">
                    <div className="text-xs text-muted-foreground">错误信息</div>
                    <div className="mt-1 rounded-md border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive">
                      {detail.error_message}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <Skeleton className="h-32 w-full" />
            )}
          </TabsContent>

          <TabsContent value="pipeline" className="pt-3">
            {detail && detail.task_type === 'doc_pipeline' ? (
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <PipelineVisual task={detail} />
                  <span className="text-xs text-muted-foreground">
                    {detail.stage ? `当前阶段：${STAGE_LABELS[detail.stage] ?? detail.stage}` : '待启动'}
                  </span>
                </div>
                {/* 按阶段打点：从 task_logs 提取每阶段成败状态，失败阶段红色定位 */}
                <div className="grid grid-cols-2 gap-2">
                  {STAGE_ORDER.map((stage) => {
                    const stageLogs = logs.filter((l) => l.stage === stage)
                    const failed = stageLogs.filter((l) => l.level === 'error').length
                    const info = stageLogs.length - failed
                    return (
                      <div
                        key={stage}
                        className={cn(
                          'flex items-center justify-between rounded-md border px-2 py-1.5',
                          failed > 0 && 'border-destructive/40 bg-destructive/5',
                        )}
                      >
                        <span className="text-xs font-medium">{STAGE_LABELS[stage]}</span>
                        {failed > 0 ? (
                          <Badge variant="destructive" className="text-[9px]">{failed} 失败</Badge>
                        ) : info > 0 ? (
                          <Badge variant="outline" className="text-[9px]">{info} 打点</Badge>
                        ) : (
                          <Badge variant="secondary" className="text-[9px]">未开始</Badge>
                        )}
                      </div>
                    )
                  })}
                </div>
                <div className="text-xs text-muted-foreground">
                  流水线阶段：采集 → 路由 → 解析 → 分块 → 知识抽取 → 向量化 → 打包 → 发布。失败阶段以红色标记定位。
                </div>
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">
                该任务类型不涉及文档流水线八阶段，当前阶段：{detail?.stage || '—'}
              </div>
            )}
          </TabsContent>

          <TabsContent value="logs" className="pt-3">
            {logsQuery.isLoading ? (
              <Skeleton className="h-40 w-full" />
            ) : logs.length === 0 ? (
              <EmptyState icon={Clock} title="暂无日志" description="该任务尚未产生执行日志" />
            ) : (
              <ScrollArea className="h-64 w-full rounded-md border">
                <div className="space-y-1 p-3 font-mono text-xs">
                  {logs.map((log) => (
                    <div key={log.id} className="flex items-start gap-2">
                      <span className="shrink-0 text-muted-foreground">
                        {formatDateTime(log.created_at)}
                      </span>
                      <Badge
                        variant={
                          log.level === 'error' ? 'destructive' : log.level === 'warn' ? 'outline' : 'secondary'
                        }
                        className="shrink-0 text-[9px]"
                      >
                        {log.level}
                      </Badge>
                      {log.stage && <Badge variant="outline" className="shrink-0 text-[9px]">{log.stage}</Badge>}
                      <span className="break-all">{log.message}</span>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </TabsContent>

          <TabsContent value="statistics" className="pt-3">
            {statsQuery.data ? (
              <div className="grid grid-cols-4 gap-3">
                {[
                  { label: '待处理', value: statsQuery.data.pending, key: 'pending' },
                  { label: '运行中', value: statsQuery.data.running, key: 'running' },
                  { label: '已完成', value: statsQuery.data.done, key: 'done' },
                  { label: '失败', value: statsQuery.data.failed, key: 'failed' },
                ].map((s) => (
                  <div key={s.key} className="rounded-lg border bg-muted/20 p-3 text-center">
                    <div className="text-2xl font-bold tabular-nums">{s.value}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{s.label}</div>
                  </div>
                ))}
              </div>
            ) : (
              <Skeleton className="h-24 w-full" />
            )}
          </TabsContent>
      </Tabs>
    </WindowedDialog>
  )
}

// ─── Pipeline 八阶段统计面板（DP-E1/DP-E2） ──────────────
const STAGE_STATE_META = {
  running: { label: '运行中', cls: 'bg-primary/10 text-primary' },
  pending: { label: '待处理', cls: 'bg-muted text-muted-foreground' },
  completed: { label: '已完成', cls: 'bg-emerald-500/10 text-emerald-600' },
  failed: { label: '失败', cls: 'bg-destructive/10 text-destructive' },
} as const

type StageStateKey = keyof typeof STAGE_STATE_META

function StageStateChip({
  state,
  count,
}: {
  state: StageStateKey
  count: number
}) {
  const meta = STAGE_STATE_META[state]
  return (
    <div className={cn('flex items-baseline gap-1 rounded-md px-1.5 py-0.5', meta.cls)}>
      <span className="text-sm font-bold tabular-nums">{count}</span>
      <span className="text-[10px]">{meta.label}</span>
    </div>
  )
}

function StagePipelineBar({
  total,
  meta,
}: {
  total: number
  meta: { running: number; completed: number; failed: number }
}) {
  const done = meta.completed
  const failed = meta.failed
  const running = meta.running
  const pending = Math.max(0, total - done - failed - running)
  const w = (n: number) => (total > 0 ? `${(n / total) * 100}%` : '0%')
  return total > 0 ? (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div className="bg-emerald-500" style={{ width: w(done) }} />
      <div className="bg-primary" style={{ width: w(running) }} />
      <div className="bg-destructive" style={{ width: w(failed) }} />
      <div className="bg-muted/60" style={{ width: w(pending) }} />
    </div>
  ) : (
    <div className="h-1.5 w-full rounded-full bg-muted/40" />
  )
}

function PipelineStatsSection({ stats }: { stats: PipelineStats | undefined }) {
  if (!stats) return null
  const maxTotal = Math.max(1, ...stats.stages.map((s) => s.completed + s.running + s.failed))
  const publishRate =
    stats.publish_success_rate == null
      ? '—'
      : `${Math.round(stats.publish_success_rate * 100)}%`

  return (
    <div className="space-y-4">
      {/* 生产统计指标卡 */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Inbox className="size-3.5" />
              入库文档
            </div>
            <div className="mt-1 text-2xl font-bold tabular-nums">
              {stats.incoming_documents.total}
              <span className="ml-1 text-xs font-normal text-muted-foreground">
                今日 +{stats.incoming_documents.today}
              </span>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <PackageCheck className="size-3.5" />
              知识包
            </div>
            <div className="mt-1 text-2xl font-bold tabular-nums">{stats.packages.total}</div>
            <div className="mt-0.5 text-[10px] text-muted-foreground">
              草稿 {stats.packages.draft} · 已发布 {stats.packages.published} · 已消费 {stats.packages.consumed}
            </div>
          </CardContent>
        </Card>
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Gauge className="size-3.5" />
              发布成功率
            </div>
            <div className="mt-1 text-2xl font-bold tabular-nums">{publishRate}</div>
            <div className="mt-0.5 text-[10px] text-muted-foreground">
              队列 {stats.queue_length} · 今日处理 {stats.processed_today}
            </div>
          </CardContent>
        </Card>
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Clock className="size-3.5" />
              平均耗时
            </div>
            <div className="mt-1 text-2xl font-bold tabular-nums">
              {stats.avg_latency_ms == null ? '—' : `${(stats.avg_latency_ms / 1000).toFixed(1)}s`}
            </div>
            <div className="mt-0.5 text-[10px] text-muted-foreground">已完成任务均值</div>
          </CardContent>
        </Card>
      </div>

      {/* 八阶段链路 */}
      <Card>
        <CardHeader className="border-b px-4 py-3">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <Boxes className="size-4 text-muted-foreground" />
            流水线八阶段
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-4">
          {stats.stages.map((s, i) => {
            const stateCount = s.completed + s.running + s.failed
            return (
              <div key={s.stage}>
                <div className="flex items-center gap-3">
                  <div className="flex w-40 shrink-0 items-center gap-2">
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-muted text-[10px] font-semibold text-muted-foreground">
                      {i + 1}
                    </span>
                    <span className="text-sm font-medium">{s.label}</span>
                  </div>
                  <div className="flex-1">
                    <StagePipelineBar total={stateCount} meta={s} />
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <StageStateChip state="completed" count={s.completed} />
                    <StageStateChip state="running" count={s.running} />
                    <StageStateChip state="failed" count={s.failed} />
                    <StageStateChip state="pending" count={s.pending} />
                  </div>
                </div>
                {s.failed > 0 && (
                  <div className="mt-1 pl-9 text-[11px] text-destructive">
                    该阶段有 {s.failed} 个失败记录，可定位到失败任务定位原因
                  </div>
                )}
              </div>
            )
          })}
          <div className="flex items-center justify-between pt-1 text-[11px] text-muted-foreground">
            <span>归一化容量 = 各阶段已完成/运行中/失败总和的最大值</span>
            <span className="tabular-nums">峰值 {maxTotal} 条</span>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

// ─── 主页面 ───────────────────────────────────────────────
export default function WorkflowPage() {
  const [status, setStatus] = useState<string>('')
  const [taskType, setTaskType] = useState<string>('')
  const [detailTask, setDetailTask] = useState<TaskInfo | null>(null)
  const [createOpen, setCreateOpen] = useState(false)

  const queryClient = useQueryClient()

  const tasksQuery = useQuery({
    queryKey: ['tasks', status, taskType],
    queryFn: () =>
      fetchTasks({
        status: status || undefined,
        task_type: taskType || undefined,
        limit: 100,
      }),
    retry: 1,
    refetchInterval: (query) => {
      const tasks = query.state.data?.tasks ?? []
      const hasActive = tasks.some((t) => t.status === 'running' || t.status === 'pending')
      return hasActive ? 10_000 : false
    },
  })

  const statsQuery = useQuery({ queryKey: ['taskStats'], queryFn: fetchTaskStats, refetchInterval: 30_000 })
  const workersQuery = useQuery({ queryKey: ['workers'], queryFn: fetchWorkers, refetchInterval: 30_000 })
  const scheduleQuery = useQuery({ queryKey: ['schedule'], queryFn: fetchSchedule, refetchInterval: 60_000 })
  const pipelineStatsQuery = useQuery({
    queryKey: ['pipelineStats'],
    queryFn: fetchPipelineStats,
    refetchInterval: 30_000,
  })
  const failedQuery = useQuery({
    queryKey: ['tasks', 'failed'],
    queryFn: () => fetchTasks({ status: 'failed', limit: 10 }),
    refetchInterval: 30_000,
  })

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ['tasks'] })
    queryClient.invalidateQueries({ queryKey: ['taskStats'] })
    queryClient.invalidateQueries({ queryKey: ['workers'] })
    queryClient.invalidateQueries({ queryKey: ['schedule'] })
    queryClient.invalidateQueries({ queryKey: ['pipelineStats'] })
  }

  const retryMutation = useMutation({
    mutationFn: retryTask,
    onSuccess: invalidateAll,
  })
  const cancelMutation = useMutation({
    mutationFn: cancelTask,
    onSuccess: invalidateAll,
  })
  const deleteMutation = useMutation({
    mutationFn: deleteTask,
    onSuccess: invalidateAll,
  })
  const cloneMutation = useMutation({
    mutationFn: cloneTask,
    onSuccess: invalidateAll,
  })

  const tasks = tasksQuery.data?.tasks ?? []
  // 运行中任务置顶
  const sortedTasks = [...tasks].sort((a, b) => {
    const rank = (t: TaskInfo) => (t.status === 'running' ? 0 : t.status === 'pending' ? 1 : 2)
    return rank(a) - rank(b)
  })

  const stats = statsQuery.data
  const statCards = [
    { key: 'pending', label: '待处理', value: stats?.pending ?? 0, active: status === 'pending' },
    { key: 'running', label: '运行中', value: stats?.running ?? 0, active: status === 'running' },
    { key: 'done', label: '已完成', value: stats?.done ?? 0, active: status === 'done' },
    { key: 'failed', label: '失败', value: stats?.failed ?? 0, active: status === 'failed' },
  ]

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-foreground">Workflow</h1>
            <Badge variant="outline" className="text-[10px]">处理中心</Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">任务/流水线编排与执行</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="gap-2" onClick={() => tasksQuery.refetch()}>
            <RefreshCw className={cn('size-3.5', tasksQuery.isFetching && 'animate-spin')} />
            刷新
          </Button>
          <Button size="sm" className="gap-2" onClick={() => setCreateOpen(true)}>
            <Plus className="size-3.5" />
            新建任务
          </Button>
        </div>
      </div>

      {/* 运行统计 */}
      <div className="grid grid-cols-4 gap-4">
        {statCards.map((card) => (
          <button
            key={card.key}
            onClick={() => setStatus(card.active ? '' : card.key)}
            className={cn(
              'rounded-xl border p-4 text-left transition-colors',
              card.active ? 'border-primary bg-primary/5 ring-1 ring-primary' : 'bg-card hover:bg-muted/40',
            )}
          >
            <div className="text-2xl font-bold tabular-nums">{card.value}</div>
            <div className="mt-0.5 text-xs text-muted-foreground">{card.label}</div>
          </button>
        ))}
      </div>

      {/* Pipeline 八阶段视图 + 生产统计（DP-E2） */}
      {pipelineStatsQuery.isLoading ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-20 w-full" />)}
          </div>
          <Skeleton className="h-64 w-full" />
        </div>
      ) : pipelineStatsQuery.isError ? (
        <EmptyState
          icon={Boxes}
          title="无法加载流水线统计"
          description="无法连接到后端统计接口，请确认 LangGraph 服务已启动（端口 8100）"
          action={{ label: '重试', onClick: () => pipelineStatsQuery.refetch() }}
        />
      ) : (
        <PipelineStatsSection stats={pipelineStatsQuery.data} />
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <Select value={status || 'all'} onValueChange={(v) => setStatus(v === 'all' || v === null ? '' : v)}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="状态" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            {STATUS_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={taskType || 'all'} onValueChange={(v) => setTaskType(v === 'all' || v === null ? '' : v)}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="任务类型" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部类型</SelectItem>
            {TYPE_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Tasks Table */}
      <Card>
        <CardHeader className="border-b px-4 py-3">
          <CardTitle className="text-sm font-medium">任务列表</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {tasksQuery.isLoading ? (
            <div className="space-y-3 p-6">
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-8 w-full" />
              ))}
            </div>
          ) : tasksQuery.isError ? (
            <EmptyState
              icon={GitBranch}
              title="无法加载任务列表"
              description="无法连接到后端服务，请确认 LangGraph 服务已启动（端口 8100）"
              action={{ label: '重试', onClick: () => tasksQuery.refetch() }}
            />
          ) : sortedTasks.length === 0 ? (
            <EmptyState icon={GitBranch} title="暂无任务" description="当前筛选条件下没有任务记录" />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>任务</TableHead>
                    <TableHead>类型</TableHead>
                    <TableHead>来源</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead>流水线</TableHead>
                    <TableHead className="w-40">进度</TableHead>
                    <TableHead>创建时间</TableHead>
                    <TableHead>耗时</TableHead>
                    <TableHead className="text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedTasks.map((task) => (
                    <TableRow key={task.id}>
                      <TableCell className="min-w-0 max-w-[220px]">
                        <button
                          className="block w-full truncate text-left font-medium text-foreground hover:text-primary"
                          onClick={() => setDetailTask(task)}
                          title={task.title}
                        >
                          {task.title}
                        </button>
                        {task.error_message && (
                          <div className="mt-0.5 truncate text-[11px] text-danger" title={task.error_message}>{task.error_message}</div>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-[10px]">{task.task_type}</Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {TYPE_SOURCE[task.task_type] ?? '—'}
                      </TableCell>
                      <TableCell>
                        <Badge variant={STATUS_META[task.status as TaskStatus]?.variant ?? 'outline'} className="text-[10px]">
                          {STATUS_META[task.status as TaskStatus]?.label ?? task.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {task.task_type === 'doc_pipeline' ? (
                          <PipelineVisual task={task} />
                        ) : (
                          <span className="text-xs text-muted-foreground">{task.stage || '—'}</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Progress value={Number(task.progress ?? 0)} className="flex-1" />
                          <span className="w-10 text-right text-[11px] tabular-nums text-muted-foreground">
                            {Math.round(Number(task.progress ?? 0))}%
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="text-muted-foreground">{formatDateTime(task.created_at)}</TableCell>
                      <TableCell className="tabular-nums text-muted-foreground">
                        {formatDuration(task.started_at, task.finished_at)}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-7"
                            title="查看详情"
                            onClick={() => setDetailTask(task)}
                          >
                            <Eye className="size-3.5" />
                          </Button>
                          {task.task_type === 'doc_pipeline' && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="size-7"
                              title="克隆"
                              onClick={() => cloneMutation.mutate(task.id)}
                            >
                              <Copy className="size-3.5" />
                            </Button>
                          )}
                          {task.status === 'failed' && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="size-7 text-primary"
                              title="重试"
                              onClick={() => retryMutation.mutate(task.id)}
                            >
                              <RotateCcw className="size-3.5" />
                            </Button>
                          )}
                          {task.status === 'running' && task.task_type === 'batch_embed' && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="size-7 text-destructive"
                              title="取消"
                              onClick={() => cancelMutation.mutate(task.id)}
                            >
                              <Ban className="size-3.5" />
                            </Button>
                          )}
                          {(task.status === 'done' || task.status === 'failed') && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="size-7 text-muted-foreground hover:text-destructive"
                              title="删除"
                              onClick={() => {
                                if (window.confirm(`确定删除任务「${task.title}」？`)) {
                                  deleteMutation.mutate(task.id)
                                }
                              }}
                            >
                              <Trash2 className="size-3.5" />
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Worker + Schedule + Failed 三栏 */}
      <div className="grid grid-cols-3 gap-4">
        {/* Worker 状态 */}
        <Card>
          <CardHeader className="border-b px-4 py-3">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <Server className="size-4 text-muted-foreground" />
              Worker 状态
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 p-4 text-sm">
            {workersQuery.data ? (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">运行状态</span>
                  <Badge variant={workersQuery.data.running ? 'default' : 'secondary'}>
                    {workersQuery.data.running ? '运行中' : '已停止'}
                  </Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">活跃任务</span>
                  <span className="tabular-nums">{workersQuery.data.active_tasks}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">当前任务</span>
                  <span className="max-w-[140px] truncate font-mono text-xs">
                    {workersQuery.data.current_task_id
                      ? `${workersQuery.data.current_task_id.slice(0, 8)}…`
                      : '—'}
                  </span>
                </div>
                <div>
                  <div className="mb-1 text-muted-foreground">已注册处理器</div>
                  <div className="flex flex-wrap gap-1">
                    {workersQuery.data.registered_handlers.map((h) => (
                      <Badge key={h} variant="outline" className="text-[9px]">{h}</Badge>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <Skeleton className="h-24 w-full" />
            )}
          </CardContent>
        </Card>

        {/* 调度面板 */}
        <Card>
          <CardHeader className="border-b px-4 py-3">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <CalendarClock className="size-4 text-muted-foreground" />
              调度计划
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {scheduleQuery.data ? (
              <ScrollArea className="h-56">
                <div className="divide-y">
                  {scheduleQuery.data.jobs.length === 0 ? (
                    <div className="p-4 text-sm text-muted-foreground">未注册调度任务</div>
                  ) : (
                    scheduleQuery.data.jobs.map((job) => (
                      <div key={job.id} className="flex items-center justify-between gap-2 px-4 py-2.5">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium">{job.name}</div>
                          <div className="truncate text-[10px] text-muted-foreground">{job.id} · {job.trigger}</div>
                        </div>
                        <div className="shrink-0 text-right text-[10px] text-muted-foreground">
                          {job.next_run_time ? (
                            <span className="flex items-center gap-1">
                              <Clock className="size-3" />
                              {new Date(job.next_run_time).toLocaleString('zh-CN', {
                                month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
                              })}
                            </span>
                          ) : (
                            '—'
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </ScrollArea>
            ) : (
              <Skeleton className="m-4 h-16 w-[calc(100%-2rem)]" />
            )}
          </CardContent>
        </Card>

        {/* Failed Tasks */}
        <Card>
          <CardHeader className="border-b px-4 py-3">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <AlertTriangle className="size-4 text-destructive" />
              失败任务
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {failedQuery.isLoading ? (
              <Skeleton className="m-4 h-16 w-[calc(100%-2rem)]" />
            ) : (failedQuery.data?.tasks ?? []).length === 0 ? (
              <div className="flex flex-col items-center gap-1 p-6 text-center text-sm text-muted-foreground">
                <Activity className="size-5" />
                暂无失败任务
              </div>
            ) : (
              <ScrollArea className="h-56">
                <div className="divide-y">
                  {(failedQuery.data?.tasks ?? []).map((task) => (
                    <div key={task.id} className="flex items-center gap-2 px-4 py-2.5">
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">{task.title}</div>
                        <div className="truncate text-[10px] text-muted-foreground">
                          {task.error_message || '—'}
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-7 shrink-0 text-primary"
                        title="重试"
                        onClick={() => retryMutation.mutate(task.id)}
                      >
                        <RotateCcw className="size-3.5" />
                      </Button>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      </div>

      <p className="text-center text-xs text-muted-foreground">
        任务由后台 Worker 异步执行 · 有进行中任务时每 10 秒自动刷新
      </p>

      <NewWorkflowDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={() => setCreateOpen(false)} />
      <TaskDetailDialog task={detailTask} onOpenChange={(v) => !v && setDetailTask(null)} />
    </div>
  )
}