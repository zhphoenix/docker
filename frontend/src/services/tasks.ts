import { apiFetch } from './api-client'

export interface TaskInfo {
  id: string
  task_type: string
  title: string
  status: string
  progress: number
  stage: string | null
  current_item: number | null
  total_items: number | null
  retry_count: number | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  error_message: string | null
}

export interface TasksResponse {
  tasks: TaskInfo[]
  total: number
}

export interface TaskQueryParams {
  status?: string
  task_type?: string
  limit?: number
}

export function fetchTasks(params?: TaskQueryParams): Promise<TasksResponse> {
  const search = new URLSearchParams()
  if (params?.status) search.set('status', params.status)
  if (params?.task_type) search.set('task_type', params.task_type)
  if (params?.limit) search.set('limit', String(params.limit))

  const qs = search.toString()
  return apiFetch<TasksResponse>(`/api/tasks${qs ? `?${qs}` : ''}`)
}
