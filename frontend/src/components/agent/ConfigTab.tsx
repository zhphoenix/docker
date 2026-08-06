import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, RotateCcw, History } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { ScrollArea } from '@/components/ui/scroll-area'
import { fetchAgentDetail, updateAgentConfig, fetchConfigHistory, rollbackConfig } from '@/services/agents'

interface ConfigTabProps {
  agentId: string
}

function Field({
  label,
  value,
  onChange,
  type = 'number',
  step,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  type?: string
  step?: string
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <Input
        type={type}
        step={step}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-8 text-sm"
      />
    </div>
  )
}

export function ConfigTab({ agentId }: ConfigTabProps) {
  const queryClient = useQueryClient()
  const detailQuery = useQuery({
    queryKey: ['agent', agentId],
    queryFn: () => fetchAgentDetail(agentId),
  })

  const runtime = detailQuery.data?.runtime

  const [form, setForm] = useState({
    model: '',
    temperature: '',
    top_p: '',
    max_tokens: '',
    timeout: '',
    retry: '',
  })

  // 同步 runtime 到表单
  useEffect(() => {
    if (runtime) {
      setForm({
        model: runtime.model || '',
        temperature: String(runtime.temperature),
        top_p: String(runtime.top_p),
        max_tokens: String(runtime.max_tokens),
        timeout: String(runtime.timeout),
        retry: String(runtime.retry),
      })
    }
  }, [runtime?.model, runtime?.temperature, runtime?.top_p, runtime?.max_tokens, runtime?.timeout, runtime?.retry])

  const saveMutation = useMutation({
    mutationFn: () =>
      updateAgentConfig(agentId, {
        model: form.model || undefined,
        temperature: form.temperature !== '' ? Number(form.temperature) : undefined,
        top_p: form.top_p !== '' ? Number(form.top_p) : undefined,
        max_tokens: form.max_tokens !== '' ? Number(form.max_tokens) : undefined,
        timeout: form.timeout !== '' ? Number(form.timeout) : undefined,
        retry: form.retry !== '' ? Number(form.retry) : undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agent', agentId] })
      queryClient.invalidateQueries({ queryKey: ['agent-config-history', agentId] })
    },
  })

  const historyQuery = useQuery({
    queryKey: ['agent-config-history', agentId],
    queryFn: () => fetchConfigHistory(agentId),
    enabled: !!agentId,
  })

  const rollbackMutation = useMutation({
    mutationFn: (historyId: string) => rollbackConfig(agentId, historyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agent', agentId] })
      queryClient.invalidateQueries({ queryKey: ['agent-config-history', agentId] })
    },
  })

  if (detailQuery.isLoading) {
    return <Skeleton className="h-64 w-full" />
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {/* 配置表单 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center justify-between text-sm">
            运行参数
            <Button
              size="sm"
              className="gap-1.5"
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
            >
              <Save className="size-3.5" /> 保存
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-4">
          <Field label="模型 Model" value={form.model} onChange={(v) => setForm((f) => ({ ...f, model: v }))} type="text" />
          <Field label="Temperature (0-2)" value={form.temperature} onChange={(v) => setForm((f) => ({ ...f, temperature: v }))} step="0.1" />
          <Field label="Top P (0-1)" value={form.top_p} onChange={(v) => setForm((f) => ({ ...f, top_p: v }))} step="0.05" />
          <Field label="Max Tokens" value={form.max_tokens} onChange={(v) => setForm((f) => ({ ...f, max_tokens: v }))} />
          <Field label="Timeout (s)" value={form.timeout} onChange={(v) => setForm((f) => ({ ...f, timeout: v }))} />
          <Field label="Retry" value={form.retry} onChange={(v) => setForm((f) => ({ ...f, retry: v }))} />
        </CardContent>
      </Card>

      {/* 历史与回滚 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <History className="size-4 text-muted-foreground" /> 配置历史
          </CardTitle>
        </CardHeader>
        <CardContent className="p-2">
          <ScrollArea className="h-[260px]">
            {historyQuery.isLoading ? (
              <div className="space-y-2 p-2">
                {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
              </div>
            ) : (historyQuery.data?.history ?? []).length === 0 ? (
              <p className="p-3 text-xs text-muted-foreground">暂无配置修改记录</p>
            ) : (
              <div className="space-y-1 p-2">
                {historyQuery.data?.history.slice(0, 10).map((h) => (
                  <div
                    key={h.id}
                    className="flex items-center justify-between rounded-md border px-3 py-2 text-xs"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-muted-foreground">
                        temp={String(h.config.temperature ?? '-')} · top_p={String(h.config.top_p ?? '-')} · max_tokens={String(h.config.max_tokens ?? '-')}
                      </div>
                      <div className="mt-0.5 text-[10px] text-muted-foreground/70">
                        {new Date(h.created_at).toLocaleString()}
                      </div>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      className="ml-2 shrink-0 gap-1"
                      onClick={() => rollbackMutation.mutate(h.id)}
                      disabled={rollbackMutation.isPending}
                    >
                      <RotateCcw className="size-3" /> 回滚
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  )
}