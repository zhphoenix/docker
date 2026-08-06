import {
  RefreshCw,
  Play,
  Pause,
  Trash2,
  Eye,
  TrendingUp,
  Boxes,
  BarChart3,
  Factory,
  Building2,
  User,
  Wallet,
  Globe,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useWatchlistItems, useUpdateWatchlist, useDeleteWatchlist } from '@/hooks/useWatchlist'
import { AddStockDialog } from './AddStockDialog'
import type { WatchlistItem } from '@/services/watchlist'

interface Props {
  filterGroup: string
  filterEnabled: string
  onFilterGroupChange: (v: string) => void
  onFilterEnabledChange: (v: string) => void
  onStockClick?: (item: WatchlistItem) => void
}

const TYPE_META: Record<string, { label: string; Icon: typeof TrendingUp }> = {
  stock: { label: '股票', Icon: TrendingUp },
  etf: { label: 'ETF', Icon: Boxes },
  index: { label: '指数', Icon: BarChart3 },
  industry: { label: '行业', Icon: Factory },
  company: { label: '公司', Icon: Building2 },
  person: { label: '人物', Icon: User },
  fund: { label: '基金', Icon: Wallet },
  macro_theme: { label: '宏观主题', Icon: Globe },
}

function ItemTypeBadge({ type }: { type: string }) {
  const meta = TYPE_META[type] ?? { label: '股票', Icon: TrendingUp }
  const { Icon, label } = meta
  return (
    <Badge variant="outline" className="gap-1 text-xs">
      <Icon className="size-3" />
      {label}
    </Badge>
  )
}

function AiScoreBadge({ score }: { score: number }) {
  if (!score) return <span className="text-xs text-muted-foreground">—</span>
  const color = score >= 80 ? 'text-green-600' : score >= 60 ? 'text-amber-600' : 'text-red-600'
  return <span className={`text-sm font-bold tabular-nums ${color}`}>{score}</span>
}

function RelativeTime({ iso }: { iso: string | null }) {
  if (!iso) return <span className="text-xs text-muted-foreground">—</span>
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return <span className="text-xs text-muted-foreground">刚刚</span>
  if (mins < 60) return <span className="text-xs text-muted-foreground">{mins}分钟前</span>
  const hours = Math.floor(mins / 60)
  if (hours < 24) return <span className="text-xs text-muted-foreground">{hours}小时前</span>
  return <span className="text-xs text-muted-foreground">{Math.floor(hours / 24)}天前</span>
}

export function WatchlistGrid({
  filterGroup,
  filterEnabled,
  onFilterGroupChange,
  onFilterEnabledChange,
  onStockClick,
}: Props) {
  const { data, isLoading, refetch, isFetching } = useWatchlistItems({
    group_name: filterGroup || undefined,
    enabled: filterEnabled === 'on' ? true : filterEnabled === 'off' ? false : undefined,
  })
  const toggleMutation = useUpdateWatchlist()
  const deleteMutation = useDeleteWatchlist()

  const items = data?.items ?? []

  const handleToggle = (item: WatchlistItem) => {
    toggleMutation.mutate({ id: item.id, data: { enabled: !item.enabled } })
  }

  const handleDelete = (id: string) => {
    if (confirm('确定要删除该股票吗？')) {
      deleteMutation.mutate(id)
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-3">
          <CardTitle className="text-base">自选股（{items.length}）</CardTitle>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Select value={filterGroup || 'all'} onValueChange={(v) => onFilterGroupChange(v === 'all' ? '' : (v ?? ''))}>
              <SelectTrigger className="w-28">
                <SelectValue placeholder="分组" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部分组</SelectItem>
                <SelectItem value="顶级持仓">顶级持仓</SelectItem>
                <SelectItem value="科技">科技</SelectItem>
                <SelectItem value="消费">消费</SelectItem>
              </SelectContent>
            </Select>
            <Select value={filterEnabled || 'all'} onValueChange={(v) => onFilterEnabledChange(v === 'all' ? '' : (v ?? ''))}>
              <SelectTrigger className="w-28">
                <SelectValue placeholder="状态" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部状态</SelectItem>
                <SelectItem value="on">监控中</SelectItem>
                <SelectItem value="off">已停用</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="ghost" size="sm" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCw className={`mr-1 size-4 ${isFetching ? 'animate-spin' : ''}`} />
              刷新
            </Button>
            <AddStockDialog />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-32 w-full" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <EmptyState title="暂无自选股" description="点击右上角「添加股票」开始监控" />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((it) => (
              <div
                key={it.id}
                className="flex flex-col gap-2 rounded-lg border p-4 transition-colors hover:border-primary/40"
              >
                {/* Top row: name + market */}
                <div className="flex items-start justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-semibold truncate">
                        {it.stock_name || it.stock_code}
                      </span>
                      <ItemTypeBadge type={it.item_type} />
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {it.stock_code}
                      {it.market ? ` · ${it.market.toUpperCase()}` : ''}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1 text-right">
                    <span className="text-xs text-muted-foreground">AI</span>
                    <AiScoreBadge score={it.ai_score ?? 0} />
                  </div>
                </div>
                {/* Stats row */}
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span>📰 {it.today_news_count ?? 0} 新闻</span>
                  <span>📋 {it.today_event_count ?? 0} 事件</span>
                </div>
                {/* Tags + group */}
                <div className="flex flex-wrap items-center gap-1">
                  {it.group_name && <Badge variant="secondary">{it.group_name}</Badge>}
                  {it.tags?.slice(0, 2).map((t) => (
                    <Badge key={t} variant="outline" className="text-xs">{t}</Badge>
                  ))}
                </div>
                {/* Bottom row: last update + actions */}
                <div className="mt-auto flex items-center justify-between border-t pt-2">
                  <span className="text-xs text-muted-foreground">
                    更新：<RelativeTime iso={it.last_event_at ?? null} />
                  </span>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      title="查看详情"
                      onClick={() => onStockClick?.(it)}
                    >
                      <Eye className="size-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      title={it.enabled ? '暂停监控' : '启用监控'}
                      onClick={() => handleToggle(it)}
                    >
                      {it.enabled ? <Pause className="size-4" /> : <Play className="size-4" />}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0 text-destructive"
                      title="删除"
                      onClick={() => handleDelete(it.id)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
