"""Watchlist Intelligence API — 自选股、监控、报告、事件、告警

复用 tools.postgres::postgres_tool 直接执行 SQL（PostgreSQL 为唯一数据源）。
监控引擎位于 langgraph/monitoring/，本模块仅做编排与对外暴露。
"""

import asyncio
import json
import logging
import os
import smtplib
from datetime import time
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
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
    item_type: str = "stock"  # stock / etf / index / industry / company / person / fund / macro_theme


class WatchlistUpdate(BaseModel):
    stock_name: Optional[str] = None
    market: Optional[str] = None
    industry: Optional[str] = None
    group_name: Optional[str] = None
    tags: Optional[list[str]] = None
    enabled: Optional[bool] = None
    item_type: Optional[str] = None


class ConfigUpdate(BaseModel):
    schedule_time: Optional[str] = None
    auto_enabled: Optional[bool] = None
    webhook_url: Optional[str] = None
    monitoring_scopes: Optional[list[str]] = None
    ai_summary_enabled: Optional[bool] = None
    daily_report_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    email_address: Optional[str] = None
    update_frequency: Optional[str] = None
    alert_threshold: Optional[int] = None
    notification_channels: Optional[list[str]] = None


class GroupCreate(BaseModel):
    group_name: str = Field(..., min_length=1, max_length=64)


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
        f"tags, enabled, ai_score, last_event_at, "
        f"today_event_count, today_news_count, created_at, item_type "
        f"FROM watchlist.watchlist {where} "
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
                (stock_code, stock_name, market, industry, group_name, tags, item_type)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, stock_code, stock_name, market, industry,
                      group_name, tags, enabled, created_at, item_type
            """,
            item.stock_code.strip().upper(),
            item.stock_name.strip(),
            item.market,
            item.industry,
            item.group_name,
            json.dumps(item.tags or []),
            item.item_type or "stock",
        )
    except Exception as e:
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="股票代码已存在")
        logger.error("[Watchlist] Add failed | %s", e)
        raise HTTPException(status_code=500, detail="添加失败")
    return _normalize_tags(row)[0]


async def _ensure_group_table():
    """确保分组表存在并归档 watchlist 中已出现的分组（幂等，可重复调用）"""
    await postgres_tool.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist.watchlist_group (
            id SERIAL PRIMARY KEY,
            group_name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    await postgres_tool.execute(
        """
        INSERT INTO watchlist.watchlist_group (group_name)
        SELECT DISTINCT group_name FROM watchlist.watchlist
        WHERE group_name IS NOT NULL AND group_name != ''
        ON CONFLICT (group_name) DO NOTHING
        """
    )


@watchlist_router.get("/groups")
async def list_groups():
    """分组列表（含未分配任何股票的空分组，保证新建分组刷新后仍保留）"""
    await _ensure_group_table()
    rows = await postgres_tool.query(
        """
        SELECT g.group_name, COALESCE(w.cnt, 0) AS cnt
        FROM watchlist.watchlist_group g
        LEFT JOIN (
            SELECT group_name, COUNT(*) AS cnt FROM watchlist.watchlist
            WHERE group_name IS NOT NULL AND group_name != ''
            GROUP BY group_name
        ) w ON w.group_name = g.group_name
        ORDER BY cnt DESC, g.group_name
        """
    )
    return {"items": rows}


@watchlist_router.post("/groups")
async def create_group(g: GroupCreate):
    """创建新分组（持久化到分组表，刷新后仍保留）"""
    await _ensure_group_table()
    name = g.group_name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="分组名不能为空")
    await postgres_tool.execute(
        "INSERT INTO watchlist.watchlist_group (group_name) VALUES ($1) "
        "ON CONFLICT (group_name) DO NOTHING",
        name,
    )
    return {"group_name": name}


@watchlist_router.get("/lookup")
async def lookup_stock(
    code: Optional[str] = Query(None, min_length=1, max_length=32),
    name: Optional[str] = Query(None, max_length=128),
    market: Optional[str] = Query(None),
):
    """按代码或名称查询公司基本信息（用于添加自选股时自动填充代码/名称/市场/行业）"""
    clauses: list[str] = []
    params: list = []
    if code:
        params.append(code.strip().upper())
        clauses.append(f"symbol = ${len(params)}")
    elif name:
        params.append(f"%{name.strip()}%")
        clauses.append(f"company_name ILIKE ${len(params)}")
    else:
        raise HTTPException(status_code=422, detail="code 或 name 至少提供一个")
    if market:
        params.append(market)
        clauses.append(f"market = ${len(params)}")
    where = " AND ".join(clauses)
    rows = await postgres_tool.query(
        f"SELECT market, symbol, company_name, exchange, industry "
        f"FROM company_basic WHERE {where} "
        f"ORDER BY COALESCE(updated_at, 'epoch') DESC LIMIT 1",
        *params,
    )
    if not rows:
        return {"item": None}
    return {"item": rows[0]}


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


# ── Overview ────────────────────────────────────────────────
@watchlist_router.get("/overview")
async def get_overview():
    """今日概览聚合（Today Overview 统计卡片）"""
    today_sql = "(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date"
    yesterday_sql = f"({today_sql} - INTERVAL '1 day')"

    rows = await postgres_tool.query(
        f"""
        SELECT
            (SELECT COUNT(*) FROM watchlist.watchlist WHERE enabled = true) AS monitored_stocks,
            (SELECT COUNT(*) FROM watchlist.watchlist_events
             WHERE (created_at AT TIME ZONE 'Asia/Shanghai')::date = {today_sql}) AS today_events,
            (SELECT COALESCE(alert_threshold, 4) FROM watchlist.watchlist_settings WHERE id = 1) AS alert_threshold,
            (SELECT COUNT(*) FROM watchlist.watchlist_events
             WHERE (created_at AT TIME ZONE 'Asia/Shanghai')::date = {today_sql}
               AND importance >= COALESCE((SELECT alert_threshold FROM watchlist.watchlist_settings WHERE id = 1), 4)
            ) AS high_risk_events,
            (SELECT COUNT(*) FROM watchlist.daily_watchlist_report
             WHERE report_date = {today_sql}) AS ai_reports,
            (SELECT COUNT(*) FROM watchlist.watchlist_alerts
             WHERE read = false AND channel = 'web') AS unread_alerts,
            (SELECT COUNT(*) FROM watchlist.watchlist_events
             WHERE (created_at AT TIME ZONE 'Asia/Shanghai')::date = {yesterday_sql}) AS yesterday_events
        """
    )
    if not rows:
        return {
            "today": "",
            "monitored_stocks": 0, "today_events": 0,
            "high_risk_events": 0, "ai_reports": 0,
            "unread_alerts": 0, "yesterday_events": 0,
        }
    r = rows[0]
    today = await postgres_tool.query(f"SELECT {today_sql} AS d")
    today_str = str(today[0]["d"]) if today else ""
    return {
        "today": today_str,
        "monitored_stocks": r["monitored_stocks"] or 0,
        "today_events": r["today_events"] or 0,
        "high_risk_events": r["high_risk_events"] or 0,
        "ai_reports": r["ai_reports"] or 0,
        "unread_alerts": r["unread_alerts"] or 0,
        "yesterday_events": r["yesterday_events"] or 0,
    }


@watchlist_router.get("/history")
async def get_history(days: int = Query(30, ge=1, le=365)):
    """监控历史趋势（优先 daily_stats 表，回退实时聚合）"""
    # 优先读缓存表
    stats_rows = await postgres_tool.query(
        "SELECT stat_date, total_stocks, total_events, high_priority_events, "
        "total_alerts, critical_alerts, ai_reports_generated "
        "FROM watchlist.watchlist_daily_stats "
        "ORDER BY stat_date DESC LIMIT $1",
        days,
    )
    if stats_rows:
        stats = []
        for row in stats_rows:
            stats.append({
                "date": str(row["stat_date"]),
                "total_stocks": row["total_stocks"],
                "total_events": row["total_events"],
                "high_priority_events": row["high_priority_events"],
                "total_alerts": row["total_alerts"],
                "critical_alerts": row["critical_alerts"],
                "ai_reports_generated": row["ai_reports_generated"],
            })
        return {"stats": stats, "source": "daily_stats"}

    # 回退：从 watchlist_events 实时聚合（按日 GROUP BY）
    event_rows = await postgres_tool.query(
        "SELECT (created_at AT TIME ZONE 'Asia/Shanghai')::date AS d, "
        "COUNT(*) AS total_events, "
        "COUNT(*) FILTER (WHERE importance >= 4) AS high_priority_events "
        "FROM watchlist.watchlist_events "
        "WHERE created_at >= NOW() - ($1 || ' days')::INTERVAL "
        "GROUP BY d ORDER BY d DESC",
        str(days),
    )
    stats = []
    for row in event_rows:
        stats.append({
            "date": str(row["d"]),
            "total_stocks": 0,
            "total_events": row["total_events"],
            "high_priority_events": row["high_priority_events"],
            "total_alerts": 0,
            "critical_alerts": 0,
            "ai_reports_generated": 0,
        })
    return {"stats": stats, "source": "realtime_fallback"}


# ── 高级 AI 分析（P4-3）───────────────────────────────────
@watchlist_router.get("/analytics/sentiment")
async def analytics_sentiment(days: int = Query(14, ge=1, le=90)):
    """Sentiment 趋势：按日聚合 bullish/bearish/neutral 事件数（堆叠图数据源）"""
    rows = await postgres_tool.query(
        """
        SELECT (created_at AT TIME ZONE 'Asia/Shanghai')::date AS d,
               COALESCE(sentiment, 'neutral') AS sentiment, COUNT(*) AS cnt
        FROM watchlist.watchlist_events
        WHERE created_at >= NOW() - ($1 || ' days')::INTERVAL
        GROUP BY d, sentiment ORDER BY d
        """,
        str(days),
    )
    by_date: dict[str, dict] = {}
    for r in rows:
        d = str(r["d"])
        bucket = by_date.setdefault(d, {"date": d, "bullish": 0, "bearish": 0, "neutral": 0})
        s = r["sentiment"] or "neutral"
        if s in bucket:
            bucket[s] += int(r["cnt"] or 0)
    return {"items": list(by_date.values()), "days": days}


@watchlist_router.get("/analytics/volatility")
async def analytics_volatility():
    """异常波动解释：行情涨跌幅 |change_pct| > 3% 的自选股，关联当日事件说明原因"""
    from tools.market_tools import financial_data_tool

    stocks = await postgres_tool.query(
        "SELECT stock_code, stock_name, market, industry FROM watchlist.watchlist "
        "WHERE enabled = true AND item_type = 'stock'"
    )
    movers: list[dict] = []
    for s in stocks:
        code = s["stock_code"]
        market = (s.get("market") or "").lower()
        try:
            if market == "hk":
                quote = await financial_data_tool.get_hk_stock_quote(code)
            elif market == "us":
                quote = await financial_data_tool.get_us_stock_quote(code)
            else:
                quote = await financial_data_tool.get_cn_stock_quote(code)
        except Exception as e:  # noqa: BLE001
            logger.warning("[Watchlist] Quote failed | %s | %s", code, e)
            continue
        if (not isinstance(quote, dict)) or "error" in quote or "change_pct" not in quote:
            continue
        change_pct = float(quote.get("change_pct") or 0)
        if abs(change_pct) < 3:
            continue

        events = await postgres_tool.query(
            """
            SELECT importance, sentiment, summary, source_type
            FROM watchlist.watchlist_events
            WHERE stock_code = $1
              AND (created_at AT TIME ZONE 'Asia/Shanghai')::date
                  = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date
            ORDER BY importance DESC LIMIT 5
            """,
            code,
        )
        movers.append({
            "stock_code": code,
            "stock_name": s.get("stock_name") or code,
            "market": s.get("market"),
            "industry": s.get("industry"),
            "price": quote.get("price"),
            "change": quote.get("change"),
            "change_pct": round(change_pct, 2),
            "data_source": quote.get("source"),
            "events": events,
        })
    movers.sort(key=lambda m: abs(m["change_pct"]), reverse=True)
    return {"items": movers}


@watchlist_router.get("/analytics/industry")
async def analytics_industry(days: int = Query(1, ge=1, le=30)):
    """行业影响分析：同一行业多只股票同时出现事件 → 标记行业级信号"""
    rows = await postgres_tool.query(
        """
        SELECT w.industry, w.stock_code, w.stock_name,
               COUNT(e.id) AS event_cnt,
               MAX(e.importance) AS max_importance
        FROM watchlist.watchlist w
        JOIN watchlist.watchlist_events e ON e.stock_code = w.stock_code
        WHERE w.industry IS NOT NULL AND w.industry <> ''
          AND e.created_at >= NOW() - ($1 || ' days')::INTERVAL
        GROUP BY w.industry, w.stock_code, w.stock_name
        ORDER BY w.industry
        """,
        str(days),
    )
    by_ind: dict[str, dict] = {}
    for r in rows:
        ind = r["industry"]
        b = by_ind.setdefault(ind, {
            "industry": ind, "stocks": [], "total_events": 0, "max_importance": 0,
        })
        b["stocks"].append({
            "stock_code": r["stock_code"],
            "stock_name": r["stock_name"],
            "event_cnt": r["event_cnt"],
        })
        b["total_events"] += int(r["event_cnt"] or 0)
        b["max_importance"] = max(b["max_importance"], int(r["max_importance"] or 0))
    items = []
    for b in by_ind.values():
        b["stock_count"] = len(b["stocks"])
        b["is_industry_signal"] = b["stock_count"] >= 2 and b["total_events"] >= 3
        items.append(b)
    items.sort(key=lambda x: (-x["stock_count"], -x["total_events"]))
    return {"items": items}


# ── 自选股详情 / AI 摘要 / 知识图 / 研究 ────────────────────
@watchlist_router.get("/stocks/{stock_code}/detail")
async def get_stock_detail(stock_code: str):
    """个股详情聚合（基本信息 + 今日分类统计 + 近期事件）

    对应前端 StockDetailDrawer。今日统计按 source_type 维度聚合。
    """
    stock_rows = await postgres_tool.query(
        "SELECT stock_code, stock_name, market, industry, ai_score, ai_summary "
        "FROM watchlist.watchlist WHERE stock_code = $1",
        stock_code,
    )
    if not stock_rows:
        raise HTTPException(status_code=404, detail="自选股不存在")
    s = stock_rows[0]

    today_sql = "(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date"
    stats_rows = await postgres_tool.query(
        f"SELECT source_type, COUNT(*) AS cnt FROM watchlist.watchlist_events "
        f"WHERE stock_code = $1 AND (created_at AT TIME ZONE 'Asia/Shanghai')::date = {today_sql} "
        f"GROUP BY source_type",
        stock_code,
    )
    counts = {r["source_type"] or "news": r["cnt"] for r in stats_rows}
    today_stats = {
        "news_count": counts.get("news", 0),
        "announcement_count": counts.get("announcement", 0),
        "research_count": counts.get("research", 0),
        "industry_news_count": counts.get("industry", counts.get("industry_news", 0)),
        "competitor_news_count": counts.get("competitor", counts.get("competitor_news", 0)),
    }

    events = await postgres_tool.query(
        "SELECT id, stock_code, news_id, event_id, importance, sentiment, "
        "confidence, impact_horizon, summary, source_type, "
        "article_title, article_url, source_name, event_time, created_at "
        "FROM watchlist.watchlist_events WHERE stock_code = $1 "
        "ORDER BY created_at DESC LIMIT 20",
        stock_code,
    )

    return {
        "stock_code": s["stock_code"],
        "stock_name": s["stock_name"],
        "market": s["market"],
        "industry": s["industry"],
        "ai_score": s.get("ai_score") or 0,
        "today_stats": today_stats,
        "ai_summary": s.get("ai_summary"),
        "recent_events": events,
    }


@watchlist_router.get("/stocks/{stock_code}/summary")
async def get_stock_summary(stock_code: str):
    """读取个股 AI 摘要（仅返回已缓存内容）"""
    rows = await postgres_tool.query(
        "SELECT ai_summary FROM watchlist.watchlist WHERE stock_code = $1",
        stock_code,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="自选股不存在")
    return {"summary": rows[0].get("ai_summary") or ""}


@watchlist_router.post("/stocks/{stock_code}/summary")
async def generate_stock_summary(stock_code: str):
    """生成/刷新个股 AI 摘要（优先 LLM 深度生成，失败降级为事件聚合）"""
    rows = await postgres_tool.query(
        "SELECT stock_code, stock_name FROM watchlist.watchlist WHERE stock_code = $1",
        stock_code,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="自选股不存在")
    name = rows[0].get("stock_name") or stock_code

    events = await postgres_tool.query(
        "SELECT importance, sentiment, summary, source_type, created_at "
        "FROM watchlist.watchlist_events WHERE stock_code = $1 "
        "ORDER BY created_at DESC LIMIT 15",
        stock_code,
    )

    summary = None
    # 无事件时不调用 LLM，直接返回提示
    if not events:
        summary = f"{name}（{stock_code}）近期暂无监控事件。"
    else:
        # 尝试 LLM 深度生成（带超时，失败降级）
        try:
            from tools.llm import llm_tool

            ev_lines = "\n".join(
                f"- [来源:{e.get('source_type') or '未知'}|情绪:{e.get('sentiment') or '未知'}|重要度:{e.get('importance')}] "
                f"{(e.get('summary') or '')[:120]}"
                for e in events
            )
            system = (
                "你是一名资深 A 股投资分析师。请根据给定的自选股监控事件，"
                "生成一份简洁、客观、中文的投资摘要（150-250字）。"
                "结构：① 一句话结论；② 关键事件及其潜在影响；③ 风险提示。"
                "只基于提供的事件，不要编造事实，不要使用 Markdown 标题。"
            )
            user = f"股票：{name}（{stock_code}）\n\n近期监控事件：\n{ev_lines}\n\n请生成投资摘要。"
            resp = await asyncio.wait_for(
                llm_tool.chat(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.3,
                    max_tokens=500,
                ),
                timeout=90.0,
            )
            content = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
            if content and content.strip():
                summary = content.strip()
            else:
                logger.warning("[Watchlist] AI summary empty for %s, fallback", stock_code)
        except asyncio.TimeoutError:
            logger.warning("[Watchlist] AI summary timed out for %s, fallback", stock_code)
        except Exception as e:  # noqa: BLE001
            logger.warning("[Watchlist] AI summary failed for %s | %s", stock_code, e)

        if not summary:
            # 降级：简单事件聚合
            top = [e for e in events if e["importance"] >= 4][:3]
            parts = []
            if top:
                parts.append("重点关注：" + "；".join(
                    f"{(e['summary'] or '')[:40]}" for e in top
                ))
            neutral = sum(1 for e in events if e.get("sentiment") == "neutral")
            bullish = sum(1 for e in events if e.get("sentiment") == "bullish")
            bearish = sum(1 for e in events if e.get("sentiment") == "bearish")
            parts.append(f"近期事件 {len(events)} 条（看多 {bullish} / 看空 {bearish} / 中性 {neutral}）。")
            summary = f"{name}（{stock_code}）" + " ".join(parts)

    await postgres_tool.execute(
        "UPDATE watchlist.watchlist SET ai_summary = $1 WHERE stock_code = $2",
        summary, stock_code,
    )
    return {"summary": summary}


@watchlist_router.get("/stocks/{stock_code}/graph")
async def get_stock_graph(stock_code: str):
    """个股知识图谱（Apache AGE 查询，容错降级为空图）"""
    nodes: list = []
    edges: list = []
    try:
        from storage.knowledge.age import GRAPH_NAME
        cypher = (
            f"MATCH (n) WHERE n.name = '{stock_code}' OR n.canonical_name = '{stock_code}' "
            f"OPTIONAL MATCH (n)-[r]->(m) RETURN n, r, m "
            f"LIMIT 60"
        )
        sql = f"SELECT * FROM cypher('{GRAPH_NAME}', $${cypher}$$) AS (n agtype, r agtype, m agtype);"
        rows = await postgres_tool.query(sql)
        seen_node: set = set()
        for row in rows:
            n = _agtype_to_dict(row.get("n"))
            m = _agtype_to_dict(row.get("m"))
            r = _agtype_to_dict(row.get("r"))
            for node in (n, m):
                if not node:
                    continue
                nid = str(node.get("entity_id") or node.get("name"))
                if nid not in seen_node:
                    seen_node.add(nid)
                    nodes.append({
                        "id": nid,
                        "label": node.get("name") or nid,
                        "type": node.get("entity_type") or "Entity",
                    })
            if r and n and m:
                src = str(n.get("entity_id") or n.get("name"))
                dst = str(m.get("entity_id") or m.get("name"))
                edges.append({"source": src, "target": dst, "label": r.get("relation_type") or ""})
    except Exception as e:  # noqa: BLE001
        logger.warning("[Watchlist] Graph query failed | %s", e)
        nodes, edges = [], []
    return {"nodes": nodes, "edges": edges}


def _agtype_to_dict(raw) -> Optional[dict]:
    """将 AGE cypher 返回的 agtype 字符串解析为 dict（尽力而为）"""
    if raw is None:
        return None
    import json as _json
    s = str(raw)
    if not s or s.strip() == "":
        return None
    try:
        return _json.loads(s)
    except Exception:
        return None


@watchlist_router.post("/stocks/{stock_code}/research")
async def trigger_stock_research(stock_code: str, question: Optional[str] = None):
    """触发个股深度研究（Research Agent，异步执行）"""
    rows = await postgres_tool.query(
        "SELECT stock_code, stock_name, market FROM watchlist.watchlist WHERE stock_code = $1",
        stock_code,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="自选股不存在")
    s = rows[0]
    name = s.get("stock_name") or stock_code
    market = s.get("market") or "cn"
    default_q = f"对 {name}（{stock_code}）进行深度投研分析"
    q = question or default_q

    import uuid
    task_id = str(uuid.uuid4())
    try:
        await postgres_tool.execute(
            "INSERT INTO research_tasks (id, question, agent_type, market, symbol, status, created_at) "
            "VALUES ($1, $2, 'research', $3, $4, 'running', NOW())",
            task_id, q, market, stock_code,
        )
    except Exception as e:
        logger.error("[Watchlist] Research task insert failed | %s", e)
        raise HTTPException(status_code=500, detail="研究任务创建失败")

    async def _run():
        try:
            from agents.research_agent import ResearchAgent
            from schemas.chat import ChatRequest, ChatMessage
            agent = ResearchAgent()
            req = ChatRequest(messages=[ChatMessage(role="user", content=q)])
            resp = await agent.run(req)
            answer = resp.choices[0].message.content if resp.choices else ""
            await postgres_tool.execute(
                "UPDATE research_tasks SET status='completed', answer=$1, "
                "completed_at=NOW() WHERE id=$2",
                answer, task_id,
            )
        except Exception as e:
            logger.error("[Watchlist] Research run failed | %s", e)
            await postgres_tool.execute(
                "UPDATE research_tasks SET status='failed', error=$1, "
                "completed_at=NOW() WHERE id=$2",
                str(e), task_id,
            )

    asyncio.create_task(_run())
    return {"task_id": task_id, "status": "running"}


# ── 配置 ───────────────────────────────────────────────────
@watchlist_router.get("/config")
async def get_config():
    """读取 watchlist_settings（含 v2 扩展字段）"""
    rows = await postgres_tool.query(
        "SELECT schedule_time, auto_enabled, webhook_url, "
        "monitoring_scopes, ai_summary_enabled, daily_report_enabled, "
        "email_enabled, email_address, update_frequency, alert_threshold, "
        "notification_channels, updated_at "
        "FROM watchlist.watchlist_settings WHERE id = 1"
    )
    if not rows:
        raise HTTPException(status_code=404, detail="配置不存在")
    row = rows[0]
    # 解析 JSONB monitoring_scopes
    scopes = row.get("monitoring_scopes")
    if isinstance(scopes, str):
        try:
            row["monitoring_scopes"] = json.loads(scopes)
        except (json.JSONDecodeError, TypeError):
            row["monitoring_scopes"] = []
    # 解析 JSONB notification_channels
    channels = row.get("notification_channels")
    if isinstance(channels, str):
        try:
            row["notification_channels"] = json.loads(channels)
        except (json.JSONDecodeError, TypeError):
            row["notification_channels"] = []
    return row


@watchlist_router.put("/config")
async def update_config(update: ConfigUpdate):
    """更新 watchlist_settings（含 v2 扩展字段），并重载调度 job"""
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
    if update.monitoring_scopes is not None:
        params.append(json.dumps(update.monitoring_scopes))
        fields.append(f"monitoring_scopes = ${len(params)}")
    if update.ai_summary_enabled is not None:
        params.append(update.ai_summary_enabled)
        fields.append(f"ai_summary_enabled = ${len(params)}")
    if update.daily_report_enabled is not None:
        params.append(update.daily_report_enabled)
        fields.append(f"daily_report_enabled = ${len(params)}")
    if update.email_enabled is not None:
        params.append(update.email_enabled)
        fields.append(f"email_enabled = ${len(params)}")
    if update.email_address is not None:
        params.append(update.email_address)
        fields.append(f"email_address = ${len(params)}")
    if update.update_frequency is not None:
        if update.update_frequency not in ("realtime", "hourly", "daily"):
            raise HTTPException(status_code=422, detail="update_frequency 必须为 realtime/hourly/daily")
        params.append(update.update_frequency)
        fields.append(f"update_frequency = ${len(params)}")
    if update.alert_threshold is not None:
        if update.alert_threshold < 1 or update.alert_threshold > 5:
            raise HTTPException(status_code=422, detail="alert_threshold 必须为 1-5")
        params.append(update.alert_threshold)
        fields.append(f"alert_threshold = ${len(params)}")
    if update.notification_channels is not None:
        valid = {"web", "email", "webhook"}
        if any(c not in valid for c in update.notification_channels):
            raise HTTPException(status_code=422, detail="notification_channels 只能为 web/email/webhook")
        params.append(json.dumps(update.notification_channels))
        fields.append(f"notification_channels = ${len(params)}")

    if len(fields) <= 1:
        raise HTTPException(status_code=400, detail="无更新字段")

    rows = await postgres_tool.query(
        f"UPDATE watchlist.watchlist_settings SET {', '.join(fields)} "
        f"WHERE id = 1 RETURNING *",
        *params,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="配置不存在")

    # 重载调度 job（时间/开关/频率变更后生效）
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


@watchlist_router.post("/reports/{report_id}/export")
async def export_report(report_id: str, format_: str = Query("md", alias="format")):
    """导出报告（md=Markdown 下载，pdf=PDF 下载）"""
    rows = await postgres_tool.query(
        "SELECT report_date, title, content FROM watchlist.daily_watchlist_report "
        "WHERE id = $1",
        report_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="报告不存在")
    row = rows[0]
    content = row.get("content") or ""
    title = row.get("title") or f"watchlist-report-{row.get('report_date') or 'unknown'}"
    report_date = str(row.get("report_date") or "")

    if format_.lower() == "pdf":
        try:
            from services.report_pdf import markdown_to_pdf_bytes

            pdf_bytes = markdown_to_pdf_bytes(content, title=title, report_date=report_date)
            filename = f"{title}.pdf"
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{filename}"
                },
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[Watchlist] PDF export failed | %s", e)
            raise HTTPException(status_code=500, detail=f"PDF 生成失败: {e}")

    filename = f"{title}.md"
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}"
        },
    )


class ReportEmailRequest(BaseModel):
    to: str = Field(..., min_length=3, max_length=256)


@watchlist_router.post("/reports/{report_id}/email")
async def email_report(report_id: str, req: ReportEmailRequest):
    """把报告通过 SMTP 发送到指定邮箱（需已配置 SMTP 环境变量）"""
    rows = await postgres_tool.query(
        "SELECT report_date, title, content FROM watchlist.daily_watchlist_report "
        "WHERE id = $1",
        report_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="报告不存在")
    row = rows[0]

    host = os.getenv("WATCHLIST_SMTP_HOST")
    port = int(os.getenv("WATCHLIST_SMTP_PORT", "465"))
    user = os.getenv("WATCHLIST_SMTP_USER")
    password = os.getenv("WATCHLIST_SMTP_PASSWORD")
    sender = os.getenv("WATCHLIST_SMTP_FROM", user or "watchlist@localhost")
    use_tls = os.getenv("WATCHLIST_SMTP_TLS", "1") not in ("0", "false", "False")

    if not host or not user or not password:
        raise HTTPException(
            status_code=400,
            detail="SMTP 未配置，请设置 WATCHLIST_SMTP_HOST/USER/PASSWORD 环境变量",
        )

    subject = row.get("title") or f"Watchlist Daily Report {row.get('report_date') or ''}"
    body = row.get("content") or ""
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr(("Watchlist", sender))
    msg["To"] = req.to

    # SMTP 同步发送放到线程池，避免阻塞事件循环
    def _send() -> None:
        if use_tls:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
        try:
            server.login(user, password)
            server.sendmail(sender, [req.to], msg.as_string())
        finally:
            server.quit()

    try:
        await asyncio.to_thread(_send)
    except Exception as e:  # noqa: BLE001
        logger.warning("[Watchlist] Email send failed | %s", e)
        raise HTTPException(status_code=502, detail=f"邮件发送失败: {e}")

    return {"ok": True, "to": req.to, "subject": subject}


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
        f"we.summary, we.source_type, "
        f"we.article_title, we.article_url, we.source_name, "
        f"we.event_time, we.created_at "
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


@watchlist_router.post("/alerts/read-all")
async def mark_all_alerts_read():
    """将所有 Web 告警标记为已读（需注册在 /{alert_id}/read 之前，避免被捕获）"""
    await postgres_tool.execute(
        "UPDATE watchlist.watchlist_alerts SET read = true WHERE channel = 'web'"
    )
    return {"ok": True}


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
    if update.item_type is not None:
        params.append(update.item_type)
        fields.append(f"item_type = ${len(params)}")

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