import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { BookOpen, Database, Layers, RefreshCw, FolderInput, CheckCircle2, XCircle, Folder, ChevronRight, ArrowUp, Loader2, Loader } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Progress } from '@/components/ui/progress'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchKnowledgeCollections, triggerIngest, fetchBrowseDirs } from '@/services/knowledge'
import { fetchTasks } from '@/services/tasks'
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

interface CollectionGridProps {
  onNavigateToTasks?: (taskId?: string) => void
}

export function CollectionGrid({ onNavigateToTasks }: CollectionGridProps) {
  const [ingestPath, setIngestPath] = useState('')
  const [ingestFeedback, setIngestFeedback] = useState<{ type: 'success' | 'error'; msg: string } | null>(null)
  const [dirDialogOpen, setDirDialogOpen] = useState(false)
  const [browsePath, setBrowsePath] = useState('/data/minio/documents')
  const queryClient = useQueryClient()

  const collectionsQuery = useQuery({
    queryKey: ['knowledge-collections'],
    queryFn: fetchKnowledgeCollections,
    retry: 1,
  })

  // 查询当前 running 的 doc_pipeline 任务，用于在卡片上展示实时进度
  const runningTasksQuery = useQuery({
    queryKey: ['ingest-running-tasks'],
    queryFn: () =>
      fetchTasks({ status: 'running', task_type: 'doc_pipeline', limit: 10 }),
    refetchInterval: 5000,
    retry: 1,
  })
  const runningTasks = runningTasksQuery.data?.tasks ?? []

  const browseQuery = useQuery({
    queryKey: ['browse-dirs', browsePath],
    queryFn: () => fetchBrowseDirs(browsePath),
    enabled: dirDialogOpen,
  })

  const ingestMutation = useMutation({
    mutationFn: (path: string) => triggerIngest(path),
    onSuccess: (res) => {
      setIngestFeedback({ type: 'success', msg: res.message })
      // 触发后刷新任务列表，让卡片展示实时进度
      queryClient.invalidateQueries({ queryKey: ['ingest-running-tasks'] })
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['knowledge-collections'] })
      }, 5000)
    },
    onError: (err: Error) => {
      setIngestFeedback({ type: 'error', msg: err.message || '导入触发失败' })
    },
  })

  const handleIngest = () => {
    if (!ingestPath.trim()) return
    setIngestFeedback(null)
    ingestMutation.mutate(ingestPath.trim())
  }

  const handleSelectDir = (path: string) => {
    setIngestPath(path)
    setDirDialogOpen(false)
  }

  const collections = collectionsQuery.data?.collections ?? []

  return (
    <div className="space-y-4">
      {/* Ingest trigger */}
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-dashed p-3">
        <FolderInput className="size-4 shrink-0 text-primary" />
        <div className="relative flex-1 min-w-[240px]">
          <Input
            placeholder="选择或输入目录路径，如 /data/minio/documents/cn/000001/"
            value={ingestPath}
            onChange={(e) => setIngestPath(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleIngest()}
          />
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setDirDialogOpen(true)}
          className="gap-1.5"
        >
          <Folder className="size-3.5" />
          选择目录
        </Button>
        <Button
          size="sm"
          onClick={handleIngest}
          disabled={ingestMutation.isPending || !ingestPath.trim()}
          className="gap-1.5"
        >
          {ingestMutation.isPending ? (
            <RefreshCw className="size-3.5 animate-spin" />
          ) : (
            <FolderInput className="size-3.5" />
          )}
          处理
        </Button>
        {ingestFeedback && (
          <span
            className={cn(
              'flex items-center gap-1 text-xs',
              ingestFeedback.type === 'success' ? 'text-green-600' : 'text-destructive'
            )}
          >
            {ingestFeedback.type === 'success' ? (
              <CheckCircle2 className="size-3" />
            ) : (
              <XCircle className="size-3" />
            )}
            {ingestFeedback.msg}
          </span>
        )}
      </div>

      {/* Directory Browser Dialog */}
      <Dialog open={dirDialogOpen} onOpenChange={setDirDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>选择目录</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            {/* Current path */}
            <div className="flex items-center gap-2 rounded-md bg-muted px-3 py-2 text-sm">
              <Folder className="size-4 shrink-0 text-muted-foreground" />
              <span className="truncate font-mono text-xs">{browseQuery.data?.current_path ?? browsePath}</span>
            </div>

            {/* Navigation */}
            <div className="flex gap-2">
              {browseQuery.data?.can_go_up && (
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  onClick={() => setBrowsePath(browseQuery.data!.parent_path!)}
                >
                  <ArrowUp className="size-3.5" />
                  上级
                </Button>
              )}
              <Button
                variant="default"
                size="sm"
                className="ml-auto gap-1.5"
                onClick={() => handleSelectDir(browseQuery.data?.current_path ?? browsePath)}
              >
                选择当前目录
              </Button>
            </div>

            {/* Directory list */}
            <div className="max-h-[300px] overflow-y-auto rounded-md border">
              {browseQuery.isLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="size-5 animate-spin text-muted-foreground" />
                </div>
              ) : browseQuery.isError ? (
                <div className="py-8 text-center text-sm text-destructive">
                  加载失败，请检查路径是否有效
                </div>
              ) : browseQuery.data?.directories.length === 0 ? (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  无子目录
                </div>
              ) : (
                <div className="divide-y">
                  {browseQuery.data?.directories.map((dir) => (
                    <button
                      key={dir.path}
                      className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted/50 transition-colors"
                      onClick={() => setBrowsePath(dir.path)}
                    >
                      <Folder className="size-4 shrink-0 text-primary" />
                      <span className="flex-1 truncate">{dir.name}</span>
                      <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

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
            // 匹配该 collection 的 running 任务（doc_pipeline 处理中）
            const runningTask = runningTasks.find(
              (t) =>
                (t.params as Record<string, unknown> | null)?.collection === coll.name
            )
            const taskPct = runningTask
              ? Math.max(0, Math.min(100, runningTask.progress ?? 0))
              : null
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

                    {/* 处理中任务实时进度 */}
                    {runningTask && taskPct != null && (
                      <button
                        type="button"
                        onClick={() => onNavigateToTasks?.(runningTask.id)}
                        className="mt-4 w-full rounded-lg border border-primary/20 bg-primary/5 p-3 text-left transition-colors hover:bg-primary/10"
                        title="点击跳转到处理详情定位该任务"
                      >
                        <div className="flex items-center justify-between text-xs">
                          <span className="flex items-center gap-1.5 font-medium text-primary">
                            <Loader className="size-3.5 animate-spin" />
                            处理中
                          </span>
                          <span className="tabular-nums text-foreground">
                            {taskPct.toFixed(0)}%
                          </span>
                        </div>
                        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full bg-primary transition-all"
                            style={{ width: `${taskPct}%` }}
                          />
                        </div>
                        {runningTask.current_item != null && runningTask.total_items != null && (
                          <div className="mt-1.5 text-[11px] tabular-nums text-muted-foreground">
                            已完成 {formatNumber(runningTask.current_item)} /{' '}
                            {formatNumber(runningTask.total_items)} 个文件
                            {runningTask.current_name
                              ? ` · ${runningTask.current_name}`
                              : ''}
                          </div>
                        )}
                      </button>
                    )}

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
