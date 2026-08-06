import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, Eye, RefreshCw, History } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchPrompts, fetchPromptDetail, savePrompt, previewPrompt } from '@/services/prompts'
import { cn } from '@/lib/utils'

export function PromptTab({ agentId }: { agentId: string }) {
  const queryClient = useQueryClient()
  const [content, setContent] = useState('')
  const [variables, setVariables] = useState<Record<string, string>>({})
  const [preview, setPreview] = useState<string | null>(null)

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
    }
  }, [activeKey, currentContent, dirtyKey])

  const saveMutation = useMutation({
    mutationFn: () => savePrompt(selAgentId, selName!, content),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompt', agentId, selAgentId, selName] })
      queryClient.invalidateQueries({ queryKey: ['prompts', agentId] })
    },
  })

  const previewMutation = useMutation({
    mutationFn: () => previewPrompt(content, variables),
    onSuccess: (d) => setPreview(d.rendered),
  })

  const current = detailQuery.data?.current

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
                <Save className="size-3.5" /> 保存新版本
              </Button>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {detailQuery.isLoading ? (
            <Skeleton className="h-56 w-full" />
          ) : !current ? (
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
                            {h.is_active ? '生效' : '历史'}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                </TabsContent>
              </Tabs>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}