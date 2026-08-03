import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { BarChart3, FileText, FlaskConical, RefreshCw, Search } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable'
import { fetchResearch, fetchResearchDetail } from '@/services/research'
import { fetchReports, fetchReportDetail, triggerAnalysis } from '@/services/reports'
import type { AnalyzeRequest } from '@/services/reports'
import { cn } from '@/lib/utils'
import { useDebounce } from '@/hooks/useDebounce'

// ===== Constants =====

const MARKET_LABELS: Record<string, string> = {
  cn: 'A股',
  hk: '港股',
  us: '美股',
}

const MARKET_VARIANTS: Record<string, 'default' | 'secondary' | 'outline'> = {
  cn: 'default',
  hk: 'secondary',
  us: 'outline',
}

const DIMENSIONS = [
  { value: 'comprehensive', label: '综合大师分析' },
  { value: 'moat', label: '护城河分析' },
  { value: 'financial', label: '财务健康度' },
  { value: 'risk', label: '排雷分析' },
  { value: 'valuation', label: '估值分析' },
  { value: 'growth', label: '成长性分析' },
]

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
  if (sec === null) return '—'
  if (sec < 60) return `${sec.toFixed(1)}s`
  return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  return `${(bytes / 1024).toFixed(1)} KB`
}

// ===== Tab 1: Reports Panel =====

function ReportsPanel() {
  const [market, setMarket] = useState('')
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const debouncedSearch = useDebounce(search, 300)

  const reportsQuery = useQuery({
    queryKey: ['reports', market, debouncedSearch],
    queryFn: () =>
      fetchReports({
        market: market || undefined,
        search: debouncedSearch || undefined,
      }),
    retry: 1,
  })

  const detailQuery = useQuery({
    queryKey: ['report-detail', selectedId],
    queryFn: () => fetchReportDetail(selectedId!),
    enabled: selectedId !== null,
    retry: 1,
  })

  const reports = reportsQuery.data?.reports ?? []

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
          <Input
            placeholder="搜索代码或公司名"
            className="w-52 pl-8"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select value={market || 'all'} onValueChange={(v) => setMarket(v === 'all' ? '' : v)}>
          <SelectTrigger className="w-28">
            <SelectValue placeholder="市场" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部市场</SelectItem>
            <SelectItem value="cn">A股</SelectItem>
            <SelectItem value="hk">港股</SelectItem>
            <SelectItem value="us">美股</SelectItem>
          </SelectContent>
        </Select>
        <span className="text-xs text-muted-foreground">
          共 {reportsQuery.data?.total ?? 0} 份报告
        </span>
      </div>

      {/* Reports Table */}
      <Card>
        <CardContent className="p-0">
          {reportsQuery.isLoading ? (
            <div className="space-y-3 p-6">
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-8 w-full" />
              ))}
            </div>
          ) : reportsQuery.isError ? (
            <EmptyState
              icon={FileText}
              title="无法加载报告列表"
              description="无法连接到后端服务，请确认 LangGraph 服务已启动（端口 8100）"
              action={{ label: '重试', onClick: () => reportsQuery.refetch() }}
            />
          ) : reports.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="暂无分析报告"
              description="data/reports/ 目录下的大师分析报告将显示在这里"
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>公司</TableHead>
                    <TableHead>代码</TableHead>
                    <TableHead>市场</TableHead>
                    <TableHead>年份</TableHead>
                    <TableHead className="text-right">大小</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {reports.map((report) => (
                    <TableRow
                      key={report.id}
                      className="cursor-pointer"
                      onClick={() => setSelectedId(report.id)}
                    >
                      <TableCell className="font-medium text-foreground">
                        {report.company}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {report.symbol}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={MARKET_VARIANTS[report.market] ?? 'outline'}
                          className="text-[10px]"
                        >
                          {MARKET_LABELS[report.market] ?? report.market}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {report.year}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {formatSize(report.size_bytes)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Report Detail Dialog */}
      <Dialog open={selectedId !== null} onOpenChange={(open) => !open && setSelectedId(null)}>
        <DialogContent className="max-w-4xl max-h-[85vh]">
          <DialogHeader>
            <DialogTitle className="text-base">
              {detailQuery.data
                ? `${detailQuery.data.company}（${detailQuery.data.symbol}）大师分析报告`
                : '分析报告'}
            </DialogTitle>
          </DialogHeader>
          <ScrollArea className="max-h-[65vh] pr-4">
            {detailQuery.isLoading ? (
              <div className="space-y-3 py-4">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" />
                <Skeleton className="h-4 w-4/6" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/6" />
              </div>
            ) : detailQuery.isError ? (
              <EmptyState
                title="加载报告失败"
                description="无法获取报告内容，请稍后重试"
                action={{ label: '重试', onClick: () => detailQuery.refetch() }}
              />
            ) : detailQuery.data ? (
              <div className="prose prose-sm max-w-none dark:prose-invert text-foreground py-2">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {detailQuery.data.content}
                </ReactMarkdown>
              </div>
            ) : null}
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ===== Tab 2: Analyze Panel =====

function AnalyzePanel() {
  const queryClient = useQueryClient()
  const [symbol, setSymbol] = useState('')
  const [market, setMarket] = useState('cn')
  const [dimension, setDimension] = useState('comprehensive')
  const [submitMsg, setSubmitMsg] = useState<string | null>(null)

  const analyzeMutation = useMutation({
    mutationFn: (req: AnalyzeRequest) => triggerAnalysis(req),
    onSuccess: (data) => {
      setSubmitMsg(data.message)
      setSymbol('')
      queryClient.invalidateQueries({ queryKey: ['research'] })
    },
    onError: (err: Error) => {
      setSubmitMsg(`提交失败: ${err.message}`)
    },
  })

  const handleSubmit = () => {
    if (!symbol.trim()) return
    setSubmitMsg(null)
    analyzeMutation.mutate({ symbol: symbol.trim(), market, dimension })
  }

  // 提交成功后显示动态进度指示
  const showProgress = submitMsg !== null && !submitMsg.includes('失败')

  return (
    <div className="mx-auto max-w-lg space-y-6 pt-8">
      <div className="text-center">
        <h2 className="text-lg font-semibold text-foreground">发起大师分析</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          输入股票代码，运用巴菲特/芒格/费雪/林奇方法论生成投资分析报告
        </p>
      </div>

      <Card>
        <CardContent className="space-y-4 p-6">
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">股票代码</label>
            <Input
              placeholder="如 600519、00700、AAPL"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">市场</label>
              <Select value={market} onValueChange={setMarket}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="cn">A股</SelectItem>
                  <SelectItem value="hk">港股</SelectItem>
                  <SelectItem value="us">美股</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">分析维度</label>
              <Select value={dimension} onValueChange={setDimension}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DIMENSIONS.map((d) => (
                    <SelectItem key={d.value} value={d.value}>
                      {d.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <Button
            className="w-full"
            onClick={handleSubmit}
            disabled={!symbol.trim() || analyzeMutation.isPending}
          >
            {analyzeMutation.isPending ? '提交中...' : '开始分析'}
          </Button>

          {submitMsg && (
            <p className={cn(
              'text-center text-sm',
              submitMsg.includes('失败') ? 'text-destructive' : 'text-emerald-600',
            )}>
              {submitMsg}
            </p>
          )}

          {showProgress && (
            <div className="space-y-2 rounded-lg border border-emerald-200 bg-emerald-50/50 p-4 dark:border-emerald-800 dark:bg-emerald-950/30">
              <div className="flex items-center gap-2">
                <RefreshCw className="size-4 animate-spin text-emerald-600" />
                <span className="text-sm font-medium text-emerald-700 dark:text-emerald-400">
                  分析进行中...
                </span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-emerald-100 dark:bg-emerald-900">
                <div className="h-full w-1/2 animate-pulse rounded-full bg-emerald-500" />
              </div>
              <p className="text-xs text-muted-foreground">
                正在运用大师方法论生成分析报告，通常需要 30-120 秒。可在「研究任务」标签页查看实时状态。
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <p className="text-center text-xs text-muted-foreground">
        分析任务提交后可在「研究任务」标签页查看进度
      </p>
    </div>
  )
}

// ===== Tab 3: Research Tasks Panel =====

function ResearchTasksPanel() {
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

  // 存在 running 任务时每 5s 自动轮询
  const hasRunning = useMemo(
    () => (researchQuery.data?.tasks ?? []).some((t) => t.status === 'running'),
    [researchQuery.data],
  )

  const pollQuery = useQuery({
    queryKey: ['research-poll', status, symbol],
    queryFn: () =>
      fetchResearch({
        status: status || undefined,
        symbol: symbol || undefined,
        limit: 50,
      }),
    enabled: hasRunning,
    refetchInterval: 5000,
    retry: 0,
  })

  // 合并数据：轮询结果优先
  const tasks = (hasRunning ? pollQuery.data?.tasks : researchQuery.data?.tasks) ?? []

  const detailQuery = useQuery({
    queryKey: ['research-detail', selectedId],
    queryFn: () => fetchResearchDetail(selectedId!),
    enabled: selectedId !== null,
    retry: 1,
  })

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="搜索股票代码"
          className="w-48"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
        />
        <Select value={status || 'all'} onValueChange={(v) => setStatus(v === 'all' || v === null ? '' : v)}>
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

      {/* Tasks Table */}
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
              description="通过「发起分析」或 Chat 发起研究分析后，历史记录将显示在这里"
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
                        {task.confidence !== null ? `${Math.round(task.confidence * 100)}%` : '—'}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={STATUS_VARIANTS[task.status] ?? 'outline'}
                          className={cn('text-[10px]', task.status === 'running' && 'animate-pulse')}
                        >
                          {task.status === 'running' ? '● running' : task.status}
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
      <Dialog open={selectedId !== null} onOpenChange={(open) => !open && setSelectedId(null)}>
        <DialogContent className="w-[95vw] max-w-[95vw] sm:max-w-[95vw] h-[85vh] flex flex-col p-0 gap-0">
          <DialogHeader className="px-6 py-4 border-b shrink-0">
            <DialogTitle className="text-base">研究详情</DialogTitle>
          </DialogHeader>

          {detailQuery.isLoading ? (
            <div className="flex-1 space-y-3 p-6">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-4/6" />
            </div>
          ) : detailQuery.isError ? (
            <div className="flex-1 flex items-center justify-center">
              <EmptyState
                title="加载详情失败"
                description="无法获取研究任务详情，请稍后重试"
                action={{ label: '重试', onClick: () => detailQuery.refetch() }}
              />
            </div>
          ) : detailQuery.data ? (
            <ResizablePanelGroup orientation="horizontal" className="flex-1 min-h-0">
              {/* 左栏：元信息 */}
              <ResizablePanel defaultSize="40" minSize="25">
                <ScrollArea className="h-full">
                  <div className="space-y-5 p-5">
                    <div>
                      <div className="text-xs font-medium text-muted-foreground">研究问题</div>
                      <p className="mt-1 text-sm font-medium text-foreground">
                        {detailQuery.data.question}
                      </p>
                    </div>

                    <div>
                      <div className="text-xs font-medium text-muted-foreground">任务状态</div>
                      <Badge
                        variant={STATUS_VARIANTS[detailQuery.data.status] ?? 'outline'}
                        className="mt-1"
                      >
                        {detailQuery.data.status}
                      </Badge>
                    </div>

                    {detailQuery.data.error && (
                      <div>
                        <div className="text-xs font-medium text-muted-foreground">错误信息</div>
                        <p className="mt-1 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
                          {detailQuery.data.error}
                        </p>
                      </div>
                    )}

                    {!detailQuery.data.answer && !detailQuery.data.error && (
                      <p className="text-sm text-muted-foreground">暂无分析结果</p>
                    )}
                  </div>
                </ScrollArea>
              </ResizablePanel>

              <ResizableHandle withHandle />

              {/* 右栏：分析报告 */}
              <ResizablePanel defaultSize="60" minSize="35">
                <ScrollArea className="h-full">
                  <div className="p-5">
                    {detailQuery.data.answer ? (
                      <div className="prose prose-sm max-w-none dark:prose-invert text-foreground">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {detailQuery.data.answer}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                        暂无报告内容
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </ResizablePanel>
            </ResizablePanelGroup>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ===== Main Page =====

export default function ResearchPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-6 p-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">研究中心</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          大师分析报告浏览、发起新分析、研究任务管理
        </p>
      </div>

      {/* Tabs */}
      <Tabs defaultValue={0} className="space-y-4">
        <TabsList>
          <TabsTrigger value={0} className="gap-1.5">
            <FileText className="size-3.5" />
            分析报告
          </TabsTrigger>
          <TabsTrigger value={1} className="gap-1.5">
            <FlaskConical className="size-3.5" />
            发起分析
          </TabsTrigger>
          <TabsTrigger value={2} className="gap-1.5">
            <BarChart3 className="size-3.5" />
            研究任务
          </TabsTrigger>
        </TabsList>

        <TabsContent value={0}>
          <ReportsPanel />
        </TabsContent>

        <TabsContent value={1}>
          <AnalyzePanel />
        </TabsContent>

        <TabsContent value={2}>
          <ResearchTasksPanel />
        </TabsContent>
      </Tabs>
    </div>
  )
}
