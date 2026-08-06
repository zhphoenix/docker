import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { Bot, Wrench, RefreshCw, Cpu, Clock } from 'lucide-react'
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

function formatLastActive(ts: string | null): string {
  if (!ts) return '从未运行'
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} 小时前`
  return `${Math.floor(hours / 24)} 天前`
}

const STATUS_META: Record<string, { label: string; dot: string }> = {
  active: { label: '运行中', dot: 'bg-success' },
  paused: { label: '已暂停', dot: 'bg-amber-500' },
  deprecated: { label: '已下线', dot: 'bg-muted-foreground/40' },
}

export default function AgentsPage() {
  const navigate = useNavigate()
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
          {agents.map((agent) => {
            const meta = STATUS_META[agent.status] ?? STATUS_META.active
            return (
              <motion.div key={agent.id} variants={item}>
                <Card
                  className="h-full cursor-pointer transition-shadow duration-200 hover:shadow-[var(--shadow-soft)]"
                  onClick={() => navigate(`/agents/${agent.id}`)}
                >
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between">
                      <div className="flex min-w-0 items-center gap-3">
                        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10">
                          <Bot className="size-5 text-primary" strokeWidth={1.8} />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="truncate text-sm font-semibold text-foreground">
                              {agent.display_name || agent.name}
                            </span>
                            {/* 在线状态点 */}
                            <span
                              className={cn('size-2 shrink-0 rounded-full', meta.dot)}
                              title={meta.label}
                            />
                          </div>
                          <div className="mt-0.5 flex items-center gap-2">
                            <Badge
                              variant={agent.source === 'builtin' ? 'default' : 'secondary'}
                              className="text-[10px]"
                            >
                              {agent.source === 'builtin' ? '内置' : '自定义'}
                            </Badge>
                            {agent.version && (
                              <span className="text-[11px] text-muted-foreground">
                                {agent.version}
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

                    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
                      {agent.model && (
                        <span className="flex items-center gap-1">
                          <Cpu className="size-3" strokeWidth={1.8} />
                          {agent.model}
                        </span>
                      )}
                      <span className="flex items-center gap-1">
                        <Clock className="size-3" strokeWidth={1.8} />
                        {formatLastActive(agent.last_active_at)}
                      </span>
                    </div>

                    {agent.tools.length > 0 && (
                      <div className="mt-3 flex flex-wrap items-center gap-1.5">
                        <Wrench className="size-3 text-muted-foreground" strokeWidth={1.8} />
                        {agent.tools.slice(0, 5).map((tool) => (
                          <Badge key={tool} variant="outline" className="text-[10px]">
                            {tool}
                          </Badge>
                        ))}
                        {agent.tools.length > 5 && (
                          <span className="text-[10px] text-muted-foreground">
                            +{agent.tools.length - 5}
                          </span>
                        )}
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
        点击卡片进入详情页 · 更多管理能力将在后续开放
      </p>
    </div>
  )
}