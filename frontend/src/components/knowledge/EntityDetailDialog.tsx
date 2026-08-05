import { useQuery } from '@tanstack/react-query'
import { FileText, Tag, Clock } from 'lucide-react'
import { WindowedDialog } from '@/components/ui/windowed-dialog'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Separator } from '@/components/ui/separator'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchFacts, type KnowledgeEntity } from '@/services/knowledge'

interface EntityDetailDialogProps {
  entity: KnowledgeEntity | null
  onClose: () => void
}

export function EntityDetailDialog({ entity, onClose }: EntityDetailDialogProps) {
  const factsQuery = useQuery({
    queryKey: ['knowledge-facts', entity?.id],
    queryFn: () => fetchFacts(entity!.id),
    enabled: !!entity,
    retry: 1,
  })

  const facts = factsQuery.data?.facts ?? []

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
      defaultWidth={480}
      defaultHeight={480}
    >
      {entity && (
        <>

            {/* Metadata */}
            <div className="space-y-3 text-sm">
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
            </div>

            <Separator />

            {/* Facts */}
            <div className="space-y-3">
              <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <FileText className="size-4 text-primary" strokeWidth={1.8} />
                关联事实
              </h4>

              {factsQuery.isLoading ? (
                <div className="space-y-2">
                  {[1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-10 w-full rounded-lg" />
                  ))}
                </div>
              ) : factsQuery.isError ? (
                <EmptyState
                  icon={FileText}
                  title="无法加载事实"
                  description="查询关联事实失败"
                />
              ) : facts.length === 0 ? (
                <p className="py-4 text-center text-xs text-muted-foreground">
                  暂无关联事实
                </p>
              ) : (
                <div className="space-y-2">
                  {facts.map((fact) => (
                    <div
                      key={fact.id}
                      className="rounded-lg bg-muted/50 px-3 py-2.5 text-xs"
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-primary">{fact.predicate}</span>
                        <span className="text-foreground">
                          {typeof fact.object_value === 'object'
                            ? JSON.stringify(fact.object_value)
                            : String(fact.object_value ?? '')}
                        </span>
                        {fact.unit && (
                          <span className="text-muted-foreground">({fact.unit})</span>
                        )}
                      </div>
                      <div className="mt-1 flex items-center gap-3 text-[10px] text-muted-foreground">
                        {fact.time_start && (
                          <span className="flex items-center gap-1">
                            <Clock className="size-3" strokeWidth={1.8} />
                            {fact.time_start}
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
            </div>
          </>
        )}
    </WindowedDialog>
  )
}
