import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { FlaskConical, CheckCircle2, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { createResearch } from '@/services/research'

interface Props {
  /** 研究问题（用于触发 Research Workflow） */
  question: string
  /** 关联标的（可选，用于去重与投研上下文） */
  symbol?: string
  /** 市场（cn / hk / us） */
  market?: string
  /** 紧凑模式：仅图标按钮 */
  compact?: boolean
}

/**
 * NIC-D3 Research Trigger：事件/新闻卡片的一键研究触发动作。
 * 仅负责触发 /api/research + 确认弹窗，跳转 Research 页跟踪，不承载研究逻辑。
 */
export function ResearchActions({ question, symbol, market, compact }: Props) {
  const navigate = useNavigate()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [fedBack, setFedBack] = useState<{ kind: 'success' | 'error'; msg: string } | null>(null)

  const mutation = useMutation({
    mutationFn: () => createResearch({ question, symbol, market }),
    onSuccess: (res) => {
      setConfirmOpen(false)
      setFedBack({
        kind: 'success',
        msg: res.duplicate ? (res.message ?? '已存在进行中的研究任务，已复用') : '研究任务已创建',
      })
      // 跳转 Research 页跟踪任务
      navigate('/research')
    },
    onError: (err: Error) => {
      setFedBack({ kind: 'error', msg: err.message || '研究任务创建失败' })
    },
  })

  const handleConfirm = () => {
    mutation.mutate()
  }

  return (
    <>
      <Button
        variant="outline"
        size={compact ? 'icon-sm' : 'sm'}
        className="gap-1.5"
        onClick={() => setConfirmOpen(true)}
        title="触发深度研究"
      >
        <FlaskConical className="size-3.5" />
        {!compact && '深度研究'}
      </Button>

      {fedBack && (
        <span
          className={
            fedBack.kind === 'success'
              ? 'inline-flex items-center gap-1 text-[11px] text-green-600'
              : 'inline-flex items-center gap-1 text-[11px] text-destructive'
          }
        >
          {fedBack.kind === 'success' ? (
            <CheckCircle2 className="size-3" />
          ) : (
            <CheckCircle2 className="size-3 text-destructive" />
          )}
          {fedBack.msg}
        </span>
      )}

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>确认触发深度研究?</DialogTitle>
            <DialogDescription className="line-clamp-3">
              将基于「{question}」创建一条 Research 任务并跳转到研究页跟踪进展。
              {symbol ? `（关联标的：${symbol}）` : ''}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)} disabled={mutation.isPending}>
              取消
            </Button>
            <Button onClick={handleConfirm} disabled={mutation.isPending} className="gap-1.5">
              {mutation.isPending && <Loader2 className="size-3.5 animate-spin" />}
              确认触发
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}