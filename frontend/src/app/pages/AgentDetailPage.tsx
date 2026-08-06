import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  Bot,
  RefreshCw,
  Power,
  Server,
  GitBranch,
  Blocks,
  Wrench,
  Cable,
  Cpu,
  FileText,
  Settings,
  Sparkles,
  Brain,
  ScrollText,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchAgentDetail, toggleAgent } from '@/services/agents'
import { PromptTab } from '@/components/agent/PromptTab'
import { ConfigTab } from '@/components/agent/ConfigTab'
import { SkillsTab } from '@/components/agent/SkillsTab'
import { ToolsTab } from '@/components/agent/ToolsTab'
import { McpTab } from '@/components/agent/McpTab'
import { MemoryTab } from '@/components/agent/MemoryTab'
import { MetricsPanel } from '@/components/agent/MetricsPanel'
import { LogsPanel } from '@/components/agent/LogsPanel'
import { cn } from '@/lib/utils'

const STATUS_META: Record<string, { label: string; dot: string }> = {
  active: { label: '运行中', dot: 'bg-success' },
  paused: { label: '已暂停', dot: 'bg-amber-500' },
  deprecated: { label: '已下线', dot: 'bg-muted-foreground/40' },
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

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-foreground">{value}</span>
    </div>
  )
}

function TagList({ items }: { items: string[] }) {
  if (items.length === 0) {
    return <span className="text-xs text-muted-foreground">—</span>
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((t) => (
        <Badge key={t} variant="outline" className="text-[10px]">
          {t}
        </Badge>
      ))}
    </div>
  )
}

export default function AgentDetailPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const detailQuery = useQuery({
    queryKey: ['agent', id],
    queryFn: () => fetchAgentDetail(id),
    enabled: !!id,
    retry: 1,
  })

  const toggleMutation = useMutation({
    mutationFn: () => toggleAgent(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agent', id] })
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    },
  })

  const agent = detailQuery.data

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-8">
      {/* 返回 + 标题 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate('/agents')}>
            <ArrowLeft className="size-4" />
          </Button>
          {agent ? (
            <div className="flex items-center gap-2">
              <div className="flex size-9 items-center justify-center rounded-xl bg-primary/10">
                <Bot className="size-5 text-primary" strokeWidth={1.8} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-xl font-bold text-foreground">
                    {agent.display_name || agent.name}
                  </h1>
                  <span
                    className={cn('size-2 rounded-full', STATUS_META[agent.status]?.dot ?? 'bg-success')}
                    title={STATUS_META[agent.status]?.label ?? '运行中'}
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  {agent.id} · v{agent.version} · {agent.source === 'builtin' ? '内置' : '自定义'}
                </p>
              </div>
            </div>
          ) : (
            <Skeleton className="h-9 w-48" />
          )}
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="gap-2" onClick={() => detailQuery.refetch()}>
            <RefreshCw className={cn('size-3.5', detailQuery.isFetching && 'animate-spin')} />
            刷新
          </Button>
          {agent && (
            <Button
              variant={agent.status === 'active' ? 'outline' : 'default'}
              size="sm"
              className="gap-2"
              onClick={() => toggleMutation.mutate()}
              disabled={toggleMutation.isPending}
            >
              <Power className="size-3.5" />
              {agent.status === 'active' ? '暂停' : '启用'}
            </Button>
          )}
        </div>
      </div>

      {/* 内容 */}
      {detailQuery.isLoading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardContent className="p-5">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="mt-3 h-3 w-full" />
                <Skeleton className="mt-2 h-3 w-2/3" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : detailQuery.isError || !agent ? (
        <EmptyState
          icon={Bot}
          title="无法加载 Agent 详情"
          description="无法连接到后端服务，或该 Agent 不存在"
        />
      ) : (
        <>
          {/* 顶部信息卡：基本信息 + Runtime + Dependencies */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Server className="size-4 text-muted-foreground" /> 基本信息
                </CardTitle>
              </CardHeader>
              <CardContent>
                <InfoRow label="名称" value={agent.display_name || agent.name} />
                <InfoRow label="版本" value={agent.version} />
                <InfoRow label="作者" value={agent.author} />
                <InfoRow label="最后活跃" value={formatLastActive(agent.last_active_at)} />
                <InfoRow
                  label="状态"
                  value={
                    <Badge variant={agent.status === 'active' ? 'default' : 'secondary'}>
                      {STATUS_META[agent.status]?.label ?? agent.status}
                    </Badge>
                  }
                />
                <p className="mt-3 text-xs text-muted-foreground">{agent.description}</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Cpu className="size-4 text-muted-foreground" /> Runtime
                </CardTitle>
              </CardHeader>
              <CardContent>
                <InfoRow label="模型" value={agent.runtime.model || '默认（跟随路由）'} />
                <InfoRow label="Temperature" value={agent.runtime.temperature} />
                <InfoRow label="Top P" value={agent.runtime.top_p} />
                <InfoRow label="Max Tokens" value={agent.runtime.max_tokens} />
                <InfoRow label="Timeout" value={`${agent.runtime.timeout}s`} />
                <InfoRow label="Retry" value={agent.runtime.retry} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Blocks className="size-4 text-muted-foreground" /> 依赖
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <div className="mb-1 flex items-center gap-1 text-xs text-muted-foreground">
                    <GitBranch className="size-3" /> Workflows
                  </div>
                  <TagList items={agent.dependencies.workflows} />
                </div>
                <div>
                  <div className="mb-1 flex items-center gap-1 text-xs text-muted-foreground">
                    <Wrench className="size-3" /> Tools
                  </div>
                  <TagList items={agent.dependencies.tools} />
                </div>
                <div>
                  <div className="mb-1 flex items-center gap-1 text-xs text-muted-foreground">
                    <Cable className="size-3" /> MCP
                  </div>
                  <TagList items={agent.dependencies.mcp} />
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Tabs：概览 / Prompt / 配置（Phase2 追加 Skills/Tools/MCP/Memory） */}
          <Tabs defaultValue="overview">
            <TabsList>
              <TabsTrigger value="overview" className="gap-1.5">
                <FileText className="size-3.5" /> 概览
              </TabsTrigger>
              <TabsTrigger value="prompt" className="gap-1.5">
                提示词
              </TabsTrigger>
              <TabsTrigger value="config" className="gap-1.5">
                <Settings className="size-3.5" /> 配置
              </TabsTrigger>
              <TabsTrigger value="skills" className="gap-1.5">
                <Sparkles className="size-3.5" /> 技能
              </TabsTrigger>
              <TabsTrigger value="tools" className="gap-1.5">
                <Wrench className="size-3.5" /> 工具
              </TabsTrigger>
              <TabsTrigger value="mcp" className="gap-1.5">
                <Cable className="size-3.5" /> MCP
              </TabsTrigger>
              <TabsTrigger value="memory" className="gap-1.5">
                <Brain className="size-3.5" /> 记忆
              </TabsTrigger>
              <TabsTrigger value="logs" className="gap-1.5">
                <ScrollText className="size-3.5" /> 日志
              </TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="pt-3">
              {/* AC-P3-3: Runtime Metrics（六项指标 + 趋势） */}
              <MetricsPanel agentId={agent.id} />
            </TabsContent>

            <TabsContent value="prompt" className="pt-3">
              <PromptTab agentId={agent.id} />
            </TabsContent>

            <TabsContent value="config" className="pt-3">
              <ConfigTab agentId={agent.id} />
            </TabsContent>

            <TabsContent value="skills" className="pt-3">
              <SkillsTab />
            </TabsContent>

            <TabsContent value="tools" className="pt-3">
              <ToolsTab />
            </TabsContent>

            <TabsContent value="mcp" className="pt-3">
              <McpTab />
            </TabsContent>

            <TabsContent value="memory" className="pt-3">
              <MemoryTab />
            </TabsContent>

            <TabsContent value="logs" className="pt-3">
              {/* AC-P3-5: Logs 与 Trace（联合视图 + CSV） */}
              <LogsPanel agentId={agent.id} />
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  )
}