import { useCallback, useEffect, useRef, useState } from 'react'
import { Star, Play, Plus, Trash2, RefreshCw, CheckCheck, Loader2, ExternalLink } from 'lucide-react'
import { useDebounce } from '@/hooks/useDebounce'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Combobox } from '@/components/ui/combobox'
import { WindowedDialog } from '@/components/ui/windowed-dialog'
import { LinkifiedText } from '@/components/ui/linkified-text'
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
import type { NewsArticle } from '@/services/news'
import { fetchNewsArticle } from '@/services/news'
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
  fetchGroups,
  lookupStock,
  createGroup,
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
  const [market, setMarket] = useState('')
  const [group, setGroup] = useState('')
  const [tags, setTags] = useState('')
  const [groupOptions, setGroupOptions] = useState<string[]>([])
  const [lookupLoading, setLookupLoading] = useState(false)
  // 记录用户最后主动编辑的字段（代码/名称），避免双向自动填充互相覆盖
  const lastEditedRef = useRef<'code' | 'name'>('code')
  // 抑制标志：添加成功后阻断仍在途的 lookup 异步回调回填，避免竞态残留
  const suppressLookupRef = useRef(false)
  // 记录最近一次发起 lookup 的输入，防止迟到的旧请求回填覆盖当前输入
  const lookupInputRef = useRef<{ kind: 'code' | 'name'; input: string } | null>(
    null
  )

  // 自选股筛选
  const [filterGroup, setFilterGroup] = useState('')
  const [filterEnabled, setFilterEnabled] = useState('')

  // 配置表单
  const [scheduleTime, setScheduleTime] = useState('07:00')
  const [autoEnabled, setAutoEnabled] = useState(true)

  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  // 事件详情弹窗：点击事件卡打开，有 news_id 时懒加载文章正文
  const [detailEvent, setDetailEvent] = useState<WatchlistEvent | null>(null)
  const [detailArticle, setDetailArticle] = useState<NewsArticle | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const openEventDetail = useCallback((ev: WatchlistEvent) => {
    setDetailEvent(ev)
    setDetailArticle(null)
    if (ev.news_id) {
      setDetailLoading(true)
      fetchNewsArticle(ev.news_id)
        .then(setDetailArticle)
        .catch(() => setDetailArticle(null))
        .finally(() => setDetailLoading(false))
    }
  }, [])
  // 采集中状态：触发监控后轮询每日报告，报告 updated 即视为本轮完成
  const [running, setRunning] = useState(false)
  const runPollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const runStartedRef = useRef<number>(0)

  const stopRunPolling = useCallback(() => {
    if (runPollRef.current) {
      clearInterval(runPollRef.current)
      runPollRef.current = null
    }
  }, [])

  // 组件卸载时清理轮询
  useEffect(() => stopRunPolling, [stopRunPolling])

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

  // 加载分组选项（已有分组 + 默认分组）
  useEffect(() => {
    fetchGroups()
      .then((res) => {
        const existing = res.items
          .map((g) => g.group_name)
          .filter((x): x is string => Boolean(x))
        const defaults = ['顶级持仓', '科技', '消费']
        setGroupOptions(Array.from(new Set([...existing, ...defaults])))
      })
      .catch(() => {})
  }, [])

  // 防抖：输入股票代码后自动填充名称/市场/行业
  const debouncedCode = useDebounce(code, 400)
  useEffect(() => {
    const c = debouncedCode.trim()
    if (!c) return
    // 仅当用户正在编辑代码时填充名称，避免反向填充(code→name)时互相覆盖
    if (lastEditedRef.current !== 'code') return
    let cancelled = false
    lookupInputRef.current = { kind: 'code', input: c }
    setLookupLoading(true)
    lookupStock({ code: c, market: market || undefined })
      .then((res) => {
        if (
          cancelled ||
          suppressLookupRef.current ||
          !res.item ||
          lookupInputRef.current?.kind !== 'code' ||
          lookupInputRef.current.input !== c
        )
          return
        if (res.item.company_name) setName(res.item.company_name)
        if (res.item.market) setMarket(res.item.market)
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLookupLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [debouncedCode, market])

  // 防抖：输入股票名称后反向自动填充代码/市场
  const debouncedName = useDebounce(name, 400)
  useEffect(() => {
    const n = debouncedName.trim()
    if (!n) return
    // 仅当用户正在编辑名称时反向填充代码，避免 code→name 填充时触发循环
    if (lastEditedRef.current !== 'name') return
    let cancelled = false
    lookupInputRef.current = { kind: 'name', input: n }
    setLookupLoading(true)
    lookupStock({ name: n, market: market || undefined })
      .then((res) => {
        if (
          cancelled ||
          suppressLookupRef.current ||
          !res.item ||
          lookupInputRef.current?.kind !== 'name' ||
          lookupInputRef.current.input !== n
        )
          return
        if (res.item.symbol) setCode(res.item.symbol)
        if (res.item.market) setMarket(res.item.market)
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLookupLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [debouncedName, market])

  // 分组选择/新建：新建分组持久化到后端，刷新后仍保留
  const handleGroupChange = useCallback((v: string) => {
    setGroup(v)
    if (!v) return
    setGroupOptions((prev) => {
      if (prev.includes(v)) return prev
      const next = [...prev, v]
      createGroup(v).catch(() => {})
      return next
    })
  }, [])

  const handleAdd = async () => {
    if (!code.trim()) return
    // 拦截重复添加：同一股票代码已在自选股中时直接提示，不再发起请求
    const normalized = code.trim().toUpperCase()
    const existing = items.find(
      (it) => it.stock_code.trim().toUpperCase() === normalized
    )
    if (existing) {
      setMsg(`"${existing.stock_name || existing.stock_code}" 已在自选股中`)
      return
    }
    setBusy(true)
    try {
      await addWatchlist({
        stock_code: code.trim(),
        stock_name: name.trim() || code.trim(),
        market: market.trim() || undefined,
        group_name: group.trim() || undefined,
        tags: tags
          .split(/[,，]/)
          .map((t) => t.trim())
          .filter(Boolean),
      })
      setCode('')
      setName('')
      setMarket('')
      setGroup('')
      setTags('')
      suppressLookupRef.current = true
      lookupInputRef.current = null
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
      // 后端为异步任务（采集·分析·报告），轮询报告 updated 检测完成
      setRunning(true)
      runStartedRef.current = Date.now()
      stopRunPolling()
      runPollRef.current = setInterval(async () => {
        // 超时保护：15 分钟后停止轮询
        if (Date.now() - runStartedRef.current > 15 * 60 * 1000) {
          stopRunPolling()
          setRunning(false)
          setMsg('采集耗时较长，请稍后手动刷新查看结果')
          return
        }
        try {
          const { report: rep } = await fetchLatestReport()
          const repTime = rep?.created_at ? new Date(rep.created_at).getTime() : 0
          // 容忍 60s 客户端/服务器时钟偏差
          if (repTime >= runStartedRef.current - 60_000) {
            stopRunPolling()
            setRunning(false)
            setMsg('采集完成')
            loadAll()
          }
        } catch {
          /* 网络抖动时继续轮询 */
        }
      }, 20_000)
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
        <div className="flex items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 px-4 py-2 text-sm text-foreground">
          {running && <Loader2 className="size-4 animate-spin text-primary" />}
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
              <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
                <Select
                  value={market}
                  onValueChange={(v) => setMarket(v === 'auto' ? '' : (v ?? ''))}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="市场" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">自动识别</SelectItem>
                    <SelectItem value="cn">A股</SelectItem>
                    <SelectItem value="hk">港股</SelectItem>
                    <SelectItem value="us">美股</SelectItem>
                  </SelectContent>
                </Select>
                <div className="relative">
                  <Input
                    placeholder="股票代码 *"
                    value={code}
                    onChange={(e) => {
                      suppressLookupRef.current = false
                      lookupInputRef.current = null
                      lastEditedRef.current = 'code'
                      setCode(e.target.value)
                    }}
                    className="pr-8"
                  />
                  {lookupLoading && (
                    <Loader2 className="absolute right-2.5 top-2.5 size-4 animate-spin text-muted-foreground" />
                  )}
                </div>
                <Input
                  placeholder="股票名称（自动填充）"
                  value={name}
                  onChange={(e) => {
                    suppressLookupRef.current = false
                    lookupInputRef.current = null
                    lastEditedRef.current = 'name'
                    setName(e.target.value)
                  }}
                />
                <Combobox
                  value={group}
                  onValueChange={handleGroupChange}
                  options={groupOptions}
                  placeholder="分组（可新建）"
                  clearLabel="未分组"
                  creatable
                  createLabel={(q) => `新建分组 "${q}"`}
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
                  <Button onClick={handleRun} disabled={busy || running}>
                    {running ? (
                      <Loader2 className="mr-1 size-4 animate-spin" />
                    ) : (
                      <Play className="mr-1 size-4" />
                    )}
                    {running ? '采集中…' : '开始监控'}
                  </Button>
                  <span className="text-xs text-muted-foreground">
                    {running
                      ? '正在采集 · 分析 · 生成报告，完成后自动刷新（约数分钟）'
                      : '手动触发立即执行一次采集 · 分析 · 报告 · 告警'}
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
                      role="button"
                      tabIndex={0}
                      onClick={() => openEventDetail(ev)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          openEventDetail(ev)
                        }
                      }}
                      className="cursor-pointer rounded-lg border p-3 transition-colors hover:border-primary/40 hover:bg-muted/40"
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">{STAR[ev.importance] ?? '★'}</span>
                        <span className="text-xs text-muted-foreground">
                          {ev.stock_name || ev.stock_code}
                        </span>
                        <Badge variant="outline">{ev.sentiment || 'neutral'}</Badge>
                        <Badge variant="secondary">{ev.confidence || 'medium'}</Badge>
                        {ev.article_title && (
                          <span className="truncate text-xs text-muted-foreground">
                            {ev.source_name ? `${ev.source_name} · ` : ''}
                            {ev.article_title}
                          </span>
                        )}
                      </div>
                      <p className="mt-1 line-clamp-2 text-sm text-foreground">{ev.summary}</p>
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

      {/* 事件详情弹窗（可拖拽/缩放/最大化/最小化） */}
      <WindowedDialog
        open={detailEvent !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDetailEvent(null)
            setDetailArticle(null)
          }
        }}
        defaultWidth={760}
        defaultHeight={600}
        title={
          detailEvent ? (
            <>
              <span className="font-semibold">
                {STAR[detailEvent.importance] ?? '★'}
              </span>
              <span>
                {detailEvent.stock_name || detailEvent.stock_code} 相关事件
              </span>
              <Badge variant="outline">{detailEvent.sentiment || 'neutral'}</Badge>
              <Badge variant="secondary">{detailEvent.confidence || 'medium'}</Badge>
            </>
          ) : (
            '事件详情'
          )
        }
      >
        {detailEvent && (
          <div className="space-y-4">
            {/* 元信息 */}
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              {detailEvent.event_time && (
                <span>
                  事件时间：
                  {new Date(detailEvent.event_time).toLocaleString('zh-CN')}
                </span>
              )}
              {detailEvent.source_type && <span>类型：{detailEvent.source_type}</span>}
              {detailEvent.impact_horizon && (
                <span>影响周期：{detailEvent.impact_horizon}</span>
              )}
              {detailEvent.source_name && <span>来源：{detailEvent.source_name}</span>}
            </div>

            {/* 摘要（自动识别其中的网址并渲染为可点击链接） */}
            {detailEvent.summary && (
              <div>
                <h4 className="mb-1 text-sm font-medium">事件摘要</h4>
                <p className="whitespace-pre-wrap text-sm leading-relaxed">
                  <LinkifiedText text={detailEvent.summary} />
                </p>
              </div>
            )}

            {/* 来源文章 */}
            {(detailEvent.news_id || detailEvent.article_title) && (
              <div className="space-y-2 rounded-lg border p-3">
                <div className="flex items-center gap-2">
                  <h4 className="text-sm font-medium">
                    {detailEvent.article_title || '来源文章'}
                  </h4>
                  {detailEvent.article_url && (
                    <a
                      href={detailEvent.article_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                    >
                      查看原文 <ExternalLink className="size-3" />
                    </a>
                  )}
                </div>
                {detailLoading ? (
                  <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" /> 加载文章正文…
                  </div>
                ) : detailArticle?.content ? (
                  <pre className="whitespace-pre-wrap rounded-md bg-muted p-3 text-xs leading-relaxed">
                    <LinkifiedText text={detailArticle.content} />
                  </pre>
                ) : (
                  <p className="text-xs text-muted-foreground">暂无正文内容</p>
                )}
              </div>
            )}
          </div>
        )}
      </WindowedDialog>
    </div>
  )
}