import { apiFetch } from './api-client'

// ─── Approvals (人审任务) ───────────────────────────────

export interface ApprovalItem {
  id: string
  title: string
  action_type: string
  content_preview: string
  created_by: string
  created_at: string | null
}

export interface ApprovalsResponse {
  approvals: ApprovalItem[]
  total: number
}

export function fetchPendingApprovals(limit = 20): Promise<ApprovalsResponse> {
  return apiFetch<ApprovalsResponse>(`/api/approvals?limit=${limit}`)
}

export function approveApproval(approvalId: string): Promise<{ status: string; action_type: string; result: string }> {
  return apiFetch<{ status: string; action_type: string; result: string }>(
    `/api/approvals/${encodeURIComponent(approvalId)}/approve`,
    { method: 'POST' }
  )
}

export function rejectApproval(
  approvalId: string,
  reason = ''
): Promise<{ status: string; reason: string }> {
  return apiFetch<{ status: string; reason: string }>(
    `/api/approvals/${encodeURIComponent(approvalId)}/reject`,
    {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }
  )
}