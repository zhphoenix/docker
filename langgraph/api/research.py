"""Research API - 研究任务历史（只读）"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/research", tags=["research"])

# 持有后台任务引用，避免被 GC 回收
_background_tasks: set = set()


class CreateResearchRequest(BaseModel):
    question: str
    symbol: str | None = None
    market: str = "cn"
    agent_type: str = "research"


@router.post("", status_code=201)
async def create_research(req: CreateResearchRequest):
    """创建研究任务（NIC Research Trigger 入口，异步执行）

    频率限制：同 symbol 在 10 分钟内去重，避免误触发拥塞任务队列。
    """
    if req.symbol:
        try:
            recent = await postgres_tool.query(
                "SELECT id FROM research_tasks "
                "WHERE symbol = $1 AND created_at > NOW() - INTERVAL '10 minutes' "
                "LIMIT 1",
                req.symbol,
            )
            if recent:
                return {
                    "task_id": str(recent[0]["id"]),
                    "status": "running",
                    "duplicate": True,
                    "message": f"{req.symbol} 相关研究已在 10 分钟内触发，复用已有任务",
                }
        except Exception:  # noqa: BLE001
            logger.warning("Frequency check failed, skip dedup", exc_info=True)

    task_id = str(uuid.uuid4())
    try:
        await postgres_tool.execute(
            "INSERT INTO research_tasks (id, question, agent_type, market, symbol, status, created_at) "
            "VALUES ($1, $2, $3, $4, $5, 'running', NOW())",
            task_id, req.question, req.agent_type, req.market, req.symbol,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to create research task")
        raise HTTPException(status_code=500, detail=f"研究任务创建失败: {e}")

    async def _run():
        try:
            from agents.research_agent import ResearchAgent
            from schemas.chat import ChatRequest, ChatMessage
            agent = ResearchAgent()
            resp = await agent.run(
                ChatRequest(messages=[ChatMessage(role="user", content=req.question)])
            )
            answer = resp.choices[0].message.content if resp.choices else ""
            await postgres_tool.execute(
                "UPDATE research_tasks SET status='completed', answer=$1, "
                "completed_at=NOW() WHERE id=$2",
                answer, task_id,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("Research run failed: task=%s", task_id)
            await postgres_tool.execute(
                "UPDATE research_tasks SET status='failed', error=$1, "
                "completed_at=NOW() WHERE id=$2",
                str(e), task_id,
            )

    task = asyncio.create_task(_run())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {"task_id": task_id, "status": "running"}


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
