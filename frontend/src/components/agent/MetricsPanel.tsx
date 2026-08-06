import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  CheckCircle2,
  XCircle,
  Timer,
  Hash,
  DollarSign,
  RefreshCw,
  type LucideIcon,
} from 'lucide-react'
import {
  Bar,
  BarChart,
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
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchAgentMetrics, fetchPromptVariants, type AgentMetricsSummary, type PromptVariantStat } from '@/services/agents'
import { cn } from '@/lib/utils'

const RANGES = [
  { key: '1d', label: '今日' },
  { key: '7d', label: '近 7 天' },
  { key: '30d', label: '近 30 天' },
]

function fmtDuration(ms: number): string {
  if (ms < 1000) return `${ms.toFixed(0)} ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} s`
  const mins = ms / 60000
  if (mins < 60) return `${mins.toFixed(1)} min`
  return `${(mins / 60).toFixed(1)} h`
}

function fmtTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return n.toFixed(0)
}

function fmtCost(n: number): string {
  if (!n) return '$0.00'
  return `$${n.toFixed(4)}`
}

function MetricCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string
  value: string | number
  icon: LucideIcon
  color: string
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <div className={cn('flex size-9 items-center justify-center rounded-lg bg-primary/5', color)}>
          <Icon className="size-4.5" strokeWidth={1.8} />
        </div>
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="truncate text-lg font-semibold text-foreground">{value}</p>
        </div>
      </CardContent>
    </Card>
  )
}

function metricCards(s: AgentMetricsSummary) {
  return [
    { label: '运行次数', value: s.runs, icon: Activity, color: 'text-primary' },
    { label: '成功', value: s.success, icon: CheckCircle2, color: 'text-emerald-500' },
    { label: '失败', value: s.failed, icon: XCircle, color: 'text-destructive' },
    { label: '平均耗时', value: fmtDuration(s.avg_latency_ms), icon: Timer, color: 'text-amber-500' },
    { label: '平均 Tokens', value: fmtTokens(s.avg_tokens), icon: Hash, color: 'text-sky-500' },
    { label: '平均成本', value: fmtCost(s.avg_cost), icon: DollarSign, color: 'text-violet-500' },
  ]
}

export function MetricsPanel({ agentId }: { agentId: string }) {
  const [range, setRange] = useState('7d')
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['agent-metrics', agentId, range],
    queryFn: () => fetchAgentMetrics(agentId, range),
    enabled: !!agentId,
    retry: 1,
  })

  const items = data?.trend ?? []
  const cards = data ? metricCards(data.summary) : []

  const { data: variantsData } = useQuery({
    queryKey: ['agent-prompt-variants', agentId, range],
    queryFn: () => fetchPromptVariants(agentId, range),
    enabled: !!agentId,
    retry: 1,
  })
  const variants = variantsData?.variants ?? []

  return (
    <div className="space-y-4">
      {/* 工具栏：时间范围切换 + 刷新 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1 rounded-lg border bg-muted/40 p-0.5">
          {RANGES.map((r) => (
            <button
              key={r.key}
              onClick={() => setRange(r.key)}
              className={cn(
                'rounded-md px-3 py-1 text-xs font-medium transition-colors',
                range === r.key
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
        <Button
          variant="outline"
          size="sm"
          className="gap-2"
          onClick={() => refetch()}
          disabled={isFetching}
        >
          <RefreshCw className={cn('size-3.5', isFetching && 'animate-spin')} />
          刷新
        </Button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : isError || !data ? (
        <EmptyState
          icon={Activity}
          title="无法加载运行指标"
          description="指标端点不可用，请检查后端服务"
        />
      ) : (
        <>
          {/* 六项指标卡 */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            {cards.map((c) => (
              <MetricCard key={c.label} {...c} />
            ))}
          </div>

          {/* 成功率进度条 */}
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>成功率（{data.summary.runs} 次运行）</span>
                <span className="font-medium text-foreground">
                  {data.summary.success_rate}%
                </span>
              </div>
              <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-emerald-500 transition-all"
                  style={{ width: `${Math.min(data.summary.success_rate, 100)}%` }}
                />
              </div>
            </CardContent>
          </Card>

          {/* A/B Prompt 变体对比（AC-P4-3） */}
          {variants.length > 0 && (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="text-sm">A/B Prompt 变体对比</CardTitle>
                <span className="text-xs text-muted-foreground">
                  {variants.length} 个变体参与分流
                </span>
              </CardHeader>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs text-muted-foreground">
                        <th className="px-4 py-2 font-medium">变体</th>
                        <th className="px-4 py-2 font-medium">运行</th>
                        <th className="px-4 py-2 font-medium">成功</th>
                        <th className="px-4 py-2 font-medium">失败</th>
                        <th className="px-4 py-2 font-medium">成功率</th>
                        <th className="px-4 py-2 font-medium">平均耗时</th>
                        <th className="px-4 py-2 font-medium">平均 Tokens</th>
                      </tr>
                    </thead>
                    <tbody>
                      {variants.map((v: PromptVariantStat) => (
                        <tr key={v.variant} className="border-b last:border-0">
                          <td className="px-4 py-2 font-medium text-primary">{v.variant}</td>
                          <td className="px-4 py-2">{v.runs}</td>
                          <td className="px-4 py-2 text-emerald-500">{v.success}</td>
                          <td className="px-4 py-2 text-destructive">{v.failed}</td>
                          <td className="px-4 py-2">
                            <span className="font-medium">{v.success_rate}%</span>
                          </td>
                          <td className="px-4 py-2">{fmtDuration(v.avg_latency_ms)}</td>
                          <td className="px-4 py-2">{fmtTokens(v.avg_tokens)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {/* 趋势图 */}
          {items.length === 0 ? (
            <EmptyState
              icon={Activity}
              title="该时间段内暂无运行记录"
              description="Agent 运行后展示按天趋势"
            />
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">运行次数趋势</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="h-52">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={items} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                        <Tooltip />
                        <Bar dataKey="runs" name="运行次数" fill="#6366f1" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Latency / Tokens / Error Rate</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="h-52">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={items} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                        <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
                        <YAxis
                          yAxisId="right"
                          orientation="right"
                          tick={{ fontSize: 11 }}
                          domain={[0, 100]}
                        />
                        <Tooltip />
                        <Legend />
                        <Line
                          yAxisId="left"
                          type="monotone"
                          dataKey="avg_latency_ms"
                          name="平均耗时(ms)"
                          stroke="#f59e0b"
                          dot={false}
                        />
                        <Line
                          yAxisId="left"
                          type="monotone"
                          dataKey="avg_tokens"
                          name="平均Tokens"
                          stroke="#0ea5e9"
                          dot={false}
                        />
                        <Line
                          yAxisId="right"
                          type="monotone"
                          dataKey="error_rate"
                          name="错误率(%)"
                          stroke="#ef4444"
                          dot={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </>
      )}
    </div>
  )
}