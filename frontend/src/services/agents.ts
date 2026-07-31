import { apiFetch } from './api-client'

export interface AgentInfo {
  id: string
  name: string
  description: string
  model: string | null
  tools: string[]
  is_active: boolean
  source: 'builtin' | 'custom'
}

export interface AgentsResponse {
  agents: AgentInfo[]
  total: number
}

export function fetchAgents(): Promise<AgentsResponse> {
  return apiFetch<AgentsResponse>('/api/agents')
}
