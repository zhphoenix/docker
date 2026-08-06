import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  FileText,
  Tag,
  Clock,
  Zap,
  Network,
  Info,
  GitCommitHorizontal,
  CalendarDays,
} from 'lucide-react'
import { WindowedDialog } from '@/components/ui/windowed-dialog'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { EmptyState } from '@/components/common/EmptyState'
import {
  fetchFacts,
  fetchEntityNeighbors,
  fetchEntityTimeline,
  type KnowledgeEntity,
  type KnowledgeFact,
  type EntityTimeline,
} from '@/services/knowledge'
import { cn } from '@/lib/utils'

interface EntityDetailDialogProps {
  entity: KnowledgeEntity | null
  onClose: () => void
}

const VERIFICATION_VARIANTS: Record<string, string> = {
  verified: 'bg-emerald-500/10 text-emerald-600',
  unverified: 'bg-muted text-muted-foreground',
  disputed: 'bg-red-500/10 text-red-600',
}

function formatFactValue(fact: KnowledgeFact): string {
  const v = fact.object_value
  return typeof v === 'object' ? JSON.stringify(v) : String(v ?? '')
}

export function EntityDetailDialog({ entity, onClose }: EntityDetailDialogProps) {
  const factsQuery = useQuery({
    queryKey: ['knowledge-facts', entity?.id],
    queryFn: () => fetchFacts(entity!.id),
    enabled: !!entity,
    retry: 1,
  })

  const neighborsQuery = useQuery({
    queryKey: ['knowledge-neighbors', entity?.id],
    queryFn: () => fetchEntityNeighbors(entity!.id, 1),
    enabled: !!entity,
    retry: 1,
  })

  // KOC-D3: 实体时间线（版本历史 + 事实 + 事件）
  const timelineQuery = useQuery({
    queryKey: ['knowledge-timeline', entity?.id],
    queryFn: () => fetchEntityTimeline(entity!.id),
    enabled: !!entity,
    retry: 1,
  })

  const facts = factsQuery.data?.facts ?? []
  const neighbors = neighborsQuery.data?.neighbors ?? []
  const timeline = timelineQuery.data

  // KOC-D3: 合并三类时间线条目（版本/事实/事件），按时间正序（演变链）
  const timelineEntries = useMemo(() => {
    type Entry = {
      key: string
      kind: 'version' | 'fact' | 'event'
      ts: string
      badge: string
      title: string
      body: string
      meta: string
    }
    const entries: Entry[] = []
    if (!timeline) return entries

    // 版本条目：相邻版本 name 变化时展示演变箭头
    timeline.versions.forEach((v, i) => {
      const name = String(v.content?.name ?? '')
      const prevName = i > 0 ? String(timeline.versions[i - 1].content?.name ?? '') : null
      const changed = prevName && prevName !== name
      entries.push({
        key: `v-${v.version}-${v.created_at ?? i}`,
        kind: 'version',
        ts: v.created_at ?? '9999-12-31',
        badge: `v${v.version}`,
        title: changed ? `${prevName} → ${name}` : name || '实体版本',
        body: Object.entries(v.content ?? {})
          .filter(([k]) => !['name', 'aliases'].includes(k))
          .map(([k, val]) => `${k}: ${typeof val === 'object' ? JSON.stringify(val) : String(val)}`)
          .join(' · '),
        meta: `${v.created_at ? new Date(v.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '时间未知'} · ${v.created_by}`,
      })
    })

    // 事实条目
    timeline.facts.forEach((f) => {
      const val = typeof f.object_value === 'object'
        ? JSON.stringify(f.object_value)
        : String(f.object_value ?? '')
      const window =
        f.time_start && f.time_end
          ? `${f.time_start} ~ ${f.time_end}`
          : (f.time_start ?? '时间未知')
      entries.push({
        key: `f-${f.id}`,
        kind: 'fact',
        ts: f.time_start ?? f.created_at ?? '9999-12-31',
        badge: f.predicate,
        title: f.predicate,
        body: `${val}${f.unit ? ` (${f.unit})` : ''}`,
        meta: `${window}${f.confidence != null ? ` · ${Math.round(f.confidence * 100)}% 置信` : ''}`,
      })
    })

    // 事件条目
    timeline.events.forEach((ev) => {
      entries.push({
        key: `e-${ev.id}`,
        kind: 'event',
        ts: ev.event_date ?? ev.created_at ?? '9999-12-31',
        badge: ev.event_type,
        title: ev.title,
        body: ev.description ?? '',
        meta: ev.event_date ?? '时间未知',
      })
    })

    return entries.sort((a, b) => a.ts.localeCompare(b.ts))
  }, [timeline])

  const timelineCount = timelineEntries.length

  return (
    <WindowedDialog
      open={!!entity}
      onOpenChange={(open) => !open && onClose()}
      title={
        entity && (
          <>
            <span>{entity.name}</span>
            <Badge variant="secondary" className="text-[10px]">
              {entity.entity_type}
            </Badge>
          </>
        )
      }
      defaultWidth={640}
      defaultHeight={560}
    >
      {entity && (
        <Tabs defaultValue="overview" className="w-full">
          <TabsList className="w-full justify-start">
            <TabsTrigger value="overview" className="text-xs">概览</TabsTrigger>
            <TabsTrigger value="facts" className="text-xs">
              事实{facts.length > 0 ? ` (${facts.length})` : ''}
            </TabsTrigger>
            <TabsTrigger value="timeline" className="text-xs">时间线</TabsTrigger>
            <TabsTrigger value="related" className="text-xs">
              关联{neighbors.length > 0 ? ` (${neighbors.length})` : ''}
            </TabsTrigger>
          </TabsList>

          {/* ── 概览 ── */}
          <TabsContent value="overview" className="mt-4 space-y-3 text-sm">
            {entity.canonical_name && entity.canonical_name !== entity.name && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Tag className="size-3.5" strokeWidth={1.8} />
                标准名：{entity.canonical_name}
              </div>
            )}
            {entity.description && (
              <p className="text-xs leading-relaxed text-muted-foreground">
                {entity.description}
              </p>
            )}
            <div className="flex gap-4 text-xs text-muted-foreground">
              {entity.confidence != null && (
                <span>置信度 {Math.round(entity.confidence * 100)}%</span>
              )}
              <span>来源 {entity.source_count} 篇</span>
            </div>

            {/* Aliases */}
            {entity.aliases && entity.aliases.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {entity.aliases.map((alias) => (
                  <Badge key={alias} variant="outline" className="text-[10px]">
                    {alias}
                  </Badge>
                ))}
              </div>
            )}

            {/* Properties（扩展属性） */}
            {entity.properties &&
              Object.keys(entity.properties).length > 0 && (
                <div className="rounded-lg bg-muted/50 p-3">
                  <h5 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
                    <Info className="size-3.5" strokeWidth={1.8} />
                    属性
                  </h5>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                    {Object.entries(entity.properties).map(([k, v]) => (
                      <div key={k} className="flex justify-between gap-2">
                        <span className="text-muted-foreground">{k}</span>
                        <span className="truncate font-medium">
                          {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
          </TabsContent>

          {/* ── 事实 ── */}
          <TabsContent value="facts" className="mt-4">
            {factsQuery.isLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-10 w-full rounded-lg" />
                ))}
              </div>
            ) : factsQuery.isError ? (
              <EmptyState icon={FileText} title="无法加载事实" description="查询关联事实失败" />
            ) : facts.length === 0 ? (
              <EmptyState icon={FileText} title="暂无关联事实" description="该实体尚未提取任何结构化事实" />
            ) : (
              <div className="space-y-2">
                {facts.map((fact) => (
                  <div key={fact.id} className="rounded-lg bg-muted/50 px-3 py-2.5 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-primary">{fact.predicate}</span>
                      <span className="text-foreground">{formatFactValue(fact)}</span>
                      {fact.unit && <span className="text-muted-foreground">({fact.unit})</span>}
                      {fact.verification_status && (
                        <Badge
                          className={cn(
                            'ml-auto text-[9px]',
                            VERIFICATION_VARIANTS[fact.verification_status] ?? 'bg-muted text-muted-foreground'
                          )}
                        >
                          {fact.verification_status}
                        </Badge>
                      )}
                    </div>
                    <div className="mt-1 flex items-center gap-3 text-[10px] text-muted-foreground">
                      {fact.time_start && (
                        <span className="flex items-center gap-1">
                          <Clock className="size-3" strokeWidth={1.8} />
                          {fact.time_start}
                          {fact.time_end && fact.time_end !== fact.time_start ? ` ~ ${fact.time_end}` : ''}
                        </span>
                      )}
                      {fact.confidence != null && (
                        <span>{Math.round(fact.confidence * 100)}% 置信</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </TabsContent>

          {/* ── 时间线（KOC-D3 Evolution：版本 + 事实 + 事件） ── */}
          <TabsContent value="timeline" className="mt-4">
            {timelineQuery.isLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-10 w-full rounded-lg" />
                ))}
              </div>
            ) : timelineQuery.isError ? (
              <EmptyState icon={Clock} title="无法加载时间线" description="版本/事实/事件查询失败" />
            ) : timelineCount === 0 ? (
              <EmptyState icon={Clock} title="暂无时间线" description="该实体没有版本记录或带时间的事实/事件" />
            ) : (
              <div className="space-y-0">
                {timelineEntries.map((entry, i) => (
                  <div key={entry.key} className="relative flex gap-3 pb-4">
                    {/* 时间轴节点（按类型着色） */}
                    <div className="flex flex-col items-center">
                      <div
                        className={cn(
                          'mt-1 size-2.5 rounded-full border-2',
                          entry.kind === 'version' && 'border-violet-500 bg-violet-500/20',
                          entry.kind === 'fact' && 'border-amber-500 bg-amber-500/20',
                          entry.kind === 'event' && 'border-rose-500 bg-rose-500/20'
                        )}
                      />
                      {i < timelineEntries.length - 1 && (
                        <div className="w-px flex-1 bg-border" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1 rounded-lg bg-muted/50 px-3 py-2 text-xs">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold tabular-nums text-foreground">
                          {entry.ts.slice(0, 10)}
                        </span>
                        <Badge
                          variant="outline"
                          className={cn(
                            'px-1.5 py-0 text-[9px]',
                            entry.kind === 'version' && 'border-violet-500/40 text-violet-600',
                            entry.kind === 'fact' && 'border-amber-500/40 text-amber-600',
                            entry.kind === 'event' && 'border-rose-500/40 text-rose-600'
                          )}
                        >
                          {entry.kind === 'version' ? (
                            <span className="flex items-center gap-1">
                              <GitCommitHorizontal className="size-3" />
                              {entry.badge}
                            </span>
                          ) : entry.kind === 'fact' ? (
                            <span className="flex items-center gap-1">
                              <Zap className="size-3" />
                              {entry.badge}
                            </span>
                          ) : (
                            <span className="flex items-center gap-1">
                              <CalendarDays className="size-3" />
                              {entry.badge}
                            </span>
                          )}
                        </Badge>
                      </div>
                      <p className="mt-1 font-medium text-foreground">{entry.title}</p>
                      {entry.body && <p className="mt-0.5 text-muted-foreground">{entry.body}</p>}
                      <p className="mt-1 text-[10px] text-muted-foreground">{entry.meta}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </TabsContent>

          {/* ── 关联 ── */}
          <TabsContent value="related" className="mt-4">
            {neighborsQuery.isLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-10 w-full rounded-lg" />
                ))}
              </div>
            ) : neighborsQuery.isError ? (
              <EmptyState icon={Network} title="无法加载关联" description="图遍历查询失败" />
            ) : neighbors.length === 0 ? (
              <EmptyState icon={Network} title="暂无关联实体" description="该实体尚未建立图关系" />
            ) : (
              <div className="space-y-2">
                {neighbors.map((n, i) => {
                  const otherName = n.source_name === entity.name ? n.target_name : n.source_name
                  const direction = n.source_name === entity.name ? 'out' : 'in'
                  return (
                    <div
                      key={`${n.source_entity}-${n.target_entity}-${n.relation_type}-${i}`}
                      className="flex items-center gap-2 rounded-lg bg-muted/50 px-3 py-2 text-xs"
                    >
                      <Badge variant="outline" className="text-[9px]">
                        {direction === 'in' ? '入' : '出'}
                      </Badge>
                      <span className="font-medium text-foreground">{otherName ?? '未知实体'}</span>
                      <span className="flex items-center gap-1 text-muted-foreground">
                        <Zap className="size-3" strokeWidth={1.8} />
                        {n.relation_type}
                      </span>
                      {n.depth > 1 && (
                        <Badge variant="secondary" className="ml-auto text-[9px]">
                          depth {n.depth}
                        </Badge>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </TabsContent>
        </Tabs>
      )}
    </WindowedDialog>
  )
}