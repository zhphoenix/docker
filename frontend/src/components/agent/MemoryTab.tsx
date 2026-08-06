import { useQuery } from '@tanstack/react-query'
import { Brain, Database, Layers, RefreshCw } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { fetchMemoryOverview } from '@/services/memory'
import { cn } from '@/lib/utils'

export function MemoryTab() {
  const overviewQuery = useQuery({
    queryKey: ['memory'],
    queryFn: fetchMemoryOverview,
  })
  const data = overviewQuery.data

  const layers = [
    {
      key: 'working',
      icon: <Brain className="size-4 text-muted-foreground" />,
      title: '工作记忆',
      desc: 'Agent 运行记录（agent_runs）',
      total: data?.working.total ?? 0,
      ok: data?.working.success ?? 0,
      fail: data?.working.failed ?? 0,
    },
    {
      key: 'episodic',
      icon: <Layers className="size-4 text-muted-foreground" />,
      title: '情景记忆',
      desc: '研究任务历史（research_tasks）',
      total: data?.episodic.total ?? 0,
      ok: data?.episodic.completed ?? 0,
      fail: data?.episodic.failed ?? 0,
    },
    {
      key: 'knowledge',
      icon: <Database className="size-4 text-muted-foreground" />,
      title: '知识记忆',
      desc: 'Qdrant 向量集合',
      total: data?.knowledge.collections.length ?? 0,
      collections: data?.knowledge.collections ?? [],
    },
  ]

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-1.5">三层记忆</span>
            <Button variant="ghost" size="icon" className="size-6" onClick={() => overviewQuery.refetch()}>
              <RefreshCw className={cn('size-3.5', overviewQuery.isFetching && 'animate-spin')} />
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {overviewQuery.isLoading ? (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              {[1, 2, 3].map((i) => <Skeleton key={i} className="h-24 w-full" />)}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              {layers.map((l) => (
                <div key={l.key} className="rounded-lg border p-4">
                  <div className="flex items-center gap-2">
                    {l.icon}
                    <span className="text-sm font-medium">{l.title}</span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{l.desc}</p>
                  <div className="mt-3 text-2xl font-bold">{l.total}</div>
                  {l.key !== 'knowledge' ? (
                    <div className="mt-1 flex gap-2 text-xs text-muted-foreground">
                      <span className="text-success">成功 {l.ok ?? 0}</span>
                      <span className="text-destructive">失败 {l.fail ?? 0}</span>
                    </div>
                  ) : (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {(l as { collections: { name: string }[] }).collections.map((c) => (
                        <Badge key={c.name} variant="outline" className="text-[9px]">{c.name}</Badge>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}