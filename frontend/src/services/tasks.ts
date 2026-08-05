import { apiFetch } from './api-client'

// 任务状态枚举（后端真实取值）：pending / running / done / failed
export type TaskStatus = 'pending' | 'running' | 'done' | 'failed'

// 任务类型枚举（后端真实取值）
export type TaskType =
  | 'doc_pipeline'
  | 'batch_embed'
  | 're-embed'
  | 'knowledge_extraction'
  | 'approval'

export interface TaskInfo {
  id: string
  task_type: string
  title: string
  status: TaskStatus
  progress: number
  stage: string | null
  current_name: string | null
  current_item: number | null
  total_items: number | null
  retry_count: number | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  error_message: string | null
  params?: Record<string, unknown> | null
  created_by?: string | null
  max_retries?: number | null
  duration_ms?: number | null
}

export interface TaskLog {
  id: string
  level: string
  message: string
  stage: string
  created_at: string | null
}

export interface TaskLogResponse {
  logs: TaskLog[]
  total: number
}

export interface TaskStats {
  total: number
  pending: number
  running: number
  done: number
  failed: number
}

export interface WorkerStatus {
  running: boolean
  active_tasks: number
  current_task_id: string | null
  registered_handlers: string[]
}

export interface ScheduleJob {
  id: string
  name: string
  next_run_time: string | null
  trigger: string
}

export interface ScheduleResponse {
  jobs: ScheduleJob[]
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

export function fetchTaskDetail(taskId: string): Promise<TaskInfo> {
  return apiFetch<TaskInfo>(`/api/tasks/${taskId}`)
}

export function retryTask(taskId: string): Promise<{ status: string; message: string }> {
  return apiFetch<{ status: string; message: string }>(`/api/tasks/${taskId}/retry`, {
    method: 'POST',
  })
}

export function fetchTaskLogs(taskId: string): Promise<TaskLogResponse> {
  return apiFetch<TaskLogResponse>(`/api/tasks/${taskId}/logs`)
}

export function cancelTask(
  taskId: string,
): Promise<{ status: string; message: string }> {
  return apiFetch<{ status: string; message: string }>(`/api/tasks/${taskId}/cancel`, {
    method: 'POST',
  })
}

export function pauseTask(
  taskId: string,
): Promise<{ status: string; message: string }> {
  return apiFetch<{ status: string; message: string }>(`/api/tasks/${taskId}/pause`, {
    method: 'POST',
  })
}

export function resumeTask(
  taskId: string,
): Promise<{ status: string; message: string }> {
  return apiFetch<{ status: string; message: string }>(`/api/tasks/${taskId}/resume`, {
    method: 'POST',
  })
}

export function deleteTask(
  taskId: string,
): Promise<{ status: string; message: string }> {
  return apiFetch<{ status: string; message: string }>(`/api/tasks/${taskId}`, {
    method: 'DELETE',
  })
}

export function cloneTask(
  taskId: string,
): Promise<{ status: string; task_id: string }> {
  return apiFetch<{ status: string; task_id: string }>(`/api/tasks/${taskId}/clone`, {
    method: 'POST',
  })
}

export function fetchTaskStats(): Promise<TaskStats> {
  return apiFetch<TaskStats>('/api/tasks/stats')
}

export function fetchWorkers(): Promise<WorkerStatus> {
  return apiFetch<WorkerStatus>('/api/tasks/workers')
}

export function fetchSchedule(): Promise<ScheduleResponse> {
  return apiFetch<ScheduleResponse>('/api/tasks/schedule')
}

export interface TriggerPipelineResponse {
  status: string
  task_id?: string
  stats?: Record<string, unknown>
}

export function triggerPipeline(params?: {
  limit?: number
  async_mode?: boolean
}): Promise<TriggerPipelineResponse> {
  return apiFetch<TriggerPipelineResponse>('/api/tasks/pipeline/trigger', {
    method: 'POST',
    body: JSON.stringify({ limit: params?.limit ?? 50, async_mode: params?.async_mode ?? true }),
  })
}

export interface BatchEmbedResponse {
  status: string
  task_id: string
}

export function triggerBatchEmbed(params?: {
  collection?: string
  batch_size?: number
  limit?: number
}): Promise<BatchEmbedResponse> {
  return apiFetch<BatchEmbedResponse>('/api/tasks/batch-embed', {
    method: 'POST',
    body: JSON.stringify({
      collection: params?.collection ?? 'documents_cn',
      batch_size: params?.batch_size ?? 64,
      limit: params?.limit ?? 0,
    }),
  })
}

export interface ReembedResponse {
  status: string
  task_id: string
}

export function reembedDocument(documentId: string): Promise<ReembedResponse> {
  return apiFetch<ReembedResponse>('/api/tasks/re-embed', {
    method: 'POST',
    body: JSON.stringify({ document_id: documentId }),
  })
}

export interface PipelineStatusResponse {
  document_status: Record<string, unknown>
}

export function fetchPipelineStatus(): Promise<PipelineStatusResponse> {
  return apiFetch<PipelineStatusResponse>('/api/tasks/pipeline/status')
}
