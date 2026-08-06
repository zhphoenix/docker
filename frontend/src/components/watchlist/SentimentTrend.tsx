import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import { useSentimentTrend } from '@/hooks/useWatchlist'

export function SentimentTrend() {
  const { data, isLoading } = useSentimentTrend(14)
  const items = data?.items ?? []

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-base">情绪趋势 Sentiment</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-52 w-full" />
        ) : items.length === 0 ? (
          <EmptyState
            title="暂无情绪数据"
            description="监控事件产生后展示情绪趋势"
          />
        ) : (
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={items}
                margin={{ top: 4, right: 8, left: -20, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="bullish" name="看多" stackId="a" fill="#10b981" />
                <Bar dataKey="neutral" name="中性" stackId="a" fill="#94a3b8" />
                <Bar dataKey="bearish" name="看空" stackId="a" fill="#ef4444" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  )
}