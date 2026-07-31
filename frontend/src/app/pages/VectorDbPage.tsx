import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Database, RefreshCw, Layers, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchVectorCollections } from '@/services/vector'
import { cn } from '@/lib/utils'

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06 } },
}

const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3 } },
}

function formatNumber(n: number | undefined): string {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN')
}

export default function VectorDbPage() {
  const vectorQuery = useQuery({
    queryKey: ['vector-collections'],
    queryFn: fetchVectorCollections,
    retry: 1,
  })

  const collections = vectorQuery.data?.collections ?? []
  const qdrantError = vectorQuery.data?.error ?? null
  // API 本身不可达（fetch 失败）
  const apiUnreachable = vectorQuery.isError

  return (
    <div className="mx-auto max-w-5xl space-y-8 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">向量数据库</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Qdrant 向量存储运行状态
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="gap-2"
          onClick={() => vectorQuery.refetch()}
        >
          <RefreshCw className={cn('size-3.5', vectorQuery.isFetching && 'animate-spin')} />
          刷新
        </Button>
      </div>

      {/* Connection Status Banner */}
      {!vectorQuery.isLoading && (
        <Card>
          <CardContent className="flex items-center gap-4 p-5">
            <div
              className={cn(
                'flex size-10 items-center justify-center rounded-xl',
                apiUnreachable || qdrantError ? 'bg-warning/10' : 'bg-success/10'
              )}
            >
              {apiUnreachable || qdrantError ? (
                <AlertTriangle className="size-5 text-warning" strokeWidth={1.8} />
              ) : (
                <CheckCircle2 className="size-5 text-success" strokeWidth={1.8} />
              )}
            </div>
            <div>
              <div className="text-sm font-semibold text-foreground">
                {apiUnreachable
                  ? '后端 API 不可达'
                  : qdrantError
                    ? 'Qdrant 连接异常'
                    : 'Qdrant 连接正常'}
              </div>
              <div className="text-xs text-muted-foreground">
                {apiUnreachable
                  ? '无法连接到后端服务，请确认 LangGraph 服务已启动（端口 8100）'
                  : qdrantError || '向量检索引擎运行中，端口 6333'}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Collections */}
      {vectorQuery.isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardContent className="p-5">
                <Skeleton className="h-10 w-10 rounded-xl" />
                <Skeleton className="mt-4 h-4 w-32" />
                <Skeleton className="mt-2 h-3 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : apiUnreachable ? (
        <EmptyState
          icon={Database}
          title="无法加载向量数据库状态"
          description="无法连接到后端服务，请确认 LangGraph 服务已启动（端口 8100）"
          action={{ label: '重试', onClick: () => vectorQuery.refetch() }}
        />
      ) : qdrantError ? (
        <EmptyState
          icon={Database}
          title="Qdrant 不可用"
          description="无法连接到 Qdrant 服务，请确认其已启动（端口 6333）"
          action={{ label: '重试', onClick: () => vectorQuery.refetch() }}
        />
      ) : collections.length === 0 ? (
        <EmptyState
          icon={Database}
          title="暂无 Collection"
          description="Qdrant 中尚未创建任何向量集合"
        />
      ) : (
        <motion.div
          variants={container}
          initial="hidden"
          animate="show"
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          {collections.map((coll) => (
            <motion.div key={coll.name} variants={item}>
              <Card className="h-full transition-shadow duration-200 hover:shadow-[var(--shadow-soft)]">
                <CardContent className="p-5">
                  <div className="flex items-start justify-between">
                    <div className="flex size-10 items-center justify-center rounded-xl bg-primary/10">
                      <Database className="size-5 text-primary" strokeWidth={1.8} />
                    </div>
                    <Badge
                      variant={coll.status === 'green' ? 'default' : 'secondary'}
                      className={cn(
                        'text-[10px]',
                        coll.status === 'green' && 'bg-success/15 text-success hover:bg-success/15'
                      )}
                    >
                      {coll.status}
                    </Badge>
                  </div>

                  <div className="mt-4">
                    <div className="text-sm font-semibold text-foreground">{coll.name}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {coll.vector_size != null ? `${coll.vector_size} 维` : '—'} ·{' '}
                      {coll.distance ?? '—'}
                    </div>
                  </div>

                  <div className="mt-4 space-y-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="flex items-center gap-1.5 text-muted-foreground">
                        <Layers className="size-3" strokeWidth={1.8} />
                        Points
                      </span>
                      <span className="tabular-nums font-medium text-foreground">
                        {formatNumber(coll.points_count)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">Vectors</span>
                      <span className="tabular-nums text-foreground">
                        {formatNumber(coll.vectors_count)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">Indexed</span>
                      <span className="tabular-nums text-foreground">
                        {formatNumber(coll.indexed_vectors_count)}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      )}

      <p className="text-center text-xs text-muted-foreground">
        数据来源：Qdrant REST API 实时统计 · 向量维度与距离度量由 Collection 配置决定
      </p>
    </div>
  )
}
