import { Fragment, useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ChevronDown,
  ChevronRight,
  Download,
  Search,
  ScrollText,
  TriangleAlert,
  Loader2,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
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
import {
  buildLogsExportUrl,
  fetchAgentLogs,
  fetchRunTrace,
  type LogEntry,
} from '@/services/agents'
import { cn } from '@/lib/utils'

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'completed', label: '成功' },
  { value: 'failed', label: '失败' },
  { value: 'running', label: '运行中' },
]

const LEVEL_META: Record<string, { label: string; cls: string }> = {
  completed: { label: '成功', cls: 'bg-emerald-500' },
  success: { label: '成功', cls: 'bg-emerald-500' },
  failed: { label: '失败', cls: 'bg-destructive' },
  running: { label: '运行中', cls: 'bg-sky-500' },
  info: { label: 'INFO', cls: 'bg-muted-foreground/50' },
  error: { label: 'ERROR', cls: 'bg-destructive' },
  warning: { label: 'WARN', cls: 'bg-amber-500' },
}

function fmtDuration(ms: number | null): string {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1000) return `${ms} ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} s`
  return `${(ms / 60000).toFixed(1)} min`
}

function ErrorCategoryBadge({ category }: { category: string | null }) {
  if (!category) return null
  return (
    <Badge variant="outline" className="border-destructive/40 text-destructive">
      {category}
    </Badge>
  )
}

function TraceView({ runId }: { runId: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['run-trace', runId],
    queryFn: () => fetchRunTrace(runId),
    enabled: !!runId,
    retry: 1,
  })

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-3 text-xs text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" /> 加载 Trace…
      </div>
    )
  }
  if (isError || !data) {
    return (
      <div className="flex items-center gap-2 py-3 text-xs text-destructive">
        <TriangleAlert className="size-3.5" /> Trace 加载失败
      </div>
    )
  }

  const timeline = data.timeline ?? []
  return (
    <div className="space-y-3 py-2">
      {/* 运行概览 */}
      <div className="rounded-lg border bg-muted/30 p-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge variant="outline">{data.task_kind}</Badge>
          <span className="text-muted-foreground">{data.question ?? '—'}</span>
          <span className="ml-auto font-medium">耗时 {fmtDuration(data.duration_ms)}</span>
        </div>
        {data.status === 'failed' && (
          <div className="mt-2 space-y-1">
            <div className="flex items-center gap-2 text-xs">
              <TriangleAlert className="size-3.5 text-destructive" />
              <ErrorCategoryBadge category={data.error_category} />
              <span className="text-muted-foreground">失败原因</span>
            </div>
            <p className="rounded bg-destructive/5 p-2 text-xs text-destructive font-mono break-all">
              {data.error ?? '未知错误'}
            </p>
          </div>
        )}
      </div>

      {/* 节点级时间线 */}
      {timeline.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          该运行未写入节点级轨迹（trace 为空），以上为运行级错误信息。
        </p>
      ) : (
        <ol className="relative space-y-3 pl-4 before:absolute before:inset-y-0 before:left-1.5 before:w-px before:bg-border">
          {timeline.map((t, i) => (
            <li key={i} className="relative">
              <span
                className={cn(
                  'absolute -left-4 top-1 size-2 rounded-full ring-2 ring-background',
                  t.status === 'failed' ? 'bg-destructive' : 'bg-emerald-500'
                )}
              />
              <div className="flex items-center gap-2 text-xs">
                <span className="font-medium text-foreground">{t.node}</span>
                {t.duration_ms !== null && t.duration_ms !== undefined && (
                  <span className="text-muted-foreground">{fmtDuration(t.duration_ms)}</span>
                )}
                {t.status === 'failed' && (
                  <Badge variant="outline" className="border-destructive/40 text-destructive">
                    失败
                  </Badge>
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
  )
}

export function LogsPanel({ agentId }: { agentId: string }) {
  const [status, setStatus] = useState('')
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)
  const [expanded, setExpanded] = useState<string | null>(null)

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['agent-logs', agentId, status, keyword, page],
    queryFn: () =>
      fetchAgentLogs({ agentId, status, keyword: keyword || undefined, page, pageSize: 20 }),
    enabled: !!agentId,
    retry: 1,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / 20))

  const exportUrl = useMemo(
    () => buildLogsExportUrl({ agentId, status, keyword: keyword || undefined }),
    [agentId, status, keyword]
  )

  // 搜索防抖：关键词变化 400ms 后重置到第 1 页
  useEffect(() => {
    const t = setTimeout(() => setPage(1), 400)
    return () => clearTimeout(t)
  }, [keyword, status])

  const toggleRow = (runId: string | null) => {
    if (!runId) return
    setExpanded((cur) => (cur === runId ? null : runId))
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ScrollText className="size-4 text-muted-foreground" /> 运行日志与 Trace
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* 工具栏：搜索 + 状态筛选 + 下载 */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-52 flex-1">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="搜索问题 / 错误信息…"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              className="pl-8"
            />
          </div>
          <Select value={status} onValueChange={(v) => setStatus(v ?? '')}>
            <SelectTrigger className="w-32">
              <SelectValue placeholder="全部状态" />
            </SelectTrigger>
            <SelectContent>
              {STATUS_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={() => {
              window.open(exportUrl, '_blank')
            }}
          >
            <Download className="size-3.5" /> CSV
          </Button>
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            {isFetching ? '刷新中…' : '刷新'}
          </Button>
        </div>

        {isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : isError ? (
          <EmptyState icon={ScrollText} title="无法加载日志" description="日志端点不可用" />
        ) : items.length === 0 ? (
          <EmptyState
            icon={ScrollText}
            title="暂无日志记录"
            description="Agent 运行后在此展示运行与任务日志"
          />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead>时间</TableHead>
                  <TableHead>来源</TableHead>
                  <TableHead>Agent / 任务</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>耗时</TableHead>
                  <TableHead>错误分类</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item: LogEntry, i: number) => {
                  const meta = LEVEL_META[item.level] ?? { label: item.level, cls: 'bg-muted-foreground/50' }
                  const isOpen = expanded === item.run_id
                  return (
                    <Fragment key={`${item.run_id ?? item.task_id}-${i}`}>
                      <TableRow
                        className="cursor-pointer hover:bg-muted/40"
                        onClick={() => toggleRow(item.run_id)}
                      >
                        <TableCell>
                          {item.run_id ? (
                            isOpen ? (
                              <ChevronDown className="size-3.5 text-muted-foreground" />
                            ) : (
                              <ChevronRight className="size-3.5 text-muted-foreground" />
                            )
                          ) : null}
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-xs">{item.time}</TableCell>
                        <TableCell className="text-xs">
                          {item.source === 'agent_run' ? (
                            <Badge variant="outline">运行</Badge>
                          ) : (
                            <Badge variant="secondary">任务</Badge>
                          )}
                        </TableCell>
                        <TableCell className="max-w-48 truncate text-xs">{item.entity}</TableCell>
                        <TableCell>
                          <span className="flex items-center gap-1.5">
                            <span className={cn('size-1.5 rounded-full', meta.cls)} />
                            <span className="text-xs">{meta.label}</span>
                          </span>
                        </TableCell>
                        <TableCell className="text-xs">{fmtDuration(item.duration_ms)}</TableCell>
                        <TableCell>
                          <ErrorCategoryBadge category={item.error_category} />
                        </TableCell>
                      </TableRow>
                      {isOpen && item.run_id && (
                        <TableRow key={`${item.run_id}-trace`} className="bg-muted/20">
                          <TableCell colSpan={7}>
                            <TraceView runId={item.run_id} />
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  )
                })}
              </TableBody>
            </Table>

            {/* 分页 */}
            <div className="flex items-center justify-between text-xs text-muted-foreground">
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
          </>
        )}
      </CardContent>
    </Card>
  )
}