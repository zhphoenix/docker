import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Brain, Bot, Wrench, RefreshCw } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchModels } from '@/services/models'
import { fetchAgents } from '@/services/agents'
import type { AgentInfo } from '@/services/agents'
import { cn } from '@/lib/utils'

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06 } },
}

const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3 } },
}

export default function ModelsPage() {
  const modelsQuery = useQuery({
    queryKey: ['models'],
    queryFn: fetchModels,
    retry: 1,
  })

  // 独立 query：agents API 失败时不影响模型列表展示
  const agentsQuery = useQuery({
    queryKey: ['agents'],
    queryFn: fetchAgents,
    retry: 1,
  })

  const models = modelsQuery.data?.data ?? []
  const agents = agentsQuery.data?.agents ?? []

  // 将 agent 详情按 id/name 关联到 model
  const agentByName = new Map<string, AgentInfo>()
  for (const a of agents) {
    agentByName.set(a.id, a)
    agentByName.set(a.name, a)
  }

  const handleRefresh = () => {
    modelsQuery.refetch()
    agentsQuery.refetch()
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">模型管理</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            可用的 LLM 推理引擎与 Agent 模型
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="gap-2"
          onClick={handleRefresh}
        >
          <RefreshCw
            className={cn('size-3.5', (modelsQuery.isFetching || agentsQuery.isFetching) && 'animate-spin')}
          />
          刷新
        </Button>
      </div>

      {/* Content */}
      {modelsQuery.isLoading ? (
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
      ) : modelsQuery.isError ? (
        <EmptyState
          icon={Brain}
          title="无法加载模型列表"
          description="无法连接到后端服务，请确认 LangGraph 服务已启动（端口 8100）"
          action={{ label: '重试', onClick: handleRefresh }}
        />
      ) : models.length === 0 ? (
        <EmptyState
          icon={Brain}
          title="暂无可用模型"
          description="尚未注册任何模型或 Agent"
        />
      ) : (
        <motion.div
          variants={container}
          initial="hidden"
          animate="show"
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          {models.map((model) => {
            const agent = agentByName.get(model.id)
            const tools = agent?.tools ?? []
            return (
              <motion.div key={model.id} variants={item}>
                <Card className="h-full transition-shadow duration-200 hover:shadow-[var(--shadow-soft)]">
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between">
                      <div className="flex size-10 items-center justify-center rounded-xl bg-primary/10">
                        <Bot className="size-5 text-primary" strokeWidth={1.8} />
                      </div>
                      {agent && (
                        <Badge
                          variant={agent.source === 'builtin' ? 'default' : 'secondary'}
                          className="text-[10px]"
                        >
                          {agent.source === 'builtin' ? '内置' : '自定义'}
                        </Badge>
                      )}
                    </div>

                    <div className="mt-4">
                      <div className="text-sm font-semibold text-foreground">{model.id}</div>
                      <div className="mt-0.5 text-xs text-muted-foreground">
                        {model.owned_by}
                      </div>
                    </div>

                    {agent?.description && (
                      <p className="mt-2 line-clamp-2 text-xs text-muted-foreground">
                        {agent.description}
                      </p>
                    )}

                    {tools.length > 0 && (
                      <div className="mt-3 flex flex-wrap items-center gap-1.5">
                        <Wrench className="size-3 text-muted-foreground" strokeWidth={1.8} />
                        {tools.map((tool) => (
                          <Badge key={tool} variant="outline" className="text-[10px]">
                            {tool}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </motion.div>
            )
          })}
        </motion.div>
      )}

      {/* Footer note */}
      <p className="text-center text-xs text-muted-foreground">
        模型通过 OpenAI 兼容接口 /v1/models 暴露 · 每个 Agent 作为一个 model 注册
      </p>
    </div>
  )
}
