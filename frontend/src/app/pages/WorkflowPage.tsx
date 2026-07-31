import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { GitBranch, RefreshCw } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Progress } from '@/components/ui/progress'
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
import { EmptyState } from '@/components/common/EmptyState'
import { fetchTasks } from '@/services/tasks'
import { cn } from '@/lib/utils'

const STATUS_VARIANTS: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  completed: 'default',
  running: 'default',
  pending: 'secondary',
  queued: 'secondary',
  failed: 'destructive',
  error: 'destructive',
}

const STATUS_LABELS: Record<string, string> = {
  completed: '已完成',
  running: '运行中',
  pending: '等待中',
  queued: '已入队',
  failed: '失败',
  error: '失败',
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

export default function WorkflowPage() {
  const [status, setStatus] = useState<string>('')
  const [taskType, setTaskType] = useState<string>('')

  const tasksQuery = useQuery({
    queryKey: ['tasks', status, taskType],
    queryFn: () =>
      fetchTasks({
        status: status || undefined,
        task_type: taskType || undefined,
        limit: 50,
      }),
    retry: 1,
    // 有进行中任务时自动刷新
    refetchInterval: (query) => {
      const tasks = query.state.data?.tasks ?? []
      const hasActive = tasks.some((t) => t.status === 'running' || t.status === 'pending')
      return hasActive ? 10_000 : false
    },
  })

  const tasks = tasksQuery.data?.tasks ?? []

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">工作流</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            任务队列与 Pipeline 执行状态
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="gap-2"
          onClick={() => tasksQuery.refetch()}
        >
          <RefreshCw className={cn('size-3.5', tasksQuery.isFetching && 'animate-spin')} />
          刷新
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <Select value={status || 'all'} onValueChange={(v) => setStatus(v === 'all' || v == null ? '' : v)}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="状态" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            <SelectItem value="pending">pending</SelectItem>
            <SelectItem value="running">running</SelectItem>
            <SelectItem value="completed">completed</SelectItem>
            <SelectItem value="failed">failed</SelectItem>
          </SelectContent>
        </Select>
        <Select value={taskType || 'all'} onValueChange={(v) => setTaskType(v === 'all' || v == null ? '' : v)}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="任务类型" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部类型</SelectItem>
            <SelectItem value="doc_pipeline">doc_pipeline</SelectItem>
            <SelectItem value="batch_embed">batch_embed</SelectItem>
          </SelectContent>
        </Select>
      </div>

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
              icon={GitBranch}
              title="无法加载任务列表"
              description="无法连接到后端服务，请确认 LangGraph 服务已启动（端口 8100）"
              action={{ label: '重试', onClick: () => tasksQuery.refetch() }}
            />
          ) : tasks.length === 0 ? (
            <EmptyState
              icon={GitBranch}
              title="暂无任务"
              description="当前筛选条件下没有任务记录"
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>任务</TableHead>
                    <TableHead>类型</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead className="w-48">进度</TableHead>
                    <TableHead>阶段</TableHead>
                    <TableHead>创建时间</TableHead>
                    <TableHead>耗时</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tasks.map((task) => (
                    <TableRow key={task.id}>
                      <TableCell className="max-w-[240px]">
                        <div className="truncate font-medium text-foreground">{task.title}</div>
                        {task.error_message && (
                          <div className="mt-0.5 truncate text-[11px] text-danger">
                            {task.error_message}
                          </div>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-[10px]">
                          {task.task_type}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={STATUS_VARIANTS[task.status] ?? 'outline'}
                          className="text-[10px]"
                        >
                          {STATUS_LABELS[task.status] ?? task.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Progress value={Number(task.progress ?? 0)} className="flex-1" />
                          <span className="w-10 text-right text-[11px] tabular-nums text-muted-foreground">
                            {Math.round(Number(task.progress ?? 0))}%
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {task.stage || '—'}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatDateTime(task.created_at)}
                      </TableCell>
                      <TableCell className="tabular-nums text-muted-foreground">
                        {formatDuration(task.started_at, task.finished_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <p className="text-center text-xs text-muted-foreground">
        任务由后台 Worker 异步执行 · 有进行中任务时每 10 秒自动刷新
      </p>
    </div>
  )
}
