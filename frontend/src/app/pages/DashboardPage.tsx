import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  FileText,
  Bot,
  Database,
  Activity,
  MessageSquare,
  BookOpen,
  ArrowRight,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { fetchHealth } from '@/services/health'
import { fetchModels } from '@/services/models'
import { cn } from '@/lib/utils'

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.08 },
  },
}

const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3 } },
}

const quickActions = [
  { to: '/chat', icon: MessageSquare, label: '开始对话', desc: '与 AI 助手交流' },
  { to: '/knowledge', icon: BookOpen, label: '知识库', desc: '检索研究资料' },
  { to: '/documents', icon: FileText, label: '文档管理', desc: '上传与解析文档' },
]

export default function DashboardPage() {
  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  })

  const modelsQuery = useQuery({
    queryKey: ['models'],
    queryFn: fetchModels,
  })

  const services = healthQuery.data?.services ?? {}
  const serviceEntries = Object.entries(services)
  const upCount = serviceEntries.filter(([, s]) => s === 'up').length
  const modelCount = modelsQuery.data?.data?.length ?? 0

  const stats = [
    {
      label: '系统服务',
      value: healthQuery.isLoading ? '...' : `${upCount}/${serviceEntries.length}`,
      sub: healthQuery.data?.status === 'healthy' ? '运行正常' : '部分异常',
      icon: Activity,
      color: 'text-success',
    },
    {
      label: '可用模型',
      value: modelsQuery.isLoading ? '...' : String(modelCount),
      sub: 'LLM 推理引擎',
      icon: Bot,
      color: 'text-primary',
    },
    {
      label: '向量数据库',
      value: services.qdrant === 'up' ? '在线' : '离线',
      sub: 'Qdrant',
      icon: Database,
      color: services.qdrant === 'up' ? 'text-success' : 'text-danger',
    },
    {
      label: '文档解析',
      value: services.embedding === 'up' ? '就绪' : '离线',
      sub: 'Embedding 服务',
      icon: FileText,
      color: services.embedding === 'up' ? 'text-success' : 'text-danger',
    },
  ]

  return (
    <div className="mx-auto max-w-6xl space-y-8 p-8">
      {/* Welcome */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">欢迎回来</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          AI 投研平台运行概览
        </p>
      </div>

      {/* Stats Grid */}
      <motion.div
        variants={container}
        initial="hidden"
        animate="show"
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
      >
        {stats.map((stat) => (
          <motion.div key={stat.label} variants={item}>
            <Card className="transition-shadow duration-200 hover:shadow-[var(--shadow-soft)]">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">
                  {stat.label}
                </CardTitle>
                <stat.icon className={cn('size-4', stat.color)} strokeWidth={1.8} />
              </CardHeader>
              <CardContent>
                {healthQuery.isLoading || modelsQuery.isLoading ? (
                  <Skeleton className="h-8 w-16" />
                ) : (
                  <div className="text-2xl font-bold text-foreground">
                    {stat.value}
                  </div>
                )}
                <p className="mt-1 text-xs text-muted-foreground">{stat.sub}</p>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </motion.div>

      {/* Service Status */}
      <motion.div variants={item} initial="hidden" animate="show">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold">服务状态</CardTitle>
          </CardHeader>
          <CardContent>
            {healthQuery.isLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-5 w-full" />
                ))}
              </div>
            ) : serviceEntries.length > 0 ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                {serviceEntries.map(([name, status]) => (
                  <div
                    key={name}
                    className="flex items-center gap-2 rounded-lg border border-border px-3 py-2"
                  >
                    <span
                      className={cn(
                        'size-2 rounded-full',
                        status === 'up' ? 'bg-success' : 'bg-danger'
                      )}
                    />
                    <span className="text-xs font-medium capitalize text-foreground">
                      {name}
                    </span>
                    <Badge
                      variant={status === 'up' ? 'default' : 'destructive'}
                      className="ml-auto text-[10px]"
                    >
                      {status}
                    </Badge>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                无法获取服务状态，请确认后端服务已启动
              </p>
            )}
          </CardContent>
        </Card>
      </motion.div>

      {/* Quick Actions */}
      <motion.div variants={item} initial="hidden" animate="show">
        <h2 className="mb-4 text-sm font-semibold text-foreground">快捷操作</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {quickActions.map((action) => (
            <Link key={action.to} to={action.to}>
              <Card className="group cursor-pointer transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow-soft)]">
                <CardContent className="flex items-center gap-4 p-5">
                  <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10">
                    <action.icon className="size-5 text-primary" strokeWidth={1.8} />
                  </div>
                  <div className="flex-1">
                    <div className="text-sm font-medium text-foreground">
                      {action.label}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {action.desc}
                    </div>
                  </div>
                  <ArrowRight className="size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </motion.div>
    </div>
  )
}
