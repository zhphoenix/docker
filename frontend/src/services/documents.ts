import { apiFetch } from './api-client'

export interface DocumentInfo {
  id: string
  market: string
  symbol: string
  company: string | null
  year: number
  document_type: string
  status: string
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
