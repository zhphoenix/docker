"""Approvals API - 人审管理"""

import json
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.approval import list_pending_approvals, approve, reject, register_approval_callback
from tools.postgres import postgres_tool
from knowledge_agent.storage.postgres import knowledge_storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/approvals", tags=["approvals"])


async def _get_approval_params(approval_id: str) -> dict:
    """读取审批任务的 params（action_type + params）"""
    rows = await postgres_tool.query(
        "SELECT params FROM tasks WHERE id = $1 AND task_type = 'approval'",
        approval_id,
    )
    if not rows:
        return {}
    params_data = rows[0].get("params") or {}
    if isinstance(params_data, str):
        try:
            params_data = json.loads(params_data)
        except Exception:
            params_data = {}
    return params_data or {}


async def _approve_knowledge_inbox(action_params: dict) -> None:
    """审批通过回调：将 knowledge_inbox 状态置为 APPROVED"""
    inbox_id = action_params.get("inbox_id")
    if inbox_id:
        await knowledge_storage.update_inbox_status(str(inbox_id), "APPROVED", reviewer="human")
        logger.info("Inbox approved via approval | inbox=%s", inbox_id)


# 注册 knowledge_inbox 审核回调：审批通过 → 同步 inbox 状态
register_approval_callback("knowledge_inbox_approve", _approve_knowledge_inbox)


class RejectRequest(BaseModel):
    reason: str = ""


@router.get("")
async def get_approvals(limit: int = 20):
    """列出待审批任务"""
    approvals = await list_pending_approvals(limit=limit)
    return {"approvals": approvals, "total": len(approvals)}


@router.post("/{approval_id}/approve")
async def approve_task(approval_id: str):
    """审批通过 → 执行操作"""
    result = await approve(approval_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", ""))
    return result


@router.post("/{approval_id}/reject")
async def reject_task(approval_id: str, req: RejectRequest):
    """审批拒绝：标记任务 rejected，并同步 knowledge_inbox 为 REJECTED"""
    params_data = await _get_approval_params(approval_id)
    action_type = params_data.get("action_type", "")
    action_params = params_data.get("params", {}) or {}

    result = await reject(approval_id, reason=req.reason)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", ""))

    # 同步 inbox 状态为 REJECTED
    if action_type == "knowledge_inbox_approve":
        inbox_id = action_params.get("inbox_id")
        if inbox_id:
            await knowledge_storage.update_inbox_status(str(inbox_id), "REJECTED", reviewer="human")
            logger.info("Inbox rejected via approval | inbox=%s", inbox_id)

    return result
