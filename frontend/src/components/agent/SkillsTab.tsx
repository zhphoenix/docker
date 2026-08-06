import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Sparkles } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchSkills, toggleSkill, reloadSkills } from '@/services/skills'
import { cn } from '@/lib/utils'

export function SkillsTab() {
  const queryClient = useQueryClient()

  const listQuery = useQuery({
    queryKey: ['skills'],
    queryFn: fetchSkills,
  })

  const toggleMutation = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      toggleSkill(name, enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['skills'] }),
  })

  const reloadMutation = useMutation({
    mutationFn: reloadSkills,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['skills'] }),
  })

  const skills = listQuery.data ?? []

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-sm">
          <span className="flex items-center gap-1.5">
            <Sparkles className="size-4 text-muted-foreground" /> Skill 技能（{skills.length}）
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => reloadMutation.mutate()}
              disabled={reloadMutation.isPending}
            >
              <RefreshCw className={cn('size-3.5', reloadMutation.isPending && 'animate-spin')} />
              重载
            </Button>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {listQuery.isLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
          </div>
        ) : skills.length === 0 ? (
          <EmptyState title="暂无 Skill" description="后端未注册任何技能能力" />
        ) : (
          <div className="space-y-2">
            {skills.map((s) => (
              <div
                key={s.name}
                className="flex items-start justify-between gap-3 rounded-lg border bg-card p-3"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-semibold">{s.name}</span>
                    <Badge variant="outline" className="text-[9px]">v{s.version}</Badge>
                    <Badge
                      variant={s.enabled ? 'default' : 'secondary'}
                      className="text-[9px]"
                    >
                      {s.enabled ? '启用' : '禁用'}
                    </Badge>
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{s.description}</p>
                  {s.tags && s.tags.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {s.tags.map((t) => (
                        <Badge key={t} variant="outline" className="text-[9px] text-muted-foreground">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
                <Button
                  variant={s.enabled ? 'default' : 'outline'}
                  size="sm"
                  className="shrink-0"
                  onClick={() => toggleMutation.mutate({ name: s.name, enabled: !s.enabled })}
                  disabled={toggleMutation.isPending}
                >
                  {s.enabled ? '禁用' : '启用'}
                </Button>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}