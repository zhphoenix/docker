import { apiFetch } from './api-client'

export interface AgentInfo {
  id: string
  name: string
  display_name: string
  description: string
  model: string | null
  tools: string[]
  version: string
  author: string
  workflows: string[]
  skills: string[]
  mcp: string[]
  is_active: boolean
  status: 'active' | 'paused' | 'deprecated'
  last_active_at: string | null
  source: 'builtin' | 'custom'
}

export interface AgentRuntime {
  model: string
  temperature: number
  top_p: number
  max_tokens: number
  timeout: number
  retry: number
}

export interface AgentDetail extends AgentInfo {
  runtime: AgentRuntime
  dependencies: {
    skills: string[]
    tools: string[]
    mcp: string[]
    workflows: string[]
  }
}

export interface AgentsResponse {
  agents: AgentInfo[]
  total: number
}

export function fetchAgents(): Promise<AgentsResponse> {
  return apiFetch<AgentsResponse>('/api/agents')
}

export interface AgentSummaryItem {
  agent_id: string
  display_name: string
  status: string
  runs_today: number
  success_today: number
  failed_today: number
  success_rate: number
  avg_latency_ms: number
  last_run_at: string | null
}

export interface AgentSummaryResponse {
  agents: AgentSummaryItem[]
  total: {
    agents: number
    runs_today: number
    success_today: number
    failed_today: number
    success_rate: number
  }
}

export function fetchAgentsSummary(): Promise<AgentSummaryResponse> {
  return apiFetch<AgentSummaryResponse>('/api/agents/summary')
}

export function fetchAgentDetail(agentId: string): Promise<AgentDetail> {
  return apiFetch<AgentDetail>(`/api/agents/${agentId}`)
}

export interface AgentMetricsSummary {
  runs: number
  success: number
  failed: number
  success_rate: number
  avg_latency_ms: number
  avg_tokens: number
  avg_cost: number
  total_cost: number
}

export interface AgentMetricsTrendPoint {
  date: string
  runs: number
  avg_latency_ms: number
  avg_tokens: number
  error_rate: number
}

export interface AgentMetrics {
  agent_id: string
  range: string
  summary: AgentMetricsSummary
  trend: AgentMetricsTrendPoint[]
}

export function fetchAgentMetrics(agentId: string, range: string = '7d'): Promise<AgentMetrics> {
  return apiFetch<AgentMetrics>(`/api/agents/${agentId}/metrics?range=${range}`)
}

export interface LogEntry {
  source: 'agent_run' | 'task_log'
  time: string | null
  entity: string
  level: string
  message: string
  duration_ms: number | null
  error_category: string | null
  run_id: string | null
  task_id: string | null
}

export interface LogsResponse {
  items: LogEntry[]
  total: number
  page: number
  page_size: number
}

export interface RunTrace {
  run_id: string
  agent_id: string
  task_kind: string
  status: string
  question: string | null
  duration_ms: number | null
  error: string | null
  error_category: string | null
  tokens_in: number
  tokens_out: number
  created_at: string | null
  trace: unknown[]
  timeline: {
    node: string
    status: string
    duration_ms: number | null
    detail: string | null
  }[]
}

export interface LogsQuery {
  agentId?: string
  status?: string
  keyword?: string
  page?: number
  pageSize?: number
}

export function fetchAgentLogs(query: LogsQuery = {}): Promise<LogsResponse> {
  const params = new URLSearchParams()
  if (query.agentId) params.set('agent_id', query.agentId)
  if (query.status) params.set('status', query.status)
  if (query.keyword) params.set('keyword', query.keyword)
  if (query.page && query.page > 1) params.set('page', String(query.page))
  if (query.pageSize) params.set('page_size', String(query.pageSize))
  const qs = params.toString()
  return apiFetch<LogsResponse>(`/api/logs${qs ? `?${qs}` : ''}`)
}

export function fetchRunTrace(runId: string): Promise<RunTrace> {
  return apiFetch<RunTrace>(`/api/logs/${runId}/trace`)
}

export function buildLogsExportUrl(query: LogsQuery = {}): string {
  const params = new URLSearchParams()
  if (query.agentId) params.set('agent_id', query.agentId)
  if (query.status) params.set('status', query.status)
  if (query.keyword) params.set('keyword', query.keyword)
  const qs = params.toString()
  return `/api/logs/export${qs ? `?${qs}` : ''}`
}

export function toggleAgent(agentId: string): Promise<{ id: string; is_active: boolean; status: string }> {
  return apiFetch<{ id: string; is_active: boolean; status: string }>(
    `/api/agents/${agentId}/toggle`,
    { method: 'POST' }
  )
}

export interface ConfigUpdateInput {
  model?: string
  temperature?: number
  top_p?: number
  max_tokens?: number
  timeout?: number
  retry?: number
}

export interface ConfigHistoryItem {
  id: string
  agent_id: string
  config: Record<string, unknown>
  changed_by: string
  created_at: string
}

export function updateAgentConfig(agentId: string, config: ConfigUpdateInput): Promise<{ id: string; config: Record<string, unknown>; updated: boolean }> {
  return apiFetch(`/api/agents/${agentId}/config`, {
    method: 'PUT',
    body: JSON.stringify(config),
  })
}

export function fetchConfigHistory(agentId: string): Promise<{ history: ConfigHistoryItem[]; total: number }> {
  return apiFetch(`/api/agents/${agentId}/config/history`)
}

export function rollbackConfig(agentId: string, historyId?: string): Promise<{ id: string; config: Record<string, unknown>; rolled_back: boolean }> {
  return apiFetch(`/api/agents/${agentId}/config/rollback`, {
    method: 'POST',
    body: JSON.stringify({ history_id: historyId ?? null }),
  })
}