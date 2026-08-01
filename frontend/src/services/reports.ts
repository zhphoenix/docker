import { apiFetch } from './api-client'

export interface ReportMeta {
  id: string
  symbol: string
  company: string
  market: string
  year: string
  filename: string
  size_bytes: number
}

export interface ReportDetail extends ReportMeta {
  content: string
}

export interface ReportsResponse {
  reports: ReportMeta[]
  total: number
}

export interface AnalyzeRequest {
  symbol: string
  market?: string
  dimension?: string
  year?: string
}

export interface AnalyzeResponse {
  task_id: string
  status: string
  message: string
}

export interface ReportQueryParams {
  market?: string
  search?: string
}

export function fetchReports(params?: ReportQueryParams): Promise<ReportsResponse> {
  const search = new URLSearchParams()
  if (params?.market) search.set('market', params.market)
  if (params?.search) search.set('search', params.search)

  const qs = search.toString()
  return apiFetch<ReportsResponse>(`/api/reports${qs ? `?${qs}` : ''}`)
}

export function fetchReportDetail(id: string): Promise<ReportDetail> {
  return apiFetch<ReportDetail>(`/api/reports/${encodeURIComponent(id)}`)
}

export function triggerAnalysis(req: AnalyzeRequest): Promise<AnalyzeResponse> {
  return apiFetch<AnalyzeResponse>('/api/reports/analyze', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}
