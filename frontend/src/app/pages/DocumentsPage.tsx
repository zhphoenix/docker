import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  FileText,
  RefreshCw,
  Search,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Upload,
  Database,
  FolderSync,
  Zap,
  Eye,
  RotateCcw,
  Trash2,
  AlertTriangle,
  Clock,
  Layers,
  Network,
  Play,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { ScrollArea } from '@/components/ui/scroll-area'
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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { EmptyState } from '@/components/common/EmptyState'
import {
  fetchDocuments,
  fetchDocumentStats,
  fetchDocumentDetail,
  fetchDocumentChunks,
  fetchDocumentEntities,
  deleteDocument,
  uploadDocumentPdf,
  DOCUMENT_STATUS_LABELS,
} from '@/services/documents'
import type { DocumentStatus, DocumentInfo } from '@/services/documents'
import {
  fetchTasks,
  retryTask,
  triggerPipeline,
  triggerBatchEmbed,
  reindexDocument,
} from '@/services/tasks'
import { fetchKnowledgeStats, triggerIngestMinio, triggerIngest, fetchBrowseDirs } from '@/services/knowledge'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 50

// 文档状态枚举（对齐后端真实写入值）
const STATUS_ORDER: DocumentStatus[] = [
  'pending',
  'waiting_parser',
  'parse_failed',
  'parsed',
  'indexed',
  'error',
]

const STATUS_VARIANTS: Record<
  DocumentStatus,
  'default' | 'secondary' | 'destructive' | 'outline'
> = {
  pending: 'secondary',
  waiting_parser: 'secondary',
  parse_failed: 'destructive',
  parsed: 'outline',
  indexed: 'default',
  error: 'destructive',
}

const MARKET_OPTIONS = [
  { value: 'a', label: 'A 股' },
  { value: 'h', label: '港股' },
  { value: 'us', label: '美股' },
]

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatElapsed(sec: number | null): string {
  if (sec === null) return '—'
  if (sec < 60) return `${sec.toFixed(1)}s`
  return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`
}

// ===== 反馈提示条 =====
function Feedback({
  msg,
}: {
  msg: { type: 'success' | 'error'; msg: string } | null
}) {
  if (!msg) return null
  return (
    <div
      className={cn(
        'rounded-lg border px-3 py-2 text-xs',
        msg.type === 'error'
          ? 'border-destructive/30 bg-destructive/10 text-destructive'
          : 'border-primary/30 bg-primary/10 text-primary'
      )}
    >
      {msg.msg}
    </div>
  )
}

// ===== 导入区域 =====
function ImportPanel() {
  const queryClient = useQueryClient()
  const [uploadOpen, setUploadOpen] = useState(false)
  const [minioOpen, setMinioOpen] = useState(false)
  const [syncOpen, setSyncOpen] = useState(false)
  const [msg, setMsg] = useState<{ type: 'success' | 'error'; msg: string } | null>(null)

  const flash = (type: 'success' | 'error', text: string) => {
    setMsg({ type, msg: text })
    setTimeout(() => setMsg(null), 6000)
  }

  // Upload PDF
  const [upFile, setUpFile] = useState<File | null>(null)
  const [upMarket, setUpMarket] = useState('a')
  const [upSymbol, setUpSymbol] = useState('')
  const [upYear, setUpYear] = useState(2026)
  const [upTrigger, setUpTrigger] = useState(true)

  const uploadMutation = useMutation({
    mutationFn: () =>
      uploadDocumentPdf({
        file: upFile!,
        market: upMarket,
        symbol: upSymbol,
        year: upYear,
        trigger: upTrigger,
      }),
    onSuccess: (res) => {
      flash('success', `上传成功：${res.object_key}，新增 ${res.registered.added} 个文档`)
      setUploadOpen(false)
      setUpFile(null)
      setUpSymbol('')
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['document-stats'] })
      queryClient.invalidateQueries({ queryKey: ['doc-tasks'] })
    },
    onError: (err: Error) => flash('error', err.message || '上传失败'),
  })

  // Import MinIO
  const [minioBucket, setMinioBucket] = useState('documents')
  const [minioPrefix, setMinioPrefix] = useState('')
  const [minioMarket, setMinioMarket] = useState('a')
  const [minioTrigger, setMinioTrigger] = useState(true)

  const minioMutation = useMutation({
    mutationFn: () =>
      triggerIngestMinio({
        bucket: minioBucket,
        prefix: minioPrefix || undefined,
        market: minioMarket,
        trigger: minioTrigger,
      }),
    onSuccess: (res) => {
      const r = (res.registered ?? {}) as Record<string, number>
      flash('success', `MinIO 导入完成：新增 ${r.added ?? 0}，跳过 ${r.skipped ?? 0}，发现 ${r.found ?? 0}`)
      setMinioOpen(false)
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['document-stats'] })
      queryClient.invalidateQueries({ queryKey: ['doc-tasks'] })
    },
    onError: (err: Error) => flash('error', err.message || 'MinIO 导入失败'),
  })

  // Sync Folder
  const [syncPath, setSyncPath] = useState('/data')
  const [syncCollection, setSyncCollection] = useState('documents_cn')

  const browseQuery = useQuery({
    queryKey: ['browse-dirs', syncPath],
    queryFn: () => fetchBrowseDirs(syncPath),
    enabled: syncOpen,
    retry: 1,
  })

  const syncMutation = useMutation({
    mutationFn: () => triggerIngest(syncPath, syncCollection),
    onSuccess: (res) => {
      flash('success', `目录同步完成：${res.file_count} 个文件，collection=${res.collection}`)
      setSyncOpen(false)
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['knowledge-tasks'] })
    },
    onError: (err: Error) => flash('error', err.message || '目录同步失败'),
  })

  // Batch Processing
  const pipelineMutation = useMutation({
    mutationFn: () => triggerPipeline({ limit: 50, async_mode: true }),
    onSuccess: () => {
      flash('success', '已触发文档处理 Pipeline（Parse → Chunk → Embedding）')
      queryClient.invalidateQueries({ queryKey: ['doc-tasks'] })
    },
    onError: (err: Error) => flash('error', err.message || 'Pipeline 触发失败'),
  })

  const batchEmbedMutation = useMutation({
    mutationFn: () => triggerBatchEmbed({ collection: 'documents_cn', batch_size: 64, limit: 0 }),
    onSuccess: () => {
      flash('success', '已触发批量向量化任务')
      queryClient.invalidateQueries({ queryKey: ['doc-tasks'] })
    },
    onError: (err: Error) => flash('error', err.message || '批量向量化触发失败'),
  })

  const items = [
    {
      icon: Upload,
      title: 'Upload PDF',
      desc: '上传年报 PDF 到 MinIO 并注册',
      onClick: () => setUploadOpen(true),
      color: 'text-blue-500',
    },
    {
      icon: Database,
      title: 'Import MinIO',
      desc: '从 MinIO 导入已有文档',
      onClick: () => setMinioOpen(true),
      color: 'text-emerald-500',
    },
    {
      icon: FolderSync,
      title: 'Sync Folder',
      desc: '同步指定目录的文件',
      onClick: () => setSyncOpen(true),
      color: 'text-amber-500',
    },
    {
      icon: Zap,
      title: 'Batch Process',
      desc: '触发 Pipeline / 批量向量化',
      onClick: () => pipelineMutation.mutate(),
      color: 'text-violet-500',
    },
  ]

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {items.map((it) => (
          <button
            key={it.title}
            onClick={it.onClick}
            className="group flex flex-col items-start gap-2 rounded-xl border bg-card p-4 text-left transition-colors hover:border-primary/40 hover:bg-muted/40"
          >
            <it.icon className={cn('size-5', it.color)} />
            <div className="text-sm font-medium text-foreground">{it.title}</div>
            <div className="text-xs text-muted-foreground">{it.desc}</div>
          </button>
        ))}
      </div>

      {/* Batch 操作按钮 */}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          onClick={() => pipelineMutation.mutate()}
          disabled={pipelineMutation.isPending}
        >
          <Play className="size-3.5" />
          {pipelineMutation.isPending ? '触发中...' : '触发文档处理 Pipeline'}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          onClick={() => batchEmbedMutation.mutate()}
          disabled={batchEmbedMutation.isPending}
        >
          <Zap className="size-3.5" />
          {batchEmbedMutation.isPending ? '触发中...' : '批量向量化'}
        </Button>
      </div>

      <Feedback msg={msg} />

      {/* ── Upload PDF Dialog ── */}
      <Dialog open={uploadOpen} onOpenChange={(o) => !o && setUploadOpen(false)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>上传 PDF</DialogTitle>
            <DialogDescription>上传年报 PDF 到 MinIO，并按规范路径注册文档</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <div className="mb-1 text-xs font-medium text-muted-foreground">PDF 文件</div>
              <Input
                type="file"
                accept=".pdf"
                onChange={(e) => setUpFile(e.target.files?.[0] ?? null)}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="mb-1 text-xs font-medium text-muted-foreground">市场</div>
                <Select value={upMarket} onValueChange={(v) => setUpMarket(v ?? '')}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {MARKET_OPTIONS.map((m) => (
                      <SelectItem key={m.value} value={m.value}>
                        {m.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <div className="mb-1 text-xs font-medium text-muted-foreground">股票代码</div>
                <Input
                  placeholder="如 000001"
                  value={upSymbol}
                  onChange={(e) => setUpSymbol(e.target.value)}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="mb-1 text-xs font-medium text-muted-foreground">年份</div>
                <Input
                  type="number"
                  value={upYear}
                  onChange={(e) => setUpYear(Number(e.target.value))}
                />
              </div>
              <div className="flex items-end pb-1">
                <label className="flex items-center gap-2 text-sm text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={upTrigger}
                    onChange={(e) => setUpTrigger(e.target.checked)}
                  />
                  立即处理
                </label>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="default"
              className="gap-1.5"
              disabled={!upFile || !upSymbol.trim() || uploadMutation.isPending}
              onClick={() => uploadMutation.mutate()}
            >
              {uploadMutation.isPending ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Upload className="size-3.5" />
              )}
              {uploadMutation.isPending ? '上传中...' : '上传并注册'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Import MinIO Dialog ── */}
      <Dialog open={minioOpen} onOpenChange={(o) => !o && setMinioOpen(false)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>从 MinIO 导入</DialogTitle>
            <DialogDescription>扫描 MinIO 中已有对象并注册为 pending 文档</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <div className="mb-1 text-xs font-medium text-muted-foreground">Bucket</div>
              <Input value={minioBucket} onChange={(e) => setMinioBucket(e.target.value)} />
            </div>
            <div>
              <div className="mb-1 text-xs font-medium text-muted-foreground">Prefix（可选）</div>
              <Input
                placeholder="如 a/000001/annual_report/2025"
                value={minioPrefix}
                onChange={(e) => setMinioPrefix(e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="mb-1 text-xs font-medium text-muted-foreground">市场</div>
                <Select value={minioMarket} onValueChange={(v) => setMinioMarket(v ?? '')}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {MARKET_OPTIONS.map((m) => (
                      <SelectItem key={m.value} value={m.value}>
                        {m.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-end pb-1">
                <label className="flex items-center gap-2 text-sm text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={minioTrigger}
                    onChange={(e) => setMinioTrigger(e.target.checked)}
                  />
                  立即处理
                </label>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="default"
              className="gap-1.5"
              disabled={minioMutation.isPending}
              onClick={() => minioMutation.mutate()}
            >
              {minioMutation.isPending ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Database className="size-3.5" />
              )}
              {minioMutation.isPending ? '导入中...' : '开始导入'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Sync Folder Dialog ── */}
      <Dialog open={syncOpen} onOpenChange={(o) => !o && setSyncOpen(false)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>同步目录</DialogTitle>
            <DialogDescription>浏览并选择服务器目录，将其中的文件导入知识库</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="flex gap-2">
              <Input
                value={syncPath}
                onChange={(e) => setSyncPath(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && browseQuery.refetch()}
              />
              <Button variant="outline" size="icon" onClick={() => browseQuery.refetch()}>
                <Search className="size-4" />
              </Button>
            </div>
            {browseQuery.isLoading ? (
              <Skeleton className="h-24 w-full" />
            ) : browseQuery.data ? (
              <div className="max-h-48 overflow-y-auto rounded-lg border">
                {browseQuery.data.can_go_up && (
                  <button
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-muted-foreground hover:bg-muted"
                    onClick={() => setSyncPath(browseQuery.data!.parent_path!)}
                  >
                    <ChevronLeft className="size-3.5" /> 上级目录
                  </button>
                )}
                {browseQuery.data.directories.map((d) => (
                  <button
                    key={d.path}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-foreground hover:bg-muted"
                    onClick={() => setSyncPath(d.path)}
                  >
                    <FolderSync className="size-3.5 text-primary" />
                    {d.name}
                  </button>
                ))}
                {browseQuery.data.directories.length === 0 && (
                  <div className="p-3 text-xs text-muted-foreground">当前目录下没有子目录</div>
                )}
              </div>
            ) : (
              <EmptyState
                title="无法浏览目录"
                description="请确认目录存在于后端容器中"
                action={{ label: '重试', onClick: () => browseQuery.refetch() }}
              />
            )}
            <div>
              <div className="mb-1 text-xs font-medium text-muted-foreground">Collection</div>
              <Input
                value={syncCollection}
                onChange={(e) => setSyncCollection(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="default"
              className="gap-1.5"
              disabled={!syncPath.trim() || syncMutation.isPending}
              onClick={() => syncMutation.mutate()}
            >
              {syncMutation.isPending ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <FolderSync className="size-3.5" />
              )}
              {syncMutation.isPending ? '同步中...' : '开始同步'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ===== Running Tasks 面板 =====
function RunningTasksPanel() {
  const runningQuery = useQuery({
    queryKey: ['doc-tasks-running'],
    queryFn: () => fetchTasks({ status: 'running', limit: 10 }),
    refetchInterval: 5000,
    retry: 1,
  })
  const tasks = runningQuery.data?.tasks ?? []
  if (tasks.length === 0) return null
  return (
    <Card>
      <CardContent className="p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-medium text-foreground">
          <Clock className="size-4 text-primary" />
          Running Tasks
        </div>
        <div className="space-y-3">
          {tasks.map((t) => {
            const pct = Math.max(0, Math.min(100, t.progress ?? 0))
            return (
              <div key={t.id} className="space-y-1.5">
                <div className="flex items-center justify-between gap-3">
                  <span className="truncate text-xs font-medium text-foreground">{t.title}</span>
                  <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                    {pct.toFixed(0)}%
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary transition-all animate-pulse"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] text-muted-foreground">
                  {t.stage && <span>阶段：{t.stage}</span>}
                  {t.current_name && <span className="truncate">当前：{t.current_name}</span>}
                  {t.started_at && (
                    <span>
                      已运行 {formatElapsed((Date.now() - new Date(t.started_at).getTime()) / 1000)}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

// ===== 失败任务面板 =====
function FailedTasksPanel() {
  const queryClient = useQueryClient()
  const failedQuery = useQuery({
    queryKey: ['doc-tasks-failed'],
    queryFn: () => fetchTasks({ status: 'failed', limit: 5 }),
    retry: 1,
  })
  const retryMutation = useMutation({
    mutationFn: (id: string) => retryTask(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['doc-tasks-failed'] })
      queryClient.invalidateQueries({ queryKey: ['doc-tasks-running'] })
    },
  })
  const tasks = failedQuery.data?.tasks ?? []
  if (tasks.length === 0) return null
  return (
    <Card>
      <CardContent className="p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-medium text-foreground">
          <AlertTriangle className="size-4 text-destructive" />
          Failed Tasks
        </div>
        <div className="space-y-2">
          {tasks.map((t) => (
            <div
              key={t.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2"
            >
              <div className="min-w-0">
                <div className="truncate text-xs font-medium text-foreground">{t.title}</div>
                <div className="mt-0.5 truncate text-[10px] text-destructive">
                  {t.error_message || '未知错误'}
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="h-7 shrink-0 gap-1.5 px-2 text-[11px]"
                onClick={() => retryMutation.mutate(t.id)}
                disabled={retryMutation.isPending}
              >
                <RotateCcw className="size-3" />
                重试
              </Button>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

// ===== 文档详情抽屉 =====
function DocumentDetailDialog({
  documentId,
  onClose,
}: {
  documentId: string | null
  onClose: () => void
}) {
  const [tab, setTab] = useState('overview')
  const [chunkKeyword, setChunkKeyword] = useState('')
  const [chunkPage, setChunkPage] = useState(1)

  const detailQuery = useQuery({
    queryKey: ['doc-detail', documentId],
    queryFn: () => fetchDocumentDetail(documentId!),
    enabled: documentId != null,
    retry: 1,
  })

  const chunksQuery = useQuery({
    queryKey: ['doc-chunks', documentId, chunkPage, chunkKeyword],
    queryFn: () =>
      fetchDocumentChunks(documentId!, {
        page: chunkPage,
        page_size: 20,
        keyword: chunkKeyword || undefined,
      }),
    enabled: documentId != null && tab === 'chunks',
    retry: 1,
  })

  const entitiesQuery = useQuery({
    queryKey: ['doc-entities', documentId],
    queryFn: () => fetchDocumentEntities(documentId!),
    enabled: documentId != null && tab === 'entities',
    retry: 1,
  })

  const doc = detailQuery.data?.document
  const stats = detailQuery.data?.stats
  const chunks = chunksQuery.data?.chunks ?? []
  const chunkTotal = chunksQuery.data?.total ?? 0
  const chunkTotalPages = Math.max(1, Math.ceil(chunkTotal / 20))
  const entities = entitiesQuery.data?.entities ?? []

  return (
    <Dialog open={documentId != null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[85vh]">
        <DialogHeader>
          <DialogTitle className="text-base">
            {doc ? `${doc.symbol} · ${doc.company ?? '—'} · ${doc.year}` : '文档详情'}
          </DialogTitle>
          <DialogDescription>
            {doc ? `${doc.document_type} · ${doc.object_key ?? ''}` : '加载中...'}
          </DialogDescription>
        </DialogHeader>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="overview" className="gap-1.5">
              <Eye className="size-3.5" /> Overview
            </TabsTrigger>
            <TabsTrigger value="chunks" className="gap-1.5">
              <Layers className="size-3.5" /> Chunks
            </TabsTrigger>
            <TabsTrigger value="entities" className="gap-1.5">
              <Network className="size-3.5" /> Entities
            </TabsTrigger>
          </TabsList>

          <TabsContent value="overview">
            {detailQuery.isLoading ? (
              <div className="space-y-3 py-4">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" />
              </div>
            ) : detailQuery.isError ? (
              <EmptyState
                title="加载详情失败"
                description="无法获取文档详情"
                action={{ label: '重试', onClick: () => detailQuery.refetch() }}
              />
            ) : doc ? (
              <div className="space-y-5 py-2">
                {/* 元数据 */}
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {[
                    ['状态', <Badge key="s" variant={STATUS_VARIANTS[doc.status] ?? 'outline'}>{DOCUMENT_STATUS_LABELS[doc.status] ?? doc.status}</Badge>],
                    ['市场', doc.market],
                    ['股票代码', doc.symbol],
                    ['年份', String(doc.year)],
                    ['文档类型', doc.document_type],
                    ['语言', doc.language ?? '—'],
                    ['解析器', doc.parser ?? '—'],
                    ['解析器版本', doc.parser_version ?? '—'],
                    ['Bucket', doc.bucket ?? '—'],
                    ['创建时间', formatDateTime(doc.created_at)],
                    ['更新时间', formatDateTime(doc.updated_at)],
                    ['分块数', String(doc.chunk_count)],
                  ].map(([k, v]) => (
                    <div key={String(k)}>
                      <div className="text-xs font-medium text-muted-foreground">{k}</div>
                      <div className="mt-1 text-sm text-foreground">{v}</div>
                    </div>
                  ))}
                </div>
                {doc.object_key && (
                  <div>
                    <div className="text-xs font-medium text-muted-foreground">对象路径</div>
                    <code className="mt-1 block break-all rounded bg-muted px-2 py-1.5 text-xs text-foreground">
                      {doc.object_key}
                    </code>
                  </div>
                )}

                {/* 统计 */}
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {[
                    ['Chunks', stats?.chunks ?? 0],
                    ['Embedded', stats?.embedded ?? 0],
                    ['Entities', stats?.entities ?? 0],
                    ['Facts', stats?.facts ?? 0],
                  ].map(([k, v]) => (
                    <div key={String(k)} className="rounded-lg border bg-muted/30 p-3">
                      <div className="text-xs font-medium text-muted-foreground">{k}</div>
                      <div className="mt-1 text-xl font-bold tabular-nums text-foreground">{v}</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </TabsContent>

          <TabsContent value="chunks">
            <div className="space-y-3 py-2">
              <div className="flex gap-2">
                <Input
                  placeholder="搜索分块内容"
                  value={chunkKeyword}
                  onChange={(e) => {
                    setChunkKeyword(e.target.value)
                    setChunkPage(1)
                  }}
                />
                <Button variant="outline" size="icon" onClick={() => chunksQuery.refetch()}>
                  <Search className="size-4" />
                </Button>
              </div>
              <ScrollArea className="max-h-[55vh]">
                {chunksQuery.isLoading ? (
                  <div className="space-y-3 py-2">
                    {[1, 2, 3].map((i) => (
                      <Skeleton key={i} className="h-16 w-full" />
                    ))}
                  </div>
                ) : chunksQuery.isError ? (
                  <EmptyState
                    title="加载分块失败"
                    action={{ label: '重试', onClick: () => chunksQuery.refetch() }}
                  />
                ) : chunks.length === 0 ? (
                  <EmptyState title="暂无分块" description="该文档尚未完成分块处理" />
                ) : (
                  <div className="space-y-3">
                    {chunks.map((c) => (
                      <div key={c.id} className="rounded-lg border p-3">
                        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                          <span className="font-medium text-foreground">#{c.chunk_index}</span>
                          {c.heading && <span className="truncate">{c.heading}</span>}
                          {c.page_start != null && (
                            <span>
                              p{c.page_start}
                              {c.page_end != null && c.page_end !== c.page_start ? `-${c.page_end}` : ''}
                            </span>
                          )}
                          {c.token_count != null && <span>{c.token_count} tokens</span>}
                          {c.qdrant_point_id ? (
                            <Badge variant="outline" className="ml-auto text-[9px]">已向量化</Badge>
                          ) : (
                            <Badge variant="secondary" className="ml-auto text-[9px]">未向量化</Badge>
                          )}
                        </div>
                        <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-foreground/80">
                          {c.content}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </ScrollArea>
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>
                  共 {chunkTotal} 条 · 第 {chunkPage}/{chunkTotalPages} 页
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={chunkPage <= 1}
                    onClick={() => setChunkPage((p) => Math.max(1, p - 1))}
                  >
                    <ChevronLeft className="size-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={chunkPage >= chunkTotalPages}
                    onClick={() => setChunkPage((p) => Math.min(chunkTotalPages, p + 1))}
                  >
                    <ChevronRight className="size-4" />
                  </Button>
                </div>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="entities">
            <ScrollArea className="max-h-[55vh]">
              {entitiesQuery.isLoading ? (
                <div className="space-y-3 py-2">
                  {[1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-10 w-full" />
                  ))}
                </div>
              ) : entitiesQuery.isError ? (
                <EmptyState
                  title="加载实体失败"
                  action={{ label: '重试', onClick: () => entitiesQuery.refetch() }}
                />
              ) : entities.length === 0 ? (
                <EmptyState
                  title="暂无实体"
                  description="该文档尚未提取知识图谱实体（由知识图谱模块处理）"
                />
              ) : (
                <div className="space-y-2 py-2">
                  {entities.map((e) => (
                    <div
                      key={e.id}
                      className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2"
                    >
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium text-foreground">{e.name}</div>
                        {e.description && (
                          <div className="truncate text-xs text-muted-foreground">{e.description}</div>
                        )}
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <Badge variant="outline" className="text-[10px]">
                          {e.entity_type}
                        </Badge>
                        {e.confidence != null && (
                          <span className="text-[10px] tabular-nums text-muted-foreground">
                            {(e.confidence * 100).toFixed(0)}%
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

// ===== 主页面 =====
export default function DocumentsPage() {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<string>('')
  const [market, setMarket] = useState<string>('')
  const [symbol, setSymbol] = useState('')
  const [page, setPage] = useState(1)
  const [selectedId, setSelectedId] = useState<string | null>(null)

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

  // 知识库规模（Chunks/Entities/Facts）
  const kStatsQuery = useQuery({
    queryKey: ['knowledge-stats'],
    queryFn: fetchKnowledgeStats,
    retry: 1,
  })

  // 删除 mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteDocument(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['document-stats'] })
      queryClient.invalidateQueries({ queryKey: ['knowledge-stats'] })
    },
    onError: (err: Error) => alert(err.message || '删除失败'),
  })

  // 重新处理 mutation
  const reindexMutation = useMutation({
    mutationFn: (id: string) => reindexDocument(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['doc-tasks'] })
    },
    onError: (err: Error) => alert(err.message || '重新处理失败'),
  })

  const documents = docsQuery.data?.documents ?? []
  const total = docsQuery.data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const byStatus = statsQuery.data?.by_status ?? {}
  const totalDocs = statsQuery.data?.total ?? 0
  const kStats = kStatsQuery.data

  const handleFilterChange = (setter: (v: string) => void) => (value: string | null) => {
    setter(value === 'all' || value === null ? '' : value)
    setPage(1)
  }

  const handleRefresh = () => {
    docsQuery.refetch()
    statsQuery.refetch()
    kStatsQuery.refetch()
  }

  const handleDelete = (doc: DocumentInfo) => {
    if (window.confirm(`确认删除 ${doc.symbol}（${doc.year}）？`)) {
      deleteMutation.mutate(doc.id)
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">文档中心</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            年报文档的导入、解析、分块与向量化状态（Parse → Chunk → Embedding）
          </p>
        </div>
        <Button variant="outline" size="sm" className="gap-2" onClick={handleRefresh}>
          <RefreshCw className={cn('size-3.5', docsQuery.isFetching && 'animate-spin')} />
          刷新
        </Button>
      </div>

      {/* 知识库规模统计 */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Card>
          <CardContent className="p-4">
            <div className="text-xs font-medium text-muted-foreground">文档总数</div>
            <div className="mt-1 text-2xl font-bold text-foreground">
              {kStats ? kStats.documents : totalDocs}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs font-medium text-muted-foreground">Chunks</div>
            <div className="mt-1 text-2xl font-bold tabular-nums text-foreground">
              {kStats ? kStats.chunks : '—'}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs font-medium text-muted-foreground">Entities</div>
            <div className="mt-1 text-2xl font-bold tabular-nums text-foreground">
              {kStats ? kStats.entities : '—'}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs font-medium text-muted-foreground">Facts</div>
            <div className="mt-1 text-2xl font-bold tabular-nums text-foreground">
              {kStats ? kStats.facts : '—'}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 导入区域 */}
      <ImportPanel />

      {/* 状态统计（按状态） */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-6">
        {statsQuery.isLoading ? (
          [1, 2, 3, 4, 5, 6].map((i) => <Skeleton key={i} className="h-16" />)
        ) : (
          STATUS_ORDER.map((s) => (
            <Card key={s} className="cursor-pointer" onClick={() => handleFilterChange(setStatus)(s)}>
              <CardContent className="p-3">
                <div className="text-[10px] font-medium text-muted-foreground capitalize">
                  {DOCUMENT_STATUS_LABELS[s]}
                </div>
                <div className="mt-1 text-xl font-bold text-foreground">{byStatus[s] ?? 0}</div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Running Tasks */}
      <RunningTasksPanel />

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
            {STATUS_ORDER.map((s) => (
              <SelectItem key={s} value={s}>
                {DOCUMENT_STATUS_LABELS[s]} · {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={market || 'all'} onValueChange={handleFilterChange(setMarket)}>
          <SelectTrigger className="w-32">
            <SelectValue placeholder="市场" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部市场</SelectItem>
            {MARKET_OPTIONS.map((m) => (
              <SelectItem key={m.value} value={m.value}>
                {m.label}
              </SelectItem>
            ))}
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
              description="当前筛选条件下没有文档，请调整筛选条件或通过上方导入区域新增文档"
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
                      <TableHead className="text-right">操作</TableHead>
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
                            {DOCUMENT_STATUS_LABELS[doc.status] ?? doc.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">
                          {doc.chunk_count}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {formatDate(doc.updated_at)}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              title="查看详情"
                              onClick={() => setSelectedId(doc.id)}
                            >
                              <Eye className="size-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              title="重新处理"
                              disabled={reindexMutation.isPending}
                              onClick={() => reindexMutation.mutate(doc.id)}
                            >
                              <RotateCcw className="size-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              title="删除文档"
                              className="text-destructive hover:text-destructive"
                              disabled={deleteMutation.isPending}
                              onClick={() => handleDelete(doc)}
                            >
                              <Trash2 className="size-3.5" />
                            </Button>
                          </div>
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

      {/* Failed Tasks */}
      <FailedTasksPanel />

      {/* 文档详情抽屉 */}
      <DocumentDetailDialog documentId={selectedId} onClose={() => setSelectedId(null)} />

      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="text-center text-xs text-muted-foreground"
      >
        文档处理 Pipeline 由后台任务执行（Parse → Chunk → Embedding）· 实体/图由知识图谱模块处理
      </motion.p>
    </div>
  )
}