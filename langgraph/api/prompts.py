"""Prompts API - 提示词管理（DB 为唯一事实源）

Agent 视角的 Prompt 集合 = 该 agent 专属 + common 下的通用节点模板。

AC-P4-2 Prompt Version Control：
  - 编辑保存为草稿（不生效）
  - 提交发布 → 创建审批任务（复用 approvals API）
  - 审批通过 → 回调将草稿发布为生效版本（旧版本失效）
  - 提供两版本 diff 可视化
"""

import difflib
import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tools.postgres import postgres_tool
from services.approval import create_approval, register_approval_callback
import prompts.loader as loader

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/prompts", tags=["prompts"])

# 幂等保障：老库无 status 列时的 ALTER TABLE（仅执行一次）
_status_ensured = False


class PromptSave(BaseModel):
    content: str


class PromptSubmit(BaseModel):
    approver: str = "admin"  # 预填审批人/备注


class PromptPreview(BaseModel):
    content: str
    variables: dict[str, str] = {}


class PromptInvalidate(BaseModel):
    agent_id: str
    name: str


async def _ensure_table() -> None:
    """确保 agent_prompts 存在 status 列（幂等，老库迁移用）"""
    global _status_ensured
    if _status_ensured:
        return
    try:
        await postgres_tool.execute(
            "ALTER TABLE agent_prompts "
            "ADD COLUMN IF NOT EXISTS status VARCHAR(32) DEFAULT 'published'"
        )
        _status_ensured = True
    except Exception as e:  # noqa: BLE001
        logger.warning("ensure agent_prompts.status column failed: %s", e)


async def _publish_prompt(params: dict) -> None:
    """审批通过回调：将指定草稿版本发布为生效版本（AC-P4-2）"""
    agent_id = params.get("agent_id")
    name = params.get("name")
    version = params.get("version")
    if not all([agent_id, name, version]):
        raise ValueError("prompt_publish params missing agent_id/name/version")
    # 旧版本全部失效
    await postgres_tool.execute(
        "UPDATE agent_prompts SET is_active=false, status='archived' "
        "WHERE agent_id=$1 AND name=$2",
        agent_id, name,
    )
    # 目标草稿发布为生效
    await postgres_tool.execute(
        "UPDATE agent_prompts SET is_active=true, status='published' "
        "WHERE agent_id=$1 AND name=$2 AND version=$3",
        agent_id, name, version,
    )
    # 刷新内存缓存
    await loader.refresh_prompt(agent_id, name)
    logger.info("Prompt published: %s/%s v%d", agent_id, name, version)


# 注册发布回调：审批通过 → 发布草稿
register_approval_callback("prompt_publish", _publish_prompt)


@router.get("")
async def list_prompts(agent_id: str | None = None):
    """列出 Prompt（agent_id 时返回该 agent + common 的集合）"""
    await _ensure_table()
    # 每个 prompt 名只返回最新版本（AC-P4-2 版本控制下避免列表重复）
    if agent_id:
        rows = await postgres_tool.query(
            "SELECT DISTINCT ON (agent_id, name) agent_id, name, version, is_active, status, created_at "
            "FROM agent_prompts WHERE agent_id IN ($1, 'common') "
            "ORDER BY agent_id, name, version DESC",
            agent_id,
        )
    else:
        rows = await postgres_tool.query(
            "SELECT DISTINCT ON (agent_id, name) agent_id, name, version, is_active, status, created_at "
            "FROM agent_prompts ORDER BY agent_id, name, version DESC"
        )
    return {"prompts": rows, "total": len(rows)}


@router.get("/{agent_id}/{name}")
async def get_prompt(agent_id: str, name: str):
    """Prompt 详情：当前生效版本内容 + 历史版本（含内容，供 diff）"""
    await _ensure_table()
    active = await postgres_tool.query(
        "SELECT agent_id, name, content, version, is_active, status, created_at "
        "FROM agent_prompts WHERE agent_id=$1 AND name=$2 AND is_active=true "
        "ORDER BY version DESC LIMIT 1",
        agent_id, name,
    )
    history = await postgres_tool.query(
        "SELECT agent_id, name, version, is_active, status, created_at "
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
    """保存新版本为草稿（AC-P4-2：不直接生效，需提交审批发布）"""
    await _ensure_table()
    max_row = await postgres_tool.query(
        "SELECT COALESCE(MAX(version), 0) AS v FROM agent_prompts "
        "WHERE agent_id=$1 AND name=$2",
        agent_id, name,
    )
    next_version = (max_row[0]["v"] if max_row else 0) + 1

    # 写入草稿（不生效）
    await postgres_tool.execute(
        "INSERT INTO agent_prompts (agent_id, name, content, version, is_active, status) "
        "VALUES ($1, $2, $3, $4, false, 'draft')",
        agent_id, name, body.content, next_version,
    )
    logger.info("Prompt draft saved: %s/%s v%d", agent_id, name, next_version)
    return {"agent_id": agent_id, "name": name, "version": next_version, "status": "draft"}


@router.post("/{agent_id}/{name}/submit")
async def submit_prompt(agent_id: str, name: str, body: PromptSubmit):
    """提交最新草稿发布审批（AC-P4-2：发布需审批通过）"""
    await _ensure_table()
    draft = await postgres_tool.query(
        "SELECT agent_id, name, content, version FROM agent_prompts "
        "WHERE agent_id=$1 AND name=$2 AND status='draft' "
        "ORDER BY version DESC LIMIT 1",
        agent_id, name,
    )
    if not draft:
        raise HTTPException(status_code=400, detail=f"No draft found for '{agent_id}/{name}'")

    d = draft[0]
    # 标记为待审批
    await postgres_tool.execute(
        "UPDATE agent_prompts SET status='pending_approval' "
        "WHERE agent_id=$1 AND name=$2 AND version=$3",
        agent_id, name, d["version"],
    )
    # 创建审批任务（复用 approval 机制）
    approval_id = await create_approval(
        title=f"发布 Prompt {agent_id}/{name} v{d['version']}",
        action_type="prompt_publish",
        params={"agent_id": agent_id, "name": name, "version": d["version"]},
        content_preview=d["content"][:5000],
        created_by=body.approver,
    )
    return {
        "approval_id": approval_id,
        "agent_id": agent_id,
        "name": name,
        "version": d["version"],
        "status": "pending_approval",
    }


@router.get("/{agent_id}/{name}/diff")
async def prompt_diff(agent_id: str, name: str, v1: int, v2: int):
    """两版本 diff 可视化（AC-P4-2）"""
    await _ensure_table()
    rows = await postgres_tool.query(
        "SELECT version, content FROM agent_prompts "
        "WHERE agent_id=$1 AND name=$2 AND version IN ($3, $4) "
        "ORDER BY version",
        agent_id, name, v1, v2,
    )
    by_ver = {r["version"]: r["content"] for r in rows}
    if v1 not in by_ver or v2 not in by_ver:
        raise HTTPException(status_code=404, detail="One of the versions not found")

    old, new = by_ver[v1], by_ver[v2]
    # 结构化 diff：逐行标记 added/removed/context
    sm = difflib.SequenceMatcher(None, old.splitlines(), new.splitlines())
    lines = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for line in old.splitlines()[i1:i2]:
                lines.append({"type": "context", "text": line})
        elif tag == "delete":
            for line in old.splitlines()[i1:i2]:
                lines.append({"type": "removed", "text": line})
        elif tag == "insert":
            for line in new.splitlines()[j1:j2]:
                lines.append({"type": "added", "text": line})
        elif tag == "replace":
            for line in old.splitlines()[i1:i2]:
                lines.append({"type": "removed", "text": line})
            for line in new.splitlines()[j1:j2]:
                lines.append({"type": "added", "text": line})

    return {
        "agent_id": agent_id,
        "name": name,
        "v1": v1,
        "v2": v2,
        "added": sum(1 for l in lines if l["type"] == "added"),
        "removed": sum(1 for l in lines if l["type"] == "removed"),
        "lines": lines,
    }


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