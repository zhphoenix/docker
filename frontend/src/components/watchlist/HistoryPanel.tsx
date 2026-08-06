import { useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import { useWatchlistHistory } from '@/hooks/useWatchlist'

const RANGE_OPTIONS = [
  { days: 7, label: '近7天' },
  { days: 30, label: '近30天' },
  { days: 90, label: '近90天' },
]

export function HistoryPanel() {
  const [days, setDays] = useState(30)
  const { data, isLoading } = useWatchlistHistory(days)

  const stats = data?.stats ?? []

  const summaryCards = (() => {
    const total = stats.reduce((s, r) => s + r.total_events, 0)
    const high = stats.reduce((s, r) => s + r.high_priority_events, 0)
    const alerts = stats.reduce((s, r) => s + r.total_alerts, 0)
    return { total, high, alerts }
  })()

  if (isLoading) {
    return (
      <Card>
        <CardHeader><Skeleton className="h-5 w-24" /></CardHeader>
        <CardContent>
          <div className="mb-4 flex gap-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-28" />
            ))}
          </div>
          <Skeleton className="h-48 w-full" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">监控历史</CardTitle>
        <div className="flex gap-1">
          {RANGE_OPTIONS.map(({ days: d, label }) => (
            <Button
              key={d}
              variant={days === d ? 'default' : 'outline'}
              size="sm"
              onClick={() => setDays(d)}
            >
              {label}
            </Button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        {stats.length === 0 ? (
          <EmptyState title="暂无历史数据" description="运行监控后，统计数据将在此展示" />
        ) : (
          <>
            {/* Summary cards */}
            <div className="mb-4 grid grid-cols-3 gap-4">
              <div className="rounded-lg border p-3 text-center">
                <p className="text-xs text-muted-foreground">总事件</p>
                <p className="text-xl font-bold">{summaryCards.total}</p>
              </div>
              <div className="rounded-lg border p-3 text-center">
                <p className="text-xs text-muted-foreground">高优先级</p>
                <p className="text-xl font-bold text-red-500">{summaryCards.high}</p>
              </div>
              <div className="rounded-lg border p-3 text-center">
                <p className="text-xs text-muted-foreground">告警</p>
                <p className="text-xl font-bold text-amber-500">{summaryCards.alerts}</p>
              </div>
            </div>
            {/* Chart */}
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={stats}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v: string) => v.slice(5)}
                />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="total_events" name="总事件" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                <Bar dataKey="high_priority_events" name="高优先级" fill="hsl(0 84% 60%)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </>
        )}
      </CardContent>
    </Card>
  )
}
