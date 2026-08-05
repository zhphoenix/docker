import { useCallback, useEffect, useState } from 'react'
import { Star, Play, Plus, Trash2, RefreshCw, CheckCheck } from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type {
  WatchlistItem,
  WatchlistEvent,
  DailyReport,
  WebAlert,
} from '@/services/watchlist'
import {
  fetchWatchlist,
  addWatchlist,
  deleteWatchlist,
  updateWatchlist,
  fetchConfig,
  updateConfig,
  runMonitoring,
  fetchLatestReport,
  fetchWatchEvents,
  fetchWebAlerts,
  markAlertRead,
} from '@/services/watchlist'

const STAR: Record<number, string> = { 5: '★★★★★', 4: '★★★★', 3: '★★★', 2: '★★', 1: '★' }

export default function WatchlistPage() {
  const [loading, setLoading] = useState(true)
  const [items, setItems] = useState<WatchlistItem[]>([])
  const [events, setEvents] = useState<WatchlistEvent[]>([])
  const [report, setReport] = useState<DailyReport | null>(null)
  const [alerts, setAlerts] = useState<WebAlert[]>([])

  // 新增表单
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [group, setGroup] = useState('')
  const [tags, setTags] = useState('')

  // 自选股筛选
  const [filterGroup, setFilterGroup] = useState('')
  const [filterEnabled, setFilterEnabled] = useState('')

  // 配置表单
  const [scheduleTime, setScheduleTime] = useState('07:00')
  const [autoEnabled, setAutoEnabled] = useState(true)

  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [wl, cfg, evt, rep, alr] = await Promise.all([
        fetchWatchlist({
          group_name: filterGroup || undefined,
          enabled:
            filterEnabled === 'on'
              ? true
              : filterEnabled === 'off'
                ? false
                : undefined,
        }),
        fetchConfig(),
        fetchWatchEvents({ limit: 50 }),
        fetchLatestReport(),
        fetchWebAlerts({ limit: 20 }),
      ])
      setItems(wl.items)
      setScheduleTime(cfg.schedule_time || '07:00')
      setAutoEnabled(cfg.auto_enabled)
      setEvents(evt.items)
      setReport(rep.report)
      setAlerts(alr.items)
    } catch (e) {
      setMsg(`加载失败: ${(e as Error).message}`)
    } finally {
      setLoading(false)
    }
  }, [filterGroup, filterEnabled])

  // 筛选变化时重载自选股
  const handleFilterChange = useCallback(() => {
    loadAll()
  }, [loadAll])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  const handleAdd = async () => {
    if (!code.trim()) return
    setBusy(true)
    try {
      await addWatchlist({
        stock_code: code.trim(),
        stock_name: name.trim() || code.trim(),
        group_name: group.trim() || undefined,
        tags: tags
          .split(/[,，]/)
          .map((t) => t.trim())
          .filter(Boolean),
      })
      setCode('')
      setName('')
      setGroup('')
      setTags('')
      setMsg('已添加')
      await loadAll()
    } catch (e) {
      setMsg(`添加失败: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteWatchlist(id)
      await loadAll()
    } catch (e) {
      setMsg(`删除失败: ${(e as Error).message}`)
    }
  }

  const handleToggle = async (item: WatchlistItem) => {
    try {
      await updateWatchlist(item.id, { enabled: !item.enabled })
      await loadAll()
    } catch (e) {
      setMsg(`更新失败: ${(e as Error).message}`)
    }
  }

  const handleSaveConfig = async () => {
    setBusy(true)
    try {
      await updateConfig({ schedule_time: scheduleTime, auto_enabled: autoEnabled })
      setMsg('配置已保存')
    } catch (e) {
      setMsg(`保存失败: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  const handleRun = async () => {
    setBusy(true)
    try {
      const res = await runMonitoring()
      setMsg(res.message || '监控任务已启动')
    } catch (e) {
      setMsg(`启动失败: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  const handleMarkRead = async (id: string) => {
    try {
      await markAlertRead(id)
      await loadAll()
    } catch (e) {
      setMsg(`操作失败: ${(e as Error).message}`)
    }
  }

  const handleMarkAllRead = async () => {
    for (const a of alerts.filter((x) => !x.read)) {
      await markAlertRead(a.id)
    }
    await loadAll()
  }

  // 按 importance 分组
  const byImportance = (src: WatchlistEvent[]) => {
    const map: Record<number, WatchlistEvent[]> = {}
    for (const ev of src) {
      ;(map[ev.importance] ||= []).push(ev)
    }
    return Object.keys(map)
      .map(Number)
      .sort((a, b) => b - a)
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-8">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-xl bg-primary/10">
          <Star className="size-5 text-primary" strokeWidth={1.8} />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-foreground">Watchlist 智能监控</h1>
          <p className="text-sm text-muted-foreground">
            自选股 · 每日监控 · 重要事件 · 日报 · 告警
          </p>
        </div>
      </div>

      {msg && (
        <div className="rounded-lg border border-primary/30 bg-primary/5 px-4 py-2 text-sm text-foreground">
          {msg}
        </div>
      )}

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : (
        <Tabs defaultValue="watchlist">
          <TabsList>
            <TabsTrigger value="watchlist">自选股</TabsTrigger>
            <TabsTrigger value="monitor">监控配置</TabsTrigger>
            <TabsTrigger value="events">今日重点</TabsTrigger>
            <TabsTrigger value="report">每日报告</TabsTrigger>
            <TabsTrigger value="alerts">通知</TabsTrigger>
          </TabsList>

          {/* 自选股 */}
          <TabsContent value="watchlist" className="mt-4 space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">添加自选股</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                <Input
                  placeholder="股票代码 *"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
                <Input
                  placeholder="股票名称"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
                <Input
                  placeholder="分组（如 科技/消费）"
                  value={group}
                  onChange={(e) => setGroup(e.target.value)}
                />
                <Input
                  placeholder="标签（逗号分隔）"
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                />
                <Button onClick={handleAdd} disabled={busy || !code.trim()}>
                  <Plus className="mr-1 size-4" /> 添加
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-center gap-3">
                  <CardTitle className="text-base">自选股列表（{items.length}）</CardTitle>
                  <div className="ml-auto flex flex-wrap items-center gap-2">
                    <Select
                      value={filterGroup}
                      onValueChange={(v) => {
                        setFilterGroup(v === 'all' ? '' : (v ?? ''))
                        handleFilterChange()
                      }}
                    >
                      <SelectTrigger className="w-36">
                        <SelectValue placeholder="全部分组" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">全部分组</SelectItem>
                        <SelectItem value="顶级持仓">顶级持仓</SelectItem>
                        <SelectItem value="科技">科技</SelectItem>
                        <SelectItem value="消费">消费</SelectItem>
                      </SelectContent>
                    </Select>
                    <Select
                      value={filterEnabled}
                      onValueChange={(v) => {
                        setFilterEnabled(v === 'all' ? '' : (v ?? ''))
                        handleFilterChange()
                      }}
                    >
                      <SelectTrigger className="w-32">
                        <SelectValue placeholder="监控状态" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">全部状态</SelectItem>
                        <SelectItem value="on">监控中</SelectItem>
                        <SelectItem value="off">已停用</SelectItem>
                      </SelectContent>
                    </Select>
                    <Button variant="ghost" size="sm" onClick={loadAll}>
                      <RefreshCw className="mr-1 size-4" /> 刷新
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-2">
                {items.length === 0 && (
                  <p className="py-6 text-center text-sm text-muted-foreground">
                    暂无自选股，请先添加
                  </p>
                )}
                {items.map((it) => (
                  <div
                    key={it.id}
                    className="flex flex-wrap items-center gap-3 rounded-lg border p-3"
                  >
                    <div className="min-w-40">
                      <div className="font-semibold">
                        {it.stock_name || it.stock_code}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {it.stock_code}
                        {it.market ? ` · ${it.market}` : ''}
                        {it.industry ? ` · ${it.industry}` : ''}
                      </div>
                    </div>
                    {it.group_name && <Badge variant="secondary">{it.group_name}</Badge>}
                    {it.tags?.map((t) => (
                      <Badge key={t} variant="outline">
                        {t}
                      </Badge>
                    ))}
                    <div className="ml-auto flex items-center gap-2">
                      <Button
                        variant={it.enabled ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => handleToggle(it)}
                      >
                        {it.enabled ? '监控中' : '已停用'}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive"
                        onClick={() => handleDelete(it.id)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          </TabsContent>

          {/* 监控配置 */}
          <TabsContent value="monitor" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">每日监控配置</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap items-center gap-4">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-muted-foreground">每日运行时间</span>
                    <Input
                      type="time"
                      value={scheduleTime}
                      onChange={(e) => setScheduleTime(e.target.value)}
                      className="w-36"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-muted-foreground">自动运行</span>
                    <Button
                      variant={autoEnabled ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setAutoEnabled(!autoEnabled)}
                    >
                      {autoEnabled ? '开启' : '关闭'}
                    </Button>
                  </div>
                  <Button onClick={handleSaveConfig} disabled={busy}>
                    保存配置
                  </Button>
                </div>
                <div className="flex items-center gap-3 border-t pt-4">
                  <Button onClick={handleRun} disabled={busy}>
                    <Play className="mr-1 size-4" /> 开始监控
                  </Button>
                  <span className="text-xs text-muted-foreground">
                    手动触发立即执行一次采集 · 分析 · 报告 · 告警
                  </span>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* 今日重点 */}
          <TabsContent value="events" className="mt-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="text-base">今日重点事件（{events.length}）</CardTitle>
                <Button variant="ghost" size="sm" onClick={loadAll}>
                  <RefreshCw className="mr-1 size-4" /> 刷新
                </Button>
              </CardHeader>
              <CardContent className="space-y-3">
                {events.length === 0 && (
                  <p className="py-6 text-center text-sm text-muted-foreground">
                    暂无事件，可点击"开始监控"触发采集
                  </p>
                )}
                {byImportance(events).map((imp) =>
                  events.filter((e) => e.importance === imp).map((ev) => (
                    <div
                      key={ev.id}
                      className="rounded-lg border p-3"
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">{STAR[ev.importance] ?? '★'}</span>
                        <span className="text-xs text-muted-foreground">
                          {ev.stock_name || ev.stock_code}
                        </span>
                        <Badge variant="outline">{ev.sentiment || 'neutral'}</Badge>
                        <Badge variant="secondary">{ev.confidence || 'medium'}</Badge>
                      </div>
                      <p className="mt-1 text-sm text-foreground">{ev.summary}</p>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* 每日报告 */}
          <TabsContent value="report" className="mt-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="text-base">
                  {report ? report.title || '每日报告' : '每日报告'}
                </CardTitle>
                <Button variant="ghost" size="sm" onClick={loadAll}>
                  <RefreshCw className="mr-1 size-4" /> 刷新
                </Button>
              </CardHeader>
              <CardContent>
                {!report && (
                  <p className="py-6 text-center text-sm text-muted-foreground">
                    暂无报告，运行监控后生成
                  </p>
                )}
                {report && (
                  <>
                    {report.summary && (
                      <p className="mb-3 text-sm text-muted-foreground">{report.summary}</p>
                    )}
                    <pre className="whitespace-pre-wrap rounded-lg bg-muted p-4 text-xs leading-relaxed">
                      {report.content}
                    </pre>
                  </>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* 通知 */}
          <TabsContent value="alerts" className="mt-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="text-base">Web 通知（{alerts.length}）</CardTitle>
                <Button variant="ghost" size="sm" onClick={handleMarkAllRead}>
                  <CheckCheck className="mr-1 size-4" /> 全部已读
                </Button>
              </CardHeader>
              <CardContent className="space-y-2">
                {alerts.length === 0 && (
                  <p className="py-6 text-center text-sm text-muted-foreground">
                    暂无通知
                  </p>
                )}
                {alerts.map((a) => (
                  <div
                    key={a.id}
                    className="flex items-start gap-3 rounded-lg border p-3"
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <Badge variant={a.level === 'critical' ? 'destructive' : 'secondary'}>
                          {a.level}
                        </Badge>
                        <span className="font-medium">{a.title}</span>
                        {a.stock_code && (
                          <span className="text-xs text-muted-foreground">{a.stock_code}</span>
                        )}
                      </div>
                      {a.content && (
                        <p className="mt-1 text-sm text-muted-foreground">{a.content}</p>
                      )}
                    </div>
                    {!a.read && (
                      <Button variant="ghost" size="sm" onClick={() => handleMarkRead(a.id)}>
                        已读
                      </Button>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      )}
    </div>
  )
}