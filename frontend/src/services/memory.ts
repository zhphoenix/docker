import { apiFetch } from './api-client'

export interface MemoryOverview {
  working: { total: number; success: number; failed: number; last_run: string | null }
  episodic: { total: number; completed: number; failed: number; last_run: string | null }
  knowledge: { collections: { name: string }[] }
}

export interface EpisodeItem {
  id: string
  question: string
  agent_type: string
  market: string | null
  symbol: string | null
  quality: string | null
  confidence: number | null
  document_count: number
  elapsed_seconds: number | null
  status: string
  created_at: string
  completed_at: string | null
}

export interface RunItem {
  id: string
  agent_id: string
  task_kind: string
  status: string
  question: string | null
  duration_ms: number | null
  error_category: string | null
  created_at: string
}

export function fetchMemoryOverview(): Promise<MemoryOverview> {
  return apiFetch<MemoryOverview>('/api/memory')
}

export function fetchEpisodes(limit = 20): Promise<{ episodes: EpisodeItem[]; total: number }> {
  return apiFetch(`/api/memory/episodes?limit=${limit}`)
}

export function fetchRuns(agentId?: string, limit = 20): Promise<RunItem[]> {
  const qs = new URLSearchParams({ limit: String(limit) })
  if (agentId) qs.set('agent_id', agentId)
  return apiFetch(`/api/memory/runs?${qs.toString()}`)
}