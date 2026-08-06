import { useState } from 'react'
import { Newspaper } from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { NewsListTab } from '@/components/news/NewsListTab'
import { EventsTab } from '@/components/news/EventsTab'
import { ImpactTab } from '@/components/news/ImpactTab'
import { TimelineTab } from '@/components/news/TimelineTab'
import { SourceHealthTab } from '@/components/news/SourceHealthTab'

export default function NewsPage() {
  const [activeTab, setActiveTab] = useState('articles')

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
            News Intelligence Pipeline — 采集 · 分析 · 影响评估
          </p>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="articles">新闻列表</TabsTrigger>
          <TabsTrigger value="events">事件</TabsTrigger>
          <TabsTrigger value="impact">影响分析</TabsTrigger>
          <TabsTrigger value="timeline">时间线</TabsTrigger>
          <TabsTrigger value="health">源健康</TabsTrigger>
        </TabsList>

        <TabsContent value="articles" className="mt-4">
          <NewsListTab />
        </TabsContent>
        <TabsContent value="events" className="mt-4">
          <EventsTab />
        </TabsContent>
        <TabsContent value="impact" className="mt-4">
          <ImpactTab />
        </TabsContent>
        <TabsContent value="timeline" className="mt-4">
          <TimelineTab />
        </TabsContent>
        <TabsContent value="health" className="mt-4">
          <SourceHealthTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
