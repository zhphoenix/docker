import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  Search,
  Sparkles,
  GitFork,
  FileText,
  BrainCircuit,
  CalendarDays,
  FileArchive,
  Layers,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import {
  searchKnowledge,
  graphragSearch,
  type HybridSearchResult,
  type GraphRAGResult,
} from '@/services/knowledge'
import { cn } from '@/lib/utils'

type SearchMode = 'hybrid' | 'graphrag'

const CHANNEL_META: Record<string, { label: string; className: string }> = {
  vector: { label: '向量', className: 'bg-blue-500/10 text-blue-600' },
  fulltext: { label: '全文', className: 'bg-emerald-500/10 text-emerald-600' },
  graph: { label: '图谱', className: 'bg-purple-500/10 text-purple-600' },
}

function ChannelBadges({ channels }: { channels?: string[] }) {
  if (!channels || channels.length === 0) return null
  return (
    <span className="flex shrink-0 gap-1">
      {channels.map((c) => (
        <Badge key={c} className={cn('text-[9px]', CHANNEL_META[c]?.className ?? 'bg-muted text-muted-foreground')}>
          {CHANNEL_META[c]?.label ?? c}
        </Badge>
      ))}
    </span>
  )
}

function ScoreBadge({ score }: { score?: number | null }) {
  if (score == null) return null
  return (
    <Badge variant="outline" className="shrink-0 text-[10px] tabular-nums">
      {Math.round(score * 100)}%
    </Badge>
  )
}

const listVariants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.04 } },
}

const listItem = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.25 } },
}

export function SemanticSearchPanel() {
  const [query, setQuery] = useState('')
  const [entityFilter, setEntityFilter] = useState('')
  const [mode, setMode] = useState<SearchMode>('hybrid')

  const searchMutation = useMutation<
    HybridSearchResult | GraphRAGResult,
    Error,
    { query: string; entity_name?: string; limit?: number }
  >({
    mutationFn: (params) =>
      mode === 'graphrag' ? graphragSearch(params) : searchKnowledge(params),
  })

  const handleSearch = () => {
    const trimmed = query.trim()
    if (!trimmed) return
    searchMutation.mutate({
      query: trimmed,
      entity_name: entityFilter.trim() || undefined,
      limit: 10,
    })
  }

  const handleModeChange = (m: SearchMode) => {
    setMode(m)
    searchMutation.reset()
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSearch()
  }

  const result = searchMutation.data
  const isGraphRAG = mode === 'graphrag'
  const isHybrid = !isGraphRAG
  const hybridResult = isHybrid ? (result as HybridSearchResult | undefined) : undefined
  const ragResult = isGraphRAG ? (result as GraphRAGResult | undefined) : undefined

  // 统一结果（KOC-C2）：优先 results 字段，兼容旧结构
  const unified = hybridResult?.results
  const channels = hybridResult?.source_channels
  const hasUnifiedData = unified
    ? unified.entities.length > 0 ||
      unified.facts.length > 0 ||
      unified.events.length > 0 ||
      unified.documents.length > 0
    : false
  const hasLegacyData =
    !!hybridResult &&
    (hybridResult.vector_results.entities.length > 0 ||
      hybridResult.vector_results.facts.length > 0 ||
      hybridResult.graph_results.length > 0)
  const hasResults =
    (isHybrid && (hasUnifiedData || hasLegacyData)) ||
    (isGraphRAG && !!ragResult && !!ragResult.fusion?.summary)

  const channelChips = channels
    ? (Object.entries(channels) as Array<[keyof typeof channels, boolean]>)
        .filter(([, active]) => active)
    : []

  return (
    <div className="space-y-6">
      {/* 检索模式切换 + Search Input */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">检索模式</span>
          <div className="flex rounded-lg border bg-muted/40 p-0.5">
            <button
              type="button"
              onClick={() => handleModeChange('hybrid')}
              className={cn(
                'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                mode === 'hybrid' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground'
              )}
            >
              <Search className="size-3.5" strokeWidth={1.8} />
              混合检索
            </button>
            <button
              type="button"
              onClick={() => handleModeChange('graphrag')}
              className={cn(
                'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                mode === 'graphrag' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground'
              )}
            >
              <BrainCircuit className="size-3.5" strokeWidth={1.8} />
              GraphRAG
            </button>
          </div>
          {isGraphRAG && (
            <Badge variant="secondary" className="text-[10px]">
              LLM 融合生成
            </Badge>
          )}
        </div>
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" strokeWidth={1.8} />
            <Input
              placeholder={isGraphRAG ? '输入查询，生成基于知识图谱的归纳回答...' : '输入自然语言查询，如：腾讯的供应链关系...'}
              className="pl-9"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
            />
          </div>
          <Input
            placeholder="实体过滤（可选）"
            className="w-40"
            value={entityFilter}
            onChange={(e) => setEntityFilter(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <Button onClick={handleSearch} disabled={!query.trim() || searchMutation.isPending}>
            {searchMutation.isPending ? '搜索中...' : '搜索'}
          </Button>
        </div>
      </div>

      {/* Idle State */}
      {searchMutation.isIdle && (
        <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
          <div className="flex size-14 items-center justify-center rounded-2xl bg-primary/10">
            <Sparkles className="size-7 text-primary" strokeWidth={1.5} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">统一搜索入口</h3>
            <p className="mt-1 max-w-sm text-xs text-muted-foreground">
              向量 + 全文 + 图谱三通道混合检索，一次查询返回实体、事实、事件与文档，并标注来源通道
            </p>
          </div>
        </div>
      )}

      {/* Loading State */}
      {searchMutation.isPending && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardContent className="flex items-center gap-4 p-4">
                <Skeleton className="size-10 rounded-xl" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="h-3 w-full" />
                </div>
                <Skeleton className="h-5 w-16" />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Error State */}
      {searchMutation.isError && (
        <EmptyState
          icon={Search}
          title="搜索失败"
          description={searchMutation.error?.message || '无法连接到知识服务，请稍后重试'}
          action={{ label: '重试', onClick: handleSearch }}
        />
      )}

      {/* Success State */}
      {searchMutation.isSuccess && !hasResults && (
        <EmptyState
          icon={Search}
          title="未找到匹配结果"
          description={`未找到与「${result?.query}」相关的知识，尝试更换关键词或移除实体过滤`}
        />
      )}

      {/* GraphRAG 结果（归纳回答 + 证据） */}
      {searchMutation.isSuccess && isGraphRAG && ragResult && hasResults && (
        <motion.div variants={listVariants} initial="hidden" animate="show" className="space-y-6">
          <Card className="border-primary/20 bg-primary/5">
            <CardContent className="p-5">
              <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <BrainCircuit className="size-4 text-primary" strokeWidth={1.8} />
                归纳回答
                {ragResult.degraded && (
                  <Badge variant="outline" className="text-[10px]">
                    降级模式
                  </Badge>
                )}
              </div>
              <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                {ragResult.fusion?.summary}
              </p>
              {ragResult.fusion?.key_findings?.length > 0 && (
                <div className="mt-4 space-y-2">
                  {ragResult.fusion.key_findings.map((f, i) => (
                    <div key={i} className="rounded-lg bg-muted/50 px-3 py-2 text-xs">
                      <span className="font-medium text-foreground">要点 {i + 1}：</span>
                      <span className="text-muted-foreground">{f.finding}</span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* 证据 */}
          {(ragResult.evidence?.graph?.length > 0 || ragResult.evidence?.vector?.length > 0) && (
            <div className="space-y-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <GitFork className="size-4 text-primary" strokeWidth={1.8} />
                检索证据
                <Badge variant="secondary" className="text-[10px]">
                  {(ragResult.evidence?.graph?.length ?? 0) + (ragResult.evidence?.vector?.length ?? 0)}
                </Badge>
              </h3>
              <div className="space-y-1.5">
                {[...(ragResult.evidence?.graph ?? []), ...(ragResult.evidence?.vector ?? [])].map(
                  (ev, i) => (
                    <motion.div
                      key={i}
                      variants={listItem}
                      className="flex items-start gap-2 rounded-lg bg-muted/50 px-3 py-2 text-xs"
                    >
                      <Badge variant="outline" className="shrink-0 text-[10px]">
                        {ev.kind === 'graph' ? '图谱' : '向量'}
                      </Badge>
                      <div className="min-w-0 flex-1 text-muted-foreground">
                        {ev.name || ev.subject || ev.source_entity || ''}
                        {ev.predicate || ev.relation_type ? (
                          <span className="text-primary">
                            {' '}
                            → {ev.predicate || ev.relation_type}
                          </span>
                        ) : null}
                        {ev.value || ev.target_entity ? ` : ${ev.value || ev.target_entity}` : ''}
                        {ev.description ? ` — ${ev.description}` : ''}
                      </div>
                    </motion.div>
                  )
                )}
              </div>
            </div>
          )}
        </motion.div>
      )}

      {/* 混合检索结果（统一入口） */}
      {searchMutation.isSuccess && isHybrid && hybridResult && hasResults && (
        <motion.div variants={listVariants} initial="hidden" animate="show" className="space-y-6">
          {/* 来源通道汇总 */}
          {channelChips.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <Layers className="size-3.5" strokeWidth={1.8} />
                命中通道
              </span>
              {channelChips.map(([key]) => (
                <Badge
                  key={key}
                  className={cn('text-[10px]', CHANNEL_META[key]?.className ?? 'bg-muted')}
                >
                  {CHANNEL_META[key]?.label ?? key}
                </Badge>
              ))}
            </div>
          )}

          {/* Entity Results（统一） */}
          {(unified?.entities.length ?? 0) > 0 && (
            <div className="space-y-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <Sparkles className="size-4 text-primary" strokeWidth={1.8} />
                实体匹配
                <Badge variant="secondary" className="text-[10px]">
                  {unified!.entities.length}
                </Badge>
              </h3>
              <div className="grid gap-3 sm:grid-cols-2">
                {unified!.entities.map((ent) => (
                  <motion.div key={ent.id} variants={listItem}>
                    <Card className="transition-shadow duration-200 hover:shadow-[var(--shadow-soft)]">
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0 text-sm font-medium text-foreground">
                            {ent.name || ent.id}
                          </div>
                          <div className="flex shrink-0 items-center gap-1.5">
                            <ScoreBadge score={ent.score} />
                            <ChannelBadges channels={ent.source_channels} />
                          </div>
                        </div>
                        {ent.entity_type ? (
                          <Badge variant="secondary" className="mt-1.5 text-[10px]">
                            {ent.entity_type}
                          </Badge>
                        ) : null}
                        {ent.description ? (
                          <p className="mt-2 line-clamp-2 text-xs text-muted-foreground">
                            {ent.description}
                          </p>
                        ) : null}
                      </CardContent>
                    </Card>
                  </motion.div>
                ))}
              </div>
            </div>
          )}

          {/* Fact Results（统一） */}
          {(unified?.facts.length ?? 0) > 0 && (
            <div className="space-y-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <FileText className="size-4 text-primary" strokeWidth={1.8} />
                事实匹配
                <Badge variant="secondary" className="text-[10px]">
                  {unified!.facts.length}
                </Badge>
              </h3>
              <div className="space-y-2">
                {unified!.facts.map((fact) => (
                  <motion.div key={fact.id} variants={listItem}>
                    <Card>
                      <CardContent className="flex items-center gap-3 p-3.5">
                        <div className="flex-1 text-xs text-foreground">
                          <span className="font-medium">{fact.subject_name || ''}</span>
                          <span className="mx-1.5 text-muted-foreground">→</span>
                          <span className="text-primary">{fact.predicate || ''}</span>
                          <span className="mx-1.5 text-muted-foreground">:</span>
                          <span>{fact.object_value || ''}</span>
                          {fact.time_start && (
                            <span className="ml-2 text-[10px] text-muted-foreground">
                              @ {fact.time_start}
                            </span>
                          )}
                        </div>
                        <div className="flex shrink-0 items-center gap-1.5">
                          <ScoreBadge score={fact.score} />
                          <ChannelBadges channels={fact.source_channels} />
                        </div>
                      </CardContent>
                    </Card>
                  </motion.div>
                ))}
              </div>
            </div>
          )}

          {/* Event Results（KOC-C2 新增） */}
          {(unified?.events.length ?? 0) > 0 && (
            <div className="space-y-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <CalendarDays className="size-4 text-primary" strokeWidth={1.8} />
                事件匹配
                <Badge variant="secondary" className="text-[10px]">
                  {unified!.events.length}
                </Badge>
              </h3>
              <div className="space-y-2">
                {unified!.events.map((ev) => (
                  <motion.div
                    key={ev.id}
                    variants={listItem}
                    className="flex items-center gap-3 rounded-lg bg-muted/50 px-3 py-2 text-xs"
                  >
                    <div className="min-w-0 flex-1">
                      <span className="font-medium text-foreground">{ev.title}</span>
                      {ev.event_type && (
                        <Badge variant="outline" className="ml-2 text-[9px]">
                          {ev.event_type}
                        </Badge>
                      )}
                      {ev.description && (
                        <p className="mt-0.5 line-clamp-1 text-muted-foreground">{ev.description}</p>
                      )}
                    </div>
                    {ev.event_date && (
                      <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground">
                        {ev.event_date}
                      </span>
                    )}
                    <ChannelBadges channels={ev.source_channels} />
                  </motion.div>
                ))}
              </div>
            </div>
          )}

          {/* Document Results（KOC-C2 新增） */}
          {(unified?.documents.length ?? 0) > 0 && (
            <div className="space-y-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <FileArchive className="size-4 text-primary" strokeWidth={1.8} />
                文档匹配
                <Badge variant="secondary" className="text-[10px]">
                  {unified!.documents.length}
                </Badge>
              </h3>
              <div className="space-y-2">
                {unified!.documents.map((doc) => (
                  <motion.div
                    key={doc.id}
                    variants={listItem}
                    className="flex items-center gap-3 rounded-lg bg-muted/50 px-3 py-2 text-xs"
                  >
                    <div className="min-w-0 flex-1">
                      <span className="font-medium text-foreground">{doc.title}</span>
                      {doc.document_type && (
                        <Badge variant="outline" className="ml-2 text-[9px]">
                          {doc.document_type}
                        </Badge>
                      )}
                    </div>
                    {doc.source && (
                      <span className="shrink-0 text-[10px] text-muted-foreground">{doc.source}</span>
                    )}
                    <ChannelBadges channels={doc.source_channels} />
                  </motion.div>
                ))}
              </div>
            </div>
          )}

          {/* Graph Results（兼容保留） */}
          {hybridResult.graph_results.length > 0 && (
            <div className="space-y-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <GitFork className="size-4 text-primary" strokeWidth={1.8} />
                关联关系
                <Badge variant="secondary" className="text-[10px]">
                  {hybridResult.graph_results.length}
                </Badge>
              </h3>
              <div className="space-y-1.5">
                {hybridResult.graph_results.slice(0, 15).map((edge, i) => (
                  <motion.div
                    key={`${edge.source_entity}-${edge.relation_type}-${edge.target_entity}-${i}`}
                    variants={listItem}
                    className="flex items-center gap-2 rounded-lg bg-muted/50 px-3 py-2 text-xs"
                  >
                    <span className="font-medium text-foreground">
                      {edge.source_name ?? edge.source_entity.slice(0, 8)}
                    </span>
                    <Badge variant="outline" className="text-[10px]">{edge.relation_type}</Badge>
                    <span className="text-muted-foreground">→</span>
                    <span className="font-medium text-foreground">
                      {edge.target_name ?? edge.target_entity.slice(0, 8)}
                    </span>
                    <ChannelBadges channels={['graph']} />
                    {edge.depth > 1 && (
                      <span className="ml-auto text-[10px] text-muted-foreground">depth {edge.depth}</span>
                    )}
                  </motion.div>
                ))}
              </div>
            </div>
          )}
        </motion.div>
      )}
    </div>
  )
}