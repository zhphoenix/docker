import { useState } from 'react'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Combobox } from '@/components/ui/combobox'
import { useAddWatchlist, useWatchlistItems } from '@/hooks/useWatchlist'
import { lookupStock } from '@/services/watchlist'
import { useDebounce } from '@/hooks/useDebounce'
import { useRef, useEffect, useCallback } from 'react'
import { Loader2 } from 'lucide-react'

export function AddStockDialog() {
  const [open, setOpen] = useState(false)
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [market, setMarket] = useState('')
  const [group, setGroup] = useState('')
  const [tags, setTags] = useState('')
  const [itemType, setItemType] = useState('stock')
  const [groupOptions, setGroupOptions] = useState<string[]>(['顶级持仓', '科技', '消费'])
  const [lookupLoading, setLookupLoading] = useState(false)
  const lastEditedRef = useRef<'code' | 'name'>('code')
  const suppressLookupRef = useRef(false)
  const lookupInputRef = useRef<{ kind: 'code' | 'name'; input: string } | null>(null)

  const { data: itemsData } = useWatchlistItems()
  const addMutation = useAddWatchlist()

  // Code lookup
  const debouncedCode = useDebounce(code, 400)
  useEffect(() => {
    const c = debouncedCode.trim()
    if (!c || lastEditedRef.current !== 'code') return
    let cancelled = false
    lookupInputRef.current = { kind: 'code', input: c }
    setLookupLoading(true)
    lookupStock({ code: c, market: market || undefined })
      .then((res) => {
        if (cancelled || suppressLookupRef.current || !res.item) return
        if (lookupInputRef.current?.kind !== 'code' || lookupInputRef.current.input !== c) return
        if (res.item.company_name) setName(res.item.company_name)
        if (res.item.market) setMarket(res.item.market)
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLookupLoading(false) })
    return () => { cancelled = true }
  }, [debouncedCode, market])

  // Name reverse lookup
  const debouncedName = useDebounce(name, 400)
  useEffect(() => {
    const n = debouncedName.trim()
    if (!n || lastEditedRef.current !== 'name') return
    let cancelled = false
    lookupInputRef.current = { kind: 'name', input: n }
    setLookupLoading(true)
    lookupStock({ name: n, market: market || undefined })
      .then((res) => {
        if (cancelled || suppressLookupRef.current || !res.item) return
        if (lookupInputRef.current?.kind !== 'name' || lookupInputRef.current.input !== n) return
        if (res.item.symbol) setCode(res.item.symbol)
        if (res.item.market) setMarket(res.item.market)
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLookupLoading(false) })
    return () => { cancelled = true }
  }, [debouncedName, market])

  const handleGroupChange = useCallback((v: string) => {
    setGroup(v)
    if (v && !groupOptions.includes(v)) {
      setGroupOptions((prev) => [...prev, v])
    }
  }, [groupOptions])

  const reset = () => {
    setCode('')
    setName('')
    setMarket('')
    setGroup('')
    setTags('')
    setItemType('stock')
    suppressLookupRef.current = true
    lookupInputRef.current = null
  }

  const handleAdd = async () => {
    if (!code.trim()) return
    const normalized = code.trim().toUpperCase()
    const existing = (itemsData?.items ?? []).find(
      (it) => it.stock_code.trim().toUpperCase() === normalized
    )
    if (existing) {
      return // Duplicate silently ignored
    }
    try {
      await addMutation.mutateAsync({
        stock_code: code.trim(),
        stock_name: name.trim() || code.trim(),
        market: market.trim() || undefined,
        group_name: group.trim() || undefined,
        tags: tags.split(/[,，]/).map((t) => t.trim()).filter(Boolean),
        item_type: itemType,
      })
      reset()
      setOpen(false)
    } catch {
      // Error handled by mutation state
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button />}>
        <Plus className="mr-1 size-4" /> 添加股票
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>添加自选股</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <Select value={itemType} onValueChange={(v) => setItemType(v ?? 'stock')}>
            <SelectTrigger>
              <SelectValue placeholder="监控对象类型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="stock">股票</SelectItem>
              <SelectItem value="etf">ETF</SelectItem>
              <SelectItem value="index">指数</SelectItem>
              <SelectItem value="industry">行业</SelectItem>
              <SelectItem value="company">公司</SelectItem>
              <SelectItem value="person">人物</SelectItem>
              <SelectItem value="fund">基金</SelectItem>
              <SelectItem value="macro_theme">宏观主题</SelectItem>
            </SelectContent>
          </Select>
          <Select value={market} onValueChange={(v) => setMarket(v === 'auto' ? '' : (v ?? ''))}>
            <SelectTrigger>
              <SelectValue placeholder="市场" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">自动识别</SelectItem>
              <SelectItem value="cn">A股</SelectItem>
              <SelectItem value="hk">港股</SelectItem>
              <SelectItem value="us">美股</SelectItem>
            </SelectContent>
          </Select>
          <div className="relative">
            <Input
              placeholder="股票代码 *"
              value={code}
              onChange={(e) => {
                suppressLookupRef.current = false
                lookupInputRef.current = null
                lastEditedRef.current = 'code'
                setCode(e.target.value)
              }}
            />
            {lookupLoading && (
              <Loader2 className="absolute right-3 top-3 size-4 animate-spin text-muted-foreground" />
            )}
          </div>
          <Input
            placeholder="股票名称（自动填充）"
            value={name}
            onChange={(e) => {
              suppressLookupRef.current = false
              lookupInputRef.current = null
              lastEditedRef.current = 'name'
              setName(e.target.value)
            }}
          />
          <Combobox
            value={group}
            onValueChange={handleGroupChange}
            options={groupOptions}
            placeholder="分组（可新建）"
            clearLabel="未分组"
            creatable
            createLabel={(q) => `新建分组 "${q}"`}
          />
          <Input
            placeholder="标签（逗号分隔）"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
          />
          {addMutation.isError && (
            <p className="text-sm text-destructive">
              添加失败：{(addMutation.error as Error)?.message || '未知错误'}
            </p>
          )}
          <Button onClick={handleAdd} disabled={addMutation.isPending || !code.trim()}>
            {addMutation.isPending ? (
              <Loader2 className="mr-1 size-4 animate-spin" />
            ) : (
              <Plus className="mr-1 size-4" />
            )}
            添加
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
