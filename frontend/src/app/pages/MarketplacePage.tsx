import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Boxes,
  Download,
  HardDriveDownload,
  Loader2,
  Package,
  Store,
  Trash2,
  Upload,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import { WindowedDialog } from '@/components/ui/windowed-dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { fetchAgents } from '@/services/agents'
import {
  deleteTemplate,
  fetchTemplates,
  importAgent,
  installTemplate,
  publishTemplate,
  type AgentTemplate,
} from '@/services/marketplace'

function fmtDate(ts: string): string {
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export default function MarketplacePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [publishOpen, setPublishOpen] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  const templatesQuery = useQuery({
    queryKey: ['marketplace-templates'],
    queryFn: () => fetchTemplates(),
    retry: 1,
  })
  const agentsQuery = useQuery({
    queryKey: ['agents'],
    queryFn: fetchAgents,
    retry: 1,
  })

  const templates = templatesQuery.data?.templates ?? []
  const agents = agentsQuery.data?.agents ?? []

  const flash = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(null), 3000)
  }

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['marketplace-templates'] })
    queryClient.invalidateQueries({ queryKey: ['agents'] })
  }

  /* ---------- 发布模板 ---------- */
  const [publishAgentId, setPublishAgentId] = useState('')
  const [publishName, setPublishName] = useState('')
  const [publishCategory, setPublishCategory] = useState('agent')
  const [publishDesc, setPublishDesc] = useState('')

  const publishMutation = useMutation({
    mutationFn: () =>
      publishTemplate({
        agent_id: publishAgentId,
        display_name: publishName || undefined,
        description: publishDesc || undefined,
        category: publishCategory || undefined,
      }),
    onSuccess: (res) => {
      invalidate()
      setPublishOpen(false)
      setPublishAgentId('')
      setPublishName('')
      setPublishCategory('agent')
      setPublishDesc('')
      flash(res.overwritten ? `模板「${res.name}」已更新` : `模板「${res.name}」已发布`)
    },
    onError: (e: Error) => flash(`发布失败：${e.message}`),
  })

  /* ---------- 导入 JSON ---------- */
  const importMutation = useMutation({
    mutationFn: (definition: unknown) => importAgent(definition as never),
    onSuccess: (res) => {
      invalidate()
      flash(`已导入 Agent「${res.agent}」，应用 ${res.prompts_applied} 个 Prompt 变体`)
    },
    onError: (e: Error) => flash(`导入失败：${e.message}`),
  })

  const handleFile = (file: File | undefined) => {
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      try {
        const json = JSON.parse(String(reader.result))
        importMutation.mutate(json)
      } catch {
        flash('文件不是有效的 JSON')
      }
    }
    reader.readAsText(file)
  }

  /* ---------- 安装 / 删除 ---------- */
  const installMutation = useMutation({
    mutationFn: (id: string) => installTemplate(id),
    onSuccess: (res) => {
      invalidate()
      flash(`已安装 Agent「${res.agent}」，应用 ${res.prompts_applied} 个 Prompt 变体`)
    },
    onError: (e: Error) => flash(`安装失败：${e.message}`),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteTemplate(id),
    onSuccess: () => {
      invalidate()
      flash('模板已删除')
    },
    onError: (e: Error) => flash(`删除失败：${e.message}`),
  })

  const categoryMeta: Record<string, { label: string; cls: string }> = {
    agent: { label: 'Agent', cls: 'bg-primary/10 text-primary' },
    news: { label: '资讯', cls: 'bg-sky-500/10 text-sky-600' },
    research: { label: '研究', cls: 'bg-emerald-500/10 text-emerald-600' },
    knowledge: { label: '知识', cls: 'bg-amber-500/10 text-amber-600' },
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-8">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon-sm" onClick={() => navigate('/agents')} title="返回 Agent Center">
            <ArrowLeft className="size-4" />
          </Button>
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-bold text-foreground">
              <Store className="size-6 text-primary" /> Agent Marketplace
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              导出 / 导入 Agent 定义，跨实例共享并安装模板
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,application/json"
            className="hidden"
            onChange={(e) => {
              handleFile(e.target.files?.[0])
              e.target.value = ''
            }}
          />
          <Button variant="outline" size="sm" className="gap-2" onClick={() => fileInputRef.current?.click()} disabled={importMutation.isPending}>
            {importMutation.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Upload className="size-3.5" />}
            导入 JSON
          </Button>
          <Button size="sm" className="gap-2" onClick={() => setPublishOpen(true)}>
            <Package className="size-3.5" /> 发布模板
          </Button>
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div className="rounded-lg border border-primary/30 bg-primary/5 px-4 py-2.5 text-sm text-foreground">
          {toast}
        </div>
      )}

      {/* 模板列表 */}
      <div>
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
          <Boxes className="size-4 text-muted-foreground" /> 已发布模板
          {templates.length > 0 && (
            <Badge variant="secondary" className="text-[10px]">{templates.length}</Badge>
          )}
        </h2>

        {templatesQuery.isLoading ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-40 w-full" />
            ))}
          </div>
        ) : templatesQuery.isError ? (
          <EmptyState icon={Store} title="无法加载" description="模板列表不可用" />
        ) : templates.length === 0 ? (
          <EmptyState
            icon={Store}
            title="暂无模板"
            description="从 Agent Center 选择一个 Agent 发布为模板，或导入 JSON"
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {templates.map((t: AgentTemplate) => {
              const cat = categoryMeta[t.category] ?? { label: t.category, cls: 'bg-muted text-muted-foreground' }
              return (
                <Card key={t.id} className="flex flex-col">
                  <CardContent className="flex flex-1 flex-col gap-2 p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="flex items-center gap-2 truncate text-sm font-semibold text-foreground">
                          <Package className="size-4 shrink-0 text-primary" />
                          {t.display_name || t.name}
                        </p>
                        <p className="mt-0.5 truncate text-xs text-muted-foreground">{t.name}</p>
                      </div>
                      <Badge className={`shrink-0 text-[10px] ${cat.cls}`}>{cat.label}</Badge>
                    </div>
                    <p className="line-clamp-2 min-h-[2rem] flex-1 text-xs text-muted-foreground">
                      {t.description || '无描述'}
                    </p>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <HardDriveDownload className="size-3" /> {t.version}
                      </span>
                      <span className="flex items-center gap-1">
                        <Download className="size-3" /> {t.installs} 次安装
                      </span>
                      <span>{t.author}</span>
                      <span className="ml-auto">{fmtDate(t.created_at)}</span>
                    </div>
                    <div className="mt-2 flex items-center gap-2 border-t pt-3">
                      <Button
                        size="sm"
                        className="flex-1 gap-2"
                        onClick={() => installMutation.mutate(t.id)}
                        disabled={installMutation.isPending}
                      >
                        {installMutation.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
                        安装
                      </Button>
                      <Button
                        variant="outline"
                        size="icon-sm"
                        onClick={() => deleteMutation.mutate(t.id)}
                        disabled={deleteMutation.isPending}
                        title="删除模板"
                      >
                        {deleteMutation.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Trash2 className="size-3.5" />}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        )}
      </div>

      {/* 发布模板对话框 */}
      <WindowedDialog
        open={publishOpen}
        onOpenChange={setPublishOpen}
        title="发布 Agent 模板"
        description="将当前实例中的一个 Agent 打包为模板，供其他实例导入安装"
        defaultWidth={480}
        defaultHeight={520}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setPublishOpen(false)} disabled={publishMutation.isPending}>
              取消
            </Button>
            <Button
              onClick={() => publishMutation.mutate()}
              disabled={publishMutation.isPending || !publishAgentId}
            >
              {publishMutation.isPending && <Loader2 className="mr-2 size-4 animate-spin" />}
              发布
            </Button>
          </div>
        }
      >
        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">选择 Agent *</label>
            <Select value={publishAgentId} onValueChange={setPublishAgentId}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="选择要发布的 Agent" />
              </SelectTrigger>
              <SelectContent className="w-full">
                {agents.map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    {a.display_name || a.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">模板名称</label>
            <Input
              value={publishName}
              onChange={(e) => setPublishName(e.target.value)}
              placeholder="留空则使用 Agent 名称"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">分类</label>
            <Select value={publishCategory} onValueChange={setPublishCategory}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="w-full">
                <SelectItem value="agent">Agent</SelectItem>
                <SelectItem value="news">资讯</SelectItem>
                <SelectItem value="research">研究</SelectItem>
                <SelectItem value="knowledge">知识</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">描述</label>
            <Textarea
              value={publishDesc}
              onChange={(e) => setPublishDesc(e.target.value)}
              placeholder="模板用途说明（可选）"
              rows={3}
            />
          </div>
        </div>
      </WindowedDialog>
    </div>
  )
}