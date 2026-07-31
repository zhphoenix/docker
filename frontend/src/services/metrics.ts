import { apiFetch } from './api-client'

export interface MetricsResponse {
  timestamp: number
  uptime_seconds: number
  database: Record<string, number> | { error: string }
  qdrant: Record<string, { points: number; status: string }> | { error: string }
  tasks: Record<string, number>
  embedding_progress: Record<string, { total: number; embedded: number; pending: number; pct: number }>
  document_status: Record<string, number>
}

export function fetchMetrics(): Promise<MetricsResponse> {
  return apiFetch<MetricsResponse>('/metrics')
}
