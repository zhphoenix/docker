import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Bot, Wrench, RefreshCw, Cpu } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchAgents } from '@/services/agents'
import { cn } from '@/lib/utils'

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06 } },
}

const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3 } },
}

export default function AgentsPage() {
  const agentsQuery = useQuery({
    queryKey: ['agents'],
    queryFn: fetchAgents,
    retry: 1,
  })

  const agents = agentsQuery.data?.agents ?? []

  return (
    <div className="mx-auto max-w-5xl space-y-8 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Agent Center</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            管理和查看 AI Agent 配置与运行状态
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="gap-2"
          onClick={() => agentsQuery.refetch()}
        >
          <RefreshCw className={cn('size-3.5', agentsQuery.isFetching && 'animate-spin')} />
          刷新
        </Button>
      </div>

      {/* Content */}
      {agentsQuery.isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}>
              <CardContent className="p-5">
                <Skeleton className="h-10 w-10 rounded-xl" />
                <Skeleton className="mt-4 h-4 w-32" />
                <Skeleton className="mt-2 h-3 w-full" />
                <Skeleton className="mt-2 h-3 w-2/3" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : agentsQuery.isError ? (
        <EmptyState
          icon={Bot}
          title="无法加载 Agent 列表"
          description="无法连接到后端服务，请确认 LangGraph 服务已启动（端口 8100）"
          action={{ label: '重试', onClick: () => agentsQuery.refetch() }}
        />
      ) : agents.length === 0 ? (
        <EmptyState
          icon={Bot}
          title="暂无 Agent"
          description="尚未注册任何 Agent"
        />
      ) : (
        <motion.div
          variants={container}
          initial="hidden"
          animate="show"
          className="grid grid-cols-1 gap-4 sm:grid-cols-2"
        >
          {agents.map((agent) => (
            <motion.div key={agent.id} variants={item}>
              <Card className="h-full transition-shadow duration-200 hover:shadow-[var(--shadow-soft)]">
                <CardContent className="p-5">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="flex size-10 items-center justify-center rounded-xl bg-primary/10">
                        <Bot className="size-5 text-primary" strokeWidth={1.8} />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-foreground">
                            {agent.name}
                          </span>
                          {/* Active 状态点 */}
                          <span
                            className={cn(
                              'size-2 rounded-full',
                              agent.is_active ? 'bg-success' : 'bg-muted-foreground/40'
                            )}
                            title={agent.is_active ? '运行中' : '已停用'}
                          />
                        </div>
                        <div className="mt-0.5 flex items-center gap-2">
                          <Badge
                            variant={agent.source === 'builtin' ? 'default' : 'secondary'}
                            className="text-[10px]"
                          >
                            {agent.source === 'builtin' ? '内置' : '自定义'}
                          </Badge>
                          {agent.model && (
                            <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                              <Cpu className="size-3" strokeWidth={1.8} />
                              {agent.model}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>

                  {agent.description && (
                    <p className="mt-3 line-clamp-2 text-xs text-muted-foreground">
                      {agent.description}
                    </p>
                  )}

                  {agent.tools.length > 0 && (
                    <div className="mt-3 flex flex-wrap items-center gap-1.5">
                      <Wrench className="size-3 text-muted-foreground" strokeWidth={1.8} />
                      {agent.tools.map((tool) => (
                        <Badge key={tool} variant="outline" className="text-[10px]">
                          {tool}
                        </Badge>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      )}

      {/* Footer note */}
      <p className="text-center text-xs text-muted-foreground">
        Agent 配置为只读展示 · 创建与编辑功能将在后续版本开放
      </p>
    </div>
  )
}
