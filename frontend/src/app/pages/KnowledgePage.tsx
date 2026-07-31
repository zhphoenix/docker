import { BookOpen } from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { CollectionGrid } from '@/components/knowledge/CollectionGrid'
import { SemanticSearchPanel } from '@/components/knowledge/SemanticSearchPanel'
import { EntityBrowser } from '@/components/knowledge/EntityBrowser'

export default function KnowledgePage() {
  return (
    <div className="mx-auto max-w-5xl space-y-6 p-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">知识库</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          知识图谱管理、语义检索与实体浏览
        </p>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList>
          <TabsTrigger value="overview" className="gap-1.5">
            <BookOpen className="size-3.5" strokeWidth={1.8} />
            概览
          </TabsTrigger>
          <TabsTrigger value="search">语义搜索</TabsTrigger>
          <TabsTrigger value="entities">实体浏览</TabsTrigger>
          <TabsTrigger value="graph" disabled className="gap-1.5">
            知识图谱
            <Badge variant="outline" className="px-1 py-0 text-[9px] leading-3">
              Soon
            </Badge>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <CollectionGrid />
        </TabsContent>

        <TabsContent value="search">
          <SemanticSearchPanel />
        </TabsContent>

        <TabsContent value="entities">
          <EntityBrowser />
        </TabsContent>
      </Tabs>
    </div>
  )
}
