import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Minus,
  Star,
  Sparkles,
  Search,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  fetchTopImpactEvents,
  type TopImpactEvent,
} from '@/services/news'
import { cn } from '@/lib/utils'

const EVENT_TYPES = [
  { value: 'earnings', label: '财报' },
  { value: 'regulation', label: '监管' },
  { value: 'merger', label: '合并' },
  { value: 'acquisition', label: '收购' },
  { value: 'product_launch', label: '产品发布' },
  { value: 'macro_policy', label: '宏观政策' },
  { value: 'geopolitical', label: '地缘政治' },
  { value: 'supply_chain', label: '供应链' },
  { value: 'technology', label: '技术' },
]

const DIRECTION_CONFIG: Record<string, { icon: typeof TrendingUp; color: string; label: string }> = {
  positive: { icon: TrendingUp, color: 'text-green-600', label: '正面' },
  negative: { icon: TrendingDown, color: 'text-red-600', label: '负面' },
  neutral: { icon: Minus, color: 'text-gray-500', label: '中性' },
}

export function ImpactTab() {
  const [company, setCompany] = useState('')
  const [companyInput, setCompanyInput] = useState('')
  const [days, setDays] = useState('30')

  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: ['top-impact-events', company, days],
    queryFn: () =>
      fetchTopImpactEvents({ company, days: Number(days), limit: 20 }),
  })

  const items = data?.items ?? []
  const avgStars =
    items.length > 0
      ? items.reduce((s, i) => s + i.stars, 0) / items.length
      : 0
  const positive = items.filter((i) => i.impact?.direction === 'positive').length
  const negative = items.filter((i) => i.impact?.direction === 'negative').length

  return (
    <div className="space-y-4">
      {/* 数据源说明 + 过滤 */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="过滤受影响公司（如 Amazon、NVIDIA）..."
            className="pl-9"
            value={companyInput}
            onChange={(e) => setCompanyInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') setCompany(companyInput.trim())
            }}
          />
        </div>
        <Select value={days} onValueChange={(v) => setDays(v ?? '')}>
          <SelectTrigger className="w-[120px]">
            <SelectValue>
              {(v: string | null) => (v ? `${v} 天` : '')}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7">7 天</SelectItem>
            <SelectItem value="30">30 天</SelectItem>
            <SelectItem value="90">90 天</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={() => refetch()} className="gap-1.5">
          <RefreshCw className={cn('size-3.5', isFetching && 'animate-spin')} />
        </Button>
      </div>

      {/* KOC 数据源徽章 */}
      <div className="flex items-center gap-2 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2">
        <Sparkles className="size-3.5 text-primary" />
        <p className="text-[11px] text-muted-foreground">
          数据来自 KOC 知识图谱（core.events）Top Impact Events，星级 = 影响评分，
          不再触发 LLM 实时重算
        </p>
      </div>

      {/* Stats */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Top 事件数" value={items.length} />
        <StatCard label="平均星级" value={avgStars.toFixed(1)} />
        <StatCard
          label="正面"
          value={positive}
          icon={<TrendingUp className="size-3.5 text-green-600" />}
          className="text-green-600"
        />
        <StatCard
          label="负面"
          value={negative}
          icon={<TrendingDown className="size-3.5 text-red-600" />}
          className="text-red-600"
        />
      </div>

      {/* Loading / Error / Empty */}
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-xl" />
          ))}
        </div>
      ) : isError ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-sm text-destructive">查询失败，请检查后端服务</p>
          </CardContent>
        </Card>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-sm text-muted-foreground">暂无高影响事件</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {items.map((event) => (
            <ImpactEventCard key={event.id} event={event} />
          ))}
        </div>
      )}
    </div>
  )
}

function StatCard({
  label,
  value,
  icon,
  className,
}: {
  label: string
  value: number | string
  icon?: React.ReactNode
  className?: string
}) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-1 p-4">
        <div className="flex items-center gap-1.5">
          {icon}
          <span className={cn('text-xl font-bold', className)}>{value}</span>
        </div>
        <span className="text-[10px] text-muted-foreground">{label}</span>
      </CardContent>
    </Card>
  )
}

function ImpactEventCard({ event }: { event: TopImpactEvent }) {
  const direction = event.impact?.direction ?? 'neutral'
  const DirectionIcon = DIRECTION_CONFIG[direction]?.icon ?? Minus
  const directionColor = DIRECTION_CONFIG[direction]?.color ?? 'text-gray-500'
  const directionLabel = DIRECTION_CONFIG[direction]?.label ?? '中性'

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          <DirectionIcon className={cn('mt-0.5 size-4 shrink-0', directionColor)} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              {/* 星级 = 影响评分 */}
              <div className="flex shrink-0 items-center gap-0.5" title={`影响评分 ${event.score?.toFixed(2) ?? '—'}`}>
                {Array.from({ length: 5 }).map((_, i) => (
                  <Star
                    key={i}
                    className={cn(
                      'size-3',
                      i < event.stars
                        ? 'fill-amber-400 text-amber-400'
                        : 'text-muted-foreground/25'
                    )}
                  />
                ))}
              </div>
              <h3 className="truncate text-sm font-medium text-foreground">
                {event.title}
              </h3>
            </div>
            {event.description && (
              <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                {event.description}
              </p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="text-[10px]">
                {EVENT_TYPES.find((t) => t.value === event.event_type)?.label ??
                  event.event_type}
              </Badge>
              {event.score != null && (
                <span className={cn('text-xs font-medium', directionColor)}>
                  {event.score.toFixed(2)} · {directionLabel}
                </span>
              )}
              {event.confidence != null && (
                <span className="text-[10px] text-muted-foreground">
                  置信度: {event.confidence.toFixed(2)}
                </span>
              )}
              {event.company_count > 0 && (
                <span className="inline-flex items-center gap-1 rounded-md bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-600">
                  影响 {event.company_count} 家公司
                </span>
              )}
              {event.companies.length > 0 && (
                <span className="hidden sm:inline max-w-[200px] truncate text-[10px] text-muted-foreground">
                  {event.companies.join('、')}
                </span>
              )}
            </div>
          </div>
          {event.event_date && (
            <span className="shrink-0 text-[10px] text-muted-foreground">
              {new Date(event.event_date).toLocaleDateString('zh-CN', {
                month: 'short',
                day: 'numeric',
              })}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}