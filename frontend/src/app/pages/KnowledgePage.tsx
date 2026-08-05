import { useState } from 'react'
import { LayoutDashboard, ListChecks } from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { KnowledgeDashboard } from '@/components/knowledge/KnowledgeDashboard'
import { SemanticSearchPanel } from '@/components/knowledge/SemanticSearchPanel'
import { EntityBrowser } from '@/components/knowledge/EntityBrowser'
import { KnowledgeTasksPanel } from '@/components/knowledge/KnowledgeTasksPanel'
import { GraphWorkspace } from '@/components/knowledge/GraphWorkspace'

export default function KnowledgePage() {
  const [activeTab, setActiveTab] = useState('dashboard')
  const [focusTaskId, setFocusTaskId] = useState<string | null>(null)

  const handleNavigateToTasks = (taskId?: string) => {
    setFocusTaskId(taskId ?? null)
    setActiveTab('tasks')
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Knowledge Hub</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          知识中台：文档、向量、实体与知识图谱的统一管理与语义检索
        </p>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList>
          <TabsTrigger value="dashboard" className="gap-1.5">
            <LayoutDashboard className="size-3.5" strokeWidth={1.8} />
            Dashboard
          </TabsTrigger>
          <TabsTrigger value="search">语义搜索</TabsTrigger>
          <TabsTrigger value="entities">实体浏览</TabsTrigger>
          <TabsTrigger value="tasks" className="gap-1.5">
            <ListChecks className="size-3.5" strokeWidth={1.8} />
            处理详情
          </TabsTrigger>
          <TabsTrigger value="graph">知识图谱</TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard">
          <KnowledgeDashboard onNavigateToTasks={handleNavigateToTasks} />
        </TabsContent>

        <TabsContent value="search">
          <SemanticSearchPanel />
        </TabsContent>

        <TabsContent value="entities">
          <EntityBrowser />
        </TabsContent>

        <TabsContent value="tasks">
          <KnowledgeTasksPanel focusTaskId={focusTaskId} />
        </TabsContent>

        <TabsContent value="graph">
          <GraphWorkspace />
        </TabsContent>
      </Tabs>
    </div>
  )
}
