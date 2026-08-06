import { apiFetch } from './api-client'

export interface SkillInfo {
  name: string
  description: string
  version: string
  tags: string[]
  enabled: boolean
}

export function fetchSkills(): Promise<SkillInfo[]> {
  return apiFetch<SkillInfo[]>('/api/skills')
}

export function fetchSkillDetail(name: string): Promise<SkillInfo> {
  return apiFetch<SkillInfo>(`/api/skills/${encodeURIComponent(name)}`)
}

export function toggleSkill(name: string, enabled: boolean): Promise<{ name: string; enabled: boolean }> {
  return apiFetch(`/api/skills/${encodeURIComponent(name)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
}

export function reloadSkills(): Promise<SkillInfo[]> {
  return apiFetch<SkillInfo[]>('/api/skills/reload', { method: 'POST' })
}