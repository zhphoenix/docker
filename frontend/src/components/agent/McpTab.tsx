import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Cable, Activity } from 'lucide-react'
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
import { fetchMcp, heartbeatMcp } from '@/services/mcp'
import { cn } from '@/lib/utils'

const STATUS_META: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' }> = {
  connected: { label: '已连接', variant: 'default' },
  disconnected: { label: '已断开', variant: 'secondary' },
  unknown: { label: '未知', variant: 'outline' },
  disabled: { label: '已禁用', variant: 'outline' },
}

function fmtTime(ts: string | null): string {
  if (!ts) return '—'
  return new Date(ts).toLocaleString('zh-CN', { hour12: false })
}

export function McpTab() {
  const queryClient = useQueryClient()
  const listQuery = useQuery({
    queryKey: ['mcp'],
    queryFn: fetchMcp,
  })

  const heartbeatMutation = useMutation({
    mutationFn: () => heartbeatMcp(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mcp'] }),
  })

  const mcp = listQuery.data?.mcp ?? []

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-sm">
          <span className="flex items-center gap-1.5">
            <Cable className="size-4 text-muted-foreground" /> MCP 服务（{mcp.length}）
          </span>
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => heartbeatMutation.mutate()}
            disabled={heartbeatMutation.isPending}
          >
            <Activity className={cn('size-3.5', heartbeatMutation.isPending && 'animate-pulse')} />
            心跳检测
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {listQuery.isLoading ? (
          <div className="space-y-2">
            {[1, 2].map((i) => <Skeleton key={i} className="h-10 w-full" />)}
          </div>
        ) : mcp.length === 0 ? (
          <EmptyState title="暂无 MCP 服务" description="后端未纳管任何 MCP 服务" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>地址</TableHead>
                <TableHead>状态</TableHead>
                <TableHead className="text-right">延迟</TableHead>
                <TableHead className="text-right">重试</TableHead>
                <TableHead className="text-right">最后心跳</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {mcp.map((s) => {
                const meta = STATUS_META[s.status] ?? STATUS_META.unknown
                return (
                  <TableRow key={s.name}>
                    <TableCell className="font-mono text-xs font-medium">{s.name}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{s.url}</TableCell>
                    <TableCell>
                      <Badge variant={meta.variant}>{meta.label}</Badge>
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground">
                      {s.latency_ms > 0 ? `${s.latency_ms}ms` : '—'}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground">{s.retry_count}</TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">{fmtTime(s.last_heartbeat)}</TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}