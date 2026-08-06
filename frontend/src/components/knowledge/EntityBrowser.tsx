import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Search, Users, Boxes, SlidersHorizontal } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { EmptyState } from '@/components/common/EmptyState'
import {
  fetchEntities,
  fetchEntityTypes,
  type KnowledgeEntity,
} from '@/services/knowledge'
import { EntityDetailDialog } from './EntityDetailDialog'
import { cn } from '@/lib/utils'

const TYPE_COLORS = [
  'bg-blue-500/10 text-blue-600',
  'bg-emerald-500/10 text-emerald-600',
  'bg-amber-500/10 text-amber-600',
  'bg-purple-500/10 text-purple-600',
  'bg-rose-500/10 text-rose-600',
  'bg-cyan-500/10 text-cyan-600',
  'bg-orange-500/10 text-orange-600',
  'bg-teal-500/10 text-teal-600',
  'bg-indigo-500/10 text-indigo-600',
  'bg-pink-500/10 text-pink-600',
]

export function EntityBrowser() {
  const [search, setSearch] = useState('')
  const [entityType, setEntityType] = useState('')
  const [minConfidence, setMinConfidence] = useState('')
  const [minSourceCount, setMinSourceCount] = useState('')
  const [selectedEntity, setSelectedEntity] = useState<KnowledgeEntity | null>(null)

  // Debounce: 使用 useMemo 延迟查询 key 更新
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const debounceTimer = useMemo(() => {
    return { current: null as ReturnType<typeof setTimeout> | null }
  }, [])

  const handleSearchChange = (value: string) => {
    setSearch(value)
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => setDebouncedSearch(value), 300)
  }

  const hasFilter =
    debouncedSearch !== '' ||
    entityType !== '' ||
    minConfidence !== '' ||
    minSourceCount !== ''

  const params = useMemo(() => {
    const p: {
      name?: string
      entity_type?: string
      min_confidence?: number
      min_source_count?: number
      limit: number
    } = { limit: 50 }
    if (debouncedSearch) p.name = debouncedSearch
    if (entityType) p.entity_type = entityType
    if (minConfidence && Number(minConfidence) > 0) p.min_confidence = Number(minConfidence)
    if (minSourceCount && Number(minSourceCount) > 0) p.min_source_count = Number(minSourceCount)
    return p
  }, [debouncedSearch, entityType, minConfidence, minSourceCount])

  const typesQuery = useQuery({
    queryKey: ['knowledge-entity-types'],
    queryFn: fetchEntityTypes,
    retry: 1,
  })

  const entitiesQuery = useQuery({
    queryKey: ['knowledge-entities', params],
    queryFn: () => fetchEntities(params),
    retry: 1,
  })

  const entities = entitiesQuery.data?.entities ?? []
  const types = typesQuery.data?.types ?? []

  const handleTypeSelect = (value: string | null) => {
    // 'all' 表示清除类型过滤
    setEntityType(!value || value === 'all' ? '' : value)
  }

  const handleClearFilters = () => {
    setSearch('')
    setDebouncedSearch('')
    setEntityType('')
    setMinConfidence('')
    setMinSourceCount('')
  }

  return (
    <div className="space-y-4">
      {/* 类型统计卡 */}
      <div>
        <div className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <Boxes className="size-4" strokeWidth={1.8} />
          实体类型统计
          <span className="text-xs text-muted-foreground/70">
            （点击卡片快速筛选）
          </span>
        </div>
        {typesQuery.isLoading ? (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-5">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-16 w-full rounded-lg" />
            ))}
          </div>
        ) : types.length === 0 ? (
          <p className="text-xs text-muted-foreground">暂无实体类型数据</p>
        ) : (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-5">
            {types.slice(0, 10).map((t, i) => {
              const active = entityType === t.entity_type
              return (
                <button
                  key={t.entity_type}
                  onClick={() => handleTypeSelect(active ? 'all' : t.entity_type)}
                  className={cn(
                    'rounded-lg border p-3 text-left transition-all',
                    active
                      ? 'border-primary bg-primary/5 ring-1 ring-primary/40'
                      : 'border-border hover:border-primary/40 hover:bg-muted/50'
                  )}
                >
                  <p className={cn('text-sm font-semibold', TYPE_COLORS[i % TYPE_COLORS.length])}>
                    {t.entity_type}
                  </p>
                  <p className="mt-0.5 text-lg font-bold tabular-nums">{t.count}</p>
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* 快速筛选 */}
      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <SlidersHorizontal className="size-4" strokeWidth={1.8} />
            快速筛选
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div className="relative min-w-40 flex-1">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" strokeWidth={1.8} />
              <Input
                placeholder="搜索实体名称..."
                className="pl-9"
                value={search}
                onChange={(e) => handleSearchChange(e.target.value)}
              />
            </div>
            <div className="w-36">
              <Select value={entityType || 'all'} onValueChange={handleTypeSelect}>
                <SelectTrigger className="text-xs">
                  <SelectValue placeholder="全部类型" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部类型</SelectItem>
                  {types.map((t) => (
                    <SelectItem key={t.entity_type} value={t.entity_type}>
                      {t.entity_type} ({t.count})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="w-32">
              <Select
                value={minConfidence || '0'}
                onValueChange={(v) => setMinConfidence(!v || v === '0' ? '' : v)}
              >
                <SelectTrigger className="text-xs">
                  <SelectValue placeholder="置信度" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="0">全部置信度</SelectItem>
                  <SelectItem value="0.9">≥ 90%</SelectItem>
                  <SelectItem value="0.8">≥ 80%</SelectItem>
                  <SelectItem value="0.6">≥ 60%</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="w-32">
              <Select
                value={minSourceCount || '0'}
                onValueChange={(v) => setMinSourceCount(!v || v === '0' ? '' : v)}
              >
                <SelectTrigger className="text-xs">
                  <SelectValue placeholder="来源数" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="0">全部来源数</SelectItem>
                  <SelectItem value="2">≥ 2 篇</SelectItem>
                  <SelectItem value="3">≥ 3 篇</SelectItem>
                  <SelectItem value="5">≥ 5 篇</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {hasFilter && (
              <Button variant="ghost" size="sm" onClick={handleClearFilters}>
                清除筛选
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Loading */}
      {entitiesQuery.isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-12 w-full rounded-lg" />
          ))}
        </div>
      ) : entitiesQuery.isError ? (
        <EmptyState
          icon={Users}
          title="无法加载实体"
          description="查询知识图谱实体失败，请确认后端服务正常"
          action={{ label: '重试', onClick: () => entitiesQuery.refetch() }}
        />
      ) : entities.length === 0 ? (
        <EmptyState
          icon={Users}
          title={hasFilter ? '未找到匹配实体' : '暂无实体数据'}
          description={
            hasFilter
              ? '请调整筛选条件后重试'
              : '知识图谱中尚未提取任何实体，请先运行知识提取任务'
          }
          action={
            hasFilter
              ? { label: '清除筛选', onClick: handleClearFilters }
              : undefined
          }
        />
      ) : (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[200px]">名称</TableHead>
                    <TableHead className="w-[120px]">类型</TableHead>
                    <TableHead>描述</TableHead>
                    <TableHead className="w-[80px] text-right">来源数</TableHead>
                    <TableHead className="w-[80px] text-right">置信度</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {entities.map((entity) => (
                    <TableRow
                      key={entity.id}
                      className="cursor-pointer transition-colors hover:bg-muted/50"
                      onClick={() => setSelectedEntity(entity)}
                    >
                      <TableCell className="font-medium">{entity.name}</TableCell>
                      <TableCell>
                        <Badge variant="secondary" className="text-[10px]">
                          {entity.entity_type}
                        </Badge>
                      </TableCell>
                      <TableCell className="max-w-[300px] truncate text-xs text-muted-foreground">
                        {entity.description || '—'}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {entity.source_count}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {entity.confidence != null ? `${Math.round(entity.confidence * 100)}%` : '—'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
          <p className="mt-2 text-xs text-muted-foreground">
            共 {entitiesQuery.data?.total ?? 0} 个实体 · 点击行查看知识卡
          </p>
        </motion.div>
      )}

      {/* Detail Dialog */}
      <EntityDetailDialog
        entity={selectedEntity}
        onClose={() => setSelectedEntity(null)}
      />
    </div>
  )
}