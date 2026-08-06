import { lazy, Suspense, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Activity,
  Boxes,
  FlaskConical,
  Gauge,
  Newspaper,
  Radio,
  Rss,
  Search,
  Sparkles,
  TrendingUp,
  Users,
} from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

// ── 懒加载各 Tab（NIC-E1 九宫格布局：按需加载，首屏仅概览） ──
const NewsListTab = lazy(() =>
  import('@/components/news/NewsListTab').then((m) => ({ default: m.NewsListTab }))
)
const IntelligenceQueueTab = lazy(() =>
  import('@/components/news/IntelligenceQueueTab').then((m) => ({ default: m.IntelligenceQueueTab }))
)
const EventsTab = lazy(() =>
  import('@/components/news/EventsTab').then((m) => ({ default: m.EventsTab }))
)
const ImpactTab = lazy(() =>
  import('@/components/news/ImpactTab').then((m) => ({ default: m.ImpactTab }))
)
const TimelineTab = lazy(() =>
  import('@/components/news/TimelineTab').then((m) => ({ default: m.TimelineTab }))
)
const TrendTab = lazy(() =>
  import('@/components/news/TrendTab').then((m) => ({ default: m.TrendTab }))
)
const WatchlistMonitorTab = lazy(() =>
  import('@/components/news/WatchlistMonitorTab').then((m) => ({ default: m.WatchlistMonitorTab }))
)
const SourceHealthTab = lazy(() =>
  import('@/components/news/SourceHealthTab').then((m) => ({ default: m.SourceHealthTab }))
)
const RecentActivities = lazy(() =>
  import('@/components/news/RecentActivities').then((m) => ({ default: m.RecentActivities }))
)

function TabFallback() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-14 w-full" />
      ))}
    </div>
  )
}

// ── 九宫格卡片定义（NIC-E1：九项能力入口） ──
interface GridItem {
  key: string
  title: string
  desc: string
  icon: typeof Radio
  tone: string
  /** 目标：tab 名（本页切换）或绝对路径（跳转） */
  target: string
}

const GRID_ITEMS: GridItem[] = [
  {
    key: 'live-feed',
    title: 'Live Feed',
    desc: '实时新闻流 · Breaking / 高影响 / 热点',
    icon: Radio,
    tone: 'text-red-400 bg-red-500/10',
    target: 'articles',
  },
  {
    key: 'queue',
    title: 'Intelligence Queue',
    desc: '四态智能队列 · 审核与重试',
    icon: Boxes,
    tone: 'text-sky-400 bg-sky-500/10',
    target: 'queue',
  },
  {
    key: 'events',
    title: 'Event Monitor',
    desc: '事件监控 · 实体与事件联动',
    icon: Activity,
    tone: 'text-emerald-400 bg-emerald-500/10',
    target: 'events',
  },
  {
    key: 'impact',
    title: 'Impact Monitor',
    desc: '影响评估 · 方向与强度',
    icon: Gauge,
    tone: 'text-amber-400 bg-amber-500/10',
    target: 'impact',
  },
  {
    key: 'trend',
    title: 'Trend Discovery',
    desc: '热点词共现 · 趋势洞察',
    icon: TrendingUp,
    tone: 'text-violet-400 bg-violet-500/10',
    target: 'trend',
  },
  {
    key: 'watchlist',
    title: 'Watchlist Monitor',
    desc: '自选股命中统计 · 实时监控',
    icon: Users,
    tone: 'text-cyan-400 bg-cyan-500/10',
    target: 'watchlist',
  },
  {
    key: 'research',
    title: 'Research Trigger',
    desc: '一键触发深度研究 Workflow',
    icon: FlaskConical,
    tone: 'text-fuchsia-400 bg-fuchsia-500/10',
    target: '/research',
  },
  {
    key: 'health',
    title: 'Source Health',
    desc: '源健康四指标 · 启停联动',
    icon: Rss,
    tone: 'text-lime-400 bg-lime-500/10',
    target: 'health',
  },
  {
    key: 'activities',
    title: 'Recent Activities',
    desc: '动态流 · 新源/异常/Breaking/发布',
    icon: Sparkles,
    tone: 'text-orange-400 bg-orange-500/10',
    target: 'activities',
  },
]

// ── 概览九宫格（默认视图） ──
function OverviewGrid({ onNavigate }: { onNavigate: (target: string) => void }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {GRID_ITEMS.map((item) => {
        const Icon = item.icon
        return (
          <button
            key={item.key}
            type="button"
            onClick={() => onNavigate(item.target)}
            className="group text-left"
          >
            <Card className="transition-colors hover:border-primary/40 hover:bg-accent/40">
              <CardContent className="flex items-start gap-4 p-5">
                <div
                  className={`flex size-11 shrink-0 items-center justify-center rounded-xl ${item.tone}`}
                >
                  <Icon className="size-5" strokeWidth={1.8} />
                </div>
                <div className="min-w-0">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                    {item.title}
                    <span className="text-xs font-normal text-muted-foreground">↗</span>
                  </h3>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{item.desc}</p>
                </div>
              </CardContent>
            </Card>
          </button>
        )
      })}
    </div>
  )
}

export default function NewsPage() {
  const [activeTab, setActiveTab] = useState('overview')
  const navigate = useNavigate()

  const handleNavigate = (target: string) => {
    if (target.startsWith('/')) {
      navigate(target)
    } else {
      setActiveTab(target)
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-8">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-xl bg-primary/10">
          <Newspaper className="size-5 text-primary" strokeWidth={1.8} />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-foreground">新闻智能</h1>
          <p className="text-sm text-muted-foreground">
            News Intelligence Center — 采集 · 分析 · 影响评估 · 洞察
          </p>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="flex-wrap">
          <TabsTrigger value="overview">
            <Search className="mr-1.5 size-3.5" />
            概览
          </TabsTrigger>
          <TabsTrigger value="articles">新闻列表</TabsTrigger>
          <TabsTrigger value="queue">智能队列</TabsTrigger>
          <TabsTrigger value="events">事件</TabsTrigger>
          <TabsTrigger value="impact">影响分析</TabsTrigger>
          <TabsTrigger value="timeline">时间线</TabsTrigger>
          <TabsTrigger value="trend">趋势</TabsTrigger>
          <TabsTrigger value="watchlist">自选监控</TabsTrigger>
          <TabsTrigger value="activities">动态</TabsTrigger>
          <TabsTrigger value="health">源健康</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4">
          <OverviewGrid onNavigate={handleNavigate} />
        </TabsContent>
        <TabsContent value="articles" className="mt-4">
          <Suspense fallback={<TabFallback />}>
            <NewsListTab />
          </Suspense>
        </TabsContent>
        <TabsContent value="queue" className="mt-4">
          <Suspense fallback={<TabFallback />}>
            <IntelligenceQueueTab />
          </Suspense>
        </TabsContent>
        <TabsContent value="events" className="mt-4">
          <Suspense fallback={<TabFallback />}>
            <EventsTab />
          </Suspense>
        </TabsContent>
        <TabsContent value="impact" className="mt-4">
          <Suspense fallback={<TabFallback />}>
            <ImpactTab />
          </Suspense>
        </TabsContent>
        <TabsContent value="timeline" className="mt-4">
          <Suspense fallback={<TabFallback />}>
            <TimelineTab />
          </Suspense>
        </TabsContent>
        <TabsContent value="trend" className="mt-4">
          <Suspense fallback={<TabFallback />}>
            <TrendTab />
          </Suspense>
        </TabsContent>
        <TabsContent value="watchlist" className="mt-4">
          <Suspense fallback={<TabFallback />}>
            <WatchlistMonitorTab />
          </Suspense>
        </TabsContent>
        <TabsContent value="activities" className="mt-4">
          <Suspense fallback={<TabFallback />}>
            <RecentActivities />
          </Suspense>
        </TabsContent>
        <TabsContent value="health" className="mt-4">
          <Suspense fallback={<TabFallback />}>
            <SourceHealthTab />
          </Suspense>
        </TabsContent>
      </Tabs>
    </div>
  )
}