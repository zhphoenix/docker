import { apiFetch } from './api-client'

export interface HealthResponse {
  status: string
  services: Record<string, string>
}

export function fetchHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/health')
}
