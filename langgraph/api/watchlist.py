"""Watchlist Intelligence API — 自选股、监控、报告、事件、告警

复用 tools.postgres::postgres_tool 直接执行 SQL（PostgreSQL 为唯一数据源）。
监控引擎位于 langgraph/monitoring/，本模块仅做编排与对外暴露。
"""

import asyncio
import json
import logging
from datetime import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)

watchlist_router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


def _parse_time(value: str) -> time:
    """将 'HH:MM' / 'HH:MM:SS' 字符串解析为 datetime.time（asyncpg TIME 参数要求）"""
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"无效的时间格式: {value}")


def _normalize_tags(rows: list[dict]) -> list[dict]:
    """将返回行中的 JSONB tags（JSON 字符串）解析为 list，保持前端类型一致"""
    for row in rows:
        tags = row.get("tags")
        if isinstance(tags, str):
            try:
                row["tags"] = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                row["tags"] = []
        elif tags is None:
            row["tags"] = []
    return rows


# ── 请求模型 ──────────────────────────────────────────────
class WatchlistCreate(BaseModel):
    stock_code: str = Field(..., min_length=1, max_length=32)
    stock_name: str = Field("", max_length=128)
    market: Optional[str] = None
    industry: Optional[str] = None
    group_name: Optional[str] = None
    tags: list[str] = []


class WatchlistUpdate(BaseModel):
    stock_name: Optional[str] = None
    market: Optional[str] = None
    industry: Optional[str] = None
    group_name: Optional[str] = None
    tags: Optional[list[str]] = None
    enabled: Optional[bool] = None


class ConfigUpdate(BaseModel):
    schedule_time: Optional[str] = None
    auto_enabled: Optional[bool] = None
    webhook_url: Optional[str] = None


# ── 自选股 CRUD ───────────────────────────────────────────
@watchlist_router.get("")
async def list_watchlist(
    group_name: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    enabled: Optional[bool] = Query(None),
):
    """自选股列表（支持 group_name/tag/enabled 过滤）"""
    clauses: list[str] = []
    params: list = []
    if group_name:
        params.append(group_name)
        clauses.append(f"group_name = ${len(params)}")
    if tag:
        params.append(tag)
        clauses.append(f"$%d = ANY(tags)" % len(params))
    if enabled is not None:
        params.append(enabled)
        clauses.append(f"enabled = ${len(params)}")

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = await postgres_tool.query(
        f"SELECT id, stock_code, stock_name, market, industry, group_name, "
        f"tags, enabled, created_at FROM watchlist.watchlist {where} "
        f"ORDER BY created_at DESC",
        *params,
    )
    return {"items": _normalize_tags(rows), "total": len(rows)}


@watchlist_router.post("")
async def add_watchlist(item: WatchlistCreate):
    """添加自选股"""
    try:
        row = await postgres_tool.query(
            """
            INSERT INTO watchlist.watchlist
                (stock_code, stock_name, market, industry, group_name, tags)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, stock_code, stock_name, market, industry,
                      group_name, tags, enabled, created_at
            """,
            item.stock_code.strip().upper(),
            item.stock_name.strip(),
            item.market,
            item.industry,
            item.group_name,
            json.dumps(item.tags or []),
        )
    except Exception as e:
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="股票代码已存在")
        logger.error("[Watchlist] Add failed | %s", e)
        raise HTTPException(status_code=500, detail="添加失败")
    return _normalize_tags(row)[0]


@watchlist_router.get("/groups")
async def list_groups():
    """分组列表"""
    rows = await postgres_tool.query(
        """
        SELECT group_name, COUNT(*) AS cnt
        FROM watchlist.watchlist
        WHERE group_name IS NOT NULL AND group_name != ''
        GROUP BY group_name ORDER BY cnt DESC
        """
    )
    return {"items": rows}


# ── 监控触发 ──────────────────────────────────────────────
@watchlist_router.post("/run")
async def run_monitoring():
    """手动触发一次监控（异步执行，立即返回 accepted）"""
    from monitoring.watchlist_monitor import run_watchlist_monitoring

    async def _task():
        try:
            result = await run_watchlist_monitoring()
            logger.info("[Watchlist] Manual run done | %s", result)
        except Exception as e:  # noqa: BLE001
            logger.error("[Watchlist] Manual run failed | %s", e)

    asyncio.create_task(_task())
    return {"status": "accepted", "message": "监控任务已启动"}


# ── 配置 ───────────────────────────────────────────────────
@watchlist_router.get("/config")
async def get_config():
    """读取 watchlist_settings"""
    rows = await postgres_tool.query(
        "SELECT schedule_time, auto_enabled, webhook_url, updated_at "
        "FROM watchlist.watchlist_settings WHERE id = 1"
    )
    if not rows:
        raise HTTPException(status_code=404, detail="配置不存在")
    return rows[0]


@watchlist_router.put("/config")
async def update_config(update: ConfigUpdate):
    """更新 schedule_time/auto_enabled/webhook_url，并重载调度 job"""
    fields: list[str] = ["updated_at = NOW()"]
    params: list = []
    if update.schedule_time is not None:
        params.append(_parse_time(update.schedule_time))
        fields.append(f"schedule_time = ${len(params)}")
    if update.auto_enabled is not None:
        params.append(update.auto_enabled)
        fields.append(f"auto_enabled = ${len(params)}")
    if update.webhook_url is not None:
        params.append(update.webhook_url)
        fields.append(f"webhook_url = ${len(params)}")

    rows = await postgres_tool.query(
        f"UPDATE watchlist.watchlist_settings SET {', '.join(fields)} "
        f"WHERE id = 1 RETURNING schedule_time, auto_enabled, webhook_url, updated_at",
        *params,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="配置不存在")

    # 重载调度 job（时间/开关变更后生效）
    try:
        from runtime.scheduler import resync_watchlist_job
        await resync_watchlist_job()
    except Exception as e:  # noqa: BLE001
        logger.warning("[Watchlist] Scheduler resync skipped | %s", e)

    return rows[0]


# ── 报告 ───────────────────────────────────────────────────
@watchlist_router.get("/reports")
async def list_reports(limit: int = Query(20, ge=1, le=100)):
    """报告列表"""
    rows = await postgres_tool.query(
        "SELECT id, report_date, title, summary, created_at "
        "FROM watchlist.daily_watchlist_report "
        "ORDER BY report_date DESC LIMIT $1",
        limit,
    )
    return {"items": rows}


@watchlist_router.get("/reports/latest")
async def get_latest_report():
    """最新报告（含完整 content）"""
    rows = await postgres_tool.query(
        "SELECT id, report_date, title, content, summary, created_at "
        "FROM watchlist.daily_watchlist_report "
        "ORDER BY report_date DESC LIMIT 1"
    )
    if not rows:
        return {"report": None}
    return {"report": rows[0]}


# ── 事件 ───────────────────────────────────────────────────
@watchlist_router.get("/events")
async def list_events(
    stock_code: Optional[str] = Query(None),
    importance: Optional[int] = Query(None, ge=1, le=5),
    sentiment: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """事件列表（按 importance/stock_code/sentiment 过滤）"""
    clauses: list[str] = []
    params: list = []
    if stock_code:
        params.append(stock_code)
        clauses.append(f"stock_code = ${len(params)}")
    if importance is not None:
        params.append(importance)
        clauses.append(f"importance >= ${len(params)}")
    if sentiment:
        params.append(sentiment)
        clauses.append(f"sentiment = ${len(params)}")

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = await postgres_tool.query(
        f"SELECT we.id, we.stock_code, w.stock_name, we.news_id, we.event_id, "
        f"we.importance, we.sentiment, we.confidence, we.impact_horizon, "
        f"we.summary, we.source_type, we.event_time, we.created_at "
        f"FROM watchlist.watchlist_events we "
        f"LEFT JOIN watchlist.watchlist w ON w.stock_code = we.stock_code "
        f"{where} ORDER BY we.importance DESC, we.created_at DESC LIMIT ${len(params) + 1}",
        *params, limit,
    )
    return {"items": rows, "total": len(rows)}


# ── Web 告警 ───────────────────────────────────────────────
@watchlist_router.get("/alerts")
async def list_alerts(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
):
    """Web 通知列表（channel='web'，未读优先）"""
    where = "channel = 'web'"
    if unread_only:
        where += " AND read = false"
    rows = await postgres_tool.query(
        f"SELECT id, stock_code, title, content, level, event_id, "
        f"delivered, read, created_at "
        f"FROM watchlist.watchlist_alerts "
        f"WHERE {where} ORDER BY read ASC, created_at DESC LIMIT $1",
        limit,
    )
    return {"items": rows}


@watchlist_router.post("/alerts/{alert_id}/read")
async def mark_alert_read(alert_id: str):
    """将 Web 告警标记为已读"""
    await postgres_tool.execute(
        "UPDATE watchlist.watchlist_alerts SET read = true WHERE id = $1",
        alert_id,
    )
    return {"ok": True}


# ── 自选股更新/删除（置于静态路由之后，避免 /{item_id} 捕获 /config）──
@watchlist_router.put("/{item_id}")
async def update_watchlist(item_id: str, update: WatchlistUpdate):
    """更新分组/标签/名称/启用状态"""
    fields: list[str] = []
    params: list = [item_id]
    if update.stock_name is not None:
        params.append(update.stock_name)
        fields.append(f"stock_name = ${len(params)}")
    if update.market is not None:
        params.append(update.market)
        fields.append(f"market = ${len(params)}")
    if update.industry is not None:
        params.append(update.industry)
        fields.append(f"industry = ${len(params)}")
    if update.group_name is not None:
        params.append(update.group_name)
        fields.append(f"group_name = ${len(params)}")
    if update.tags is not None:
        params.append(json.dumps(update.tags))
        fields.append(f"tags = ${len(params)}")
    if update.enabled is not None:
        params.append(update.enabled)
        fields.append(f"enabled = ${len(params)}")

    if not fields:
        raise HTTPException(status_code=400, detail="无更新字段")

    rows = await postgres_tool.query(
        f"UPDATE watchlist.watchlist SET {', '.join(fields)} "
        f"WHERE id = $1 RETURNING *",
        *params,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="自选股不存在")
    return _normalize_tags(rows)[0]


@watchlist_router.delete("/{item_id}")
async def delete_watchlist(item_id: str):
    """删除自选股"""
    result = await postgres_tool.execute(
        "DELETE FROM watchlist.watchlist WHERE id = $1", item_id
    )
    return {"deleted": "删除成功"}