import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Clock, ExternalLink } from 'lucide-react'
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
import { fetchNewsTimeline, type TimelineItem } from '@/services/news'

export function TimelineTab() {
  const [entityName, setEntityName] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [days, setDays] = useState('90')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['news-timeline', entityName, days],
    queryFn: () => fetchNewsTimeline(entityName, Number(days), 50),
    enabled: entityName.length > 0,
  })

  const items = data?.items ?? []

  // Group by date
  const grouped = items.reduce<Record<string, TimelineItem[]>>((acc, item) => {
    const date = item.published_at
      ? new Date(item.published_at).toLocaleDateString('zh-CN', {
          year: 'numeric',
          month: 'long',
          day: 'numeric',
        })
      : '未知日期'
    if (!acc[date]) acc[date] = []
    acc[date].push(item)
    return acc
  }, {})

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
            placeholder="输入实体名称查看新闻时间线..."
            className="pl-9"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          />
        </div>
        <Select value={days} onValueChange={(v) => setDays(v ?? '')}>
          <SelectTrigger className="w-[120px]">
            <SelectValue>
              {(v: string | null) => (v ? `${v} 天` : '')}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="30">30 天</SelectItem>
            <SelectItem value="90">90 天</SelectItem>
            <SelectItem value="180">180 天</SelectItem>
          </SelectContent>
        </Select>
        <Button size="sm" onClick={handleSearch} disabled={!searchInput.trim()}>
          查询
        </Button>
      </div>

      {/* Empty state */}
      {!entityName && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <Clock className="size-8 text-muted-foreground/50" />
            <p className="mt-3 text-sm text-muted-foreground">
              输入实体名称，查看相关新闻时间线
            </p>
          </CardContent>
        </Card>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-16 w-full rounded-xl" />
              <Skeleton className="h-16 w-full rounded-xl" />
            </div>
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

      {/* Timeline */}
      {data && !isLoading && items.length === 0 && (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-sm text-muted-foreground">
              未找到 "{entityName}" 的相关新闻
            </p>
          </CardContent>
        </Card>
      )}

      {data && !isLoading && items.length > 0 && (
        <div className="relative space-y-6 pl-6">
          {/* Vertical line */}
          <div className="absolute bottom-0 left-[7px] top-2 w-px bg-border" />

          {Object.entries(grouped).map(([date, dateItems]) => (
            <div key={date} className="relative">
              {/* Dot */}
              <div className="absolute -left-6 top-1.5 size-[15px] rounded-full border-2 border-primary bg-background" />

              {/* Date label */}
              <h3 className="mb-2 text-xs font-semibold text-muted-foreground">
                {date}
              </h3>

              {/* Items */}
              <div className="space-y-2">
                {dateItems.map((item, idx) => (
                  <Card key={idx} className="transition-shadow hover:shadow-[var(--shadow-soft)]">
                    <CardContent className="p-3">
                      <div className="flex items-start justify-between gap-2">
                        <p className="min-w-0 flex-1 text-sm text-foreground">
                          {item.title}
                        </p>
                        {item.url && (
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="shrink-0 text-muted-foreground hover:text-foreground"
                          >
                            <ExternalLink className="size-3.5" />
                          </a>
                        )}
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        {item.category && (
                          <Badge variant="secondary" className="text-[10px]">
                            {item.category}
                          </Badge>
                        )}
                        {item.importance && (
                          <Badge variant="outline" className="text-[10px]">
                            重要度: {item.importance}
                          </Badge>
                        )}
                        {item.source_name && (
                          <span className="text-[10px] text-muted-foreground">
                            {item.source_name}
                          </span>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
