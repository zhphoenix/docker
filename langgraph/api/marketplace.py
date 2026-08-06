"""Agent Marketplace API - 模板发布 / 导入导出 Agent 定义 JSON（AC-P4-4）

- 导出：将 Agent 定义（基本信息 + 配置 + prompt 版本）序列化为标准 JSON
- 导入：将标准 Agent 定义 JSON 重建到 agents 表 + agent_prompts 表（可在另一实例导入）
- 模板：发布当前 Agent 为模板，或从模板安装新 Agent
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tools.postgres import postgres_tool
from config.agent_meta import get_agent_meta

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])

SCHEMA_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_tools(tools) -> list:
    if isinstance(tools, str):
        try:
            tools = json.loads(tools)
        except (json.JSONDecodeError, TypeError):
            return []
    return tools or []


def _num(v, default):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


async def _fetch_agent_row(name: str) -> dict | None:
    """查询 agents 表单行配置"""
    rows = await postgres_tool.query(
        "SELECT id, name, description, prompt_template, model, temperature, tools, config, "
        "version, display_name, is_active, status "
        "FROM agents WHERE name=$1",
        name,
    )
    return rows[0] if rows else None


async def _fetch_prompts(agent_id: str) -> list[dict]:
    return await postgres_tool.query(
        "SELECT name, content, version, is_active, traffic_weight "
        "FROM agent_prompts WHERE agent_id=$1 ORDER BY name, version",
        agent_id,
    )


def _build_agent_definition(row: dict) -> dict:
    """从 agents 表行构造标准 Agent 定义（不含 prompt）"""
    meta = get_agent_meta().get(row.get("name"), {})
    cfg = row.get("config") or {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except (json.JSONDecodeError, TypeError):
            cfg = {}
    return {
        "name": row.get("name"),
        "display_name": row.get("display_name") or meta.get("display_name") or row.get("name"),
        "description": row.get("description") or meta.get("description") or "",
        "version": row.get("version") or meta.get("version") or "v1.0",
        "author": meta.get("author") or "custom",
        "model": row.get("model"),
        "temperature": _num(row.get("temperature"), 0.7),
        "tools": _normalize_tools(row.get("tools")) or meta.get("tools", []),
        "config": cfg,
        "workflows": meta.get("workflows", []),
        "skills": meta.get("skills", []),
        "mcp": meta.get("mcp", []),
    }


async def _export_definition(agent_id: str) -> dict:
    """导出 Agent 完整定义 JSON（含 prompt），供另一实例导入"""
    row = await _fetch_agent_row(agent_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    prompts = await _fetch_prompts(agent_id)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "agent",
        "agent": _build_agent_definition(row),
        "prompts": prompts,
        "exported_at": _now_iso(),
    }


def _validate_definition(d: dict):
    """校验 Agent 定义 JSON 结构，返回错误信息（None 表示通过）"""
    if not isinstance(d, dict):
        return "定义必须是 JSON 对象"
    if d.get("schema_version") != SCHEMA_VERSION:
        return f"不支持的 schema_version（期望 {SCHEMA_VERSION}）"
    if d.get("kind") != "agent":
        return "kind 必须是 'agent'"
    agent = d.get("agent")
    if not isinstance(agent, dict) or not agent.get("name"):
        return "缺少 agent.name"
    if not isinstance(d.get("prompts", []), list):
        return "prompts 必须是数组"
    return None


async def _apply_definition(d: dict) -> dict:
    """将 Agent 定义应用到 agents + agent_prompts 表（导入核心逻辑）"""
    err = _validate_definition(d)
    if err:
        raise HTTPException(status_code=400, detail=err)

    agent: dict = d["agent"]
    name = agent["name"]
    prompts: list = d.get("prompts", [])

    # 1. upsert agents 表
    await postgres_tool.query(
        "INSERT INTO agents (name, description, model, temperature, tools, config, version, "
        "display_name, status, is_active) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'active', true) "
        "ON CONFLICT (name) DO UPDATE SET "
        "  description=EXCLUDED.description, model=EXCLUDED.model, "
        "  temperature=EXCLUDED.temperature, tools=EXCLUDED.tools, config=EXCLUDED.config, "
        "  version=EXCLUDED.version, display_name=EXCLUDED.display_name, "
        "  status='active', is_active=true, updated_at=NOW()",
        name,
        agent.get("description"),
        agent.get("model"),
        agent.get("temperature"),
        json.dumps(agent.get("tools", []), ensure_ascii=False),
        json.dumps(agent.get("config", {}), ensure_ascii=False),
        agent.get("version", "v1.0"),
        agent.get("display_name"),
    )

    # 2. upsert prompts（按 agent_id + name + version）
    applied_prompts = 0
    for p in prompts:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        await postgres_tool.query(
            "INSERT INTO agent_prompts (agent_id, name, content, version, is_active, traffic_weight, status) "
            "VALUES ($1, $2, $3, $4, $5, $6, 'published') "
            "ON CONFLICT (agent_id, name, version) DO UPDATE SET "
            "  content=EXCLUDED.content, is_active=EXCLUDED.is_active, "
            "  traffic_weight=EXCLUDED.traffic_weight, status='published'",
            name,
            p.get("name"),
            p.get("content", ""),
            int(p.get("version", 1)),
            bool(p.get("is_active", True)),
            int(p.get("traffic_weight", 100)),
        )
        applied_prompts += 1

    # 3. 刷新 Prompt Hub 缓存（DB 为唯一事实源）
    try:
        from prompts.loader import refresh_prompt
        await refresh_prompt(name)
    except Exception:
        logger.warning("Prompt reload after import skipped for %s", name, exc_info=True)

    return {"agent": name, "prompts_applied": applied_prompts}


# ---------- 端点 ----------


@router.get("/templates")
async def list_templates(category: str | None = None):
    """列出所有模板（可按 category 过滤）"""
    if category:
        rows = await postgres_tool.query(
            "SELECT id, name, display_name, description, category, version, author, installs, "
            "created_at, updated_at FROM agent_templates WHERE category=$1 ORDER BY installs DESC",
            category,
        )
    else:
        rows = await postgres_tool.query(
            "SELECT id, name, display_name, description, category, version, author, installs, "
            "created_at, updated_at FROM agent_templates ORDER BY installs DESC"
        )
    return {"templates": rows, "total": len(rows)}


@router.get("/templates/{template_id}")
async def get_template(template_id: str):
    """模板详情（含完整 definition）"""
    rows = await postgres_tool.query(
        "SELECT * FROM agent_templates WHERE id=$1::uuid", template_id
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Template not found")
    t = rows[0]
    if isinstance(t.get("definition"), str):
        try:
            t["definition"] = json.loads(t["definition"])
        except (json.JSONDecodeError, TypeError):
            t["definition"] = {}
    return t


class PublishBody(BaseModel):
    agent_id: str
    display_name: str | None = None
    description: str | None = None
    category: str = Field(default="general")
    overwrite: bool = False


@router.post("/templates")
async def publish_template(body: PublishBody):
    """将现有 Agent 发布为模板"""
    definition = await _export_definition(body.agent_id)
    row = definition["agent"]
    tmpl_name = row["name"]

    existing = await postgres_tool.query(
        "SELECT id FROM agent_templates WHERE name=$1", tmpl_name
    )
    if existing and not body.overwrite:
        raise HTTPException(
            status_code=409,
            detail=f"模板 '{tmpl_name}' 已存在，设置 overwrite=true 可覆盖",
        )

    serialized = json.dumps(definition, ensure_ascii=False)
    if existing:
        await postgres_tool.query(
            "UPDATE agent_templates SET display_name=$1, description=$2, category=$3, "
            "version=$4, author=$5, definition=$6, source_agent=$7, updated_at=NOW() "
            "WHERE name=$8",
            body.display_name or row.get("display_name"),
            body.description or row.get("description"),
            body.category,
            row.get("version", "v1.0"),
            row.get("author", "community"),
            serialized,
            body.agent_id,
            tmpl_name,
        )
        return {"published": True, "name": tmpl_name, "overwritten": True}

    await postgres_tool.query(
        "INSERT INTO agent_templates (name, display_name, description, category, version, "
        "author, definition, source_agent) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
        tmpl_name,
        body.display_name or row.get("display_name"),
        body.description or row.get("description"),
        body.category,
        row.get("version", "v1.0"),
        row.get("author", "community"),
        serialized,
        body.agent_id,
    )
    return {"published": True, "name": tmpl_name, "overwritten": False}


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str):
    """删除模板"""
    await postgres_tool.query(
        "DELETE FROM agent_templates WHERE id=$1::uuid", template_id
    )
    return {"deleted": True, "id": template_id}


@router.post("/templates/{template_id}/install")
async def install_template(template_id: str):
    """从模板安装 Agent（复用导入逻辑，重建 agents + prompts）"""
    rows = await postgres_tool.query(
        "SELECT definition FROM agent_templates WHERE id=$1::uuid", template_id
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Template not found")
    definition = rows[0]["definition"]
    if isinstance(definition, str):
        try:
            definition = json.loads(definition)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(status_code=400, detail="Template definition 损坏")

    result = await _apply_definition(definition)
    await postgres_tool.query(
        "UPDATE agent_templates SET installs=installs+1 WHERE id=$1::uuid", template_id
    )
    return {"installed": True, **result}


@router.post("/import")
async def import_agent(payload: dict):
    """导入 Agent 定义 JSON（另一实例导出的定义）"""
    result = await _apply_definition(payload)
    return {"imported": True, **result}


@router.get("/export/{agent_id}")
async def export_agent(agent_id: str):
    """导出 Agent 定义 JSON（供另一实例导入）"""
    return await _export_definition(agent_id)