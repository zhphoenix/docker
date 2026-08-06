"""MCP API - 平台 MCP 服务连接管理

基于 mcp_connections 表展示纳管状态，支持手动心跳探测。
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tools.postgres import postgres_tool
from monitoring.mcp_manager import check_heartbeat

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class McpUpdate(BaseModel):
    status: str | None = None


@router.get("")
async def list_mcp():
    """列出纳管的 MCP 服务"""
    rows = await postgres_tool.query(
        "SELECT name, url, kind, status, last_heartbeat, latency_ms, retry_count, updated_at "
        "FROM mcp_connections ORDER BY name"
    )
    return {"mcp": rows, "total": len(rows)}


@router.get("/{name}")
async def get_mcp(name: str):
    """单个 MCP 服务明细"""
    rows = await postgres_tool.query(
        "SELECT name, url, kind, status, last_heartbeat, latency_ms, retry_count, updated_at "
        "FROM mcp_connections WHERE name=$1",
        name,
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"MCP '{name}' not found")
    return rows[0]


@router.patch("/{name}")
async def update_mcp(name: str, body: McpUpdate):
    """更新 MCP 服务状态（人工标记）"""
    if body.status not in (None, "connected", "disconnected", "disabled"):
        raise HTTPException(status_code=400, detail="invalid status")
    result = await postgres_tool.execute(
        "UPDATE mcp_connections SET status=$2, updated_at=NOW() WHERE name=$1",
        name,
        body.status,
    )
    if "0" in result and await _exists(name) is False:
        raise HTTPException(status_code=404, detail=f"MCP '{name}' not found")
    return {"name": name, "status": body.status}


@router.post("/heartbeat")
async def heartbeat_all():
    """对所有已知 MCP 服务执行心跳探测"""
    results = await check_heartbeat()
    return {"results": results, "total": len(results)}


@router.post("/{name}/heartbeat")
async def heartbeat_one(name: str):
    """对单个 MCP 服务执行心跳探测"""
    results = await check_heartbeat(name)
    if not results:
        raise HTTPException(status_code=404, detail=f"MCP '{name}' not known")
    return results[0]


async def _exists(name: str) -> bool:
    rows = await postgres_tool.query("SELECT 1 FROM mcp_connections WHERE name=$1", name)
    return bool(rows)