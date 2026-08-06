"""Skills API - Skill 管理（基于运行时注册表）

Skill 为运行时注册（RAG 检索 / 大师分析 / 文章摘要等），
enabled 状态存于内存 registry，支持热重载与启用/禁用。
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from skills.registry import get_registry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/skills", tags=["skills"])


class SkillToggle(BaseModel):
    enabled: bool


@router.get("")
async def list_skills():
    """列出所有已注册 Skill（含启用状态）"""
    return get_registry().list_all()


@router.get("/{name}")
async def get_skill(name: str):
    """获取单个 Skill 明细"""
    reg = get_registry()
    skill = reg.get(name)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return {
        "name": skill.name,
        "description": skill.description,
        "version": skill.version,
        "tags": skill.tags,
        "enabled": reg.is_enabled(name),
    }


@router.patch("/{name}")
async def toggle_skill(name: str, body: SkillToggle):
    """启用/禁用 Skill（持久化到 DB）"""
    reg = get_registry()
    if not await reg.set_enabled(name, body.enabled):
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return {"name": name, "enabled": body.enabled}


@router.post("/reload")
async def reload_skills():
    """重新加载全部 Skill（保留启用状态）"""
    return await get_registry().reload()