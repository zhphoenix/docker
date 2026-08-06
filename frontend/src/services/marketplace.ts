import { apiFetch } from './api-client'

export interface AgentTemplate {
  id: string
  name: string
  display_name: string | null
  description: string | null
  category: string
  version: string
  author: string
  installs: number
  created_at: string
  updated_at: string
}

export interface TemplatesResponse {
  templates: AgentTemplate[]
  total: number
}

export interface AgentDefinition {
  schema_version: string
  kind: string
  agent: Record<string, unknown>
  prompts: unknown[]
  exported_at?: string
}

export function fetchTemplates(category?: string): Promise<TemplatesResponse> {
  const qs = category ? `?category=${encodeURIComponent(category)}` : ''
  return apiFetch<TemplatesResponse>(`/api/marketplace/templates${qs}`)
}

export function fetchTemplateDetail(id: string): Promise<AgentTemplate & { definition: AgentDefinition }> {
  return apiFetch(`/api/marketplace/templates/${id}`)
}

export function publishTemplate(body: {
  agent_id: string
  display_name?: string
  description?: string
  category?: string
  overwrite?: boolean
}): Promise<{ published: boolean; name: string; overwritten: boolean }> {
  return apiFetch('/api/marketplace/templates', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function deleteTemplate(id: string): Promise<{ deleted: boolean; id: string }> {
  return apiFetch(`/api/marketplace/templates/${id}`, { method: 'DELETE' })
}

export function installTemplate(id: string): Promise<{ installed: boolean; agent: string; prompts_applied: number }> {
  return apiFetch(`/api/marketplace/templates/${id}/install`, { method: 'POST' })
}

export function importAgent(definition: AgentDefinition): Promise<{ imported: boolean; agent: string; prompts_applied: number }> {
  return apiFetch('/api/marketplace/import', {
    method: 'POST',
    body: JSON.stringify(definition),
  })
}

export function exportAgent(agentId: string): Promise<AgentDefinition> {
  return apiFetch<AgentDefinition>(`/api/marketplace/export/${agentId}`)
}

/** 触发浏览器下载 Agent 定义 JSON（导出） */
export async function downloadAgentJson(agentId: string, displayName?: string): Promise<void> {
  const definition = await exportAgent(agentId)
  const blob = new Blob([JSON.stringify(definition, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `agent-${agentId || displayName || 'export'}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}