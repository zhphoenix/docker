import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Search, RefreshCw, ExternalLink, ChevronLeft, ChevronRight, Radar, CheckCircle2, XCircle } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { fetchNewsArticles, triggerNewsCollect, type NewsArticle } from '@/services/news'
import { ArticleDetailDialog } from './ArticleDetailDialog'
import { cn } from '@/lib/utils'

const CATEGORIES = [
  { value: 'macro', label: '宏观' },
  { value: 'stock', label: '股票' },
  { value: 'company', label: '公司' },
  { value: 'geopolitics', label: '地缘政治' },
  { value: 'policy', label: '政策' },
  { value: 'technology', label: '科技' },
]

const DAYS_OPTIONS = [
  { value: '1', label: '最近 1 天' },
  { value: '7', label: '最近 7 天' },
  { value: '30', label: '最近 30 天' },
  { value: '90', label: '最近 90 天' },
]

const PAGE_SIZE = 15

const CATEGORY_COLORS: Record<string, string> = {
  macro: 'bg-blue-500/15 text-blue-600',
  stock: 'bg-green-500/15 text-green-600',
  company: 'bg-purple-500/15 text-purple-600',
  geopolitics: 'bg-red-500/15 text-red-600',
  policy: 'bg-amber-500/15 text-amber-600',
  technology: 'bg-cyan-500/15 text-cyan-600',
}

export function NewsListTab() {
  const [keyword, setKeyword] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [category, setCategory] = useState('')
  const [days, setDays] = useState('7')
  const [page, setPage] = useState(0)
  const [selectedArticle, setSelectedArticle] = useState<string | null>(null)
  const [collectInput, setCollectInput] = useState('')
  const [collectFeedback, setCollectFeedback] = useState<{ type: 'success' | 'error'; msg: string } | null>(null)

  const queryClient = useQueryClient()

  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: ['news-articles', keyword, category, days, page],
    queryFn: () =>
      fetchNewsArticles({
        keyword,
        category,
        days: Number(days),
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
  })

  const collectMutation = useMutation({
    mutationFn: (kw: string) => triggerNewsCollect(kw),
    onSuccess: (res) => {
      setCollectFeedback({ type: 'success', msg: res.message })
      // 延迟刷新列表，给后台采集一些时间
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['news-articles'] })
      }, 3000)
    },
    onError: (err: Error) => {
      setCollectFeedback({ type: 'error', msg: err.message || '采集触发失败' })
    },
  })

  const handleCollect = () => {
    setCollectFeedback(null)
    collectMutation.mutate(collectInput)
  }

  const articles = data?.articles ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / PAGE_SIZE)

  const handleSearch = () => {
    setKeyword(searchInput)
    setPage(0)
  }

  return (
    <div className="space-y-4">
      {/* Collect trigger */}
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-dashed p-3">
        <Radar className="size-4 shrink-0 text-primary" />
        <div className="relative flex-1 min-w-[200px]">
          <Input
            placeholder="输入采集关键词，如“NVIDIA 财报”..."
            value={collectInput}
            onChange={(e) => setCollectInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCollect()}
          />
        </div>
        <Button
          size="sm"
          onClick={handleCollect}
          disabled={collectMutation.isPending}
          className="gap-1.5"
        >
          {collectMutation.isPending ? (
            <RefreshCw className="size-3.5 animate-spin" />
          ) : (
            <Search className="size-3.5" />
          )}
          搜索
        </Button>
        {collectFeedback && (
          <span
            className={cn(
              'flex items-center gap-1 text-xs',
              collectFeedback.type === 'success' ? 'text-green-600' : 'text-destructive'
            )}
          >
            {collectFeedback.type === 'success' ? (
              <CheckCircle2 className="size-3" />
            ) : (
              <XCircle className="size-3" />
            )}
            {collectFeedback.msg}
          </span>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="搜索新闻关键词..."
            className="pl-9"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          />
        </div>
        <Select
          value={category}
          onValueChange={(v) => { setCategory(v === 'all' ? '' : (v ?? '')); setPage(0) }}
        >
          <SelectTrigger className="w-[130px]">
            <SelectValue placeholder="全部分类" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部分类</SelectItem>
            {CATEGORIES.map((c) => (
              <SelectItem key={c.value} value={c.value}>
                {c.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={days} onValueChange={(v) => { setDays(v ?? ''); setPage(0) }}>
          <SelectTrigger className="w-[130px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DAYS_OPTIONS.map((d) => (
              <SelectItem key={d.value} value={d.value}>
                {d.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={() => refetch()} className="gap-1.5">
          <RefreshCw className={cn('size-3.5', isFetching && 'animate-spin')} />
          刷新
        </Button>
      </div>

      {/* Results count */}
      <div className="text-xs text-muted-foreground">
        共 {total} 条新闻{totalPages > 1 && ` · 第 ${page + 1}/${totalPages} 页`}
      </div>

      {/* Article list */}
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-xl" />
          ))}
        </div>
      ) : isError ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <p className="text-sm text-destructive">查询失败，请检查后端服务</p>
            <p className="mt-1 text-xs text-muted-foreground">
              确认 LangGraph Agent 服务已启动（端口 8100）
            </p>
          </CardContent>
        </Card>
      ) : articles.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <p className="text-sm text-muted-foreground">暂无新闻数据</p>
            <p className="mt-1 text-xs text-muted-foreground">
              请确认 News Pipeline 已运行并采集数据
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {articles.map((article) => (
            <ArticleCard
              key={article.id}
              article={article}
              onClick={() => setSelectedArticle(article.id)}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
          >
            <ChevronLeft className="size-4" />
          </Button>
          <span className="text-sm text-muted-foreground">
            {page + 1} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => p + 1)}
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      )}

      {/* Article Detail Dialog */}
      <ArticleDetailDialog
        articleId={selectedArticle}
        onClose={() => setSelectedArticle(null)}
      />
    </div>
  )
}

function ArticleCard({
  article,
  onClick,
}: {
  article: NewsArticle
  onClick: () => void
}) {
  return (
    <Card
      className="cursor-pointer transition-shadow duration-200 hover:shadow-[var(--shadow-soft)]"
      onClick={onClick}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-sm font-medium text-foreground">
              {article.title}
            </h3>
            {article.summary && (
              <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                {article.summary}
              </p>
            )}
          </div>
          {article.url && (
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="shrink-0 text-muted-foreground hover:text-foreground"
            >
              <ExternalLink className="size-3.5" />
            </a>
          )}
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          {article.category && (
            <Badge
              variant="secondary"
              className={cn('text-[10px]', CATEGORY_COLORS[article.category])}
            >
              {CATEGORIES.find((c) => c.value === article.category)?.label ??
                article.category}
            </Badge>
          )}
          {article.importance && (
            <Badge variant="outline" className="text-[10px]">
              重要度: {article.importance}
            </Badge>
          )}
          {article.source_name && (
            <span className="text-[10px] text-muted-foreground">
              {article.source_name}
            </span>
          )}
          {article.published_at && (
            <span className="ml-auto text-[10px] text-muted-foreground">
              {new Date(article.published_at).toLocaleDateString('zh-CN', {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
