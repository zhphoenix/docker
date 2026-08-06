import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  TrendingUp,
  Flame,
  Search,
  Loader2,
  Newspaper,
  RefreshCw,
  ArrowLeft,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  fetchKnowledgeInsights,
  type CooccurringTopics,
  type KnowledgeInsightTopic,
} from '@/services/knowledge'
import { fetchNewsArticles, type NewsArticle } from '@/services/news'
import { cn } from '@/lib/utils'

/**
 * NIC-D1 Trend Discovery：展示近 24h 热点词共现增长（如 AI+GPU+Cloud）。
 * 数据源为 KOC-D2 Insights（/api/knowledge/insights），点击趋势卡下钻到相关新闻。
 */
export function TrendTab() {
  const [selected, setSelected] = useState<string | null>(null)

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['news', 'trend', 'insights'],
    queryFn: () => fetchKnowledgeInsights(1, 10),
  })

  const {
    data: drill,
    isLoading: drillLoading,
    isError: drillError,
  } = useQuery({
    queryKey: ['news', 'trend', 'drill', selected],
    queryFn: () => fetchNewsArticles({ keyword: selected ?? '', limit: 20, days: 1 }),
    enabled: !!selected,
  })

  const selectedMeta =
    data?.cooccurring_topics.find((c) => c.topics.join('+') === selected) ??
    data?.hot_topics.find((h) => h.topic === selected)

  return (
    <div className="space-y-4">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TrendingUp className="size-4 text-primary" strokeWidth={1.8} />
          <h2 className="text-sm font-semibold text-foreground">Trend Discovery · 近 24h</h2>
          <span className="text-xs text-muted-foreground">
            数据源：KOC-D2 Knowledge Insights
          </span>
        </div>
        <Button variant="ghost" size="sm" onClick={() => refetch()} disabled={isFetching}>
          {isFetching ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <RefreshCw className="size-3.5" />
          )}
          刷新
        </Button>
      </div>

      {isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      ) : isError ? (
        <EmptyState
          title="加载失败"
          desc="无法获取 Knowledge Insights，请检查 KOC 分析链路是否运行。"
        />
      ) : (
        <>
          {/* 共现组合趋势卡（设计意图：AI+GPU+Cloud 共同增长） */}
          <div>
            <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Flame className="size-3.5 text-orange-500" />
              共现增长组合
            </div>
            {data?.cooccurring_topics?.length ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {data.cooccurring_topics.map((c) => (
                  <TrendCard
                    key={c.topics.join('+')}
                    topics={c.topics}
                    count={c.count}
                    active={selected === c.topics.join('+')}
                    onClick={() => setSelected(c.topics.join('+'))}
                  />
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">暂无共现组合数据（需含多关键词实体名）。</p>
            )}
          </div>

          {/* 热点词 */}
          <div>
            <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Flame className="size-3.5 text-red-500" />
              热点关键词
            </div>
            {data?.hot_topics?.length ? (
              <div className="flex flex-wrap gap-2">
                {data.hot_topics.map((h) => (
                  <button
                    key={h.topic}
                    onClick={() => setSelected(h.topic)}
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors',
                      selected === h.topic
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border bg-muted/40 text-foreground hover:bg-muted'
                    )}
                  >
                    <Search className="size-3" />
                    {h.topic}
                    <span className="text-muted-foreground">{h.count}</span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">暂无热点关键词。</p>
            )}
          </div>

          {/* 下钻：相关新闻 */}
          {selected && (
            <DrillPanel
              topic={selected}
              meta={selectedMeta}
              articles={drill?.articles ?? []}
              loading={drillLoading}
              error={drillError}
              onBack={() => setSelected(null)}
            />
          )}
        </>
      )}
    </div>
  )
}

function TrendCard({
  topics,
  count,
  active,
  onClick,
}: {
  topics: string[]
  count: number
  active: boolean
  onClick: () => void
}) {
  return (
    <button onClick={onClick} className="text-left">
      <Card
        className={cn(
          'h-full cursor-pointer transition-colors hover:border-primary/40',
          active && 'border-primary/60 bg-primary/5'
        )}
      >
        <CardContent className="p-3">
          <div className="flex flex-wrap items-center gap-1 text-sm font-medium text-foreground">
            {topics.map((t, i) => (
              <span key={t} className="inline-flex items-center gap-1">
                {i > 0 && <span className="text-muted-foreground">+</span>}
                <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[11px] text-primary">
                  {t}
                </span>
              </span>
            ))}
          </div>
          <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
            <span>共现 {count} 次</span>
            <span className="inline-flex items-center gap-1 text-primary">
              <Search className="size-3" /> 下钻
            </span>
          </div>
        </CardContent>
      </Card>
    </button>
  )
}

function DrillPanel({
  topic,
  meta,
  articles,
  loading,
  error,
  onBack,
}: {
  topic: string
  meta: CooccurringTopics | KnowledgeInsightTopic | undefined
  articles: NewsArticle[]
  loading: boolean
  error: boolean
  onBack: () => void
}) {
  return (
    <div className="rounded-xl border bg-muted/30 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon-sm" onClick={onBack}>
            <ArrowLeft className="size-3.5" />
          </Button>
          <h3 className="text-sm font-semibold text-foreground">
            相关新闻 · <span className="text-primary">{topic}</span>
          </h3>
          {meta && (
            <Badge variant="secondary" className="text-[11px]">
              共现 {meta.count} 次
            </Badge>
          )}
        </div>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-14 rounded-lg" />
          ))}
        </div>
      ) : error ? (
        <p className="text-xs text-destructive">相关新闻加载失败。</p>
      ) : articles.length === 0 ? (
        <p className="text-xs text-muted-foreground">近 24h 无匹配该关键词的新闻。</p>
      ) : (
        <ul className="space-y-2">
          {articles.map((a) => (
            <li
              key={a.id}
              className="flex items-start justify-between gap-3 rounded-lg border bg-card p-3"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-foreground">{a.title}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {a.source_name ?? '未知来源'} · {a.published_at ?? '—'}
                </p>
              </div>
              {a.url && (
                <a
                  href={a.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex shrink-0 items-center gap-1 text-xs text-primary hover:underline"
                >
                  <Newspaper className="size-3" />
                  原文
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function EmptyState({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed p-8 text-center">
      <TrendingUp className="size-8 text-muted-foreground/50" />
      <p className="text-sm font-medium text-foreground">{title}</p>
      <p className="max-w-sm text-xs text-muted-foreground">{desc}</p>
    </div>
  )
}