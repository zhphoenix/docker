import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { ClipboardCheck, RefreshCw, Check, X, Inbox } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { EmptyState } from '@/components/common/EmptyState'
import {
  fetchPendingApprovals,
  approveApproval,
  rejectApproval,
} from '@/services/approvals'
import { cn } from '@/lib/utils'

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.05 } },
}

const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3 } },
}

function formatActionType(t: string): string {
  const map: Record<string, string> = {
    knowledge_inbox_approve: '知识实体审核',
    vault_write: '写入 Vault',
    report_publish: '报告发布',
  }
  return map[t] ?? t
}

export default function KnowledgeReviewPage() {
  const queryClient = useQueryClient()
  const [rejectingId, setRejectingId] = useState<string | null>(null)
  const [reason, setReason] = useState('')

  const approvalsQuery = useQuery({
    queryKey: ['pending-approvals'],
    queryFn: () => fetchPendingApprovals(50),
    retry: 1,
  })

  const approvals = approvalsQuery.data?.approvals ?? []

  const approveMutation = useMutation({
    mutationFn: (id: string) => approveApproval(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pending-approvals'] })
    },
  })

  const rejectMutation = useMutation({
    mutationFn: (id: string) => rejectApproval(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pending-approvals'] })
      setRejectingId(null)
      setReason('')
    },
  })

  const handleRefresh = () => approvalsQuery.refetch()

  return (
    <div className="mx-auto max-w-5xl space-y-8 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-foreground">
            <ClipboardCheck className="size-6 text-primary" />
            知识审核中心
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            人工审核 AI 提取的知识实体（Knowledge Inbox HITL 审核流）
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="gap-2"
          onClick={handleRefresh}
          disabled={approvalsQuery.isLoading}
        >
          <RefreshCw
            className={cn('size-3.5', (approvalsQuery.isFetching || approveMutation.isPending || rejectMutation.isPending) && 'animate-spin')}
          />
          刷新
        </Button>
      </div>

      {/* Content */}
      {approvalsQuery.isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardContent className="p-5">
                <Skeleton className="h-4 w-1/3" />
                <Skeleton className="mt-3 h-3 w-full" />
                <Skeleton className="mt-2 h-3 w-2/3" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : approvalsQuery.isError ? (
        <EmptyState
          icon={Inbox}
          title="无法加载待审核任务"
          description="无法连接到后端服务，请确认 LangGraph 服务已启动（端口 8100）"
          action={{ label: '重试', onClick: handleRefresh }}
        />
      ) : approvals.length === 0 ? (
        <EmptyState
          icon={ClipboardCheck}
          title="暂无待审核任务"
          description="所有知识实体均已审核通过，或暂无可审内容"
        />
      ) : (
        <motion.div
          variants={container}
          initial="hidden"
          animate="show"
          className="space-y-4"
        >
          {approvals.map((approval) => {
            let preview: Record<string, unknown> | null = null
            try {
              const parsed = JSON.parse(approval.content_preview || '{}')
              if (parsed && typeof parsed === 'object') preview = parsed
            } catch {
              preview = null
            }

            const name = preview?.name
            const entityType = preview?.entity_type
            const description = preview?.description
            const confidence = preview?.confidence

            const nameStr = name ? String(name) : ''
            const entityTypeStr = entityType ? String(entityType) : ''
            const descriptionStr = description ? String(description) : ''

            return (
              <motion.div key={approval.id} variants={item}>
                <Card className="transition-shadow duration-200 hover:shadow-[var(--shadow-soft)]">
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold text-foreground">
                            {approval.title}
                          </span>
                          <Badge variant="secondary" className="text-[10px]">
                            {formatActionType(approval.action_type)}
                          </Badge>
                          {entityTypeStr && (
                            <Badge variant="outline" className="text-[10px]">
                              {entityTypeStr}
                            </Badge>
                          )}
                          {typeof confidence === 'number' && (
                            <Badge
                              variant={confidence >= 0.7 ? 'default' : 'secondary'}
                              className="text-[10px]"
                            >
                              {(confidence * 100).toFixed(0)}% 置信
                            </Badge>
                          )}
                        </div>

                        {descriptionStr && (
                          <p className="mt-2 line-clamp-2 text-xs text-muted-foreground">
                            {nameStr ? <span className="font-medium text-foreground">{nameStr}：</span> : null}
                            {descriptionStr}
                          </p>
                        )}

                        {approval.created_at && (
                          <p className="mt-2 text-[11px] text-muted-foreground/60">
                            创建: {approval.created_at.replace('T', ' ').slice(0, 19)}
                            {approval.created_by ? ` · 来源: ${approval.created_by}` : ''}
                          </p>
                        )}
                      </div>

                      {/* Actions */}
                      <div className="flex shrink-0 flex-col items-end gap-2">
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            variant="default"
                            className="gap-1.5"
                            onClick={() => approveMutation.mutate(approval.id)}
                            disabled={approveMutation.isPending || rejectMutation.isPending}
                          >
                            <Check className="size-3.5" />
                            通过
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="gap-1.5 text-destructive hover:bg-destructive/10"
                            onClick={() => setRejectingId(rejectingId === approval.id ? null : approval.id)}
                            disabled={approveMutation.isPending || rejectMutation.isPending}
                          >
                            <X className="size-3.5" />
                            拒绝
                          </Button>
                        </div>

                        {rejectingId === approval.id && (
                          <div className="flex w-64 flex-col gap-2">
                            <Textarea
                              value={reason}
                              onChange={(e) => setReason(e.target.value)}
                              placeholder="拒绝原因（可选）"
                              rows={2}
                              className="text-xs"
                            />
                            <div className="flex justify-end gap-2">
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => { setRejectingId(null); setReason('') }}
                              >
                                取消
                              </Button>
                              <Button
                                size="sm"
                                variant="destructive"
                                className="gap-1.5"
                                onClick={() => rejectMutation.mutate(approval.id)}
                                disabled={rejectMutation.isPending}
                              >
                                <X className="size-3.5" />
                                确认拒绝
                              </Button>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )
          })}
        </motion.div>
      )}

      {/* Footer note */}
      <p className="text-center text-xs text-muted-foreground">
        审核通过后知识实体将正式入库 · 审核记录保存在 audit.knowledge_review_log
      </p>
    </div>
  )
}