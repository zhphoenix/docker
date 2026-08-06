import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Copy,
  GitMerge,
  Layers,
  RefreshCw,
  ShieldQuestion,
  TriangleAlert,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { EmptyState } from '@/components/common/EmptyState'
import {
  fetchGovernanceSummary,
  fetchGovernanceItems,
  resolveGovernanceItem,
} from '@/services/knowledge'
import type { GovernanceItem } from '@/services/knowledge'
import { cn } from '@/lib/utils'

// ===== Constants =====

const TYPE_META: Record<
  string,
  { label: string; icon: React.ReactNode; color: string }
> = {
  duplicate_entity: {
    label: '重复实体',
    icon: <Copy className="size-3.5" strokeWidth={1.8} />,
    color: 'text-amber-500',
  },
  value_mismatch: {
    label: '冲突事实',
    icon: <TriangleAlert className="size-3.5" strokeWidth={1.8} />,
    color: 'text-red-500',
  },
  low_confidence: {
    label: '低置信',
    icon: <ShieldQuestion className="size-3.5" strokeWidth={1.8} />,
    color: 'text-blue-500',
  },
  stale_fact: {
    label: '过期知识',
    icon: <Layers className="size-3.5" strokeWidth={1.8} />,
    color: 'text-purple-500',
  },
  sync_conflict: {
    label: '同步冲突',
    icon: <GitMerge className="size-3.5" strokeWidth={1.8} />,
    color: 'text-orange-500',
  },
}

const TYPE_ORDER = [
  'duplicate_entity',
  'value_mismatch',
  'low_confidence',
  'stale_fact',
  'sync_conflict',
]

function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function itemDescription(item: GovernanceItem): string {
  const res = item.resolution_obj ?? {}
  const name = item.entity_name ?? '—'
  switch (item.conflict_type) {
    case 'duplicate_entity':
      return `「${name}」与「${res.duplicate_name ?? '?'}」相似（sim=${res.similarity ?? '?'}）`
    case 'value_mismatch':
      return `${name} | ${res.predicate ?? '?'}: ${JSON.stringify(res.object_a)} vs ${JSON.stringify(res.object_b)}`
    case 'low_confidence':
      return `${name} | ${res.kind === 'relation' ? `关系 ${res.relation_type ?? ''}` : `事实 ${res.predicate ?? ''}`} (conf=${res.confidence ?? '?'})`
    case 'stale_fact':
      return `${name} | ${res.predicate ?? '?'} [${res.lifecycle_status ?? '?'}]`
    case 'sync_conflict':
      return `${name} sync_status=${res.sync_status ?? 'Conflict'}`
    default:
      return name
  }
}

// ===== Component =====

export function KnowledgeGovernancePanel() {
  const queryClient = useQueryClient()
  const [activeType, setActiveType] = useState<string>('all')
  const [resolvingId, setResolvingId] = useState<string | null>(null)

  const summaryQuery = useQuery({
    queryKey: ['governance-summary'],
    queryFn: fetchGovernanceSummary,
    refetchInterval: 30_000,
  })

  const itemsQuery = useQuery({
    queryKey: ['governance-items', activeType],
    queryFn: () =>
      fetchGovernanceItems(activeType === 'all' ? undefined : activeType, 100),
  })

  const resolveMutation = useMutation({
    mutationFn: ({ id, action, note }: { id: string; action: 'merge' | 'keep' | 'dismiss'; note: string }) =>
      resolveGovernanceItem(id, action, note),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['governance-summary'] })
      void queryClient.invalidateQueries({ queryKey: ['governance-items'] })
    },
  })

  const handleResolve = (item: GovernanceItem, action: 'merge' | 'keep' | 'dismiss') => {
    setResolvingId(item.id)
    resolveMutation.mutate(
      { id: item.id, action, note: action === 'merge' ? '面板合并' : '面板确认' },
      { onSettled: () => setResolvingId(null) }
    )
  }

  const summary = summaryQuery.data?.summary
  const cards = TYPE_ORDER.map((type) => ({
    type,
    ...TYPE_META[type],
    count: summary?.[type as keyof typeof summary] ?? 0,
  }))

  return (
    <div className="space-y-6">
      {/* 加载失败不阻塞：EmptyState 降级 */}
      {summaryQuery.isError && (
        <p className="text-sm text-destructive">治理统计加载失败，请检查后端服务</p>
      )}

      {/* 计数卡 */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        {cards.map((card) => (
          <Card key={card.type} className={cn('transition-colors', card.color)}>
            <CardContent className="flex items-center gap-3 p-4">
              <div className="flex size-9 items-center justify-center rounded-lg bg-secondary">
                {card.icon}
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm text-muted-foreground">{card.label}</p>
                {summaryQuery.isLoading ? (
                  <Skeleton className="mt-1.5 h-7 w-10" />
                ) : (
                  <p className="text-2xl font-bold">{card.count}</p>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* 处理队列 */}
      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold">处理队列</h3>
              <Badge variant="secondary">{itemsQuery.data?.total ?? 0} 项待处理</Badge>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void queryClient.invalidateQueries({ queryKey: ['governance-summary'] })
                void queryClient.invalidateQueries({ queryKey: ['governance-items'] })
              }}
            >
              <RefreshCw className="size-3.5" strokeWidth={1.8} />
              刷新
            </Button>
          </div>

          <Tabs value={activeType} onValueChange={setActiveType}>
            <TabsList>
              <TabsTrigger value="all">全部</TabsTrigger>
              {TYPE_ORDER.map((t) => (
                <TabsTrigger key={t} value={t}>
                  {TYPE_META[t].label}
                  {summary && summary[t as keyof typeof summary] > 0
                    ? ` (${summary[t as keyof typeof summary]})`
                    : ''}
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value={activeType} className="mt-4">
              {itemsQuery.isLoading ? (
                <div className="space-y-2">
                  {[1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </div>
              ) : !itemsQuery.data || itemsQuery.data.items.length === 0 ? (
                <EmptyState
                  title="暂无待处理治理项"
                  description="治理检测结果将在此展示，可在 Knowledge Operations Center 触发检测"
                />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-28">类型</TableHead>
                      <TableHead>内容</TableHead>
                      <TableHead className="w-32">创建时间</TableHead>
                      <TableHead className="w-44 text-right">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {itemsQuery.data.items.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell>
                          <Badge variant="outline" className="gap-1">
                            <span className={TYPE_META[item.conflict_type]?.color}>
                              {TYPE_META[item.conflict_type]?.icon ?? null}
                            </span>
                            {TYPE_META[item.conflict_type]?.label ?? item.conflict_type}
                          </Badge>
                        </TableCell>
                        <TableCell className="max-w-md truncate text-sm">
                          {itemDescription(item)}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {formatDateTime(item.created_at)}
                        </TableCell>
                        <TableCell>
                          <div className="flex justify-end gap-1.5">
                            {item.conflict_type === 'duplicate_entity' && (
                              <Button
                                variant="outline"
                                size="sm"
                                disabled={resolvingId === item.id}
                                onClick={() => handleResolve(item, 'merge')}
                              >
                                <GitMerge className="size-3.5" strokeWidth={1.8} />
                                合并
                              </Button>
                            )}
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={resolvingId === item.id}
                              onClick={() => handleResolve(item, 'keep')}
                            >
                              保留
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={resolvingId === item.id}
                              onClick={() => handleResolve(item, 'dismiss')}
                            >
                              驳回
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  )
}