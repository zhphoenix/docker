import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, Eye, RefreshCw, History, Send, GitCompareArrows } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { EmptyState } from '@/components/common/EmptyState'
import {
  fetchPrompts,
  fetchPromptDetail,
  savePrompt,
  previewPrompt,
  submitPrompt,
  fetchPromptDiff,
  type PromptDiffLine,
} from '@/services/prompts'
import { cn } from '@/lib/utils'

const STATUS_LABEL: Record<string, string> = {
  published: '已发布',
  draft: '草稿',
  pending_approval: '审批中',
  archived: '历史',
}

function DiffLine({ line }: { line: PromptDiffLine }) {
  return (
    <div
      className={cn(
        'flex gap-2 px-2 py-0.5 font-mono text-xs',
        line.type === 'added' && 'bg-emerald-500/10 text-emerald-600',
        line.type === 'removed' && 'bg-rose-500/10 text-rose-500',
        line.type === 'context' && 'text-muted-foreground'
      )}
    >
      <span className="w-4 shrink-0 select-none">
        {line.type === 'added' ? '+' : line.type === 'removed' ? '-' : ' '}
      </span>
      <span className="whitespace-pre-wrap break-all">{line.text || ' '}</span>
    </div>
  )
}

export function PromptTab({ agentId }: { agentId: string }) {
  const queryClient = useQueryClient()
  const [content, setContent] = useState('')
  const [variables, setVariables] = useState<Record<string, string>>({})
  const [preview, setPreview] = useState<string | null>(null)
  // diff 对比：选中的两个版本
  const [diffV1, setDiffV1] = useState<number | null>(null)
  const [diffV2, setDiffV2] = useState<number | null>(null)

  const listQuery = useQuery({
    queryKey: ['prompts', agentId],
    queryFn: () => fetchPrompts(agentId),
  })

  const prompts = listQuery.data?.prompts ?? []

  // 选中项：默认取第一条；selectedKey 为 `${agent_id}/${name}`
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const resolvedKey = selectedKey ?? (prompts[0] ? `${prompts[0].agent_id}/${prompts[0].name}` : null)
  const selectedPrompt = prompts.find((p) => `${p.agent_id}/${p.name}` === resolvedKey) ?? null
  const selAgentId = selectedPrompt?.agent_id ?? agentId
  const selName = selectedPrompt?.name ?? null

  const detailQuery = useQuery({
    queryKey: ['prompt', agentId, selAgentId, selName],
    queryFn: () => fetchPromptDetail(selAgentId, selName!),
    enabled: !!selName,
  })

  // 切换选中项时同步编辑器内容
  const currentContent = detailQuery.data?.current?.content ?? ''
  const [dirtyKey, setDirtyKey] = useState<string | null>(null)
  const activeKey = `${resolvedKey}:${currentContent}`
  useEffect(() => {
    if (dirtyKey !== activeKey) {
      setContent(currentContent)
      setDirtyKey(activeKey)
      setDiffV1(null)
      setDiffV2(null)
    }
  }, [activeKey, currentContent, dirtyKey])

  const saveMutation = useMutation({
    mutationFn: () => savePrompt(selAgentId, selName!, content),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompt', agentId, selAgentId, selName] })
      queryClient.invalidateQueries({ queryKey: ['prompts', agentId] })
    },
  })

  const submitMutation = useMutation({
    mutationFn: () => submitPrompt(selAgentId, selName!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompt', agentId, selAgentId, selName] })
      queryClient.invalidateQueries({ queryKey: ['prompts', agentId] })
    },
  })

  const previewMutation = useMutation({
    mutationFn: () => previewPrompt(content, variables),
    onSuccess: (d) => setPreview(d.rendered),
  })

  const diffQuery = useQuery({
    queryKey: ['prompt-diff', selAgentId, selName, diffV1, diffV2],
    queryFn: () => fetchPromptDiff(selAgentId!, selName!, diffV1!, diffV2!),
    enabled: !!selName && diffV1 !== null && diffV2 !== null && diffV1 !== diffV2,
  })

  const current = detailQuery.data?.current
  const hasDraft = (detailQuery.data?.history ?? []).some((h) => h.status === 'draft')

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[260px_1fr]">
      {/* 左侧：Prompt 列表 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center justify-between text-sm">
            提示词列表
            <Button variant="ghost" size="icon" className="size-6" onClick={() => listQuery.refetch()}>
              <RefreshCw className={cn('size-3.5', listQuery.isFetching && 'animate-spin')} />
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-2">
          <ScrollArea className="h-[420px]">
            {listQuery.isLoading ? (
              <div className="space-y-2 p-2">
                {[1, 2, 3].map((i) => <Skeleton key={i} className="h-8 w-full" />)}
              </div>
            ) : prompts.length === 0 ? (
              <EmptyState title="暂无提示词" description="该 Agent 未配置提示词" />
            ) : (
              <div className="space-y-1">
                {prompts.map((p) => (
                  <button
                    key={`${p.agent_id}/${p.name}`}
                    onClick={() => setSelectedKey(`${p.agent_id}/${p.name}`)}
                    className={cn(
                      'flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-xs transition-colors',
                      `${p.agent_id}/${p.name}` === resolvedKey
                        ? 'bg-primary/10 text-primary'
                        : 'hover:bg-muted'
                    )}
                  >
                    <span className="truncate font-medium">
                      {p.agent_id === 'common' ? '' : `${p.agent_id}/`}{p.name}
                    </span>
                    <Badge variant="outline" className="ml-2 shrink-0 text-[9px]">
                      v{p.version}
                    </Badge>
                  </button>
                ))}
              </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>

      {/* 右侧：编辑区 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center justify-between text-sm">
            <span className="truncate">
              {resolvedKey ? `${resolvedKey} · v${current?.version ?? '?'}` : '提示词编辑'}
            </span>
            <div className="flex shrink-0 items-center gap-2">
              <Button variant="outline" size="sm" className="gap-1.5" onClick={() => previewMutation.mutate()}>
                <Eye className="size-3.5" /> 预览
              </Button>
              <Button
                size="sm"
                className="gap-1.5"
                onClick={() => saveMutation.mutate()}
                disabled={!selName || saveMutation.isPending}
              >
                <Save className="size-3.5" /> 保存草稿
              </Button>
              <Button
                size="sm"
                variant="secondary"
                className="gap-1.5"
                onClick={() => submitMutation.mutate()}
                disabled={!hasDraft || submitMutation.isPending}
                title="提交草稿发布审批"
              >
                <Send className="size-3.5" /> 提交发布
              </Button>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {detailQuery.isLoading ? (
            <Skeleton className="h-56 w-full" />
          ) : !current && detailQuery.data?.history.length === 0 ? (
            <EmptyState title="无生效版本" description="该提示词暂无生效内容" />
          ) : (
            <>
              <Textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                className="min-h-[240px] font-mono text-xs"
                placeholder="输入提示词内容，支持 {variable} 变量"
              />
              <Tabs defaultValue="preview">
                <TabsList>
                  <TabsTrigger value="preview" className="gap-1.5">
                    <Eye className="size-3.5" /> 变量预览
                  </TabsTrigger>
                  <TabsTrigger value="history" className="gap-1.5">
                    <History className="size-3.5" /> 历史版本
                  </TabsTrigger>
                  <TabsTrigger value="diff" className="gap-1.5">
                    <GitCompareArrows className="size-3.5" /> 版本对比
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="preview" className="pt-2">
                  <div className="space-y-2">
                    <div className="flex flex-wrap gap-2">
                      {(variables && Object.keys(variables).length > 0 ? Object.keys(variables) : ['question', 'context'])
                        .map((k) => (
                          <Input
                            key={k}
                            value={variables[k] ?? ''}
                            placeholder={`{${k}}`}
                            onChange={(e) => setVariables((v) => ({ ...v, [k]: e.target.value }))}
                            className="h-8 w-40 text-xs"
                          />
                        ))}
                    </div>
                    {preview !== null && (
                      <pre className="max-h-40 overflow-auto rounded-md bg-muted p-3 text-xs text-muted-foreground">
                        {preview}
                      </pre>
                    )}
                  </div>
                </TabsContent>
                <TabsContent value="history" className="pt-2">
                  <ScrollArea className="h-40">
                    <div className="space-y-1">
                      {detailQuery.data?.history.map((h) => (
                        <div
                          key={h.version}
                          className="flex items-center justify-between rounded-md px-3 py-1.5 text-xs"
                        >
                          <span>v{h.version}</span>
                          <Badge variant={h.is_active ? 'default' : 'outline'}>
                            {STATUS_LABEL[h.status ?? (h.is_active ? 'published' : 'archived')] ?? '历史'}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                </TabsContent>
                <TabsContent value="diff" className="pt-2">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs text-muted-foreground">对比版本</span>
                      <select
                        value={diffV1 ?? ''}
                        onChange={(e) => setDiffV1(e.target.value ? Number(e.target.value) : null)}
                        className="h-8 rounded-md border bg-background px-2 text-xs"
                      >
                        <option value="">v1...</option>
                        {detailQuery.data?.history.map((h) => (
                          <option key={h.version} value={h.version}>v{h.version}</option>
                        ))}
                      </select>
                      <span className="text-xs text-muted-foreground">→</span>
                      <select
                        value={diffV2 ?? ''}
                        onChange={(e) => setDiffV2(e.target.value ? Number(e.target.value) : null)}
                        className="h-8 rounded-md border bg-background px-2 text-xs"
                      >
                        <option value="">v2...</option>
                        {detailQuery.data?.history.map((h) => (
                          <option key={h.version} value={h.version}>v{h.version}</option>
                        ))}
                      </select>
                    </div>
                    {diffQuery.isLoading ? (
                      <Skeleton className="h-40 w-full" />
                    ) : diffQuery.data ? (
                      <>
                        <div className="flex items-center gap-2 text-xs">
                          <Badge variant="outline" className="bg-emerald-500/10 text-emerald-600">
                            +{diffQuery.data.added}
                          </Badge>
                          <Badge variant="outline" className="bg-rose-500/10 text-rose-500">
                            -{diffQuery.data.removed}
                          </Badge>
                          <span className="text-muted-foreground">
                            v{diffQuery.data.v1} → v{diffQuery.data.v2}
                          </span>
                        </div>
                        <ScrollArea className="h-52 rounded-md bg-muted/40">
                          <div className="py-1">
                            {diffQuery.data.lines.map((line, i) => (
                              <DiffLine key={i} line={line} />
                            ))}
                          </div>
                        </ScrollArea>
                      </>
                    ) : (
                      <p className="text-xs text-muted-foreground">选择两个不同版本进行对比</p>
                    )}
                  </div>
                </TabsContent>
              </Tabs>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}