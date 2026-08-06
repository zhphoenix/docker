"""Memory API - 三层记忆管理

- 工作记忆 (Working): agent_runs 运行记录
- 情景记忆 (Episodic): research_tasks 研究任务历史
- 知识记忆 (Knowledge): Qdrant 向量集合
"""
import logging

from fastapi import APIRouter

from tools.postgres import postgres_tool
from tools.qdrant import qdrant_tool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("")
async def memory_overview():
    """三层记忆概览"""
    work = await postgres_tool.query(
        "SELECT COUNT(*) AS total, "
        "COUNT(*) FILTER (WHERE status='success') AS success, "
        "COUNT(*) FILTER (WHERE status='failed') AS failed, "
        "MAX(created_at) AS last_run FROM agent_runs"
    )
    epi = await postgres_tool.query(
        "SELECT COUNT(*) AS total, "
        "COUNT(*) FILTER (WHERE status='completed') AS completed, "
        "COUNT(*) FILTER (WHERE status='failed') AS failed, "
        "MAX(created_at) AS last_run FROM research_tasks"
    )
    # 知识记忆：Qdrant 集合列表（尽力而为）
    collections = []
    try:
        cols = await qdrant_tool.list_collections()
        collections = cols or []
    except Exception as e:
        logger.warning("Qdrant list_collections failed: %s", e)

    return {
        "working": work[0] if work else {},
        "episodic": epi[0] if epi else {},
        "knowledge": {"collections": collections},
    }


@router.get("/episodes")
async def list_episodes(symbol: str | None = None, limit: int = 20, offset: int = 0):
    """情景记忆：研究任务列表"""
    if symbol:
        rows = await postgres_tool.query(
            "SELECT id, question, agent_type, market, symbol, quality, confidence, "
            "document_count, elapsed_seconds, status, created_at, completed_at "
            "FROM research_tasks WHERE symbol=$1 "
            "ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            symbol,
            limit,
            offset,
        )
    else:
        rows = await postgres_tool.query(
            "SELECT id, question, agent_type, market, symbol, quality, confidence, "
            "document_count, elapsed_seconds, status, created_at, completed_at "
            "FROM research_tasks ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit,
            offset,
        )
    total_rows = await postgres_tool.query("SELECT COUNT(*) AS total FROM research_tasks")
    for r in rows:
        r["id"] = str(r["id"])
    return {"episodes": rows, "total": total_rows[0]["total"] if total_rows else 0}


@router.get("/episodes/{task_id}")
async def get_episode(task_id: str):
    """情景记忆：单个任务详情"""
    rows = await postgres_tool.query("SELECT * FROM research_tasks WHERE id=$1", task_id)
    if not rows:
        return None
    rows[0]["id"] = str(rows[0]["id"])
    return rows[0]


@router.get("/runs")
async def list_runs(agent_id: str | None = None, limit: int = 20):
    """工作记忆：Agent 运行记录"""
    if agent_id:
        rows = await postgres_tool.query(
            "SELECT id, agent_id, task_kind, status, question, duration_ms, "
            "error_category, tokens_in, tokens_out, created_at "
            "FROM agent_runs WHERE agent_id=$1 ORDER BY created_at DESC LIMIT $2",
            agent_id,
            limit,
        )
    else:
        rows = await postgres_tool.query(
            "SELECT id, agent_id, task_kind, status, question, duration_ms, "
            "error_category, tokens_in, tokens_out, created_at "
            "FROM agent_runs ORDER BY created_at DESC LIMIT $1",
            limit,
        )
    for r in rows:
        r["id"] = str(r["id"])
    return rows