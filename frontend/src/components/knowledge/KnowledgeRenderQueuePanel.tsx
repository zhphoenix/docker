import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Layers, RotateCcw, RefreshCw, AlertTriangle, Clock } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchRenderJobs, retryRenderJob } from '@/services/renderJobs'
import type { RenderJob } from '@/services/renderJobs'
import { cn } from '@/lib/utils'

// ===== 常量 =====

const STATUS_VARIANTS: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'outline',
  running: 'secondary',
  done: 'default',
  failed: 'destructive',
}

const STATUS_LABELS: Record<string, string> = {
  pending: 'pending',
  running: '● running',
  done: 'done',
  failed: 'failed',
}

// 优先级：越小越优先（Company/Event 优先）
const PRIORITY_LABELS: Record<number, string> = {
  1: 'P1 高',
  2: 'P2',
  3: 'P3',
  4: 'P4',
  5: 'P5 低',
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

function priorityLabel(p: number): string {
  return PRIORITY_LABELS[p] ?? `P${p}`
}

// ===== 面板 =====

export function KnowledgeRenderQueuePanel() {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<string>('')
  const [msg, setMsg] = useState<{ type: 'success' | 'error'; msg: string } | null>(null)

  const jobsQuery = useQuery({
    queryKey: ['knowledge-render-jobs', status],
    queryFn: () => fetchRenderJobs({ status: status || undefined, limit: 100 }),
    retry: 1,
  })

  // 存在 pending/running 任务时每 5s 自动轮询
  const hasActive = useMemo(
    () =>
      (jobsQuery.data?.jobs ?? []).some(
        (j) => j.status === 'pending' || j.status === 'running'
      ),
    [jobsQuery.data]
  )

  useQuery({
    queryKey: ['knowledge-render-jobs-poll', status],
    queryFn: () => fetchRenderJobs({ status: status || undefined, limit: 100 }),
    enabled: hasActive,
    refetchInterval: 5000,
    retry: 0,
  })

  const retryMutation = useMutation({
    mutationFn: (jobId: string) => retryRenderJob(jobId),
    onSuccess: () => {
      setMsg({ type: 'success', msg: '渲染任务已重新入队' })
      queryClient.invalidateQueries({ queryKey: ['knowledge-render-jobs'] })
      setTimeout(() => setMsg(null), 5000)
    },
    onError: (err: Error) => {
      setMsg({ type: 'error', msg: err.message || '重试失败' })
    },
  })

  const handleRetry = (job: RenderJob) => {
    retryMutation.mutate(job.id)
  }

  return (
    <div className="space-y-4">
      {/* 过滤器 + 刷新 */}
      <div className="flex flex-wrap items-center gap-3">
        <Select value={status || 'all'} onValueChange={(v) => setStatus(v === 'all' || !v ? '' : v)}>
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
        <Button
          variant="outline"
          size="sm"
          className="gap-2"
          onClick={() => jobsQuery.refetch()}
        >
          <RefreshCw className={cn('size-3.5', jobsQuery.isFetching && 'animate-spin')} />
          刷新
        </Button>
        <span className="ml-auto text-xs text-muted-foreground">
          共 {jobsQuery.data?.total ?? 0} 个渲染任务 · 优先级越小越优先
        </span>
      </div>

      {/* 操作反馈 */}
      {msg && (
        <div
          className={cn(
            'rounded-lg border px-3 py-2 text-xs',
            msg.type === 'error'
              ? 'border-destructive/30 bg-destructive/10 text-destructive'
              : 'border-primary/30 bg-primary/10 text-primary'
          )}
        >
          {msg.msg}
        </div>
      )}

      {/* 任务表 */}
      <Card>
        <CardContent className="p-0">
          {jobsQuery.isLoading ? (
            <div className="space-y-3 p-6">
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-8 w-full" />
              ))}
            </div>
          ) : jobsQuery.isError ? (
            <EmptyState
              icon={Layers}
              title="无法加载渲染队列"
              description="无法连接到后端服务，请确认 LangGraph 服务已启动（端口 8100）"
              action={{ label: '重试', onClick: () => jobsQuery.refetch() }}
            />
          ) : (jobsQuery.data?.jobs ?? []).length === 0 ? (
            <EmptyState
              icon={Layers}
              title="暂无渲染任务"
              description="审核通过的实体将自动进入渲染队列，SiYuan 工作区页面由此生成"
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>实体</TableHead>
                    <TableHead>类型</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead>优先级</TableHead>
                    <TableHead>重试</TableHead>
                    <TableHead>失败原因</TableHead>
                    <TableHead>创建时间</TableHead>
                    <TableHead className="text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(jobsQuery.data?.jobs ?? []).map((job) => (
                    <TableRow key={job.id}>
                      <TableCell className="min-w-0 max-w-[220px]">
                        <div className="truncate font-medium text-foreground" title={job.entity_name ?? job.id}>
                          {job.entity_name ?? '（未关联实体）'}
                        </div>
                        {job.section && (
                          <div className="text-[10px] text-muted-foreground">{job.section}</div>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-[10px]">
                          {job.type}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={STATUS_VARIANTS[job.status] ?? 'outline'}
                          className={cn(
                            'text-[10px]',
                            job.status === 'running' && 'animate-pulse'
                          )}
                        >
                          {STATUS_LABELS[job.status] ?? job.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        <span className="tabular-nums">{priorityLabel(job.priority)}</span>
                      </TableCell>
                      <TableCell className="tabular-nums text-muted-foreground">
                        {job.retry}
                      </TableCell>
                      <TableCell className="min-w-0 max-w-[240px]">
                        {job.status === 'failed' && job.error_message ? (
                          <div
                            className="flex items-start gap-1 text-xs text-destructive"
                            title={job.error_message}
                          >
                            <AlertTriangle className="mt-0.5 size-3 shrink-0" />
                            <span className="truncate">{job.error_message}</span>
                          </div>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatDateTime(job.created_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        {job.status === 'failed' && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="gap-1.5 h-7 px-2 text-[11px]"
                            onClick={() => handleRetry(job)}
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

      {/* 说明 */}
      <div className="flex items-start gap-2 rounded-lg bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
        <Clock className="mt-0.5 size-3.5 shrink-0" />
        <span>
          渲染链路：审核通过 → render_jobs（pending）→ render worker 领取（running）→ 同步至
          SiYuan（done）；渲染失败不影响知识入库，仅置 failed。失败自动重试上限 3 次，超限后可在此手动重试恢复。
        </span>
      </div>
    </div>
  )
}