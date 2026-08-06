"""Tools API - Tool 管理与调用统计

工具清单来自运行时已埋点的工具（agent_tool_stats 表决），
以及配置文件中的声明式工具集合。
"""
import logging

from fastapi import APIRouter, HTTPException

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tools", tags=["tools"])

# 已埋点采集的核心工具（llm.chat / search / embedding / qdrant / reranker）
INSTRUMENTED_TOOLS = ["llm.chat", "search", "embedding", "qdrant", "reranker"]


@router.get("")
async def list_tools():
    """列出已知工具及其调用统计概要"""
    rows = await postgres_tool.query(
        "SELECT tool_name, COUNT(*) AS calls, "
        "COUNT(*) FILTER (WHERE success) AS success_calls, "
        "AVG(duration_ms) AS avg_ms, MAX(duration_ms) AS max_ms, "
        "MAX(created_at) AS last_at "
        "FROM agent_tool_stats GROUP BY tool_name ORDER BY calls DESC"
    )
    stats = {r["tool_name"]: r for r in rows}
    tools = []
    for name in INSTRUMENTED_TOOLS:
        s = stats.get(name)
        tools.append(
            {
                "name": name,
                "registered": True,
                "calls": s["calls"] if s else 0,
                "success_calls": s["success_calls"] if s else 0,
                "avg_ms": round(s["avg_ms"], 1) if s and s["avg_ms"] is not None else None,
                "max_ms": s["max_ms"] if s else None,
                "last_at": s["last_at"] if s else None,
            }
        )
    return {"tools": tools, "total": len(tools)}


@router.get("/stats")
async def tool_stats(agent_id: str | None = None, days: int = 7):
    """工具调用聚合统计（按时段）"""
    if agent_id:
        rows = await postgres_tool.query(
            "SELECT tool_name, COUNT(*) AS calls, "
            "COUNT(*) FILTER (WHERE success) AS success_calls, "
            "AVG(duration_ms) AS avg_ms, "
            "COUNT(*) FILTER (WHERE error_type IS NOT NULL) AS errors "
            "FROM agent_tool_stats "
            "WHERE agent_id=$1 AND created_at > NOW() - ($2 || ' days')::interval "
            "GROUP BY tool_name ORDER BY calls DESC",
            agent_id,
            str(days),
        )
    else:
        rows = await postgres_tool.query(
            "SELECT tool_name, COUNT(*) AS calls, "
            "COUNT(*) FILTER (WHERE success) AS success_calls, "
            "AVG(duration_ms) AS avg_ms, "
            "COUNT(*) FILTER (WHERE error_type IS NOT NULL) AS errors "
            "FROM agent_tool_stats "
            "WHERE created_at > NOW() - ($1 || ' days')::interval "
            "GROUP BY tool_name ORDER BY calls DESC",
            str(days),
        )
    return {"agent_id": agent_id, "days": days, "stats": rows}


@router.get("/{name}")
async def get_tool(name: str):
    """单个工具明细"""
    rows = await postgres_tool.query(
        "SELECT tool_name, COUNT(*) AS calls, "
        "COUNT(*) FILTER (WHERE success) AS success_calls, "
        "AVG(duration_ms) AS avg_ms, MAX(duration_ms) AS max_ms, "
        "COUNT(*) FILTER (WHERE error_type IS NOT NULL) AS errors, "
        "MAX(created_at) AS last_at "
        "FROM agent_tool_stats WHERE tool_name=$1 GROUP BY tool_name",
        name,
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' has no stats yet")
    return rows[0]