"""Prompts API - 提示词管理（DB 为唯一事实源）

Agent 视角的 Prompt 集合 = 该 agent 专属 + common 下的通用节点模板。
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tools.postgres import postgres_tool
import prompts.loader as loader

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/prompts", tags=["prompts"])


class PromptSave(BaseModel):
    content: str


class PromptPreview(BaseModel):
    content: str
    variables: dict[str, str] = {}


class PromptInvalidate(BaseModel):
    agent_id: str
    name: str


@router.get("")
async def list_prompts(agent_id: str | None = None):
    """列出 Prompt（agent_id 时返回该 agent + common 的集合）"""
    if agent_id:
        rows = await postgres_tool.query(
            "SELECT agent_id, name, version, is_active, created_at "
            "FROM agent_prompts WHERE agent_id IN ($1, 'common') "
            "ORDER BY agent_id, name, version DESC",
            agent_id,
        )
    else:
        rows = await postgres_tool.query(
            "SELECT agent_id, name, version, is_active, created_at "
            "FROM agent_prompts ORDER BY agent_id, name, version DESC"
        )
    return {"prompts": rows, "total": len(rows)}


@router.get("/{agent_id}/{name}")
async def get_prompt(agent_id: str, name: str):
    """Prompt 详情：当前生效版本内容 + 历史版本"""
    active = await postgres_tool.query(
        "SELECT agent_id, name, content, version, is_active, created_at "
        "FROM agent_prompts WHERE agent_id=$1 AND name=$2 AND is_active=true "
        "ORDER BY version DESC LIMIT 1",
        agent_id, name,
    )
    history = await postgres_tool.query(
        "SELECT agent_id, name, version, is_active, created_at "
        "FROM agent_prompts WHERE agent_id=$1 AND name=$2 "
        "ORDER BY version DESC",
        agent_id, name,
    )
    if not active and not history:
        raise HTTPException(status_code=404, detail=f"Prompt '{agent_id}/{name}' not found")
    return {
        "current": active[0] if active else None,
        "history": history,
    }


@router.put("/{agent_id}/{name}")
async def save_prompt(agent_id: str, name: str, body: PromptSave):
    """保存新版本（version=max+1，标记为生效，旧版本失效）"""
    max_row = await postgres_tool.query(
        "SELECT COALESCE(MAX(version), 0) AS v FROM agent_prompts "
        "WHERE agent_id=$1 AND name=$2",
        agent_id, name,
    )
    next_version = (max_row[0]["v"] if max_row else 0) + 1

    # 旧版本失效
    await postgres_tool.query(
        "UPDATE agent_prompts SET is_active=false WHERE agent_id=$1 AND name=$2",
        agent_id, name,
    )
    # 写入新版本
    await postgres_tool.query(
        "INSERT INTO agent_prompts (agent_id, name, content, version, is_active) "
        "VALUES ($1, $2, $3, $4, true)",
        agent_id, name, body.content, next_version,
    )
    # 更新内存缓存
    await loader.refresh_prompt(agent_id, name, body.content)
    logger.info("Prompt saved: %s/%s v%d", agent_id, name, next_version)
    return {"agent_id": agent_id, "name": name, "version": next_version}


@router.post("/preview")
async def preview_prompt(body: PromptPreview):
    """变量替换预览"""
    content = body.content
    for key, value in body.variables.items():
        content = content.replace("{" + key + "}", str(value))
    return {"rendered": content}


@router.post("/cache/invalidate")
async def invalidate_cache(body: PromptInvalidate):
    """使 loader 从 DB 重新加载该 Prompt（用于恢复/外部修改后同步）"""
    await loader.refresh_prompt(body.agent_id, body.name)
    return {"ok": True, "agent_id": body.agent_id, "name": body.name}