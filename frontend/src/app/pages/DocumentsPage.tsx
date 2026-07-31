import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { FileText, RefreshCw, Search, ChevronLeft, ChevronRight } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchDocuments, fetchDocumentStats } from '@/services/documents'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 50

const STATUS_VARIANTS: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  parsed: 'default',
  embedded: 'default',
  pending: 'secondary',
  parsing: 'secondary',
  error: 'destructive',
  failed: 'destructive',
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

export default function DocumentsPage() {
  const [status, setStatus] = useState<string>('')
  const [market, setMarket] = useState<string>('')
  const [symbol, setSymbol] = useState('')
  const [page, setPage] = useState(1)

  const docsQuery = useQuery({
    queryKey: ['documents', status, market, symbol, page],
    queryFn: () =>
      fetchDocuments({
        status: status || undefined,
        market: market || undefined,
        symbol: symbol || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    retry: 1,
  })

  // 独立 query：stats 失败不影响列表
  const statsQuery = useQuery({
    queryKey: ['document-stats'],
    queryFn: fetchDocumentStats,
    retry: 1,
  })

  const documents = docsQuery.data?.documents ?? []
  const total = docsQuery.data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const byStatus = statsQuery.data?.by_status ?? {}
  const totalDocs = statsQuery.data?.total ?? 0

  const handleFilterChange = (setter: (v: string) => void) => (value: string | null) => {
    setter(value === 'all' || value == null ? '' : value)
    setPage(1)
  }

  const handleRefresh = () => {
    docsQuery.refetch()
    statsQuery.refetch()
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">文档管理</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            年报文档的解析、分块与向量化状态
          </p>
        </div>
        <Button variant="outline" size="sm" className="gap-2" onClick={handleRefresh}>
          <RefreshCw className={cn('size-3.5', docsQuery.isFetching && 'animate-spin')} />
          刷新
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {statsQuery.isLoading ? (
          [1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-20" />)
        ) : (
          <>
            <Card>
              <CardContent className="p-4">
                <div className="text-xs font-medium text-muted-foreground">文档总数</div>
                <div className="mt-1 text-2xl font-bold text-foreground">{totalDocs}</div>
              </CardContent>
            </Card>
            {(['pending', 'parsed', 'embedded'] as const).map((s) => (
              <Card key={s}>
                <CardContent className="p-4">
                  <div className="text-xs font-medium text-muted-foreground capitalize">{s}</div>
                  <div className="mt-1 text-2xl font-bold text-foreground">
                    {byStatus[s] ?? 0}
                  </div>
                </CardContent>
              </Card>
            ))}
          </>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-56">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="搜索股票代码 / 公司名"
            className="pl-9"
            value={symbol}
            onChange={(e) => {
              setSymbol(e.target.value)
              setPage(1)
            }}
          />
        </div>
        <Select value={status || 'all'} onValueChange={handleFilterChange(setStatus)}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="状态" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            <SelectItem value="pending">pending</SelectItem>
            <SelectItem value="parsing">parsing</SelectItem>
            <SelectItem value="parsed">parsed</SelectItem>
            <SelectItem value="embedded">embedded</SelectItem>
            <SelectItem value="error">error</SelectItem>
          </SelectContent>
        </Select>
        <Select value={market || 'all'} onValueChange={handleFilterChange(setMarket)}>
          <SelectTrigger className="w-32">
            <SelectValue placeholder="市场" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部市场</SelectItem>
            <SelectItem value="a">A 股</SelectItem>
            <SelectItem value="h">港股</SelectItem>
            <SelectItem value="us">美股</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {docsQuery.isLoading ? (
            <div className="space-y-3 p-6">
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-8 w-full" />
              ))}
            </div>
          ) : docsQuery.isError ? (
            <EmptyState
              icon={FileText}
              title="无法加载文档列表"
              description="无法连接到后端服务，请确认 LangGraph 服务已启动（端口 8100）"
              action={{ label: '重试', onClick: handleRefresh }}
            />
          ) : documents.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="暂无文档"
              description="当前筛选条件下没有文档，请调整筛选条件或稍后再试"
            />
          ) : (
            <>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>代码</TableHead>
                      <TableHead>公司</TableHead>
                      <TableHead>年份</TableHead>
                      <TableHead>类型</TableHead>
                      <TableHead>状态</TableHead>
                      <TableHead className="text-right">分块数</TableHead>
                      <TableHead>更新时间</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {documents.map((doc) => (
                      <TableRow key={doc.id}>
                        <TableCell className="font-medium">
                          <span className="text-foreground">{doc.symbol}</span>
                          <span className="ml-1.5 text-[10px] uppercase text-muted-foreground">
                            {doc.market}
                          </span>
                        </TableCell>
                        <TableCell className="max-w-[180px] truncate text-muted-foreground">
                          {doc.company ?? '—'}
                        </TableCell>
                        <TableCell className="text-muted-foreground">{doc.year}</TableCell>
                        <TableCell className="text-muted-foreground">{doc.document_type}</TableCell>
                        <TableCell>
                          <Badge
                            variant={STATUS_VARIANTS[doc.status] ?? 'outline'}
                            className="text-[10px]"
                          >
                            {doc.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">
                          {doc.chunk_count}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {formatDate(doc.updated_at)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {/* Pagination */}
              <div className="flex items-center justify-between border-t border-border px-4 py-3">
                <span className="text-xs text-muted-foreground">
                  共 {total} 条 · 第 {page}/{totalPages} 页
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    <ChevronLeft className="size-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  >
                    <ChevronRight className="size-4" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="text-center text-xs text-muted-foreground"
      >
        文档处理 Pipeline 由后台任务执行 · 此处为只读状态展示
      </motion.p>
    </div>
  )
}
