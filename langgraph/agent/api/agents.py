"""Agents API - Agent 只读列表（合并 DB 配置 + 运行时注册表）"""

import json
import logging

from fastapi import APIRouter

from graph.router import AGENT_REGISTRY
from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
async def list_agents():
    """列出所有 Agent（内置 + 自定义）

    合并 AGENT_REGISTRY 运行时信息与 agents 表配置。
    agents 表查询失败时降级为仅返回内置 Agent。
    """
    agents = []

    # 1. 内置 Agent（来自 AGENT_REGISTRY）
    for name, cls in AGENT_REGISTRY.items():
        agents.append({
            "id": name,
            "name": name,
            "description": (cls.__doc__ or "").strip().split("\n")[0],
            "model": None,
            "tools": [],
            "is_active": True,
            "source": "builtin",
        })

    # 2. 自定义 Agent（来自 agents 表，查询失败时降级跳过）
    try:
        rows = await postgres_tool.query(
            "SELECT id, name, description, model, tools, is_active "
            "FROM agents ORDER BY created_at DESC"
        )
        for r in rows:
            # tools 可能是 JSONB 字符串或 list
            tools = r.get("tools") or []
            if isinstance(tools, str):
                try:
                    tools = json.loads(tools)
                except (json.JSONDecodeError, TypeError):
                    tools = []

            agents.append({
                "id": str(r["id"]),
                "name": r["name"],
                "description": r.get("description") or "",
                "model": r.get("model"),
                "tools": tools,
                "is_active": bool(r.get("is_active", True)),
                "source": "custom",
            })
    except Exception:
        logger.warning("Failed to query agents table, returning builtin agents only", exc_info=True)

    return {"agents": agents, "total": len(agents)}
