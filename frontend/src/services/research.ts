import { apiFetch } from './api-client'

export interface ResearchTask {
  id: string
  question: string
  agent_type: string | null
  market: string | null
  symbol: string | null
  quality: string | null
  confidence: number | null
  status: string
  elapsed_seconds: number | null
  document_count: number
  created_at: string | null
}

export interface ResearchListResponse {
  tasks: ResearchTask[]
  total: number
}

export interface ResearchDetail extends ResearchTask {
  plan: Record<string, unknown>
  answer: string | null
  error: string | null
  completed_at: string | null
}

export interface ResearchQueryParams {
  status?: string
  symbol?: string
  limit?: number
}

export function fetchResearch(params?: ResearchQueryParams): Promise<ResearchListResponse> {
  const search = new URLSearchParams()
  if (params?.status) search.set('status', params.status)
  if (params?.symbol) search.set('symbol', params.symbol)
  if (params?.limit) search.set('limit', String(params.limit))

  const qs = search.toString()
  return apiFetch<ResearchListResponse>(`/api/research${qs ? `?${qs}` : ''}`)
}

export function fetchResearchDetail(id: string): Promise<ResearchDetail> {
  return apiFetch<ResearchDetail>(`/api/research/${id}`)
}

export interface CreateResearchInput {
  question: string
  symbol?: string
  market?: string
  agent_type?: string
}

export interface CreateResearchResult {
  task_id: string
  status: string
  duplicate?: boolean
  message?: string
}

export function createResearch(input: CreateResearchInput): Promise<CreateResearchResult> {
  return apiFetch<CreateResearchResult>('/api/research', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}
