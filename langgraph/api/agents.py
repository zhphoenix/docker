"""Agents API - Agent 注册表（合并 DB 配置 + 运行时注册表 + 元数据）"""

import json
import logging
import math

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.router import AGENT_REGISTRY, reload_agent_registry
from tools.postgres import postgres_tool
from config.agent_meta import get_agent_meta

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents", tags=["agents"])


def _to_float(value) -> float:
    """asyncpg numeric → float（NaN/Inf 视为 0）"""
    try:
        f = float(value) if value is not None else 0.0
        return f if math.isfinite(f) else 0.0
    except (TypeError, ValueError):
        return 0.0


class ConfigUpdate(BaseModel):
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout: int | None = Field(default=None, ge=1)
    retry: int | None = Field(default=None, ge=0)


class PermissionUpdate(BaseModel):
    """AC-P4-6 Agent API 权限开关"""
    enabled: bool = True

def _load_agent_meta() -> dict:
    """内置 Agent 元数据（agent_meta.yaml）"""
    return get_agent_meta()


async def _fetch_db_agents() -> list[dict]:
    """查询 agents 表全部配置，失败时返回空列表"""
    try:
        rows = await postgres_tool.query(
            "SELECT id, name, description, prompt_template, model, temperature, "
            "tools, config, is_active, version, status, last_active_at, api_enabled "
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
            "api_enabled": True,
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
            a["api_enabled"] = bool(r.get("api_enabled", True))
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
            "api_enabled": bool(r.get("api_enabled", True)),
        })

    return {"agents": merged, "total": len(merged)}


@router.get("/summary")
async def agent_summary():
    """全局汇总：全部 Agent 的今日运行/成功/失败/成功率（Dashboard 三栏第 2 栏数据源）

    - 基于 agent_runs 按 agent_id 聚合当日数据（created_at >= CURRENT_DATE）
    - 与 list_agents 合并，运行数为 0 的 Agent 也返回（runs_today=0）
    - 注：本端点必须声明在 /{agent_id} 之前，避免被单段路径捕获
    """
    try:
        rows = await postgres_tool.query(
            "SELECT agent_id, "
            "COUNT(*) AS runs_today, "
            "COUNT(*) FILTER (WHERE status='completed') AS success_today, "
            "COUNT(*) FILTER (WHERE status='failed') AS failed_today, "
            "COALESCE(AVG(duration_ms) FILTER (WHERE status IN ('completed','failed')), 0) AS avg_latency_ms, "
            "MAX(created_at) AS last_run_at "
            "FROM agent_runs WHERE created_at >= CURRENT_DATE "
            "GROUP BY agent_id ORDER BY runs_today DESC"
        )
    except Exception:
        logger.warning("Failed to query agent_runs daily summary", exc_info=True)
        rows = []

    stats: dict[str, dict] = {}
    for r in rows:
        stats[r["agent_id"]] = {
            "runs_today": int(r.get("runs_today") or 0),
            "success_today": int(r.get("success_today") or 0),
            "failed_today": int(r.get("failed_today") or 0),
            "avg_latency_ms": _to_float(r.get("avg_latency_ms")),
            "last_run_at": r.get("last_run_at"),
        }

    agents = (await list_agents())["agents"]
    result = []
    for a in agents:
        s = stats.get(a["name"], {})
        runs = s.get("runs_today", 0)
        success = s.get("success_today", 0)
        failed = s.get("failed_today", 0)
        result.append({
            "agent_id": a["name"],
            "display_name": a.get("display_name") or a["name"],
            "status": a.get("status", "active"),
            "runs_today": runs,
            "success_today": success,
            "failed_today": failed,
            "success_rate": round(success / runs * 100, 1) if runs else 0.0,
            "avg_latency_ms": s.get("avg_latency_ms", 0.0),
            "last_run_at": s.get("last_run_at"),
        })

    total_runs = sum(x["runs_today"] for x in result)
    total_success = sum(x["success_today"] for x in result)
    total_failed = sum(x["failed_today"] for x in result)
    return {
        "agents": result,
        "total": {
            "agents": len(result),
            "runs_today": total_runs,
            "success_today": total_success,
            "failed_today": total_failed,
            "success_rate": round(total_success / total_runs * 100, 1) if total_runs else 0.0,
        },
    }


@router.post("/reload")
async def reload_agents():
    """热更新 Agent 注册表：重建 AGENT_REGISTRY（无服务重启）

    - 重新读取 agents.yaml 并 importlib 导入最新 Agent 类
    - 原地替换注册表（clear + update），新请求立即路由到新配置
    - 不断开在途请求：在途请求持有已实例化的 Agent 对象，不受替换影响
    """
    try:
        reload_agent_registry()
    except Exception as e:
        logger.error("Agent registry reload failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Reload failed: {e}")
    return {
        "reloaded": True,
        "agents": list(AGENT_REGISTRY.keys()),
        "count": len(AGENT_REGISTRY),
    }


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


async def is_agent_api_enabled(agent_id: str) -> bool:
    """AC-P4-6：查询 Agent 的 API 权限开关（默认开启）

    供 Agent 执行入口（chat_completions 等）校验：停用后其 API 返回 403。
    """
    try:
        rows = await postgres_tool.query(
            "SELECT api_enabled FROM agents WHERE name = $1", agent_id
        )
        return bool(rows[0]["api_enabled"]) if rows else True
    except Exception:
        logger.warning("is_agent_api_enabled query failed for %s", agent_id, exc_info=True)
        return True


@router.post("/{agent_id}/permission")
async def set_agent_permission(agent_id: str, body: PermissionUpdate):
    """AC-P4-6：切换 Agent 的 API 权限开关

    enabled=false 后，该 Agent 的执行端点（chat_completions）返回 403。
    """
    try:
        rows = await postgres_tool.query(
            "SELECT name FROM agents WHERE name = $1", agent_id
        )
    except Exception:
        rows = []

    if rows:
        await postgres_tool.execute(
            "UPDATE agents SET api_enabled=$1, updated_at=NOW() WHERE name=$2",
            body.enabled, agent_id,
        )
    else:
        # 内置 Agent 无表行时，先 upsert 再设置权限
        meta = _load_agent_meta()
        m = meta.get(agent_id, {})
        await postgres_tool.execute(
            "INSERT INTO agents (name, description, model, status, is_active, api_enabled) "
            "VALUES ($1, $2, $3, 'active', true, $4) "
            "ON CONFLICT (name) DO UPDATE SET api_enabled=$4, updated_at=NOW()",
            agent_id, m.get("description", ""), m.get("default_model"), body.enabled,
        )
    return {"id": agent_id, "api_enabled": body.enabled}


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