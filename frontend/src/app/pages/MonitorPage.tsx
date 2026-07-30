import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  Database,
  HardDrive,
  Cpu,
  FileSearch,
  Brain,
  Bot,
  Globe,
  MessageSquare,
  Layers,
  Server,
  RefreshCw,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { fetchHealth } from '@/services/health'
import { cn } from '@/lib/utils'

interface ServiceInfo {
  name: string
  label: string
  port: string
  icon: typeof Database
  category: 'storage' | 'ai' | 'application'
  command: string
  description: string
}

const SERVICES: ServiceInfo[] = [
  {
    name: 'postgres',
    label: 'PostgreSQL',
    port: '5432',
    icon: Database,
    category: 'storage',
    command: 'docker compose up -d postgres',
    description: '业务数据库 (pgvector)',
  },
  {
    name: 'qdrant',
    label: 'Qdrant',
    port: '6333',
    icon: Layers,
    category: 'storage',
    command: 'docker compose up -d qdrant',
    description: '向量检索引擎',
  },
  {
    name: 'minio',
    label: 'MinIO',
    port: '9000',
    icon: HardDrive,
    category: 'storage',
    command: 'docker compose up -d minio',
    description: '对象存储 (文件真相源)',
  },
  {
    name: 'embedding',
    label: 'Embedding',
    port: '8001',
    icon: Cpu,
    category: 'ai',
    command: 'docker compose up -d embedding',
    description: 'Qwen3-Embedding-4B 向量化',
  },
  {
    name: 'reranker',
    label: 'Reranker',
    port: '8002',
    icon: Cpu,
    category: 'ai',
    command: 'docker compose up -d reranker',
    description: 'Qwen3-Reranker-0.6B 重排序',
  },
  {
    name: 'llm',
    label: 'Sisyphus (LLM)',
    port: '8080',
    icon: Brain,
    category: 'ai',
    command: 'docker compose up -d sisyphus',
    description: 'Qwen3 推理引擎 (llama.cpp)',
  },
  {
    name: 'docling',
    label: 'Docling',
    port: '5001',
    icon: FileSearch,
    category: 'ai',
    command: 'docker compose up -d docling',
    description: '文档解析服务 (PDF→MD)',
  },
  {
    name: 'langgraph',
    label: 'LangGraph Agent',
    port: '8100',
    icon: Bot,
    category: 'application',
    command: 'docker compose up -d langgraph',
    description: 'FastAPI + Agent 编排服务',
  },
  {
    name: 'crawl4ai',
    label: 'Crawl4AI',
    port: '11235',
    icon: Globe,
    category: 'application',
    command: 'docker compose up -d crawl4ai',
    description: 'Web 抓取服务',
  },
  {
    name: 'open-webui',
    label: 'Open WebUI',
    port: '3000',
    icon: MessageSquare,
    category: 'application',
    command: 'docker compose up -d open-webui',
    description: 'AI 对话界面 (备用)',
  },
]

const CATEGORY_LABELS: Record<string, string> = {
  storage: '数据存储',
  ai: 'AI 服务',
  application: '应用服务',
}

export default function MonitorPage() {
  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    retry: 1,
  })

  const services = healthQuery.data?.services ?? {}
  const backendReachable = !healthQuery.isError && healthQuery.data != null

  const getStatus = (name: string): 'up' | 'down' | 'unknown' => {
    if (!backendReachable) return 'unknown'
    return services[name] === 'up' ? 'up' : 'down'
  }

  const upCount = Object.values(services).filter((s) => s === 'up').length
  const totalCount = SERVICES.length

  return (
    <div className="mx-auto max-w-5xl space-y-8 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">服务监控</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            所有基础设施服务的运行状态
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="gap-2"
          onClick={() => healthQuery.refetch()}
        >
          <RefreshCw
            className={cn('size-3.5', healthQuery.isFetching && 'animate-spin')}
          />
          刷新
        </Button>
      </div>

      {/* Summary Banner */}
      <Card>
        <CardContent className="flex items-center gap-4 p-5">
          <div
            className={cn(
              'flex size-10 items-center justify-center rounded-xl',
              !backendReachable
                ? 'bg-warning/10'
                : upCount === totalCount
                  ? 'bg-success/10'
                  : 'bg-danger/10'
            )}
          >
            <Server
              className={cn(
                'size-5',
                !backendReachable
                  ? 'text-warning'
                  : upCount === totalCount
                    ? 'text-success'
                    : 'text-danger'
              )}
            />
          </div>
          <div>
            <div className="text-sm font-semibold text-foreground">
              {!backendReachable
                ? '后端 API 不可达'
                : upCount === totalCount
                  ? '所有服务运行正常'
                  : `${upCount}/${totalCount} 个服务在线`}
            </div>
            <div className="text-xs text-muted-foreground">
              {!backendReachable
                ? '无法获取服务状态，请确认 LangGraph 服务已启动 (端口 8100)'
                : '通过 /health 接口获取，点击刷新按钮更新状态'}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Service Categories */}
      {(['storage', 'ai', 'application'] as const).map((category, catIdx) => (
        <motion.div
          key={category}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: catIdx * 0.1 }}
        >
          <h2 className="mb-3 text-sm font-semibold text-foreground">
            {CATEGORY_LABELS[category]}
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {SERVICES.filter((s) => s.category === category).map((service) => {
              const status = getStatus(service.name)
              return (
                <Card
                  key={service.name}
                  className="transition-shadow duration-200 hover:shadow-[var(--shadow-soft)]"
                >
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className="flex size-9 items-center justify-center rounded-lg bg-muted">
                          <service.icon
                            className="size-4.5 text-muted-foreground"
                            strokeWidth={1.8}
                          />
                        </div>
                        <div>
                          <div className="text-sm font-medium text-foreground">
                            {service.label}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            :{service.port}
                          </div>
                        </div>
                      </div>
                      {healthQuery.isLoading ? (
                        <Skeleton className="h-5 w-14 rounded-full" />
                      ) : (
                        <Badge
                          variant={
                            status === 'up'
                              ? 'default'
                              : status === 'down'
                                ? 'destructive'
                                : 'secondary'
                          }
                          className={cn(
                            'text-[10px]',
                            status === 'up' && 'bg-success/15 text-success hover:bg-success/15',
                            status === 'unknown' && 'text-muted-foreground'
                          )}
                        >
                          {status === 'up'
                            ? '运行中'
                            : status === 'down'
                              ? '离线'
                              : '未知'}
                        </Badge>
                      )}
                    </div>

                    <p className="mt-3 text-xs text-muted-foreground">
                      {service.description}
                    </p>


                  </CardContent>
                </Card>
              )
            })}
          </div>
        </motion.div>
      ))}

      {/* Footer note */}
      <p className="text-center text-xs text-muted-foreground">
        服务管理请通过终端执行 docker compose 命令 · 状态数据来源: FastAPI /health 接口
      </p>
    </div>
  )
}
