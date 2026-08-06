import { useQuery } from '@tanstack/react-query'
import { Activity, Box, PlugZap, Rss, TriangleAlert } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { fetchNewsActivities, type NewsActivity } from '@/services/news'

const KIND_META: Record<
  NewsActivity['kind'],
  { icon: typeof Activity; label: string; badge: string; iconColor: string }
> = {
  source_added: {
    icon: PlugZap,
    label: '新源接入',
    badge: 'border-sky-500/30 bg-sky-500/10 text-sky-400',
    iconColor: 'text-sky-400',
  },
  collect_error: {
    icon: TriangleAlert,
    label: '采集异常',
    badge: 'border-red-500/30 bg-red-500/10 text-red-400',
    iconColor: 'text-red-400',
  },
  breaking: {
    icon: Rss,
    label: 'Breaking',
    badge: 'border-amber-500/30 bg-amber-500/10 text-amber-400',
    iconColor: 'text-amber-400',
  },
  package_publish: {
    icon: Box,
    label: 'Package 发布',
    badge: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
    iconColor: 'text-emerald-400',
  },
}

function timeAgo(iso: string): string {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const diff = Date.now() - t
  const min = Math.floor(diff / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr} 小时前`
  return `${Math.floor(hr / 24)} 天前`
}

function ActivityRow({ item }: { item: NewsActivity }) {
  const meta = KIND_META[item.kind] ?? {
    icon: Activity,
    label: item.label,
    badge: 'border-muted bg-muted/40 text-muted-foreground',
    iconColor: 'text-muted-foreground',
  }
  const Icon = meta.icon
  return (
    <div className="flex items-start gap-3 py-2.5">
      <div className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted/40 ${meta.iconColor}`}>
        <Icon className="size-4" strokeWidth={1.8} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className={`px-1.5 py-0 text-[10px] ${meta.badge}`}>
            {meta.label}
          </Badge>
          <span className="truncate text-sm font-medium text-foreground">{item.title}</span>
        </div>
        {item.detail ? (
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{item.detail}</p>
        ) : null}
      </div>
      <span className="shrink-0 text-xs text-muted-foreground" title={item.time}>
        {timeAgo(item.time)}
      </span>
    </div>
  )
}

export function RecentActivities() {
  const { data, isLoading } = useQuery({
    queryKey: ['news-activities'],
    queryFn: () => fetchNewsActivities({ days: 14, limit: 40 }),
  })

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    )
  }

  const activities = data?.activities ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Activity className="size-4 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          近 {data?.days ?? 14} 天 · 共 {data?.total ?? 0} 条动态
        </p>
      </div>
      {activities.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center gap-2 py-12 text-center">
            <Activity className="size-8 text-muted-foreground/60" strokeWidth={1.5} />
            <p className="text-sm text-muted-foreground">暂无动态</p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="divide-y divide-border/60 px-4 py-1">
            {activities.map((item, i) => (
              <ActivityRow key={`${item.kind}-${item.time}-${i}`} item={item} />
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

export function RecentActivitiesPreview() {
  const { data, isLoading } = useQuery({
    queryKey: ['news-activities', 'preview'],
    queryFn: () => fetchNewsActivities({ days: 7, limit: 5 }),
  })

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    )
  }

  const activities = data?.activities ?? []
  if (activities.length === 0) {
    return <p className="text-sm text-muted-foreground">暂无动态</p>
  }
  return (
    <div className="space-y-1">
      {activities.map((item, i) => {
        const meta = KIND_META[item.kind] ?? KIND_META_project(item.kind, item.label)
        const Icon = meta.icon
        return (
          <div key={`${item.kind}-${item.time}-${i}`} className="flex items-center gap-2 py-1">
            <Icon className={`size-3.5 shrink-0 ${meta.iconColor}`} strokeWidth={1.8} />
            <span className="truncate text-xs text-muted-foreground">{item.title}</span>
            <span className="ml-auto shrink-0 text-[10px] text-muted-foreground/60">
              {timeAgo(item.time)}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function KIND_META_project(
  kind: string,
  label: string
): { icon: typeof Activity; label: string; badge: string; iconColor: string } {
  return KIND_META[kind as NewsActivity['kind']] ?? {
    icon: Activity,
    label,
    badge: 'border-muted bg-muted/40 text-muted-foreground',
    iconColor: 'text-muted-foreground',
  }
}