import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, RefreshCw } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchResearch, fetchResearchDetail } from '@/services/research'
import { cn } from '@/lib/utils'

const QUALITY_VARIANTS: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  high: 'default',
  good: 'default',
  medium: 'secondary',
  low: 'destructive',
}

const STATUS_VARIANTS: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  completed: 'default',
  running: 'secondary',
  failed: 'destructive',
  error: 'destructive',
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

function formatElapsed(sec: number | null): string {
  if (sec == null) return '—'
  if (sec < 60) return `${sec.toFixed(1)}s`
  return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`
}

export default function ResearchPage() {
  const [status, setStatus] = useState<string>('')
  const [symbol, setSymbol] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const researchQuery = useQuery({
    queryKey: ['research', status, symbol],
    queryFn: () =>
      fetchResearch({
        status: status || undefined,
        symbol: symbol || undefined,
        limit: 50,
      }),
    retry: 1,
  })

  // 详情按需加载（点击行时）
  const detailQuery = useQuery({
    queryKey: ['research-detail', selectedId],
    queryFn: () => fetchResearchDetail(selectedId!),
    enabled: selectedId != null,
    retry: 1,
  })

  const tasks = researchQuery.data?.tasks ?? []

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">研究中心</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            投研分析任务历史与质量评估
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="gap-2"
          onClick={() => researchQuery.refetch()}
        >
          <RefreshCw className={cn('size-3.5', researchQuery.isFetching && 'animate-spin')} />
          刷新
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="搜索股票代码"
          className="w-48"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
        />
        <Select value={status || 'all'} onValueChange={(v) => setStatus(v === 'all' || v == null ? '' : v)}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="状态" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            <SelectItem value="running">running</SelectItem>
            <SelectItem value="completed">completed</SelectItem>
            <SelectItem value="failed">failed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Research Table */}
      <Card>
        <CardContent className="p-0">
          {researchQuery.isLoading ? (
            <div className="space-y-3 p-6">
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-8 w-full" />
              ))}
            </div>
          ) : researchQuery.isError ? (
            <EmptyState
              icon={BarChart3}
              title="无法加载研究历史"
              description="无法连接到后端服务，请确认 LangGraph 服务已启动（端口 8100）"
              action={{ label: '重试', onClick: () => researchQuery.refetch() }}
            />
          ) : tasks.length === 0 ? (
            <EmptyState
              icon={BarChart3}
              title="暂无研究记录"
              description="通过 Chat 发起研究分析后，历史记录将显示在这里"
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>研究问题</TableHead>
                    <TableHead>代码</TableHead>
                    <TableHead>Agent</TableHead>
                    <TableHead>质量</TableHead>
                    <TableHead className="text-right">置信度</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead>耗时</TableHead>
                    <TableHead>时间</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tasks.map((task) => (
                    <TableRow
                      key={task.id}
                      className="cursor-pointer"
                      onClick={() => setSelectedId(task.id)}
                    >
                      <TableCell className="max-w-[280px]">
                        <div className="truncate font-medium text-foreground">
                          {task.question}
                        </div>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {task.symbol ?? '—'}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-[10px]">
                          {task.agent_type ?? '—'}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {task.quality ? (
                          <Badge
                            variant={QUALITY_VARIANTS[task.quality] ?? 'outline'}
                            className="text-[10px]"
                          >
                            {task.quality}
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {task.confidence != null ? `${Math.round(task.confidence * 100)}%` : '—'}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={STATUS_VARIANTS[task.status] ?? 'outline'}
                          className="text-[10px]"
                        >
                          {task.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="tabular-nums text-muted-foreground">
                        {formatElapsed(task.elapsed_seconds)}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatDateTime(task.created_at)}
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
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="text-base">研究详情</DialogTitle>
          </DialogHeader>
          <ScrollArea className="max-h-[60vh] pr-4">
            {detailQuery.isLoading ? (
              <div className="space-y-3 py-4">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" />
                <Skeleton className="h-4 w-4/6" />
              </div>
            ) : detailQuery.isError ? (
              <EmptyState
                title="加载详情失败"
                description="无法获取研究任务详情，请稍后重试"
                action={{ label: '重试', onClick: () => detailQuery.refetch() }}
              />
            ) : detailQuery.data ? (
              <div className="space-y-4 py-2">
                <div>
                  <div className="text-xs font-medium text-muted-foreground">研究问题</div>
                  <p className="mt-1 text-sm font-medium text-foreground">
                    {detailQuery.data.question}
                  </p>
                </div>

                {detailQuery.data.error && (
                  <div>
                    <div className="text-xs font-medium text-muted-foreground">错误信息</div>
                    <p className="mt-1 rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">
                      {detailQuery.data.error}
                    </p>
                  </div>
                )}

                {detailQuery.data.answer ? (
                  <div>
                    <div className="mb-2 text-xs font-medium text-muted-foreground">分析结果</div>
                    <div className="prose prose-sm max-w-none dark:prose-invert text-foreground">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {detailQuery.data.answer}
                      </ReactMarkdown>
                    </div>
                  </div>
                ) : (
                  !detailQuery.data.error && (
                    <p className="text-sm text-muted-foreground">暂无分析结果</p>
                  )
                )}
              </div>
            ) : null}
          </ScrollArea>
        </DialogContent>
      </Dialog>

      <p className="text-center text-xs text-muted-foreground">
        点击行查看研究详情 · 研究任务由 Research Agent 自动执行
      </p>
    </div>
  )
}
