import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { BookOpen, Database, Layers, RefreshCw } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Progress } from '@/components/ui/progress'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchKnowledgeCollections } from '@/services/knowledge'
import { cn } from '@/lib/utils'

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06 } },
}

const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3 } },
}

function formatNumber(n: number): string {
  return n.toLocaleString('zh-CN')
}

export function CollectionGrid() {
  const collectionsQuery = useQuery({
    queryKey: ['knowledge-collections'],
    queryFn: fetchKnowledgeCollections,
    retry: 1,
  })

  const collections = collectionsQuery.data?.collections ?? []

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex justify-end">
        <Button
          variant="outline"
          size="sm"
          className="gap-2"
          onClick={() => collectionsQuery.refetch()}
        >
          <RefreshCw className={cn('size-3.5', collectionsQuery.isFetching && 'animate-spin')} />
          刷新
        </Button>
      </div>

      {/* States */}
      {collectionsQuery.isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardContent className="p-5">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="mt-2 h-3 w-full" />
                <Skeleton className="mt-4 h-2 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : collectionsQuery.isError ? (
        <EmptyState
          icon={BookOpen}
          title="无法加载知识库"
          description="无法连接到后端服务，请确认 LangGraph 服务已启动（端口 8100）"
          action={{ label: '重试', onClick: () => collectionsQuery.refetch() }}
        />
      ) : collections.length === 0 ? (
        <EmptyState
          icon={BookOpen}
          title="暂无知识集合"
          description="尚未创建任何知识库 Collection"
        />
      ) : (
        <motion.div
          variants={container}
          initial="hidden"
          animate="show"
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          {collections.map((coll) => {
            const pct =
              coll.chunk_count > 0
                ? Math.round((coll.embedded_count / coll.chunk_count) * 100)
                : 0
            return (
              <motion.div key={coll.id} variants={item}>
                <Card className="h-full transition-shadow duration-200 hover:shadow-[var(--shadow-soft)]">
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between">
                      <div className="flex size-10 items-center justify-center rounded-xl bg-primary/10">
                        <Database className="size-5 text-primary" strokeWidth={1.8} />
                      </div>
                      {coll.domain && (
                        <Badge variant="secondary" className="text-[10px]">
                          {coll.domain}
                        </Badge>
                      )}
                    </div>

                    <div className="mt-4">
                      <div className="text-sm font-semibold text-foreground">{coll.name}</div>
                      {coll.description && (
                        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                          {coll.description}
                        </p>
                      )}
                    </div>

                    {/* 向量化进度 */}
                    <div className="mt-4 space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">向量化进度</span>
                        <span className="tabular-nums text-foreground">
                          {formatNumber(coll.embedded_count)}/{formatNumber(coll.chunk_count)}
                        </span>
                      </div>
                      <Progress value={pct} />
                    </div>

                    {/* 元数据 */}
                    <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Layers className="size-3" strokeWidth={1.8} />
                        {coll.vector_size} 维
                      </span>
                      <span>{coll.distance ?? '—'}</span>
                      <span>
                        Qdrant:{' '}
                        {coll.qdrant_points != null ? formatNumber(coll.qdrant_points) : '—'}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )
          })}
        </motion.div>
      )}
    </div>
  )
}
