"""Tasks API - 任务管理与 Pipeline 触发"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from graph.task_queue import task_queue
from graph.pipeline import doc_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TriggerPipelineRequest(BaseModel):
    limit: int = 50


@router.get("")
async def list_tasks(status: str | None = None, task_type: str | None = None, limit: int = 20):
    """列出任务"""
    from tools.postgres import postgres_tool

    query = "SELECT id, task_type, title, status, progress, stage, current_item, total_items, created_at, error_message FROM tasks WHERE 1=1"
    params = []
    idx = 1

    if status:
        query += f" AND status = ${idx}"
        params.append(status)
        idx += 1
    if task_type:
        query += f" AND task_type = ${idx}"
        params.append(task_type)
        idx += 1

    query += f" ORDER BY created_at DESC LIMIT ${idx}"
    params.append(limit)

    rows = await postgres_tool.query(query, *params)
    for r in rows:
        r["id"] = str(r["id"])
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
    return {"tasks": rows, "total": len(rows)}


@router.get("/{task_id}")
async def get_task(task_id: str):
    """获取任务详情"""
    task = await task_queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task["id"] = str(task["id"])
    return task


@router.post("/{task_id}/retry")
async def retry_task(task_id: str):
    """重试失败的任务"""
    success = await task_queue.retry_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Task is not in failed state")
    return {"status": "ok", "message": "Task reset to pending"}


@router.post("/pipeline/trigger")
async def trigger_pipeline(req: TriggerPipelineRequest):
    """手动触发文档处理 Pipeline"""
    stats = await doc_pipeline.process_pending_documents(limit=req.limit)
    return {"status": "ok", "stats": stats}


@router.get("/pipeline/status")
async def pipeline_status():
    """获取文档处理状态统计"""
    status = await doc_pipeline.get_pipeline_status()
    return {"document_status": status}
