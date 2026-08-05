import * as React from 'react'
import { Minus, Maximize2, Minimize2, XIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogClose } from '@/components/ui/dialog'

/** 标题栏高度（最小化时弹窗收缩为此高度） */
const HEADER_H = 44

interface Rect {
  x: number
  y: number
  w: number
  h: number
}

type DragMode = 'move' | 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'

/** 8 向缩放手柄配置 */
const HANDLES: { mode: DragMode; cls: string }[] = [
  { mode: 'n', cls: 'top-0 left-3 right-3 h-1.5 cursor-n-resize' },
  { mode: 's', cls: 'bottom-0 left-3 right-3 h-1.5 cursor-s-resize' },
  { mode: 'e', cls: 'right-0 top-3 bottom-3 w-1.5 cursor-e-resize' },
  { mode: 'w', cls: 'left-0 top-3 bottom-3 w-1.5 cursor-w-resize' },
  { mode: 'ne', cls: 'top-0 right-0 size-3 cursor-ne-resize' },
  { mode: 'nw', cls: 'top-0 left-0 size-3 cursor-nw-resize' },
  { mode: 'se', cls: 'bottom-0 right-0 size-3 cursor-se-resize' },
  { mode: 'sw', cls: 'bottom-0 left-0 size-3 cursor-sw-resize' },
]

export interface WindowedDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 标题栏内容（拖拽热区） */
  title: React.ReactNode
  /** 标题下方的副标题（可选） */
  description?: React.ReactNode
  /** 固定于底部的操作区（可选） */
  footer?: React.ReactNode
  /** 内容区自定义 className */
  contentClassName?: string
  /** 内容区是否滚动（默认 true）。为 false 时内容区不填充内边距，供撑满布局（如 ResizablePanelGroup）使用 */
  contentScroll?: boolean
  children: React.ReactNode
  defaultWidth?: number
  defaultHeight?: number
  minWidth?: number
  minHeight?: number
}

/**
 * 可自由移动/缩放/最大化/最小化的 Dialog。
 * 基于基础 Dialog 原语（保留遮罩点击关闭、ESC 关闭、焦点管理），
 * 通过内联样式接管定位实现窗口化交互。
 */
export function WindowedDialog({
  open,
  onOpenChange,
  title,
  description,
  footer,
  contentClassName,
  contentScroll = true,
  children,
  defaultWidth = 720,
  defaultHeight = 560,
  minWidth = 360,
  minHeight = 220,
}: WindowedDialogProps) {
  const [rect, setRect] = React.useState<Rect | null>(null)
  const [maximized, setMaximized] = React.useState(false)
  const [minimized, setMinimized] = React.useState(false)
  const dragStateRef = React.useRef<{
    mode: DragMode
    startX: number
    startY: number
    rect: Rect
  } | null>(null)

  // 打开时初始化为居中尺寸（用 100dvh 兜底实际可视高度，避免 fixed 定位跑出视口）
  React.useEffect(() => {
    if (open) {
      const vw = window.innerWidth
      const vh = window.visualViewport?.height ?? window.innerHeight
      const w = Math.min(defaultWidth, vw - 32)
      const h = Math.min(defaultHeight, vh - 64)
      setRect({
        x: Math.max(16, (vw - w) / 2),
        y: Math.max(16, (vh - h) / 2),
        w,
        h,
      })
      setMaximized(false)
      setMinimized(false)
    }
  }, [open, defaultWidth, defaultHeight])

  const startDrag =
    (mode: DragMode) =>
    (e: React.PointerEvent) => {
      if (!rect || maximized || minimized) return
      // 仅拦截窗口控制按钮区（标题区内的 Badge 等装饰元素不影响拖拽）
      if ((e.target as HTMLElement).closest('[data-window-controls]')) return
      e.preventDefault()
      dragStateRef.current = {
        mode,
        startX: e.clientX,
        startY: e.clientY,
        rect,
      }
      const onMove = (ev: PointerEvent) => {
        const d = dragStateRef.current
        if (!d) return
        const dx = ev.clientX - d.startX
        const dy = ev.clientY - d.startY
        const vw = window.innerWidth
        const vh = window.innerHeight
        setRect(() => {
          let { x, y, w, h } = d.rect
          if (d.mode === 'move') {
            // 保证标题栏至少部分可见
            x = Math.min(Math.max(x + dx, 64 - w), vw - 64)
            y = Math.min(Math.max(y + dy, 0), vh - HEADER_H)
          } else {
            if (d.mode.includes('e')) w = Math.max(minWidth, w + dx)
            if (d.mode.includes('s')) h = Math.max(minHeight, h + dy)
            if (d.mode.includes('w')) {
              const nw = Math.max(minWidth, w - dx)
              x += w - nw
              w = nw
            }
            if (d.mode.includes('n')) {
              const nh = Math.max(minHeight, h - dy)
              y += h - nh
              h = nh
            }
          }
          return { x, y, w, h }
        })
      }
      const onUp = () => {
        dragStateRef.current = null
        window.removeEventListener('pointermove', onMove)
        window.removeEventListener('pointerup', onUp)
      }
      window.addEventListener('pointermove', onMove)
      window.addEventListener('pointerup', onUp)
    }

  const toggleMaximize = () => {
    if (minimized) {
      setMinimized(false)
      return
    }
    setMaximized((m) => !m)
  }

  const toggleMinimize = () => setMinimized((m) => !m)

  const style: React.CSSProperties = maximized
    ? {
        left: 8,
        top: 8,
        width: 'calc(100vw - 16px)',
        height: 'calc(100dvh - 16px)',
        transform: 'none',
        translate: 'none',
        maxWidth: 'none',
      }
    : rect
      ? {
          left: rect.x,
          top: rect.y,
          width: rect.w,
          height: minimized ? HEADER_H : rect.h,
          transform: 'none',
          translate: 'none',
          maxWidth: 'none',
        }
      : {}

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        // 去除默认居中 translate 与入场动画（Tailwind v4 的 translate 为独立 CSS 属性，
        // 动画 keyframes 也会注入 translate，与手动定位冲突）
        className="flex flex-col gap-0 overflow-hidden p-0 data-open:animate-none data-closed:animate-none"
        style={style}
      >
        {/* 标题栏：拖拽热区 + 窗口控制按钮 */}
        <div
          onPointerDown={startDrag('move')}
          onDoubleClick={() => !minimized && setMaximized((m) => !m)}
          className="flex shrink-0 cursor-move select-none items-center gap-2 border-b px-4"
          style={{ height: HEADER_H }}
        >
          <div className="flex min-w-0 flex-1 flex-col justify-center gap-0.5">
            <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm font-medium">
              {title}
            </div>
            {description && (
              <div className="flex min-w-0 flex-wrap items-center gap-2 truncate text-xs text-muted-foreground">
                {description}
              </div>
            )}
          </div>
          <div
            data-window-controls
            className="flex shrink-0 items-center"
            onPointerDown={(e) => e.stopPropagation()}
          >
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={toggleMinimize}
              aria-label={minimized ? '还原' : '最小化'}
              title={minimized ? '还原' : '最小化'}
            >
              {minimized ? <Maximize2 className="size-4" /> : <Minus className="size-4" />}
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={toggleMaximize}
              aria-label={maximized ? '还原' : '最大化'}
              title={maximized ? '还原' : '最大化'}
            >
              {maximized ? (
                <Minimize2 className="size-4" />
              ) : (
                <Maximize2 className="size-4" />
              )}
            </Button>
            <DialogClose render={<Button variant="ghost" size="icon-sm" />}>
              <XIcon />
              <span className="sr-only">关闭</span>
            </DialogClose>
          </div>
        </div>

        {/* 内容区：默认滚动，可通过 contentScroll/contentClassName 定制 */}
        {!minimized && (
          <div
            className={cn(
              'min-h-0 flex-1',
              contentScroll ? 'overflow-y-auto p-4' : 'overflow-hidden p-0',
              contentClassName
            )}
          >
            {children}
          </div>
        )}

        {/* 底部操作区（可选） */}
        {footer && !minimized && (
          <div className="shrink-0 border-t px-4 py-3">{footer}</div>
        )}

        {/* 缩放手柄（最大化/最小化时隐藏） */}
        {!maximized &&
          !minimized &&
          HANDLES.map((h) => (
            <div
              key={h.mode}
              onPointerDown={startDrag(h.mode)}
              className={cn('absolute z-10', h.cls)}
            />
          ))}
      </DialogContent>
    </Dialog>
  )
}
