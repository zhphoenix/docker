import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, TrendingUp, TrendingDown, Minus, Activity } from 'lucide-react'
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
import { fetchNewsImpact } from '@/services/news'
import { cn } from '@/lib/utils'

export function ImpactTab() {
  const [entityName, setEntityName] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [days, setDays] = useState('30')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['news-impact', entityName, days],
    queryFn: () => fetchNewsImpact(entityName, Number(days)),
    enabled: entityName.length > 0,
  })

  const handleSearch = () => {
    if (searchInput.trim()) setEntityName(searchInput.trim())
  }

  return (
    <div className="space-y-4">
      {/* Input */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="输入实体名称（如 NVIDIA、台积电）..."
            className="pl-9"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          />
        </div>
        <Select value={days} onValueChange={(v) => setDays(v ?? '')}>
          <SelectTrigger className="w-[120px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7">7 天</SelectItem>
            <SelectItem value="30">30 天</SelectItem>
            <SelectItem value="90">90 天</SelectItem>
          </SelectContent>
        </Select>
        <Button size="sm" onClick={handleSearch} disabled={!searchInput.trim()}>
          分析
        </Button>
      </div>

      {/* Empty state */}
      {!entityName && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <Activity className="size-8 text-muted-foreground/50" />
            <p className="mt-3 text-sm text-muted-foreground">
              输入实体名称，分析其近期新闻影响
            </p>
          </CardContent>
        </Card>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      )}

      {/* Error */}
      {isError && (
        <Card>
          <CardContent className="py-8 text-center">
            <p className="text-sm text-destructive">查询失败，请检查后端服务</p>
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {data && !isLoading && (
        <div className="space-y-4">
          {/* Stats cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard
              label="总事件数"
              value={data.total_events}
              className="text-foreground"
            />
            <StatCard
              label="正面"
              value={data.positive_count}
              icon={<TrendingUp className="size-3.5 text-green-600" />}
              className="text-green-600"
            />
            <StatCard
              label="负面"
              value={data.negative_count}
              icon={<TrendingDown className="size-3.5 text-red-600" />}
              className="text-red-600"
            />
            <StatCard
              label="平均影响分"
              value={data.avg_impact_score}
              icon={<Minus className="size-3.5 text-muted-foreground" />}
              className="text-foreground"
            />
          </div>

          {/* Message for no data */}
          {data.total_events === 0 && data.message && (
            <p className="text-center text-sm text-muted-foreground">
              {data.message}
            </p>
          )}

          {/* Events breakdown */}
          {data.events.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-semibold text-muted-foreground">
                事件明细（前 20 条）
              </h3>
              {data.events.map((event, idx) => (
                <div
                  key={idx}
                  className="flex items-center gap-3 rounded-lg border p-3"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-foreground">
                      {event.event_title ?? event.article_title ?? '—'}
                    </p>
                    <p className="mt-0.5 text-[10px] text-muted-foreground">
                      {event.event_type && (
                        <Badge variant="outline" className="mr-2 text-[9px]">
                          {event.event_type}
                        </Badge>
                      )}
                      {event.published_at &&
                        new Date(event.published_at).toLocaleDateString('zh-CN')}
                    </p>
                  </div>
                  {event.impact_direction && (
                    <Badge
                      variant="secondary"
                      className={cn(
                        'shrink-0 text-[10px]',
                        event.impact_direction === 'positive' &&
                          'bg-green-500/15 text-green-600',
                        event.impact_direction === 'negative' &&
                          'bg-red-500/15 text-red-600'
                      )}
                    >
                      {event.impact_direction}
                      {event.impact_score != null && ` (${event.impact_score})`}
                    </Badge>
                  )}
                </div>
              ))}
            </div>
          )}
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
  value: number
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
