import { apiFetch } from './api-client'

export interface PromptInfo {
  agent_id: string
  name: string
  version: number
  is_active: boolean
  status?: string
  created_at: string
}

export interface PromptDetail {
  agent_id: string
  name: string
  content: string
  version: number
  is_active: boolean
  status?: string
  created_at: string
}

export interface PromptDiffLine {
  type: 'added' | 'removed' | 'context'
  text: string
}

export interface PromptDiff {
  agent_id: string
  name: string
  v1: number
  v2: number
  added: number
  removed: number
  lines: PromptDiffLine[]
}

export interface PromptListResponse {
  prompts: PromptInfo[]
  total: number
}

export interface PromptDetailResponse {
  current: PromptDetail | null
  history: PromptInfo[]
}

export function fetchPrompts(agentId?: string): Promise<PromptListResponse> {
  const q = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : ''
  return apiFetch<PromptListResponse>(`/api/prompts${q}`)
}

export function fetchPromptDetail(agentId: string, name: string): Promise<PromptDetailResponse> {
  return apiFetch<PromptDetailResponse>(`/api/prompts/${agentId}/${name}`)
}

export function savePrompt(
  agentId: string,
  name: string,
  content: string
): Promise<{ agent_id: string; name: string; version: number }> {
  return apiFetch(`/api/prompts/${agentId}/${name}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })
}

export function previewPrompt(content: string, variables: Record<string, string>): Promise<{ rendered: string }> {
  return apiFetch('/api/prompts/preview', {
    method: 'POST',
    body: JSON.stringify({ content, variables }),
  })
}

export function submitPrompt(
  agentId: string,
  name: string
): Promise<{ approval_id: string; status: string; version: number }> {
  return apiFetch(`/api/prompts/${agentId}/${name}/submit`, {
    method: 'POST',
    body: JSON.stringify({ approver: 'admin' }),
  })
}

export function fetchPromptDiff(
  agentId: string,
  name: string,
  v1: number,
  v2: number
): Promise<PromptDiff> {
  return apiFetch(`/api/prompts/${agentId}/${name}/diff?v1=${v1}&v2=${v2}`)
}