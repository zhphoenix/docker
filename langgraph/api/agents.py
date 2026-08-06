"""Agents API - Agent 注册表（合并 DB 配置 + 运行时注册表 + 元数据）"""

import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.router import AGENT_REGISTRY
from tools.postgres import postgres_tool
from config.agent_meta import get_agent_meta

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents", tags=["agents"])


class ConfigUpdate(BaseModel):
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout: int | None = Field(default=None, ge=1)
    retry: int | None = Field(default=None, ge=0)

def _load_agent_meta() -> dict:
    """内置 Agent 元数据（agent_meta.yaml）"""
    return get_agent_meta()


async def _fetch_db_agents() -> list[dict]:
    """查询 agents 表全部配置，失败时返回空列表"""
    try:
        rows = await postgres_tool.query(
            "SELECT id, name, description, prompt_template, model, temperature, "
            "tools, config, is_active, version, status, last_active_at "
            "FROM agents ORDER BY created_at DESC"
        )
        return rows
    except Exception:
        logger.warning("Failed to query agents table", exc_info=True)
        return []


def _normalize_tools(tools) -> list[str]:
    if isinstance(tools, str):
        try:
            tools = json.loads(tools)
        except (json.JSONDecodeError, TypeError):
            return []
    return tools or []


def _merge_builtin(meta: dict) -> list[dict]:
    """内置 Agent（来自 AGENT_REGISTRY + agent_meta.yaml）

    遍历 AGENT_REGISTRY 与 meta 的 key 并集，使 Pipeline Agent
    （如 knowledge_ingestion / news_intelligence，为 graph 非 BaseAgent）
    也能从 meta 进入返回列表。
    """
    agents = []
    names: list[str] = list(AGENT_REGISTRY.keys())
    # 追加 meta 中尚未覆盖的 pipeline/对话 Agent（并集去重，保持 AGENT_REGISTRY 顺序优先）
    for name in meta:
        if name not in names:
            names.append(name)
    for name in names:
        m = meta.get(name, {})
        cls = AGENT_REGISTRY.get(name)
        agents.append({
            "id": name,
            "name": name,
            "display_name": m.get("display_name") or name,
            "description": m.get("description") or (cls.__doc__ or "").strip().split("\n")[0] if cls else "",
            "model": m.get("default_model"),
            "tools": m.get("tools", []),
            "version": m.get("version", "v1.0"),
            "author": m.get("author", "System"),
            "workflows": m.get("workflows", []),
            "skills": m.get("skills", []),
            "mcp": m.get("mcp", []),
            "is_active": True,
            "status": "active",
            "last_active_at": None,
            "source": "builtin",
        })
    return agents


_builtin_cache: list[dict] = []


@router.get("")
async def list_agents():
    """列出所有 Agent（内置 + 自定义）"""
    meta = _load_agent_meta()
    builtin = _merge_builtin(meta)
    global _builtin_cache
    _builtin_cache = builtin
    db_rows = await _fetch_db_agents()

    # 内置 Agent 名称集合（用于去重覆盖）
    builtin_names = {a["id"] for a in builtin}
    merged: list[dict] = []
    db_by_name = {r.get("name"): r for r in db_rows}

    for b in builtin:
        a = dict(b)
        r = db_by_name.get(b["id"])
        if r:
            a["model"] = r.get("model") or a["model"]
            a["tools"] = _normalize_tools(r.get("tools")) or a["tools"]
            a["version"] = r.get("version") or a["version"]
            a["status"] = r.get("status") or "active"
            a["is_active"] = bool(r.get("is_active", True))
            a["last_active_at"] = r.get("last_active_at")
        merged.append(a)

    # 自定义 Agent（name 不在内置集合中）
    for r in db_rows:
        name = r.get("name")
        if name in builtin_names:
            continue
        merged.append({
            "id": str(r["id"]),
            "name": name,
            "display_name": r.get("display_name") or name,
            "description": r.get("description") or "",
            "model": r.get("model"),
            "tools": _normalize_tools(r.get("tools")),
            "version": r.get("version") or "v1.0",
            "author": "custom",
            "workflows": [],
            "skills": [],
            "mcp": [],
            "is_active": bool(r.get("is_active", True)),
            "status": r.get("status") or ("active" if r.get("is_active", True) else "paused"),
            "last_active_at": r.get("last_active_at"),
            "source": "custom",
        })

    return {"agents": merged, "total": len(merged)}


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    """Agent 详情：基本信息 + 运行时配置 + 依赖"""
    all_agents = (await list_agents())["agents"]
    agent = next((a for a in all_agents if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    # 运行时配置（内置取 meta 默认，自定义取 DB config）
    from config.policy_loader import get_policy
    runtime = {
        "model": agent.get("model") or get_policy(f"agents.{agent_id}.model", ""),
        "temperature": 0.7,
        "top_p": 0.95,
        "max_tokens": 4096,
        "timeout": 180,
        "retry": get_policy("retry.max_retries", 3),
    }

    # 若表中有配置则覆盖
    db_rows = await _fetch_db_agents()
    r = next((x for x in db_rows if x.get("name") == agent_id), None)
    if r:
        cfg = r.get("config") or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except (json.JSONDecodeError, TypeError):
                cfg = {}
        runtime["model"] = r.get("model") or runtime["model"]
        runtime["temperature"] = _num(r.get("temperature"), runtime["temperature"])
        runtime["top_p"] = _num(cfg.get("top_p"), runtime["top_p"])
        runtime["max_tokens"] = _num(cfg.get("max_tokens"), runtime["max_tokens"])
        runtime["timeout"] = _num(cfg.get("timeout"), runtime["timeout"])
        runtime["retry"] = _num(cfg.get("retry"), runtime["retry"])

    return {
        **agent,
        "runtime": runtime,
        "dependencies": {
            "skills": agent.get("skills", []),
            "tools": agent.get("tools", []),
            "mcp": agent.get("mcp", []),
            "workflows": agent.get("workflows", []),
        },
    }


def _num(v, default):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


@router.post("/{agent_id}/toggle")
async def toggle_agent(agent_id: str):
    """切换 Agent 生命周期状态（active ↔ paused）"""
    db_rows = await _fetch_db_agents()
    r = next((x for x in db_rows if x.get("name") == agent_id), None)

    if r:
        new_active = not bool(r.get("is_active", True))
        new_status = "active" if new_active else "paused"
        await postgres_tool.query(
            "UPDATE agents SET is_active=$1, status=$2, updated_at=NOW() WHERE name=$3",
            new_active, new_status, agent_id,
        )
        return {"id": agent_id, "is_active": new_active, "status": new_status}
    else:
        # 内置 Agent 无表行时，先 upsert 再切换
        meta = _load_agent_meta()
        m = meta.get(agent_id, {})
        await postgres_tool.query(
            "INSERT INTO agents (name, description, model, status, is_active) "
            "VALUES ($1, $2, $3, 'paused', false) "
            "ON CONFLICT (name) DO UPDATE SET is_active=false, status='paused', updated_at=NOW()",
            agent_id, m.get("description", ""), m.get("default_model"),
        )
        return {"id": agent_id, "is_active": False, "status": "paused"}


@router.put("/{agent_id}/config")
async def update_config(agent_id: str, body: ConfigUpdate):
    """在线修改 Agent 运行配置（model/temperature/top_p/max_tokens/timeout/retry）

    - 校验通过后落库（model/temperature 为专列，其余进 config JSONB）
    - 写入 agent_configs_history 供回滚
    - 读取方运行时动态查询，保存即生效（热更新）
    """
    db_rows = await _fetch_db_agents()
    r = next((x for x in db_rows if x.get("name") == agent_id), None)
    if not r:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    # 读取现有 config JSONB
    cfg = r.get("config") or {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except (json.JSONDecodeError, TypeError):
            cfg = {}

    # 合并新配置
    update_fields = {}
    if body.model is not None:
        update_fields["model"] = body.model
    if body.temperature is not None:
        update_fields["temperature"] = body.temperature
    for key in ("top_p", "max_tokens", "timeout", "retry"):
        val = getattr(body, key, None)
        if val is not None:
            cfg[key] = val

    # 落库
    if cfg:
        await postgres_tool.query(
            "UPDATE agents SET config=$1, updated_at=NOW() WHERE name=$2",
            json.dumps(cfg, ensure_ascii=False), agent_id,
        )
    if update_fields:
        sets = ", ".join([f"{k}=${i+1}" for i, k in enumerate(update_fields)])
        args = list(update_fields.values()) + [agent_id]
        await postgres_tool.query(
            f"UPDATE agents SET {sets}, updated_at=NOW() WHERE name=${len(args)}",
            *args,
        )

    # 写历史（快照完整配置）
    merged = {}
    merged["model"] = update_fields.get("model", r.get("model"))
    merged["temperature"] = update_fields.get("temperature", r.get("temperature"))
    merged.update(cfg)
    await postgres_tool.query(
        "INSERT INTO agent_configs_history (agent_id, config) VALUES ($1, $2)",
        agent_id, json.dumps(merged, ensure_ascii=False),
    )

    return {"id": agent_id, "config": merged, "updated": True}


@router.get("/{agent_id}/config/history")
async def config_history(agent_id: str):
    """配置修改历史"""
    rows = await postgres_tool.query(
        "SELECT id, agent_id, config, changed_by, created_at "
        "FROM agent_configs_history WHERE agent_id=$1 ORDER BY created_at DESC",
        agent_id,
    )
    return {"history": rows, "total": len(rows)}


class RollbackBody(BaseModel):
    history_id: str | None = None  # 缺省回滚到最近一次


@router.post("/{agent_id}/config/rollback")
async def rollback_config(agent_id: str, body: RollbackBody):
    """回滚配置到指定历史快照（缺省为最近一次）"""
    if body.history_id:
        rows = await postgres_tool.query(
            "SELECT config FROM agent_configs_history WHERE id=$1::uuid", body.history_id
        )
    else:
        rows = await postgres_tool.query(
            "SELECT config FROM agent_configs_history WHERE agent_id=$1 "
            "ORDER BY created_at DESC LIMIT 1",
            agent_id,
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No config history to rollback")

    cfg = rows[0]["config"]
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except (json.JSONDecodeError, TypeError):
            cfg = {}

    model = cfg.get("model")
    temperature = cfg.get("temperature")
    rest = {k: v for k, v in cfg.items() if k not in ("model", "temperature")}

    await postgres_tool.query(
        "UPDATE agents SET model=$1, temperature=$2, config=$3, updated_at=NOW() WHERE name=$4",
        model, temperature, json.dumps(rest, ensure_ascii=False), agent_id,
    )
    return {"id": agent_id, "config": cfg, "rolled_back": True}