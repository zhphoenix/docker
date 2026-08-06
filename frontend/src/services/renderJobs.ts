import { apiFetch } from './api-client'

// Render Queue 任务状态枚举（后端真实取值）
export type RenderJobStatus = 'pending' | 'running' | 'done' | 'failed'

export interface RenderJob {
  id: string
  entity: string | null
  entity_name: string | null
  type: string
  section: string | null
  status: RenderJobStatus
  retry: number
  priority: number
  error_message: string | null
  created_at: string | null
  updated_at: string | null
}

export interface RenderJobsResponse {
  jobs: RenderJob[]
  total: number
}

export function fetchRenderJobs(params?: {
  status?: string
  limit?: number
}): Promise<RenderJobsResponse> {
  const search = new URLSearchParams()
  if (params?.status) search.set('status', params.status)
  if (params?.limit) search.set('limit', String(params.limit))
  const qs = search.toString()
  return apiFetch<RenderJobsResponse>(`/api/knowledge/render-jobs${qs ? `?${qs}` : ''}`)
}

export function retryRenderJob(jobId: string): Promise<{
  status: string
  message: string
  job_id: string
}> {
  return apiFetch<{ status: string; message: string; job_id: string }>(
    `/api/knowledge/render-jobs/${jobId}/retry`,
    { method: 'POST' }
  )
}