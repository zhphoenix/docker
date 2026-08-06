import { useState } from 'react'
import { Loader2, RefreshCw, BookOpen, Plus, History } from 'lucide-react'
import { WindowedDialog } from '@/components/ui/windowed-dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { EmptyState } from '@/components/common/EmptyState'
import { StockKnowledgeGraph } from './StockKnowledgeGraph'
import {
  useStockDetail,
  useStockSummary,
  useGenerateStockSummary,
  useStockGraph,
  useTriggerStockResearch,
  useStockResearchTasks,
} from '@/hooks/useWatchlist'
import type { WatchlistItem } from '@/services/watchlist'
import type { ResearchTask } from '@/services/research'

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  running: 'secondary',
  completed: 'default',
  failed: 'destructive',
}

const AGENT_LABEL: Record<string, string> = {
  research: '投研 Agent',
  investment: '投资 Agent',
}

function statusLabel(task: ResearchTask) {
  if (task.status === 'running') return '进行中'
  if (task.status === 'completed') return '已完成'
  if (task.status === 'failed') return '失败'
  return task.status
}

function formatTime(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

interface Props {
  stock: WatchlistItem | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function StockDetailDrawer({ stock, open, onOpenChange }: Props) {
  const stockCode = stock?.stock_code ?? null
  const { data: detail, isLoading: detailLoading } = useStockDetail(stockCode)
  const { data: summary } = useStockSummary(stockCode)
  const { data: graph } = useStockGraph(stockCode)
  const genSummary = useGenerateStockSummary()
  const triggerResearch = useTriggerStockResearch()
  const { data: researchData } = useStockResearchTasks(stockCode)
  const [researchOpen, setResearchOpen] = useState(false)
  const [researchQuestion, setResearchQuestion] = useState('')
  const [researchAgent, setResearchAgent] = useState('research')

  const openResearchDialog = () => {
    setResearchQuestion(`分析 ${stock?.stock_name || stock?.stock_code || ''} 近期投资价值`)
    setResearchAgent('research')
    setResearchOpen(true)
  }

  if (!stock) return null

  return (
    <WindowedDialog
      open={open}
      onOpenChange={onOpenChange}
      defaultWidth={800}
      defaultHeight={700}
      title={
        <span>
          {stock.stock_name || stock.stock_code}{' '}
          <span className="text-sm text-muted-foreground">{stock.stock_code}</span>
        </span>
      }
    >
      <Tabs defaultValue="today" className="h-full">
        <TabsList>
          <TabsTrigger value="today">今日</TabsTrigger>
          <TabsTrigger value="ai">AI 摘要</TabsTrigger>
          <TabsTrigger value="research">研究</TabsTrigger>
          <TabsTrigger value="graph">知识图谱</TabsTrigger>
        </TabsList>

        {/* Today Tab */}
        <TabsContent value="today" className="mt-4 space-y-4">
          {detailLoading ? (
            <div className="grid grid-cols-5 gap-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-20" />
              ))}
            </div>
          ) : detail ? (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
                {[
                  { label: '新闻', value: detail.today_stats.news_count, color: 'text-blue-500', bg: 'bg-blue-500/10' },
                  { label: '公告', value: detail.today_stats.announcement_count, color: 'text-green-500', bg: 'bg-green-500/10' },
                  { label: '研报', value: detail.today_stats.research_count, color: 'text-purple-500', bg: 'bg-purple-500/10' },
                  { label: '行业新闻', value: detail.today_stats.industry_news_count, color: 'text-amber-500', bg: 'bg-amber-500/10' },
                  { label: '竞品', value: detail.today_stats.competitor_news_count, color: 'text-rose-500', bg: 'bg-rose-500/10' },
                ].map(({ label, value, color, bg }) => (
                  <div key={label} className={`rounded-lg ${bg} p-3 text-center`}>
                    <p className={`text-2xl font-bold ${color}`}>{value}</p>
                    <p className="text-xs text-muted-foreground">{label}</p>
                  </div>
                ))}
              </div>
              <div>
                <h4 className="mb-2 text-sm font-medium">近期事件</h4>
                {detail.recent_events.length === 0 ? (
                  <EmptyState title="暂无事件" />
                ) : (
                  <div className="space-y-2">
                    {detail.recent_events.slice(0, 10).map((ev) => (
                      <div key={ev.id} className="rounded-lg border p-3 text-sm">
                        <span className="font-medium">{ev.summary?.slice(0, 100)}</span>
                        <span className="ml-2 text-xs text-muted-foreground">
                          {ev.sentiment} · {ev.event_time ? new Date(ev.event_time).toLocaleDateString('zh-CN') : ''}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <EmptyState title="加载失败" />
          )}
        </TabsContent>

        {/* AI Summary Tab */}
        <TabsContent value="ai" className="mt-4">
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-sm font-medium">AI 分析摘要</h4>
            <Button
              variant="outline"
              size="sm"
              onClick={() => genSummary.mutate(stock.stock_code)}
              disabled={genSummary.isPending}
            >
              {genSummary.isPending ? (
                <Loader2 className="mr-1 size-4 animate-spin" />
              ) : (
                <RefreshCw className="mr-1 size-4" />
              )}
              生成摘要
            </Button>
          </div>
          {summary?.summary ? (
            <div className="rounded-lg bg-muted p-4 text-sm leading-relaxed whitespace-pre-wrap">
              {summary.summary}
            </div>
          ) : (
            <EmptyState title="暂无 AI 摘要" description="点击「生成摘要」由 AI 分析今日事件" />
          )}
          <div className="mt-4">
            <Button variant="outline" onClick={openResearchDialog}>
              <BookOpen className="mr-1 size-4" />
              发起深度研究
            </Button>
          </div>
        </TabsContent>

        {/* Research Tab */}
        <TabsContent value="research" className="mt-4">
          <div className="mb-4 flex items-center justify-between">
            <h4 className="flex items-center gap-1.5 text-sm font-medium">
              <History className="size-4" /> 研究任务
            </h4>
            <Button variant="outline" size="sm" onClick={openResearchDialog}>
              <Plus className="mr-1 size-4" /> 发起新研究
            </Button>
          </div>
          {researchData?.tasks && researchData.tasks.length > 0 ? (
            <div className="space-y-2">
              {researchData.tasks.map((t) => (
                <div key={t.id} className="rounded-lg border p-3 text-sm">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="font-medium">{t.question}</span>
                    <Badge variant={STATUS_VARIANT[t.status] ?? 'outline'}>
                      {statusLabel(t)}
                    </Badge>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                    <span>{AGENT_LABEL[t.agent_type ?? ''] ?? t.agent_type ?? '—'}</span>
                    <span>文档 {t.document_count}</span>
                    {t.confidence != null && <span>置信度 {(t.confidence * 100).toFixed(0)}%</span>}
                    <span>{formatTime(t.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="暂无研究任务"
              description="发起一次深度研究，由 Agent 自动收集并分析资料"
            />
          )}
        </TabsContent>

        {/* Knowledge Graph Tab */}
        <TabsContent value="graph" className="mt-4">
          {graph?.nodes && graph.nodes.length > 0 ? (
            <>
              <p className="mb-2 text-xs text-muted-foreground">
                实体关系图（{graph.nodes.length} 节点 / {graph.edges.length} 边）
              </p>
              <StockKnowledgeGraph nodes={graph.nodes} edges={graph.edges} />
            </>
          ) : (
            <EmptyState title="图谱数据暂不可用" description="AGE 图存储可能未连接" />
          )}
        </TabsContent>
      </Tabs>

      {/* Research dialog */}
      <Dialog open={researchOpen} onOpenChange={setResearchOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>发起深度研究</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <Input
              value={researchQuestion}
              onChange={(e) => setResearchQuestion(e.target.value)}
              placeholder="研究问题"
            />
            <Select value={researchAgent} onValueChange={(v) => setResearchAgent(v ?? 'research')}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="research">投研 Agent</SelectItem>
                <SelectItem value="investment">投资 Agent</SelectItem>
              </SelectContent>
            </Select>
            {triggerResearch.isError && (
              <p className="text-sm text-destructive">
                发起失败：{(triggerResearch.error as Error)?.message || '未知错误'}
              </p>
            )}
            <Button
              onClick={() => {
                triggerResearch.mutate({
                  stockCode: stock.stock_code,
                  question: researchQuestion.trim() || undefined,
                })
                setResearchOpen(false)
              }}
              disabled={triggerResearch.isPending || !researchQuestion.trim()}
            >
              {triggerResearch.isPending ? (
                <Loader2 className="mr-1 size-4 animate-spin" />
              ) : (
                <BookOpen className="mr-1 size-4" />
              )}
              开始研究
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </WindowedDialog>
  )
}
