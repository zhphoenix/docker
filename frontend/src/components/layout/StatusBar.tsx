import { useQuery } from '@tanstack/react-query'
import { fetchHealth } from '@/services/health'
import { fetchModels } from '@/services/models'
import { cn } from '@/lib/utils'

export function StatusBar() {
  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  })

  const modelsQuery = useQuery({
    queryKey: ['models'],
    queryFn: fetchModels,
  })

  const isHealthy = healthQuery.data?.status === 'healthy'
  const modelCount = modelsQuery.data?.data?.length ?? 0

  return (
    <footer className="flex h-7 shrink-0 items-center justify-between border-t border-border bg-background/80 px-4 text-[11px] text-muted-foreground backdrop-blur-[30px]">
      <div className="flex items-center gap-4">
        <span className="flex items-center gap-1.5">
          <span
            className={cn(
              'size-1.5 rounded-full',
              healthQuery.isLoading
                ? 'bg-warning animate-pulse'
                : isHealthy
                  ? 'bg-success'
                  : 'bg-danger'
            )}
          />
          {healthQuery.isLoading
            ? '检测中...'
            : isHealthy
              ? '服务正常'
              : '服务异常'}
        </span>

        {healthQuery.data?.services && (
          <span className="hidden items-center gap-2 sm:flex">
            {Object.entries(healthQuery.data.services).map(([name, status]) => (
              <span key={name} className="flex items-center gap-1">
                <span
                  className={cn(
                    'size-1 rounded-full',
                    status === 'up' ? 'bg-success' : 'bg-danger'
                  )}
                />
                {name}
              </span>
            ))}
          </span>
        )}
      </div>

      <div className="flex items-center gap-4">
        {modelCount > 0 && <span>{modelCount} 个模型</span>}
        <span>AI Platform v1.0</span>
      </div>
    </footer>
  )
}
