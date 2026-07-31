import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Search, Users } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchEntities, type KnowledgeEntity } from '@/services/knowledge'
import { EntityDetailDialog } from './EntityDetailDialog'

export function EntityBrowser() {
  const [search, setSearch] = useState('')
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

  const entitiesQuery = useQuery({
    queryKey: ['knowledge-entities', debouncedSearch],
    queryFn: () => fetchEntities({ name: debouncedSearch || undefined, limit: 50 }),
    retry: 1,
  })

  const entities = entitiesQuery.data?.entities ?? []

  return (
    <div className="space-y-4">
      {/* Search Filter */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" strokeWidth={1.8} />
        <Input
          placeholder="搜索实体名称..."
          className="pl-9"
          value={search}
          onChange={(e) => handleSearchChange(e.target.value)}
        />
      </div>

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
          title={debouncedSearch ? '未找到匹配实体' : '暂无实体数据'}
          description={
            debouncedSearch
              ? `未找到名称包含「${debouncedSearch}」的实体`
              : '知识图谱中尚未提取任何实体，请先运行知识提取任务'
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
            共 {entitiesQuery.data?.total ?? 0} 个实体 · 点击行查看详情
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
