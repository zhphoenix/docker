"""Approvals API - 人审管理"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.approval import list_pending_approvals, approve, reject

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/approvals", tags=["approvals"])


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
    """审批拒绝"""
    result = await reject(approval_id, reason=req.reason)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", ""))
    return result
