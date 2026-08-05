import { apiFetch } from './api-client'

/** 文档状态枚举（对齐后端 services/pipeline.py 实际写入值） */
export type DocumentStatus =
  | 'pending'
  | 'waiting_parser'
  | 'parse_failed'
  | 'parsed'
  | 'indexed'
  | 'error'

/** 文档状态中文标签（对齐 docs/design/术语统一规范.md） */
export const DOCUMENT_STATUS_LABELS: Record<DocumentStatus, string> = {
  pending: '待处理',
  waiting_parser: '等待解析器',
  parse_failed: '解析失败',
  parsed: '已解析',
  indexed: '已索引',
  error: '错误',
}

/** 文档 Pipeline 真实阶段（Parse → Chunk → Embedding） */
export type DocumentPipelineStage = 'parse' | 'chunk' | 'embedding'

export interface DocumentInfo {
  id: string
  market: string
  symbol: string
  company: string | null
  year: number
  document_type: string
  status: DocumentStatus
  chunk_count: number
  created_at: string | null
  updated_at: string | null
}

export interface DocumentsResponse {
  documents: DocumentInfo[]
  total: number
  page: number
  page_size: number
}

export interface DocumentStats {
  by_status: Record<string, number>
  total: number
}

export interface DocumentQueryParams {
  status?: string
  market?: string
  symbol?: string
  page?: number
  page_size?: number
}

export function fetchDocuments(params?: DocumentQueryParams): Promise<DocumentsResponse> {
  const search = new URLSearchParams()
  if (params?.status) search.set('status', params.status)
  if (params?.market) search.set('market', params.market)
  if (params?.symbol) search.set('symbol', params.symbol)
  if (params?.page) search.set('page', String(params.page))
  if (params?.page_size) search.set('page_size', String(params.page_size))

  const qs = search.toString()
  return apiFetch<DocumentsResponse>(`/api/documents${qs ? `?${qs}` : ''}`)
}

export function fetchDocumentStats(): Promise<DocumentStats> {
  return apiFetch<DocumentStats>('/api/documents/stats')
}

// ─── 文档详情 / 分块 / 实体 / 删除 / 上传 ───

export interface DocumentDetailResponse {
  document: DocumentInfo & {
    language?: string | null
    bucket?: string | null
    object_key?: string | null
    parser?: string | null
    parser_version?: string | null
    metadata?: Record<string, unknown> | null
  }
  stats: {
    chunks: number
    embedded: number
    entities: number
    facts: number
  }
}

export interface ChunkInfo {
  id: string
  chunk_index: number
  content: string
  heading: string | null
  page_start: number | null
  page_end: number | null
  token_count: number | null
  collection_name: string | null
  qdrant_point_id: string | null
}

export interface ChunksResponse {
  chunks: ChunkInfo[]
  total: number
  page: number
  page_size: number
}

export interface DocumentEntity {
  id: string
  name: string
  entity_type: string
  description: string | null
  confidence: number | null
  source_count: number
}

export interface DocumentEntitiesResponse {
  entities: DocumentEntity[]
  total: number
}

export interface DeleteResponse {
  status: string
  deleted: string
}

export interface UploadResponse {
  status: string
  object_key: string
  registered: { added: number; skipped: number; found: number }
  pipeline_task_id: string | null
}

export interface UploadFolderResponse {
  status: string
  folder: string
  market: string
  stats: { found: number; added: number; skipped: number; failed: number }
  results: Array<{
    file: string
    status: 'ok' | 'skipped' | 'failed'
    reason?: string
    object_key?: string
    symbol?: string
    year?: number
  }>
  pipeline_task_id: string | null
}

export function fetchDocumentDetail(documentId: string): Promise<DocumentDetailResponse> {
  return apiFetch<DocumentDetailResponse>(`/api/documents/${documentId}`)
}

export function fetchDocumentChunks(
  documentId: string,
  params?: { page?: number; page_size?: number; keyword?: string }
): Promise<ChunksResponse> {
  const search = new URLSearchParams()
  if (params?.page) search.set('page', String(params.page))
  if (params?.page_size) search.set('page_size', String(params.page_size))
  if (params?.keyword) search.set('keyword', params.keyword)
  const qs = search.toString()
  return apiFetch<ChunksResponse>(`/api/documents/${documentId}/chunks${qs ? `?${qs}` : ''}`)
}

export function fetchDocumentEntities(documentId: string): Promise<DocumentEntitiesResponse> {
  return apiFetch<DocumentEntitiesResponse>(`/api/documents/${documentId}/entities`)
}

export function deleteDocument(documentId: string): Promise<DeleteResponse> {
  return apiFetch<DeleteResponse>(`/api/documents/${documentId}`, { method: 'DELETE' })
}

export function uploadDocumentPdf(params: {
  file: File
  market: string
  symbol: string
  year: number
  trigger?: boolean
}): Promise<UploadResponse> {
  const form = new FormData()
  form.append('file', params.file)
  form.append('market', params.market)
  form.append('symbol', params.symbol)
  form.append('year', String(params.year))
  form.append('trigger', String(params.trigger ?? false))

  return apiFetch<UploadResponse>('/api/documents/upload', {
    method: 'POST',
    body: form,
  })
}

export interface UploadFolderAsyncResponse {
  status: string
  folder: string
  market: string
  task_id: string
  total: number
  async_mode: boolean
}

export function uploadFolderPdf(params: {
  folder_path: string
  market?: string
  trigger?: boolean
  async_mode?: boolean
}): Promise<UploadFolderResponse | UploadFolderAsyncResponse> {
  const form = new FormData()
  form.append('folder_path', params.folder_path)
  if (params.market) form.append('market', params.market)
  form.append('trigger', String(params.trigger ?? false))
  if (params.async_mode) form.append('async_mode', 'true')

  return apiFetch<UploadFolderResponse | UploadFolderAsyncResponse>('/api/documents/upload-folder', {
    method: 'POST',
    body: form,
  })
}
