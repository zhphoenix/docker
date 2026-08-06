import { apiFetch } from './api-client'

export interface ToolInfo {
  name: string
  registered: boolean
  calls: number
  success_calls: number
  avg_ms: number | null
  max_ms: number | null
  last_at: string | null
}

export interface ToolStatsItem {
  tool_name: string
  calls: number
  success_calls: number
  avg_ms: number | null
  errors: number
}

export interface ToolsResponse {
  tools: ToolInfo[]
  total: number
}

export function fetchTools(): Promise<ToolsResponse> {
  return apiFetch<ToolsResponse>('/api/tools')
}

export function fetchToolStats(agentId?: string, days = 7): Promise<{ stats: ToolStatsItem[] }> {
  const qs = new URLSearchParams({ days: String(days) })
  if (agentId) qs.set('agent_id', agentId)
  return apiFetch(`/api/tools/stats?${qs.toString()}`)
}