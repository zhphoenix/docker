import { useEffect, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ListChecks, RefreshCw, RotateCcw, AlertTriangle, Clock, Zap, RefreshCcw } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { EmptyState } from '@/components/common/EmptyState'
import {
  fetchTasks,
  fetchTaskDetail,
  retryTask,
  triggerBatchEmbed,
  reembedDocument,
} from '@/services/tasks'
import type { TaskInfo } from '@/services/tasks'
import { cn } from '@/lib/utils'

// ===== Constants =====

const TASK_TYPE_LABELS: Record<string, string> = {
  knowledge_extraction: '知识提取',
  doc_pipeline: '文档处理 Pipeline',
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

const STATUS_LABELS: Record<string, string> = {
  pending: 'pending',
  running: 'running',
  done: 'done',
  failed: 'failed',
}

// ===== Helpers =====

function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatElapsed(sec: number | null): string {
  if (sec == null) return '—'
  if (sec < 60) return `${sec.toFixed(1)}s`
  return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`
}

function taskTypeLabel(t: string): string {
  return TASK_TYPE_LABELS[t] ?? t
}

function humanizeCount(task: TaskInfo): string {
  const total = task.total_items
  if (total == null || total <= 0) return '—'
  return `${total} 项`
}

// ===== Progress Bar =====

function ProgressBar({ task }: { task: TaskInfo }) {
  const progress = task.progress ?? 0
  const pct = Math.max(0, Math.min(100, progress))
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            'h-full rounded-full transition-all',
            task.status === 'failed' ? 'bg-destructive' : 'bg-primary',
            task.status === 'running' && 'animate-pulse'
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs tabular-nums text-muted-foreground">
        {pct.toFixed(0)}%
      </span>
    </div>
  )
}

// ===== Panel =====

interface KnowledgeTasksPanelProps {
  focusTaskId?: string | null
}

export function KnowledgeTasksPanel({ focusTaskId }: KnowledgeTasksPanelProps) {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<string>('')
  const [taskType, setTaskType] = useState<string>('')
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [docId, setDocId] = useState('')
  const [triggerMsg, setTriggerMsg] = useState<{
    type: 'success' | 'error'
    msg: string
  } | null>(null)

  // 从概览卡片跳转而来时，定位该任务并打开详情
  useEffect(() => {
    if (focusTaskId) {
      setSelectedId(focusTaskId)
    }
  }, [focusTaskId])

  const tasksQuery = useQuery({
    queryKey: ['knowledge-tasks', status, taskType],
    queryFn: () =>
      fetchTasks({
        status: status || undefined,
        task_type: taskType || undefined,
        limit: 50,
      }),
    retry: 1,
  })

  // 存在 running 任务时每 5s 自动轮询
  const hasRunning = useMemo(
    () => (tasksQuery.data?.tasks ?? []).some((t) => t.status === 'running'),
    [tasksQuery.data],
  )

  const pollQuery = useQuery({
    queryKey: ['knowledge-tasks-poll', status, taskType],
    queryFn: () =>
      fetchTasks({
        status: status || undefined,
        task_type: taskType || undefined,
        limit: 50,
      }),
    enabled: hasRunning,
    refetchInterval: 5000,
    retry: 0,
  })

  // 合并数据：轮询结果优先
  const allTasks = (hasRunning ? pollQuery.data?.tasks : tasksQuery.data?.tasks) ?? []

  const filteredTasks = useMemo(() => {
    if (!search.trim()) return allTasks
    const q = search.trim().toLowerCase()
    return allTasks.filter(
      (t) =>
        t.title.toLowerCase().includes(q) ||
        taskTypeLabel(t.task_type).toLowerCase().includes(q) ||
        t.id.toLowerCase().includes(q)
    )
  }, [allTasks, search])

  const detailQuery = useQuery({
    queryKey: ['knowledge-task-detail', selectedId],
    queryFn: () => fetchTaskDetail(selectedId!),
    enabled: selectedId != null,
    retry: 1,
  })

  const retryMutation = useMutation({
    mutationFn: (id: string) => retryTask(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge-tasks'] })
      queryClient.invalidateQueries({ queryKey: ['knowledge-task-detail'] })
    },
  })

  const batchEmbedMutation = useMutation({
    mutationFn: () => triggerBatchEmbed(),
    onSuccess: () => {
      setTriggerMsg({ type: 'success', msg: '已触发批量向量化任务' })
      queryClient.invalidateQueries({ queryKey: ['knowledge-tasks'] })
      setTimeout(() => setTriggerMsg(null), 5000)
    },
    onError: (err: Error) => {
      setTriggerMsg({ type: 'error', msg: err.message || '批量向量化触发失败' })
    },
  })

  const reembedMutation = useMutation({
    mutationFn: (documentId: string) => reembedDocument(documentId),
    onSuccess: () => {
      setTriggerMsg({ type: 'success', msg: '已触发重新向量化任务' })
      queryClient.invalidateQueries({ queryKey: ['knowledge-tasks'] })
      setTimeout(() => setTriggerMsg(null), 5000)
    },
    onError: (err: Error) => {
      setTriggerMsg({ type: 'error', msg: err.message || '重新向量化触发失败' })
    },
  })

  const selectedTask = detailQuery.data

  const handleRetry = (task: TaskInfo) => {
    retryMutation.mutate(task.id)
  }

  const handleReembed = () => {
    if (!docId.trim()) {
      setTriggerMsg({ type: 'error', msg: '请输入要重新向量化的文档 ID' })
      return
    }
    reembedMutation.mutate(docId.trim())
  }

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Input
            placeholder="搜索任务标题或类型"
            className="w-52"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select
          value={status || 'all'}
          onValueChange={(v) => setStatus(v === 'all' || v == null ? '' : v)}
        >
          <SelectTrigger className="w-32">
            <SelectValue placeholder="状态" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            <SelectItem value="pending">pending</SelectItem>
            <SelectItem value="running">running</SelectItem>
            <SelectItem value="done">done</SelectItem>
            <SelectItem value="failed">failed</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={taskType || 'all'}
          onValueChange={(v) => setTaskType(v === 'all' || v == null ? '' : v)}
        >
          <SelectTrigger className="w-40">
            <SelectValue placeholder="任务类型" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部类型</SelectItem>
            <SelectItem value="knowledge_extraction">知识提取</SelectItem>
            <SelectItem value="doc_pipeline">文档处理 Pipeline</SelectItem>
            <SelectItem value="batch_embed">批量向量化</SelectItem>
            <SelectItem value="re-embed">重新向量化</SelectItem>
            <SelectItem value="approval">Inbox 审核</SelectItem>
          </SelectContent>
        </Select>
        <Button
          variant="outline"
          size="sm"
          className="gap-2"
          onClick={() => tasksQuery.refetch()}
        >
          <RefreshCw className={cn('size-3.5', tasksQuery.isFetching && 'animate-spin')} />
          刷新
        </Button>

        {/* 触发入口：批量向量化 / 重新向量化 */}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => batchEmbedMutation.mutate()}
            disabled={batchEmbedMutation.isPending}
          >
            <Zap className="size-3.5" />
            {batchEmbedMutation.isPending ? '触发中...' : '批量向量化'}
          </Button>
          <div className="flex items-center gap-1.5">
            <Input
              placeholder="文档 ID"
              className="h-8 w-36"
              value={docId}
              onChange={(e) => setDocId(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleReembed()}
            />
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={handleReembed}
              disabled={reembedMutation.isPending}
            >
              <RefreshCcw className="size-3.5" />
              {reembedMutation.isPending ? '向量化中...' : '重新向量化'}
            </Button>
          </div>
        </div>
      </div>

      {/* 触发结果反馈 */}
      {triggerMsg && (
        <div
          className={cn(
            'rounded-lg border px-3 py-2 text-xs',
            triggerMsg.type === 'error'
              ? 'border-destructive/30 bg-destructive/10 text-destructive'
              : 'border-primary/30 bg-primary/10 text-primary'
          )}
        >
          {triggerMsg.msg}
        </div>
      )}

      {/* Tasks Table */}
      <Card>
        <CardContent className="p-0">
          {tasksQuery.isLoading ? (
            <div className="space-y-3 p-6">
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-8 w-full" />
              ))}
            </div>
          ) : tasksQuery.isError ? (
            <EmptyState
              icon={ListChecks}
              title="无法加载处理任务"
              description="无法连接到后端服务，请确认 LangGraph 服务已启动（端口 8100）"
              action={{ label: '重试', onClick: () => tasksQuery.refetch() }}
            />
          ) : filteredTasks.length === 0 ? (
            <EmptyState
              icon={ListChecks}
              title="暂无处理任务"
              description="通过知识提取、文档处理 Pipeline 或批量向量化触发的任务将显示在这里"
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>任务</TableHead>
                    <TableHead>类型</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead>进度</TableHead>
                    <TableHead>处理对象</TableHead>
                    <TableHead>耗时</TableHead>
                    <TableHead>创建时间</TableHead>
                    <TableHead className="text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredTasks.map((task) => (
                    <TableRow
                      key={task.id}
                      className="cursor-pointer"
                      onClick={() => setSelectedId(task.id)}
                    >
                      <TableCell className="min-w-0 max-w-[260px]">
                        <div className="truncate font-medium text-foreground" title={task.title}>
                          {task.title}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-[10px]">
                          {taskTypeLabel(task.task_type)}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={STATUS_VARIANTS[task.status] ?? 'outline'}
                          className={cn(
                            'text-[10px]',
                            task.status === 'running' && 'animate-pulse'
                          )}
                        >
                          {task.status === 'running' ? '● running' : STATUS_LABELS[task.status] ?? task.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <ProgressBar task={task} />
                      </TableCell>
                      <TableCell className="tabular-nums text-muted-foreground">
                        {humanizeCount(task)}
                      </TableCell>
                      <TableCell className="tabular-nums text-muted-foreground">
                        {task.status === 'running' && task.started_at
                          ? formatElapsed(
                              (Date.now() - new Date(task.started_at).getTime()) / 1000
                            )
                          : task.status === 'done' && task.started_at && task.finished_at
                            ? formatElapsed(
                                (new Date(task.finished_at).getTime() -
                                  new Date(task.started_at).getTime()) /
                                  1000
                              )
                            : '—'}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatDateTime(task.created_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        {task.status === 'failed' && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="gap-1.5 h-7 px-2 text-[11px]"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleRetry(task)
                            }}
                            disabled={retryMutation.isPending}
                          >
                            <RotateCcw className="size-3" />
                            重试
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Detail Dialog */}
      <Dialog open={selectedId != null} onOpenChange={(open) => !open && setSelectedId(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh]">
          <DialogHeader>
            <DialogTitle className="text-base">处理详情</DialogTitle>
          </DialogHeader>
          <ScrollArea className="max-h-[65vh] pr-4">
            {detailQuery.isLoading ? (
              <div className="space-y-3 py-4">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" />
                <Skeleton className="h-4 w-4/6" />
              </div>
            ) : detailQuery.isError ? (
              <EmptyState
                title="加载详情失败"
                description="无法获取任务详情，请稍后重试"
                action={{ label: '重试', onClick: () => detailQuery.refetch() }}
              />
            ) : selectedTask ? (
              <div className="space-y-5 py-2">
                {/* 标题与状态 */}
                <div>
                  <div className="text-xs font-medium text-muted-foreground">任务标题</div>
                  <p className="mt-1 text-sm font-medium text-foreground">
                    {selectedTask.title}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-4">
                  <div>
                    <div className="text-xs font-medium text-muted-foreground">任务类型</div>
                    <Badge variant="outline" className="mt-1">
                      {taskTypeLabel(selectedTask.task_type)}
                    </Badge>
                  </div>
                  <div>
                    <div className="text-xs font-medium text-muted-foreground">任务状态</div>
                    <Badge
                      variant={STATUS_VARIANTS[selectedTask.status] ?? 'outline'}
                      className={cn('mt-1', selectedTask.status === 'running' && 'animate-pulse')}
                    >
                      {selectedTask.status === 'running'
                        ? '● running'
                        : STATUS_LABELS[selectedTask.status] ?? selectedTask.status}
                    </Badge>
                  </div>
                  {selectedTask.retry_count != null && selectedTask.retry_count > 0 && (
                    <div>
                      <div className="text-xs font-medium text-muted-foreground">重试次数</div>
                      <span className="mt-1 block text-sm tabular-nums text-foreground">
                        {selectedTask.retry_count}
                      </span>
                    </div>
                  )}
                </div>

                {/* 进度 */}
                {selectedTask.status === 'running' && (
                  <div className="rounded-lg border bg-muted/30 p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                        <Clock className="size-4 text-primary" />
                        处理进度
                      </div>
                      <span className="text-sm tabular-nums text-muted-foreground">
                        {selectedTask.progress?.toFixed(0) ?? 0}%
                      </span>
                    </div>
                    <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-primary transition-all"
                        style={{ width: `${Math.max(0, Math.min(100, selectedTask.progress ?? 0))}%` }}
                      />
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                      {selectedTask.current_item != null && selectedTask.total_items != null && (
                        <span className="tabular-nums">
                          已完成 {selectedTask.current_item} / {selectedTask.total_items}
                        </span>
                      )}
                      {selectedTask.stage && <span>阶段：{selectedTask.stage}</span>}
                      {selectedTask.current_name && (
                        <span className="truncate">当前：{selectedTask.current_name}</span>
                      )}
                    </div>
                  </div>
                )}

                {/* 时间线 */}
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <div>
                    <div className="text-xs font-medium text-muted-foreground">创建时间</div>
                    <p className="mt-1 text-sm text-foreground">
                      {formatDateTime(selectedTask.created_at)}
                    </p>
                  </div>
                  <div>
                    <div className="text-xs font-medium text-muted-foreground">开始时间</div>
                    <p className="mt-1 text-sm text-foreground">
                      {formatDateTime(selectedTask.started_at)}
                    </p>
                  </div>
                  <div>
                    <div className="text-xs font-medium text-muted-foreground">完成时间</div>
                    <p className="mt-1 text-sm text-foreground">
                      {formatDateTime(selectedTask.finished_at)}
                    </p>
                  </div>
                </div>

                {/* 处理对象数量 */}
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div>
                    <div className="text-xs font-medium text-muted-foreground">处理对象</div>
                    <p className="mt-1 text-sm tabular-nums text-foreground">
                      {humanizeCount(selectedTask)}
                    </p>
                  </div>
                  <div>
                    <div className="text-xs font-medium text-muted-foreground">已完成</div>
                    <p className="mt-1 text-sm tabular-nums text-foreground">
                      {selectedTask.current_item ?? '—'}
                    </p>
                  </div>
                  <div>
                    <div className="text-xs font-medium text-muted-foreground">当前阶段</div>
                    <p className="mt-1 text-sm text-foreground">
                      {selectedTask.stage || '—'}
                    </p>
                  </div>
                  <div>
                    <div className="text-xs font-medium text-muted-foreground">耗时</div>
                    <p className="mt-1 text-sm tabular-nums text-foreground">
                      {selectedTask.status === 'running' && selectedTask.started_at
                        ? formatElapsed(
                            (Date.now() - new Date(selectedTask.started_at).getTime()) / 1000
                          )
                        : selectedTask.started_at && selectedTask.finished_at
                          ? formatElapsed(
                              (new Date(selectedTask.finished_at).getTime() -
                                new Date(selectedTask.started_at).getTime()) /
                                1000
                            )
                          : '—'}
                    </p>
                  </div>
                </div>

                {/* 错误信息 */}
                {selectedTask.error_message && (
                  <div>
                    <div className="flex items-center gap-1.5 text-xs font-medium text-destructive">
                      <AlertTriangle className="size-3.5" />
                      错误信息
                    </div>
                    <p className="mt-1 whitespace-pre-wrap rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
                      {selectedTask.error_message}
                    </p>
                  </div>
                )}
              </div>
            ) : null}
          </ScrollArea>

          {/* 底部操作：失败任务重试 */}
          {selectedTask?.status === 'failed' && (
            <div className="flex justify-end border-t px-6 py-4">
              <Button
                variant="default"
                className="gap-1.5"
                onClick={() => handleRetry(selectedTask)}
                disabled={retryMutation.isPending}
              >
                <RotateCcw className="size-3.5" />
                {retryMutation.isPending ? '重试中...' : '重试该任务'}
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}