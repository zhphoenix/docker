import { useQuery } from '@tanstack/react-query'
import { Boxes, ExternalLink, FileText, Lightbulb } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import {
  SIYUAN_GRAPH_GUIDE,
  SIYUAN_URL,
  fetchEntities,
  fetchKnowledgeStats,
} from '@/services/knowledge'

/**
 * 知识图谱工作台：以 SiYuan 关系图作为展示层（PG 为唯一数据源 SoT）。
 * 提供图谱统计概览 + 实体预览 + 跳转 SiYuan 关系图入口。
 */
export function GraphWorkspace() {
  const statsQuery = useQuery({
    queryKey: ['knowledge-graph-stats'],
    queryFn: fetchKnowledgeStats,
    retry: 1,
  })

  const entitiesQuery = useQuery({
    queryKey: ['knowledge-graph-entities'],
    queryFn: () => fetchEntities({ limit: 8 }),
    retry: 1,
  })

  const stats = statsQuery.data
  const entities = entitiesQuery.data?.entities ?? []

  const openSiyuan = () => window.open(SIYUAN_URL, '_blank', 'noopener,noreferrer')

  const statCards = [
    { label: '实体', value: stats?.entities ?? 0, icon: Boxes },
    { label: '事实', value: stats?.facts ?? 0, icon: Lightbulb },
    { label: '文档', value: stats?.documents ?? 0, icon: FileText },
  ]

  return (
    <div className="space-y-6">
      {/* 统计卡片 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {statCards.map((c) => (
          <Card key={c.label}>
            <CardContent className="flex items-center gap-3 p-4">
              <c.icon className="size-5 text-muted-foreground" strokeWidth={1.8} />
              <div>
                <p className="text-xs text-muted-foreground">{c.label}</p>
                <p className="text-2xl font-bold tabular-nums">
                  {statsQuery.isLoading ? '…' : c.value.toLocaleString()}
                </p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* 跳转 SiYuan */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">知识图谱（SiYuan 关系图）</CardTitle>
          <CardDescription>
            知识图谱以 SiYuan 作为展示层，基于实体文档链接自动生成关联图谱。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button onClick={openSiyuan}>
            <ExternalLink className="size-4" strokeWidth={1.8} />
            打开 SiYuan 关系图
          </Button>
          <p className="text-xs text-muted-foreground">{SIYUAN_GRAPH_GUIDE}</p>
        </CardContent>
      </Card>

      {/* 实体预览 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">实体预览</CardTitle>
          <CardDescription>最近提取的实体，可在 SiYuan 中查看对应文档。</CardDescription>
        </CardHeader>
        <CardContent>
          {entitiesQuery.isLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-10 w-full rounded-lg" />
              ))}
            </div>
          ) : entitiesQuery.isError ? (
            <EmptyState
              icon={Boxes}
              title="无法加载实体"
              description="查询知识图谱实体失败，请确认后端服务正常"
              action={{ label: '重试', onClick: () => entitiesQuery.refetch() }}
            />
          ) : entities.length === 0 ? (
            <EmptyState
              icon={Boxes}
              title="暂无实体数据"
              description="知识图谱中尚未提取任何实体，请先运行知识提取任务"
            />
          ) : (
            <div className="space-y-2">
              {entities.map((e) => (
                <div
                  key={e.id}
                  className="flex items-center justify-between rounded-lg border px-3 py-2"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="truncate text-sm font-medium">{e.name}</span>
                    <Badge variant="secondary" className="shrink-0 text-[10px]">
                      {e.entity_type}
                    </Badge>
                  </div>
                  <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                    {e.confidence != null ? `置信度 ${Math.round(e.confidence * 100)}%` : '—'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}