import { Star, Newspaper, AlertTriangle, FileText, Bell } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useWatchlistOverview } from '@/hooks/useWatchlist'

const cards = [
  { key: 'monitored_stocks', label: '监控股票', icon: Star, color: 'text-blue-500', bg: 'bg-blue-500/10' },
  { key: 'today_events', label: '今日事件', icon: Newspaper, color: 'text-green-500', bg: 'bg-green-500/10' },
  { key: 'high_risk_events', label: '高风险', icon: AlertTriangle, color: 'text-red-500', bg: 'bg-red-500/10' },
  { key: 'ai_reports', label: 'AI 报告', icon: FileText, color: 'text-purple-500', bg: 'bg-purple-500/10' },
  { key: 'unread_alerts', label: '未读通知', icon: Bell, color: 'text-amber-500', bg: 'bg-amber-500/10' },
] as const

export function TodayOverview() {
  const { data, isLoading } = useWatchlistOverview()

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {cards.map((c) => (
          <Card key={c.key}>
            <CardContent className="p-4">
              <Skeleton className="mb-2 h-4 w-12" />
              <Skeleton className="h-8 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  const values: Record<string, number> = {
    monitored_stocks: data?.monitored_stocks ?? 0,
    today_events: data?.today_events ?? 0,
    high_risk_events: data?.high_risk_events ?? 0,
    ai_reports: data?.ai_reports ?? 0,
    unread_alerts: data?.unread_alerts ?? 0,
  }

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {cards.map(({ key, label, icon: Icon, color, bg }) => (
        <Card key={key} className="transition-colors hover:border-primary/40">
          <CardContent className="flex items-center gap-3 p-4">
            <div className={`flex size-10 items-center justify-center rounded-lg ${bg}`}>
              <Icon className={`size-5 ${color}`} strokeWidth={1.8} />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className="text-2xl font-bold tabular-nums">{values[key]}</p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
