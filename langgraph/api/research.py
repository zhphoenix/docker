"""Research API - 研究任务历史（只读）"""

import logging

from fastapi import APIRouter, HTTPException

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/research", tags=["research"])


@router.get("")
async def list_research(
    status: str | None = None,
    symbol: str | None = None,
    limit: int = 50,
):
    """研究任务历史列表"""
    query = (
        "SELECT id, question, agent_type, market, symbol, quality, "
        "confidence, status, elapsed_seconds, document_count, created_at "
        "FROM research_tasks WHERE 1=1"
    )
    params: list = []
    idx = 1

    if status:
        query += f" AND status = ${idx}"
        params.append(status)
        idx += 1
    if symbol:
        query += f" AND symbol ILIKE ${idx}"
        params.append(f"%{symbol}%")
        idx += 1

    query += f" ORDER BY created_at DESC LIMIT ${idx}"
    params.append(limit)

    try:
        rows = await postgres_tool.query(query, *params)
        tasks = []
        for r in rows:
            tasks.append({
                "id": str(r["id"]),
                "question": r["question"],
                "agent_type": r.get("agent_type"),
                "market": r.get("market"),
                "symbol": r.get("symbol"),
                "quality": r.get("quality"),
                "confidence": r.get("confidence"),
                "status": r["status"],
                "elapsed_seconds": r.get("elapsed_seconds"),
                "document_count": r.get("document_count") or 0,
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            })
        return {"tasks": tasks, "total": len(tasks)}
    except Exception as e:
        logger.exception("Failed to list research tasks")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{research_id}")
async def get_research(research_id: str):
    """研究任务详情（含 plan 与 answer 全文）"""
    try:
        rows = await postgres_tool.query(
            "SELECT id, question, agent_type, market, symbol, plan, answer, "
            "quality, confidence, status, error, document_count, "
            "elapsed_seconds, created_at, completed_at "
            "FROM research_tasks WHERE id = $1",
            research_id,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Research task not found")

        r = rows[0]
        return {
            "id": str(r["id"]),
            "question": r["question"],
            "agent_type": r.get("agent_type"),
            "market": r.get("market"),
            "symbol": r.get("symbol"),
            "plan": r.get("plan") or {},
            "answer": r.get("answer"),
            "quality": r.get("quality"),
            "confidence": r.get("confidence"),
            "status": r["status"],
            "error": r.get("error"),
            "document_count": r.get("document_count") or 0,
            "elapsed_seconds": r.get("elapsed_seconds"),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            "completed_at": r["completed_at"].isoformat() if r.get("completed_at") else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get research task %s", research_id)
        raise HTTPException(status_code=500, detail=str(e))
