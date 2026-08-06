import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Minus,
  CalendarPlus,
  Building2,
  Gauge,
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
import { fetchEventMonitor, type CoreEvent } from '@/services/news'
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

export function EventsTab() {
  const [eventType, setEventType] = useState('')
  const [company, setCompany] = useState('')
  const [companyInput, setCompanyInput] = useState('')
  const [days, setDays] = useState('30')

  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: ['core-events-monitor', eventType, company, days],
    queryFn: () =>
      fetchEventMonitor({
        event_type: eventType,
        company,
        days: Number(days),
        limit: 30,
      }),
  })

  const events = data?.events ?? []
  const direction = data?.direction ?? { positive: 0, negative: 0, neutral: 0 }

  return (
    <div className="space-y-4">
      {/* 统计卡片（core.events 今日新增 / 方向分布） */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={CalendarPlus}
          iconClass="text-blue-500"
          label="今日新增事件"
          value={data ? data.today_new : '–'}
          sub={`近 ${data?.days ?? days} 天共 ${data?.window_total ?? '–'} 条 · ${data?.source ?? ''}`}
        />
        <StatCard
          icon={Gauge}
          iconClass="text-violet-500"
          label="平均影响分"
          value={data?.avg_score != null ? data.avg_score.toFixed(2) : '–'}
          sub="窗口内事件 impact.score 均值"
        />
        <StatCard
          icon={TrendingUp}
          iconClass="text-green-500"
          label="正面 / 负面"
          value={`${direction.positive} / ${direction.negative}`}
          sub={`中性 ${direction.neutral} 条`}
        />
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center gap-2">
            <Building2 className="size-4 text-amber-500" />
            <span className="text-sm font-medium">受影响公司 Top</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {(data?.company_mentions ?? []).slice(0, 6).map((m) => (
              <button
                key={m.company}
                onClick={() => {
                  setCompany(m.company)
                  setCompanyInput(m.company)
                }}
                className={cn(
                  'rounded-md border px-2 py-0.5 text-[11px] transition-colors',
                  company === m.company
                    ? 'border-primary/50 bg-primary/10 text-primary'
                    : 'border-border hover:border-primary/30 bg-muted/40'
                )}
              >
                {m.company} · {m.event_count}
              </button>
            ))}
            {(data?.company_mentions ?? []).length === 0 && (
              <span className="text-[11px] text-muted-foreground">暂无</span>
            )}
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-[180px]">
          <Input
            placeholder="受影响公司（如 Amazon、NVIDIA）..."
            value={companyInput}
            onChange={(e) => setCompanyInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                setCompany(companyInput.trim())
              }
            }}
          />
        </div>
        <Select
          value={eventType}
          onValueChange={(v) => setEventType(v === 'all' ? '' : (v ?? ''))}
        >
          <SelectTrigger className="w-[130px]">
            <SelectValue>
              {(v: string | null) =>
                v && v !== 'all'
                  ? (EVENT_TYPES.find((t) => t.value === v)?.label ?? v)
                  : '全部类型'
              }
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部类型</SelectItem>
            {EVENT_TYPES.map((t) => (
              <SelectItem key={t.value} value={t.value}>
                {t.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
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

      {/* Events list（与 core.events 一致） */}
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full rounded-xl" />
          ))}
        </div>
      ) : isError ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-sm text-destructive">查询失败，请检查后端服务</p>
          </CardContent>
        </Card>
      ) : events.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-sm text-muted-foreground">暂无事件数据</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {events.map((event) => (
            <EventCard
              key={event.id}
              event={event}
              onCompanyClick={(name) => {
                setCompany(name)
                setCompanyInput(name)
              }}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function StatCard({
  icon: Icon,
  iconClass,
  label,
  value,
  sub,
}: {
  icon: typeof CalendarPlus
  iconClass: string
  label: string
  value: string | number
  sub: string
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center gap-2">
        <Icon className={cn('size-4', iconClass)} />
        <span className="text-sm font-medium">{label}</span>
      </div>
      <p className="mt-1 text-2xl font-bold tabular-nums">{value}</p>
      <p className="mt-0.5 truncate text-[10px] text-muted-foreground">{sub}</p>
    </div>
  )
}

function EventCard({
  event,
  onCompanyClick,
}: {
  event: CoreEvent
  onCompanyClick: (name: string) => void
}) {
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
              {event.impact?.score != null && (
                <span className={cn('text-xs font-medium', directionColor)}>
                  影响分: {event.impact.score.toFixed(2)} · {directionLabel}
                </span>
              )}
              {event.confidence != null && (
                <span className="text-[10px] text-muted-foreground">
                  置信度: {event.confidence}
                </span>
              )}
              {event.company_count > 0 && (
                <button
                  onClick={() => onCompanyClick(event.entities[0])}
                  className="inline-flex items-center gap-1 rounded-md bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-600 hover:bg-amber-500/20"
                >
                  <Building2 className="size-3" />
                  影响 {event.company_count} 家公司
                </button>
              )}
              {event.entities.length > 0 && (
                <span className="hidden sm:inline max-w-[220px] truncate text-[10px] text-muted-foreground">
                  {event.entities.join('、')}
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