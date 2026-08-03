import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Search, Sparkles, GitFork, FileText, BrainCircuit } from 'lucide-react'
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
  const hasResults =
    (isHybrid &&
      !!hybridResult &&
      (hybridResult.vector_results.entities.length > 0 ||
        hybridResult.vector_results.facts.length > 0 ||
        hybridResult.graph_results.length > 0)) ||
    (isGraphRAG && !!ragResult && !!ragResult.fusion?.summary)

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
              placeholder={isGraphRAG ? '输入查询，生成基于知识图谱的归纳回答...' : '输入自然语言查询，如：华为的供应链关系...'}
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
            <h3 className="text-sm font-semibold text-foreground">语义搜索</h3>
            <p className="mt-1 max-w-sm text-xs text-muted-foreground">
              基于 Embedding + Qdrant 向量检索 + 知识图谱的混合搜索，支持实体、事实和关系的多路召回
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

      {/* 混合检索结果 */}
      {searchMutation.isSuccess && isHybrid && hybridResult && hasResults && (
        <motion.div variants={listVariants} initial="hidden" animate="show" className="space-y-6">
          {/* Entity Results */}
          {hybridResult.vector_results.entities.length > 0 && (
            <div className="space-y-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <Sparkles className="size-4 text-primary" strokeWidth={1.8} />
                实体匹配
                <Badge variant="secondary" className="text-[10px]">
                  {hybridResult.vector_results.entities.length}
                </Badge>
              </h3>
              <div className="grid gap-3 sm:grid-cols-2">
                {hybridResult.vector_results.entities.map((ent) => (
                  <motion.div key={ent.id} variants={listItem}>
                    <Card className="transition-shadow duration-200 hover:shadow-[var(--shadow-soft)]">
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between">
                          <div className="text-sm font-medium text-foreground">
                            {String(ent.payload.name || ent.id)}
                          </div>
                          <Badge variant="outline" className="text-[10px] tabular-nums">
                            {Math.round(ent.score * 100)}%
                          </Badge>
                        </div>
                        {ent.payload.entity_type ? (
                          <Badge variant="secondary" className="mt-1.5 text-[10px]">
                            {String(ent.payload.entity_type)}
                          </Badge>
                        ) : null}
                        {ent.payload.description ? (
                          <p className="mt-2 line-clamp-2 text-xs text-muted-foreground">
                            {String(ent.payload.description)}
                          </p>
                        ) : null}
                      </CardContent>
                    </Card>
                  </motion.div>
                ))}
              </div>
            </div>
          )}

          {/* Fact Results */}
          {hybridResult.vector_results.facts.length > 0 && (
            <div className="space-y-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <FileText className="size-4 text-primary" strokeWidth={1.8} />
                事实匹配
                <Badge variant="secondary" className="text-[10px]">
                  {hybridResult.vector_results.facts.length}
                </Badge>
              </h3>
              <div className="space-y-2">
                {hybridResult.vector_results.facts.map((fact) => (
                  <motion.div key={fact.id} variants={listItem}>
                    <Card>
                      <CardContent className="flex items-center gap-3 p-3.5">
                        <div className="flex-1 text-xs text-foreground">
                          <span className="font-medium">{String(fact.payload.subject_name || '')}</span>
                          <span className="mx-1.5 text-muted-foreground">→</span>
                          <span className="text-primary">{String(fact.payload.predicate || '')}</span>
                          <span className="mx-1.5 text-muted-foreground">:</span>
                          <span>{String(fact.payload.object_value || '')}</span>
                        </div>
                        <Badge variant="outline" className="shrink-0 text-[10px] tabular-nums">
                          {Math.round(fact.score * 100)}%
                        </Badge>
                      </CardContent>
                    </Card>
                  </motion.div>
                ))}
              </div>
            </div>
          )}

          {/* Graph Results */}
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
                    <span className="font-medium text-foreground">{edge.source_entity.slice(0, 8)}</span>
                    <Badge variant="outline" className="text-[10px]">{edge.relation_type}</Badge>
                    <span className="text-muted-foreground">→</span>
                    <span className="font-medium text-foreground">{edge.target_entity.slice(0, 8)}</span>
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
