import { useQuery } from '@tanstack/react-query'
import { fetchHealth } from '@/services/health'

/**
 * 全局健康检测器（唯一检测源）
 *
 * 挂载于 AppShell（常驻，所有路由页面的父级），是唯一发起 /health 轮询的组件。
 * 约定统一缓存键 ['health']，全局仅此一处配置 refetchInterval。
 * 其余页面（StatusBar / Dashboard / Monitor 等）通过 useQuery(['health']) 只读消费，
 * 从本检测器共享到的最新状态中「反映」展示，不再自行发请求。
 */
export const HEALTH_QUERY_KEY = ['health'] as const

// 全局唯一轮询间隔（10 分钟）
const HEALTH_POLL_INTERVAL = 10 * 60_000

export function HealthProvider({ children }: { children: React.ReactNode }) {
  useQuery({
    queryKey: HEALTH_QUERY_KEY,
    queryFn: fetchHealth,
    refetchInterval: HEALTH_POLL_INTERVAL,
    // 轮询窗口内复用缓存，避免重复请求；窗口内窗口聚焦/重连不额外刷新
    staleTime: HEALTH_POLL_INTERVAL,
  })
  return <>{children}</>
}