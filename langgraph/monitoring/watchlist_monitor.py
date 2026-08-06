"""Watchlist Monitor — 每日监控主流程

流程：加载自选股 → 复用 news 采集管线逐股采集 → 查询当日相关文章/事件 →
幂等写入 watchlist_events → 生成每日报告 → 发送 Web/Webhook 告警。
"""

import asyncio
import json
import logging
import re
from typing import Optional

from services.news_storage import news_storage
from tools.postgres import postgres_tool

from monitoring.watchlist_alerts import notify_event
from monitoring.watchlist_report import generate_daily_report

logger = logging.getLogger(__name__)

# 情绪方向映射
_SENTIMENT_MAP = {"positive": "bullish", "negative": "bearish"}
# 影响时长映射（short_term/mid_term/long_term，与 news.events.impact_duration 对齐）
_HORIZON_MAP = {"short_term": "short_term", "mid_term": "mid_term", "long_term": "long_term"}

# 监控维度 → 事件类型（news.events.event_type）推断的 source_type
_EVENT_SOURCE_MAP = {
    "earnings": "earnings",
    "regulation": "announcement",
    "merger": "announcement",
    "acquisition": "announcement",
    "product_launch": "announcement",
    "macro_policy": "policy",
    "geopolitical": "overseas",
    "supply_chain": "industry",
    "technology": "industry",
}

# 监控维度 → 文章分类（news.articles.category）推断的 source_type
_CATEGORY_SOURCE_MAP = {
    "policy": "policy",
    "geopolitics": "overseas",
    "technology": "industry",
    "company": "announcement",
}


# 监控对象类型 → 默认监控维度（非个股对象按主题归类，空則用事件/文章自身推断）
_TYPE_FALLBACK_SOURCE = {
    "etf": "market",
    "index": "market",
    "industry": "industry",
    "macro_theme": "macro",
    "fund": "market",
}


def _source_with_fallback(source_type: Optional[str], item_type: str) -> str:
    """事件/文章推断的 source_type 若为默认 news，则按 item_type 兜底归类"""
    if source_type and source_type != "news":
        return source_type
    return _TYPE_FALLBACK_SOURCE.get(item_type, "news")


def _importance_from_score(score) -> int:
    """从事件 impact_score（-1~1）映射为 1~5"""
    if score is None:
        return 3
    s = abs(float(score))
    if s >= 0.8:
        return 5
    if s >= 0.6:
        return 4
    if s >= 0.4:
        return 3
    if s >= 0.2:
        return 2
    return 1


def _confidence_from_score(score) -> str:
    """从事件 confidence（0~1）映射为枚举"""
    if score is None:
        return "medium"
    s = float(score)
    if s >= 0.9:
        return "official"
    if s >= 0.7:
        return "high"
    if s >= 0.5:
        return "medium"
    return "low"


def _summarize_article(art: dict, limit: int = 300) -> str:
    """生成事件摘要：优先文章 summary，其次正文截断（去除 Markdown 噪音），兜底标题"""
    text = (art.get("summary") or "").strip()
    if text:
        return text
    content = art.get("content") or ""
    # 去 Markdown 链接/标记，压缩空白
    content = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", content)
    content = re.sub(r"[#>*`|]+", " ", content)
    content = re.sub(r"\s+", " ", content).strip()
    if content:
        return content[:limit]
    return art.get("title") or ""


def _event_to_watch_event(stock_code: str, ev: dict, art: Optional[dict] = None,
                          item_type: str = "stock") -> dict:
    """将 news.events 行转换为 watchlist_events 行（art 提供文章冗余信息）"""
    art = art or {}
    # 按事件类型推断监控维度（source_type），用于 monitoring_scopes 过滤
    source_type = _source_with_fallback(
        _EVENT_SOURCE_MAP.get(ev.get("event_type"), "news"), item_type
    )
    return {
        "stock_code": stock_code,
        "news_id": ev.get("article_id"),
        "event_id": ev.get("id"),
        "importance": _importance_from_score(ev.get("impact_score")),
        "sentiment": _SENTIMENT_MAP.get(ev.get("impact_direction"), "neutral"),
        "confidence": _confidence_from_score(ev.get("confidence")),
        "impact_horizon": _HORIZON_MAP.get(ev.get("impact_duration"), "short_term"),
        "summary": ev.get("summary") or ev.get("title") or _summarize_article(art),
        "source_type": source_type,
        "article_title": art.get("title"),
        "article_url": art.get("url"),
        "source_name": art.get("source_name"),
        "event_time": ev.get("event_time") or ev.get("created_at"),
    }


def _article_to_watch_event(stock_code: str, art: dict, event: Optional[dict] = None,
                            item_type: str = "stock") -> dict:
    """将 news.articles 行（可附事件）转换为 watchlist_events 行"""
    article_meta = {
        "article_title": art.get("title"),
        "article_url": art.get("url"),
        "source_name": art.get("source_name"),
    }
    if event:
        return {
            "stock_code": stock_code,
            "news_id": art.get("id"),
            "event_id": event.get("id"),
            "importance": _importance_from_score(event.get("impact_score")),
            "sentiment": _SENTIMENT_MAP.get(event.get("impact_direction"), "neutral"),
            "confidence": _confidence_from_score(event.get("confidence")),
            "impact_horizon": _HORIZON_MAP.get(event.get("impact_duration"), "short_term"),
            "summary": event.get("summary") or event.get("title") or _summarize_article(art),
            "source_type": _source_with_fallback(
                _EVENT_SOURCE_MAP.get(event.get("event_type"), "news"), item_type
            ),
            **article_meta,
            "event_time": event.get("event_time") or art.get("published_at"),
        }
    return {
        "stock_code": stock_code,
        "news_id": art.get("id"),
        "event_id": None,
        # news.articles 无 importance 列，用 importance_score（0~1）映射
        "importance": _importance_from_score(art.get("importance_score")),
        "sentiment": "neutral",
        "confidence": "medium",
        "impact_horizon": "short_term",
        "summary": _summarize_article(art),
        "source_type": _source_with_fallback(
            _CATEGORY_SOURCE_MAP.get(art.get("category"), "news"), item_type
        ),
        **article_meta,
        "event_time": art.get("published_at"),
    }


async def _load_watchlist() -> list[dict]:
    """加载启用中的自选股（含监控对象类型）"""
    return await postgres_tool.query(
        "SELECT stock_code, stock_name, item_type FROM watchlist.watchlist "
        "WHERE enabled = true"
    )


async def _existing_keys() -> set[tuple]:
    """当前已存在的 (stock_code, news_id) 集合（去除 news_id 为空的）"""
    rows = await postgres_tool.query(
        """
        SELECT stock_code, news_id FROM watchlist.watchlist_events
        WHERE news_id IS NOT NULL
        """
    )
    return {(r["stock_code"], str(r["news_id"])) for r in rows}


async def _collect_and_analyze_stock(stock_code: str, stock_name: str,
                                     item_type: str = "stock") -> list[dict]:
    """对单只股票执行采集 + 关联分析，返回待写入的 watchlist_events 行"""
    # 复用现有新闻采集管线（延迟导入避免循环依赖）
    from api.news import _run_collection

    logger.info("[Monitor] Collect | %s (%s) | type=%s", stock_name, stock_code, item_type)

    # 触发采集（按股票名关键词过滤）
    try:
        await _run_collection(stock_name, "high")
    except Exception as e:  # noqa: BLE001
        logger.error("[Monitor] Collect failed | %s | %s", stock_code, e)

    # 查询当日相关文章
    articles = await news_storage.search_articles(
        keyword=stock_name, days=2, limit=20,
    )
    if not articles:
        logger.info("[Monitor] No related articles | %s", stock_code)
        return []

    return await _articles_to_watch_events(stock_code, articles, item_type=item_type)


async def _articles_to_watch_events(stock_code: str, articles: list[dict],
                                    item_type: str = "stock") -> list[dict]:
    """对文章列表关联事件并构造 watchlist_events 行（不触发采集，供增量使用）"""
    watch_events: list[dict] = []
    for art in articles:
        try:
            detail = await news_storage.get_article_by_id(str(art["id"]))
        except Exception as e:  # noqa: BLE001
            logger.warning("[Monitor] Article detail failed | %s | %s", art.get("id"), e)
            detail = None

        evs = (detail or {}).get("events") or []
        # 文章详情含完整正文，合并进列表行用于生成摘要
        merged = {**art, **(detail or {})}
        if evs:
            for ev in evs:
                # news.events 查询未返回 article_id，从文章上下文注入以保持可追溯性
                ev = dict(ev)
                ev["article_id"] = art.get("id")
                watch_events.append(_event_to_watch_event(stock_code, ev, merged, item_type))
        else:
            watch_events.append(_article_to_watch_event(stock_code, merged, item_type=item_type))

    return watch_events


async def run_watchlist_monitoring() -> dict:
    """执行一次完整监控流程（并发采集 + 流式写入）

    按 watchlist_settings.monitoring_scopes 过滤采集维度：
    仅当 scopes 为空或包含某维度时，才写入该维度的 watchlist_events。

    Returns:
        {"collected": int, "written": int, "report": dict}
    """
    watchlist = await _load_watchlist()
    logger.info("[Monitor] Watchlist monitoring start | stocks=%d", len(watchlist))

    # 读取监控维度配置（为空表示全部维度）
    scopes: list[str] = []
    try:
        cfg_rows = await postgres_tool.query(
            "SELECT monitoring_scopes FROM watchlist.watchlist_settings WHERE id = 1"
        )
        if cfg_rows:
            raw = cfg_rows[0].get("monitoring_scopes")
            if isinstance(raw, str):
                try:
                    scopes = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    scopes = []
            elif isinstance(raw, list):
                scopes = raw
    except Exception as e:  # noqa: BLE001
        logger.warning("[Monitor] Read monitoring_scopes failed | %s", e)

    existing = await _existing_keys()
    all_watch_events: list[dict] = []
    total_collected = 0
    written = 0

    # 并发采集（Semaphore 限制并发度，避免 News Pipeline 过载）
    sem = asyncio.Semaphore(5)

    async def collect_one(item: dict) -> list[dict]:
        stock_code = item["stock_code"]
        stock_name = item["stock_name"]
        item_type = item.get("item_type") or "stock"
        async with sem:
            try:
                return await asyncio.wait_for(
                    _collect_and_analyze_stock(stock_code, stock_name, item_type),
                    timeout=180.0,
                )
            except asyncio.TimeoutError:
                logger.error("[Monitor] Timeout collecting | %s", stock_code)
                return []
            except Exception as e:  # noqa: BLE001
                logger.error("[Monitor] Collect failed | %s | %s", stock_code, e)
                return []

    results = await asyncio.gather(*[collect_one(item) for item in watchlist])

    # 聚合结果 + 更新统计
    stock_event_counts: dict[str, int] = {}
    stock_news_counts: dict[str, int] = {}
    for item, events in zip(watchlist, results):
        stock_code = item["stock_code"]
        # 按监控维度过滤（scopes 为空 = 全部）
        if scopes:
            events = [ev for ev in events if ev.get("source_type") in scopes]
        total_collected += len(events)
        for ev in events:
            key = (stock_code, str(ev["news_id"])) if ev.get("news_id") else None
            if key and key in existing:
                continue
            all_watch_events.append(ev)
            if key:
                existing.add(key)
        # Track per-stock counts
        stock_event_counts[stock_code] = len(events)
        stock_news_counts[stock_code] = len(
            {str(e["news_id"]) for e in events if e.get("news_id")}
        )

    # 批量写入 watchlist_events
    if all_watch_events:
        rows = [
            (
                ev["stock_code"], ev["news_id"], ev["event_id"], ev["importance"],
                ev["sentiment"], ev["confidence"], ev["impact_horizon"],
                ev["summary"], ev["source_type"],
                ev.get("article_title"), ev.get("article_url"), ev.get("source_name"),
                ev["event_time"],
            )
            for ev in all_watch_events
        ]
        await postgres_tool.execute_many(
            """
            INSERT INTO watchlist.watchlist_events
                (stock_code, news_id, event_id, importance, sentiment, confidence,
                 impact_horizon, summary, source_type,
                 article_title, article_url, source_name, event_time)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
            rows,
        )
        written = len(rows)
        logger.info("[Monitor] Written %d watchlist_events", written)

        # 发送告警（仅高优先事件）
        for ev in all_watch_events:
            if ev["importance"] >= 4:
                try:
                    await notify_event(ev)
                except Exception as e:  # noqa: BLE001
                    logger.error("[Monitor] Alert failed | %s", e)
    else:
        logger.info("[Monitor] No new events to write")

    # 更新每只股票的统计列
    now_iso = None
    date_rows = await postgres_tool.query(
        "SELECT NOW() AS now"
    )
    if date_rows:
        now_iso = date_rows[0]["now"]
    for stock_code in stock_event_counts:
        await postgres_tool.execute(
            "UPDATE watchlist.watchlist SET "
            "last_event_at = $1, today_event_count = $2, today_news_count = $3 "
            "WHERE stock_code = $4",
            now_iso,
            stock_event_counts.get(stock_code, 0),
            stock_news_counts.get(stock_code, 0),
            stock_code,
        )

    # 写入 daily_stats 快照
    await _update_daily_stats()

    # 生成每日报告
    report = await generate_daily_report()

    logger.info("[Monitor] Watchlist monitoring done | collected=%d | written=%d",
                total_collected, written)
    return {"collected": total_collected, "written": written, "report": report}


async def run_incremental_watchlist_monitoring(hours_back: float = 1.0) -> dict:
    """盘中增量监控：不触发新一轮新闻采集，仅查询最近 hours_back 小时已入库的
    news.articles 增量，关联事件后幂等写入 watchlist_events。

    Args:
        hours_back: 回看窗口（小时），例如 realtime=0.25、hourly=1。

    Returns:
        {"scanned": int, "collected": int, "written": int}
    """
    watchlist = await _load_watchlist()
    logger.info(
        "[Monitor] Incremental start | stocks=%d | window=%.2fh",
        len(watchlist), hours_back,
    )
    if not watchlist:
        return {"scanned": 0, "collected": 0, "written": 0}

    # 读取监控维度配置（为空表示全部维度）
    scopes: list[str] = []
    try:
        cfg_rows = await postgres_tool.query(
            "SELECT monitoring_scopes FROM watchlist.watchlist_settings WHERE id = 1"
        )
        if cfg_rows:
            raw = cfg_rows[0].get("monitoring_scopes")
            if isinstance(raw, str):
                try:
                    scopes = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    scopes = []
            elif isinstance(raw, list):
                scopes = raw
    except Exception as e:  # noqa: BLE001
        logger.warning("[Monitor] Read monitoring_scopes failed | %s", e)

    existing = await _existing_keys()
    sem = asyncio.Semaphore(5)

    async def scan_one(item: dict) -> list[dict]:
        stock_code = item["stock_code"]
        stock_name = item["stock_name"]
        item_type = item.get("item_type") or "stock"
        async with sem:
            try:
                # 轻量增量查询：仅窗口内文章，不触发采集
                articles = await news_storage.search_articles(
                    keyword=stock_name, days=hours_back / 24.0, limit=20,
                )
                if not articles:
                    return []
                return await _articles_to_watch_events(stock_code, articles, item_type=item_type)
            except asyncio.TimeoutError:
                logger.error("[Monitor] Incremental timeout | %s", stock_code)
                return []
            except Exception as e:  # noqa: BLE001
                logger.error("[Monitor] Incremental scan failed | %s | %s", stock_code, e)
                return []

    results = await asyncio.gather(*[scan_one(item) for item in watchlist])

    all_watch_events: list[dict] = []
    scanned = 0
    for item, events in zip(watchlist, results):
        stock_code = item["stock_code"]
        if scopes:
            events = [ev for ev in events if ev.get("source_type") in scopes]
        scanned += len(events)
        for ev in events:
            key = (stock_code, str(ev["news_id"])) if ev.get("news_id") else None
            if key and key in existing:
                continue
            all_watch_events.append(ev)
            if key:
                existing.add(key)

    written = 0
    if all_watch_events:
        rows = [
            (
                ev["stock_code"], ev["news_id"], ev["event_id"], ev["importance"],
                ev["sentiment"], ev["confidence"], ev["impact_horizon"],
                ev["summary"], ev["source_type"],
                ev.get("article_title"), ev.get("article_url"), ev.get("source_name"),
                ev["event_time"],
            )
            for ev in all_watch_events
        ]
        await postgres_tool.execute_many(
            """
            INSERT INTO watchlist.watchlist_events
                (stock_code, news_id, event_id, importance, sentiment, confidence,
                 impact_horizon, summary, source_type,
                 article_title, article_url, source_name, event_time)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
            rows,
        )
        written = len(rows)
        logger.info("[Monitor] Incremental written %d events", written)

        for ev in all_watch_events:
            if ev["importance"] >= 4:
                try:
                    await notify_event(ev)
                except Exception as e:  # noqa: BLE001
                    logger.error("[Monitor] Alert failed | %s", e)
    else:
        logger.info("[Monitor] Incremental: no new events")

    # 刷新当日统计快照
    await _update_daily_stats()

    logger.info(
        "[Monitor] Incremental done | window=%.2fh | scanned=%d | written=%d",
        hours_back, scanned, written,
    )
    return {"scanned": scanned, "collected": scanned, "written": written}


async def _update_daily_stats():
    """生成/更新当日 watchlist_daily_stats 快照"""
    from monitoring.watchlist_alerts import _level_for_importance
    try:
        rows = await postgres_tool.query(
            """
            SELECT
                (SELECT COUNT(*) FROM watchlist.watchlist WHERE enabled = true) AS total_stocks,
                (SELECT COUNT(*) FROM watchlist.watchlist_events
                 WHERE (created_at AT TIME ZONE 'Asia/Shanghai')::date
                     = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date) AS total_events,
                (SELECT COUNT(*) FROM watchlist.watchlist_events
                 WHERE (created_at AT TIME ZONE 'Asia/Shanghai')::date
                     = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date
                   AND importance >= 4) AS high_priority_events,
                (SELECT COUNT(*) FROM watchlist.watchlist_alerts
                 WHERE created_at::date = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date) AS total_alerts,
                (SELECT COUNT(*) FROM watchlist.watchlist_alerts
                 WHERE level = 'critical'
                   AND created_at::date = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date) AS critical_alerts,
                (SELECT COUNT(*) FROM watchlist.daily_watchlist_report
                 WHERE report_date = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date) AS ai_reports
        """
        )
        if not rows:
            return
        r = rows[0]
        await postgres_tool.execute(
            """
            INSERT INTO watchlist.watchlist_daily_stats
                (stat_date, total_stocks, total_events, high_priority_events,
                 total_alerts, critical_alerts, ai_reports_generated)
            VALUES ((CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date,
                    $1, $2, $3, $4, $5, $6)
            ON CONFLICT (stat_date)
            DO UPDATE SET total_stocks = EXCLUDED.total_stocks,
                          total_events = EXCLUDED.total_events,
                          high_priority_events = EXCLUDED.high_priority_events,
                          total_alerts = EXCLUDED.total_alerts,
                          critical_alerts = EXCLUDED.critical_alerts,
                          ai_reports_generated = EXCLUDED.ai_reports_generated
            """,
            r["total_stocks"] or 0,
            r["total_events"] or 0,
            r["high_priority_events"] or 0,
            r["total_alerts"] or 0,
            r["critical_alerts"] or 0,
            r["ai_reports"] or 0,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[Monitor] daily_stats update failed | %s", e)