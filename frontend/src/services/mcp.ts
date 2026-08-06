import { apiFetch } from './api-client'

export interface McpInfo {
  name: string
  url: string
  kind: string
  status: 'connected' | 'disconnected' | 'unknown' | 'disabled'
  last_heartbeat: string | null
  latency_ms: number
  retry_count: number
  updated_at: string
}

export interface McpResponse {
  mcp: McpInfo[]
  total: number
}

export function fetchMcp(): Promise<McpResponse> {
  return apiFetch<McpResponse>('/api/mcp')
}

export function heartbeatMcp(name?: string): Promise<{ name: string; status: string; latency_ms: number } | { results: { name: string; status: string; latency_ms: number }[] }> {
  const path = name ? `/api/mcp/${encodeURIComponent(name)}/heartbeat` : '/api/mcp/heartbeat'
  return apiFetch(path, { method: 'POST' })
}

export function updateMcpStatus(name: string, status: string): Promise<{ name: string; status: string }> {
  return apiFetch(`/api/mcp/${encodeURIComponent(name)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
}