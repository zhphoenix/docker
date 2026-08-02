import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { RefreshCw, TrendingUp, TrendingDown, Minus } from 'lucide-react'
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
import { fetchNewsEvents, type NewsEvent } from '@/services/news'
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

const DIRECTION_CONFIG: Record<string, { icon: typeof TrendingUp; color: string }> = {
  positive: { icon: TrendingUp, color: 'text-green-600' },
  negative: { icon: TrendingDown, color: 'text-red-600' },
  neutral: { icon: Minus, color: 'text-gray-500' },
}

export function EventsTab() {
  const [eventType, setEventType] = useState('')
  const [entityName, setEntityName] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [days, setDays] = useState('30')

  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: ['news-events', eventType, entityName, days],
    queryFn: () =>
      fetchNewsEvents({
        event_type: eventType,
        entity_name: entityName,
        days: Number(days),
        limit: 30,
      }),
  })

  const events = data?.events ?? []

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-[180px]">
          <Input
            placeholder="实体名称（如 NVIDIA、腾讯）..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') setEntityName(searchInput)
            }}
          />
        </div>
        <Select
          value={eventType}
          onValueChange={(v) => setEventType(v === 'all' ? '' : v)}
        >
          <SelectTrigger className="w-[130px]">
            <SelectValue placeholder="事件类型" />
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
        <Select value={days} onValueChange={setDays}>
          <SelectTrigger className="w-[120px]">
            <SelectValue />
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

      {/* Events list */}
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
            <EventCard key={event.id} event={event} />
          ))}
        </div>
      )}
    </div>
  )
}

function EventCard({ event }: { event: NewsEvent }) {
  const direction = event.impact_direction ?? 'neutral'
  const DirectionIcon = DIRECTION_CONFIG[direction]?.icon ?? Minus
  const directionColor = DIRECTION_CONFIG[direction]?.color ?? 'text-gray-500'

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
            {event.summary && (
              <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                {event.summary}
              </p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="text-[10px]">
                {EVENT_TYPES.find((t) => t.value === event.event_type)?.label ??
                  event.event_type}
              </Badge>
              {event.impact_score != null && (
                <span className={cn('text-xs font-medium', directionColor)}>
                  影响分: {event.impact_score}
                </span>
              )}
              {event.market && (
                <span className="text-[10px] text-muted-foreground">
                  {event.market}
                </span>
              )}
              {event.sector && (
                <span className="text-[10px] text-muted-foreground">
                  {event.sector}
                </span>
              )}
              {event.article_title && (
                <span className="ml-auto max-w-[200px] truncate text-[10px] text-muted-foreground">
                  {event.article_title}
                </span>
              )}
            </div>
          </div>
          {event.event_time && (
            <span className="shrink-0 text-[10px] text-muted-foreground">
              {new Date(event.event_time).toLocaleDateString('zh-CN', {
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
