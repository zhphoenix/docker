import * as React from 'react'
import { ExternalLink } from 'lucide-react'
import { cn } from '@/lib/utils'

/** 匹配 http/https 开头链接，遇到空白/括号/引号/尖括号等边界停止 */
const URL_RE = /(https?:\/\/[^\s)\]"'<>`，。；]+)/g

export interface LinkifiedTextProps {
  text: string
  className?: string
  /** 链接附加类名（默认主色 + 下划线 + 外链图标） */
  linkClassName?: string
}

/**
 * 将文本中的 http/https 网址自动识别并渲染为可点击超链接。
 * 链接在新标签页打开；点击事件阻止冒泡，避免触发弹窗关闭/拖拽等外层行为。
 */
export function LinkifiedText({ text, className, linkClassName }: LinkifiedTextProps) {
  const parts = React.useMemo(() => text.split(URL_RE), [text])
  return (
    <span className={className}>
      {parts.map((part, i) =>
        /^https?:\/\//.test(part) ? (
          <a
            key={i}
            href={part}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className={cn(
              'inline-flex items-center gap-0.5 break-all align-baseline text-primary underline underline-offset-2 hover:opacity-80',
              linkClassName
            )}
          >
            {part}
            <ExternalLink className="size-3 shrink-0 self-center" />
          </a>
        ) : (
          <React.Fragment key={i}>{part}</React.Fragment>
        )
      )}
    </span>
  )
}
