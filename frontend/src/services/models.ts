import { apiFetch } from './api-client'

export interface ModelInfo {
  id: string
  object: string
  created?: number
  owned_by: string
}

export interface ModelsResponse {
  object: string
  data: ModelInfo[]
}

export function fetchModels(): Promise<ModelsResponse> {
  return apiFetch<ModelsResponse>('/v1/models')
}
