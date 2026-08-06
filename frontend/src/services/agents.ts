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

export function fetchAgentDetail(agentId: string): Promise<AgentDetail> {
  return apiFetch<AgentDetail>(`/api/agents/${agentId}`)
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