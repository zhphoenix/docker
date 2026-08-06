import { Check, Circle, Loader2, Workflow } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { useWatchlistOverview } from '@/hooks/useWatchlist'
import type { WatchlistOverview } from '@/services/watchlist'

interface StageDef {
  key: string
  label: string
  done: (ov: WatchlistOverview | undefined) => boolean
}

// 监控生命周期：加载 → 采集 → 分析 → 写入 → 日报 → 告警 → 研究
const STAGES: StageDef[] = [
  { key: 'load', label: '加载自选股', done: (ov) => (ov?.monitored_stocks ?? 0) > 0 },
  { key: 'collect', label: '采集新闻', done: (ov) => (ov?.today_events ?? 0) > 0 },
  { key: 'analyze', label: '分析事件', done: (ov) => (ov?.today_events ?? 0) > 0 },
  { key: 'write', label: '写入事件', done: (ov) => (ov?.today_events ?? 0) > 0 },
  { key: 'report', label: '生成日报', done: (ov) => (ov?.ai_reports ?? 0) > 0 },
  { key: 'alert', label: '发送告警', done: (ov) => (ov?.unread_alerts ?? 0) > 0 },
  { key: 'research', label: '研究', done: () => false },
]

export function LifecycleFlow({ isRunning }: { isRunning: boolean }) {
  const { data: overview } = useWatchlistOverview()

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center gap-2">
          <Workflow className="size-4 text-primary" />
          <h4 className="text-sm font-medium text-muted-foreground">监控生命周期</h4>
          {isRunning && (
            <span className="ml-auto flex items-center gap-1.5 text-sm text-primary">
              <Loader2 className="size-4 animate-spin" />
              执行中…
            </span>
          )}
        </div>

        <ol className="mt-4 flex flex-wrap items-center gap-y-3">
          {STAGES.map((stage, i) => {
            const done = stage.done(overview)
            const running = isRunning && !done
            const Icon = running ? Loader2 : done ? Check : Circle
            const iconClass = running
              ? 'animate-spin text-blue-500'
              : done
                ? 'text-emerald-500'
                : 'text-muted-foreground/40'
            return (
              <li key={stage.key} className="flex items-center">
                {i > 0 && <span className="mx-2 h-px w-6 bg-border" />}
                <div className="flex items-center gap-2">
                  <span
                    className={`flex size-7 items-center justify-center rounded-full border ${
                      running
                        ? 'border-blue-400/40 bg-blue-500/10'
                        : done
                          ? 'border-emerald-400/40 bg-emerald-500/10'
                          : 'border-border bg-muted/40'
                    }`}
                  >
                    <Icon className={`size-4 ${iconClass}`} />
                  </span>
                  <span
                    className={`text-sm ${
                      running ? 'text-blue-500' : done ? 'text-foreground' : 'text-muted-foreground/50'
                    }`}
                  >
                    {stage.label}
                  </span>
                </div>
              </li>
            )
          })}
        </ol>

        {!isRunning && !overview && (
          <p className="mt-3 text-xs text-muted-foreground">等待监控数据…</p>
        )}
      </CardContent>
    </Card>
  )
}