import { useQuery } from '@tanstack/react-query'
import { Wrench, RefreshCw } from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchTools } from '@/services/tools'
import { cn } from '@/lib/utils'

function fmtMs(ms: number | null): string {
  if (ms === null) return '—'
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}

function fmtTime(ts: string | null): string {
  if (!ts) return '—'
  const d = new Date(ts)
  return d.toLocaleString('zh-CN', { hour12: false })
}

function successRate(t: { calls: number; success_calls: number }): number {
  if (!t.calls) return 0
  return Math.round((t.success_calls / t.calls) * 100)
}

export function ToolsTab() {
  const listQuery = useQuery({
    queryKey: ['tools'],
    queryFn: fetchTools,
  })

  const tools = listQuery.data?.tools ?? []

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-sm">
          <span className="flex items-center gap-1.5">
            <Wrench className="size-4 text-muted-foreground" /> Tool 工具（{tools.length}）
          </span>
          <Button variant="ghost" size="icon" className="size-6" onClick={() => listQuery.refetch()}>
            <RefreshCw className={cn('size-3.5', listQuery.isFetching && 'animate-spin')} />
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {listQuery.isLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-10 w-full" />)}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>工具</TableHead>
                <TableHead className="text-right">调用次数</TableHead>
                <TableHead className="text-right">成功率</TableHead>
                <TableHead className="text-right">平均耗时</TableHead>
                <TableHead className="text-right">最大耗时</TableHead>
                <TableHead className="text-right">最后调用</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tools.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-8">
                    <EmptyState title="暂无工具统计" description="运行 Agent 后工具调用数据将在此展示" />
                  </TableCell>
                </TableRow>
              ) : (
                tools.map((t) => (
                  <TableRow key={t.name}>
                    <TableCell className="font-mono text-xs font-medium">{t.name}</TableCell>
                    <TableCell className="text-right">{t.calls}</TableCell>
                    <TableCell className="text-right">
                      {t.calls > 0 ? (
                        <Badge variant={successRate(t) >= 90 ? 'default' : 'secondary'}>
                          {successRate(t)}%
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground">{fmtMs(t.avg_ms)}</TableCell>
                    <TableCell className="text-right text-muted-foreground">{fmtMs(t.max_ms)}</TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">{fmtTime(t.last_at)}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}