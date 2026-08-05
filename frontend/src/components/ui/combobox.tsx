import * as React from 'react'
import { createPortal } from 'react-dom'
import { Check, ChevronsUpDown, Plus } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'

/**
 * 可下拉选择 + 支持自定义输入新建选项的 Combobox
 */
export function Combobox({
  value,
  onValueChange,
  options,
  placeholder = '请选择',
  emptyText = '无匹配',
  clearLabel,
  creatable = false,
  createLabel = (q) => `创建 "${q}"`,
}: {
  value: string
  onValueChange: (v: string) => void
  options: string[]
  placeholder?: string
  emptyText?: string
  clearLabel?: string
  creatable?: boolean
  createLabel?: (query: string) => string
}) {
  const [open, setOpen] = React.useState(false)
  const [query, setQuery] = React.useState('')
  const containerRef = React.useRef<HTMLDivElement>(null)
  const [pos, setPos] = React.useState<{
    top: number
    left: number
    width: number
  } | null>(null)

  // 计算按钮位置，浮层以 fixed 定位到 body，避免被父级 overflow 裁剪
  const updatePos = React.useCallback(() => {
    const el = containerRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    setPos({ top: r.bottom + 4, left: r.left, width: r.width })
  }, [])

  const toggleOpen = () => {
    if (!open) updatePos()
    setOpen((o) => !o)
  }

  // 打开时监听滚动/缩放，保持浮层贴合按钮
  React.useEffect(() => {
    if (!open) return
    updatePos()
    const onScroll = () => updatePos()
    window.addEventListener('scroll', onScroll, true)
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll, true)
      window.removeEventListener('resize', onScroll)
    }
  }, [open, updatePos])

  const trimmed = query.trim()
  const filtered = trimmed
    ? options.filter((o) => o.toLowerCase().includes(trimmed.toLowerCase()))
    : options

  const canCreate =
    creatable && trimmed.length > 0 && !options.some((o) => o === trimmed)

  const select = (v: string) => {
    onValueChange(v)
    setOpen(false)
    setQuery('')
  }

  return (
    <div className="relative" ref={containerRef}>
      <Button
        type="button"
        variant="outline"
        role="combobox"
        aria-expanded={open}
        className="w-full justify-between font-normal"
        onClick={toggleOpen}
      >
        {value ? (
          <span className="truncate">{value}</span>
        ) : (
          <span className="text-muted-foreground">{placeholder}</span>
        )}
        <ChevronsUpDown className="ml-2 size-4 shrink-0 opacity-50" />
      </Button>
      {open &&
        pos &&
        createPortal(
          <div
            className="fixed z-50 w-max max-w-md rounded-xl bg-popover text-popover-foreground shadow-lg ring-1 ring-foreground/10"
            style={{ top: pos.top, left: pos.left, minWidth: pos.width }}
          >
            <Command>
              <CommandInput
                placeholder={placeholder}
                value={query}
                onValueChange={setQuery}
              />
              {/* 内联样式覆盖 CommandList 默认的 overflow-x-hidden：
                  overflow auto 使选项过多时出现垂直滑块(上下滑动)、超长单行文字出现水平滑块(左右滑动)；
                  maxHeight 限制下拉区域高度，避免挫破页面 */}
              <CommandList style={{ overflow: 'auto', maxHeight: 260 }}>
                <CommandEmpty>{emptyText}</CommandEmpty>
                <CommandGroup>
                  {clearLabel && (
                    <CommandItem
                      value="__clear__"
                      onSelect={() => select('')}
                      className="whitespace-nowrap"
                    >
                      <Check
                        className={cn(
                          'mr-2 size-4',
                          value === '' ? 'opacity-100' : 'opacity-0'
                        )}
                      />
                      {clearLabel}
                    </CommandItem>
                  )}
                  {filtered.map((o) => (
                    <CommandItem
                      key={o}
                      value={o}
                      onSelect={() => select(o)}
                      className="whitespace-nowrap"
                    >
                      <Check
                        className={cn(
                          'mr-2 size-4',
                          value === o ? 'opacity-100' : 'opacity-0'
                        )}
                      />
                      {o}
                    </CommandItem>
                  ))}
                  {canCreate && (
                    <CommandItem
                      value={trimmed}
                      onSelect={() => select(trimmed)}
                      className="whitespace-nowrap"
                    >
                      <Plus className="mr-2 size-4" />
                      {createLabel(trimmed)}
                    </CommandItem>
                  )}
                </CommandGroup>
              </CommandList>
            </Command>
          </div>,
          document.body
        )}
    </div>
  )
}