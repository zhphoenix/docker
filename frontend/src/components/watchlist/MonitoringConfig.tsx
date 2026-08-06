import { Loader2, Play } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useWatchlistConfig, useUpdateWatchlistConfig, useRunMonitoring } from '@/hooks/useWatchlist'

const SCOPE_OPTIONS = [
  { key: 'news', label: '新闻' },
  { key: 'announcement', label: '公告' },
  { key: 'earnings', label: '财报' },
  { key: 'industry', label: '行业' },
  { key: 'policy', label: '政策' },
  { key: 'social_media', label: '社交媒体' },
  { key: 'overseas', label: '海外新闻' },
  { key: 'competitor', label: '竞争对手' },
]

const FREQ_OPTIONS = [
  { key: 'daily', label: '每日' },
  { key: 'hourly', label: '每小时' },
  { key: 'realtime', label: '实时' },
]

const CHANNEL_OPTIONS = [
  { key: 'web', label: '站内通知' },
  { key: 'email', label: '邮件' },
  { key: 'webhook', label: 'Webhook' },
]

export function MonitoringConfig() {
  const { data: config, isLoading } = useWatchlistConfig()
  const updateConfig = useUpdateWatchlistConfig()
  const runMonitor = useRunMonitoring()

  if (isLoading) {
    return (
      <Card>
        <CardHeader><Skeleton className="h-5 w-24" /></CardHeader>
        <CardContent className="space-y-4">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </CardContent>
      </Card>
    )
  }

  if (!config) return null

  const toggleScope = (key: string) => {
    const scopes = config.monitoring_scopes ?? []
    const next = scopes.includes(key) ? scopes.filter((s) => s !== key) : [...scopes, key]
    updateConfig.mutate({ monitoring_scopes: next })
  }

  const toggleChannel = (key: string) => {
    const channels = config.notification_channels ?? ['web']
    const next = channels.includes(key)
      ? channels.filter((c) => c !== key)
      : [...channels, key]
    updateConfig.mutate({ notification_channels: next })
  }

  const toggleFeature = (field: 'ai_summary_enabled' | 'daily_report_enabled' | 'email_enabled') => {
    updateConfig.mutate({ [field]: !config[field] })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">监控配置</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* 监控维度 */}
        <div>
          <h4 className="mb-2 text-sm font-medium text-muted-foreground">监控维度</h4>
          <div className="flex flex-wrap gap-2">
            {SCOPE_OPTIONS.map(({ key, label }) => {
              const active = (config.monitoring_scopes ?? []).includes(key)
              return (
                <Button
                  key={key}
                  variant={active ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => toggleScope(key)}
                  disabled={updateConfig.isPending}
                >
                  {active ? '✓ ' : ''}{label}
                </Button>
              )
            })}
          </div>
        </div>

        {/* 更新频率 */}
        <div>
          <h4 className="mb-2 text-sm font-medium text-muted-foreground">更新频率</h4>
          <div className="flex flex-wrap gap-2">
            {FREQ_OPTIONS.map(({ key, label }) => (
              <Button
                key={key}
                variant={config.update_frequency === key ? 'default' : 'outline'}
                size="sm"
                onClick={() => updateConfig.mutate({ update_frequency: key })}
                disabled={updateConfig.isPending}
              >
                {label}
              </Button>
            ))}
          </div>
        </div>

        {/* AI 功能开关 */}
        <div>
          <h4 className="mb-2 text-sm font-medium text-muted-foreground">AI 功能</h4>
          <div className="flex flex-wrap gap-2">
            {[
              { field: 'ai_summary_enabled' as const, label: 'AI 摘要' },
              { field: 'daily_report_enabled' as const, label: '日报' },
              { field: 'email_enabled' as const, label: '邮件通知' },
            ].map(({ field, label }) => (
              <Button
                key={field}
                variant={config[field] ? 'default' : 'outline'}
                size="sm"
                onClick={() => toggleFeature(field)}
                disabled={updateConfig.isPending}
              >
                {config[field] ? '✓ ' : ''}{label}
              </Button>
            ))}
          </div>
        </div>

        {/* 告警阈值 */}
        <div>
          <h4 className="mb-2 text-sm font-medium text-muted-foreground">告警阈值（重要性 ≥）</h4>
          <Input
            type="number"
            min={1}
            max={5}
            value={config.alert_threshold ?? 4}
            onChange={(e) => {
              const v = parseInt(e.target.value)
              if (v >= 1 && v <= 5) updateConfig.mutate({ alert_threshold: v })
            }}
            className="w-20"
          />
        </div>

        {/* 通知通道 */}
        <div>
          <h4 className="mb-2 text-sm font-medium text-muted-foreground">通知通道</h4>
          <div className="flex flex-wrap gap-2">
            {CHANNEL_OPTIONS.map(({ key, label }) => {
              const active = (config.notification_channels ?? ['web']).includes(key)
              return (
                <Button
                  key={key}
                  variant={active ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => toggleChannel(key)}
                  disabled={updateConfig.isPending}
                >
                  {active ? '✓ ' : ''}{label}
                </Button>
              )
            })}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            邮件需在邮箱配置中开启并填写收件地址，Webhook 需填写 Webhook URL
          </p>
        </div>

        {/* 手动运行 */}
        <div className="flex items-center gap-3 border-t pt-4">
          <Button onClick={() => runMonitor.mutate()} disabled={runMonitor.isPending}>
            {runMonitor.isPending ? (
              <Loader2 className="mr-1 size-4 animate-spin" />
            ) : (
              <Play className="mr-1 size-4" />
            )}
            开始监控
          </Button>
          <span className="text-xs text-muted-foreground">
            {runMonitor.isPending
              ? '正在采集 · 分析 · 生成报告…'
              : '手动触发立即执行一次采集 · 分析 · 报告 · 告警'}
          </span>
        </div>
      </CardContent>
    </Card>
  )
}
