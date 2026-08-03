"""Tasks API - 任务管理与 Pipeline 触发"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from runtime.queue import task_queue
from pipelines.document_pipeline import doc_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TriggerPipelineRequest(BaseModel):
    limit: int = 50
    async_mode: bool = True  # True=入队等待 Worker 处理，False=同步执行


class ReindexRequest(BaseModel):
    document_id: str


class BatchEmbedRequest(BaseModel):
    collection: str = "documents_cn"
    batch_size: int = 64
    limit: int = 0  # 0=全部


@router.get("")
async def list_tasks(status: str | None = None, task_type: str | None = None, limit: int = 20):
    """列出任务"""
    from tools.postgres import postgres_tool

    query = "SELECT id, task_type, title, status, progress, stage, current_name, current_item, total_items, retry_count, params, created_at, started_at, finished_at, error_message FROM tasks WHERE 1=1"
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
        if r.get("started_at"):
            r["started_at"] = r["started_at"].isoformat()
        if r.get("finished_at"):
            r["finished_at"] = r["finished_at"].isoformat()
    return {"tasks": rows, "total": len(rows)}


@router.get("/pipeline/status")
async def pipeline_status():
    """获取文档处理状态统计"""
    status = await doc_pipeline.get_pipeline_status()
    return {"document_status": status}


@router.post("/pipeline/trigger")
async def trigger_pipeline(req: TriggerPipelineRequest):
    """触发文档处理 Pipeline

    async_mode=True: 创建任务入队，由 Worker 后台处理
    async_mode=False: 同步执行（等待完成）
    """
    if req.async_mode:
        task_id = await task_queue.create_task(
            task_type="doc_pipeline",
            title=f"文档处理 Pipeline (limit={req.limit})",
            params={"limit": req.limit},
            total_items=req.limit,
            created_by="api",
        )
        return {"status": "queued", "task_id": task_id}
    else:
        stats = await doc_pipeline.process_pending_documents(limit=req.limit)
        return {"status": "ok", "stats": stats}


@router.post("/batch-embed")
async def trigger_batch_embed(req: BatchEmbedRequest):
    """触发批量向量化（异步入队）"""
    task_id = await task_queue.create_task(
        task_type="batch_embed",
        title=f"Batch Embed {req.collection} (batch={req.batch_size})",
        params={
            "collection": req.collection,
            "batch_size": req.batch_size,
            "limit": req.limit,
        },
        created_by="api",
    )
    return {"status": "queued", "task_id": task_id}


@router.post("/reindex")
async def reindex_document(req: ReindexRequest):
    """重新索引单个文档"""
    success = await doc_pipeline.reindex_document(req.document_id)
    if not success:
        raise HTTPException(status_code=400, detail="Reindex failed")
    # 创建任务入队
    task_id = await task_queue.create_task(
        task_type="doc_pipeline",
        title=f"重新索引 {req.document_id[:8]}",
        params={"limit": 1},
        total_items=1,
        created_by="api",
    )
    return {"status": "queued", "task_id": task_id}


@router.get("/workers")
async def worker_status():
    """获取 Worker 运行状态（in-process 内存态）"""
    from runtime.worker import get_worker_status
    return get_worker_status()


@router.get("/schedule")
async def schedule_list():
    """获取 APScheduler 已注册任务列表（只读）"""
    from runtime.scheduler import get_scheduler_jobs
    return {"jobs": get_scheduler_jobs()}


@router.get("/stats")
async def task_stats():
    """按状态分组的任务统计（pending/running/done/failed）"""
    from tools.postgres import postgres_tool
    rows = await postgres_tool.query(
        "SELECT status, COUNT(*) AS cnt FROM tasks GROUP BY status"
    )
    counts = {r["status"]: r["cnt"] for r in rows}
    return {
        "total": sum(counts.values()),
        "pending": counts.get("pending", 0),
        "running": counts.get("running", 0),
        "done": counts.get("done", 0),
        "failed": counts.get("failed", 0),
    }


@router.get("/{task_id}")
async def get_task(task_id: str):
    """获取任务详情"""
    task = await task_queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task["id"] = str(task["id"])
    if task.get("created_at"):
        task["created_at"] = task["created_at"].isoformat()
    if task.get("started_at"):
        task["started_at"] = task["started_at"].isoformat()
    if task.get("finished_at"):
        task["finished_at"] = task["finished_at"].isoformat()
    return task


@router.get("/{task_id}/logs")
async def get_task_logs(task_id: str, limit: int = 200):
    """获取任务日志（按 created_at 升序）"""
    task = await task_queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    logs = await task_queue.get_task_logs(task_id, limit=limit)
    return {"logs": logs, "total": len(logs)}


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """取消运行中的任务（batch_embed 支持优雅中断，其余不支持的返回 400）"""
    task = await task_queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] not in ("pending", "running"):
        raise HTTPException(status_code=400, detail="Task is not active")

    if task["task_type"] == "batch_embed":
        from services.batch_embed import cancel_batch_embed
        cancel_batch_embed()
        return {"status": "ok", "message": "Cancel requested for batch_embed"}

    raise HTTPException(status_code=400, detail="Task type not cancellable (use Cancel via batch_embed)")


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """删除任务记录（仅 done/failed 可删）"""
    success = await task_queue.delete_task(task_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Task not found or only done/failed tasks can be deleted",
        )
    return {"status": "ok", "message": "Task deleted"}


@router.post("/{task_id}/clone")
async def clone_task(task_id: str):
    """复制任务参数创建新任务"""
    new_id = await task_queue.clone_task(task_id)
    if not new_id:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "ok", "task_id": new_id}


@router.post("/{task_id}/retry")
async def retry_task(task_id: str):
    """重试失败的任务"""
    success = await task_queue.retry_task(task_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Task is not in failed state or exceeded max retries",
        )
    return {"status": "ok", "message": "Task reset to pending"}
