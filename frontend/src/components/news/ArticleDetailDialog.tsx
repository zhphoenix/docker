import { useQuery } from '@tanstack/react-query'
import { ExternalLink } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { fetchNewsArticle } from '@/services/news'
import { cn } from '@/lib/utils'

const IMPACT_COLORS: Record<string, string> = {
  positive: 'bg-green-500/15 text-green-600',
  negative: 'bg-red-500/15 text-red-600',
  neutral: 'bg-gray-500/15 text-gray-600',
}

interface Props {
  articleId: string | null
  onClose: () => void
}

export function ArticleDetailDialog({ articleId, onClose }: Props) {
  const { data: article, isLoading } = useQuery({
    queryKey: ['news-article', articleId],
    queryFn: () => fetchNewsArticle(articleId!),
    enabled: !!articleId,
  })

  return (
    <Dialog open={!!articleId} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="pr-8 text-base leading-snug">
            {isLoading ? (
              <Skeleton className="h-5 w-3/4" />
            ) : (
              article?.title
            )}
          </DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        ) : article ? (
          <div className="space-y-5">
            {/* Meta */}
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              {article.category && (
                <Badge variant="secondary">{article.category}</Badge>
              )}
              {article.source_name && <span>{article.source_name}</span>}
              {article.published_at && (
                <span>
                  {new Date(article.published_at).toLocaleString('zh-CN')}
                </span>
              )}
              {article.url && (
                <a
                  href={article.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-primary hover:underline"
                >
                  原文 <ExternalLink className="size-3" />
                </a>
              )}
            </div>

            {/* Summary */}
            {article.summary && (
              <div className="rounded-lg bg-muted/50 p-3">
                <p className="text-sm text-foreground">{article.summary}</p>
              </div>
            )}

            {/* Content */}
            {article.content && (
              <div className="prose prose-sm max-w-none text-foreground">
                <p className="whitespace-pre-wrap text-sm leading-relaxed">
                  {article.content}
                </p>
              </div>
            )}

            {/* Entities */}
            {article.entities && article.entities.length > 0 && (
              <div>
                <h4 className="mb-2 text-xs font-semibold text-muted-foreground">
                  关联实体
                </h4>
                <div className="flex flex-wrap gap-2">
                  {article.entities.map((entity) => (
                    <Badge key={entity.id} variant="outline" className="text-xs">
                      {entity.name}
                      <span className="ml-1 text-muted-foreground">
                        ({entity.entity_type})
                      </span>
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Events */}
            {article.events && article.events.length > 0 && (
              <div>
                <h4 className="mb-2 text-xs font-semibold text-muted-foreground">
                  关联事件
                </h4>
                <div className="space-y-2">
                  {article.events.map((event) => (
                    <div
                      key={event.id}
                      className="flex items-center gap-2 rounded-lg border p-2.5"
                    >
                      <Badge variant="outline" className="shrink-0 text-[10px]">
                        {event.event_type}
                      </Badge>
                      <span className="min-w-0 flex-1 truncate text-xs">
                        {event.title}
                      </span>
                      {event.impact_direction && (
                        <Badge
                          variant="secondary"
                          className={cn(
                            'shrink-0 text-[10px]',
                            IMPACT_COLORS[event.impact_direction]
                          )}
                        >
                          {event.impact_direction}
                          {event.impact_score != null &&
                            ` (${event.impact_score})`}
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
