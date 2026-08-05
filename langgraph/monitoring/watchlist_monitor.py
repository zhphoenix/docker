"""Watchlist Monitor — 每日监控主流程

流程：加载自选股 → 复用 news 采集管线逐股采集 → 查询当日相关文章/事件 →
幂等写入 watchlist_events → 生成每日报告 → 发送 Web/Webhook 告警。
"""

import logging
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


def _event_to_watch_event(stock_code: str, ev: dict) -> dict:
    """将 news.events 行转换为 watchlist_events 行"""
    return {
        "stock_code": stock_code,
        "news_id": ev.get("article_id"),
        "event_id": ev.get("id"),
        "importance": _importance_from_score(ev.get("impact_score")),
        "sentiment": _SENTIMENT_MAP.get(ev.get("impact_direction"), "neutral"),
        "confidence": _confidence_from_score(ev.get("confidence")),
        "impact_horizon": _HORIZON_MAP.get(ev.get("impact_duration"), "short_term"),
        "summary": ev.get("summary") or ev.get("title"),
        "source_type": "company",
        "event_time": ev.get("event_time") or ev.get("created_at"),
    }


def _article_to_watch_event(stock_code: str, art: dict, event: Optional[dict] = None) -> dict:
    """将 news.articles 行（可附事件）转换为 watchlist_events 行"""
    if event:
        return {
            "stock_code": stock_code,
            "news_id": art.get("id"),
            "event_id": event.get("id"),
            "importance": _importance_from_score(event.get("impact_score")),
            "sentiment": _SENTIMENT_MAP.get(event.get("impact_direction"), "neutral"),
            "confidence": _confidence_from_score(event.get("confidence")),
            "impact_horizon": _HORIZON_MAP.get(event.get("impact_duration"), "short_term"),
            "summary": event.get("summary") or event.get("title") or art.get("summary"),
            "source_type": "company",
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
        "summary": art.get("summary") or art.get("title"),
        "source_type": "company",
        "event_time": art.get("published_at"),
    }


async def _load_watchlist() -> list[dict]:
    """加载启用中的自选股"""
    return await postgres_tool.query(
        "SELECT stock_code, stock_name FROM watchlist.watchlist WHERE enabled = true"
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


async def _collect_and_analyze_stock(stock_code: str, stock_name: str) -> list[dict]:
    """对单只股票执行采集 + 关联分析，返回待写入的 watchlist_events 行"""
    # 复用现有新闻采集管线（延迟导入避免循环依赖）
    from api.news import _run_collection

    logger.info("[Monitor] Collect stock | %s (%s)", stock_name, stock_code)

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

    # 对每篇文章关联其事件，构造 watch_event
    watch_events: list[dict] = []
    for art in articles:
        try:
            detail = await news_storage.get_article_by_id(str(art["id"]))
        except Exception as e:  # noqa: BLE001
            logger.warning("[Monitor] Article detail failed | %s | %s", art.get("id"), e)
            detail = None

        evs = (detail or {}).get("events") or []
        if evs:
            for ev in evs:
                # news.events 查询未返回 article_id，从文章上下文注入以保持可追溯性
                ev = dict(ev)
                ev["article_id"] = art.get("id")
                watch_events.append(_event_to_watch_event(stock_code, ev))
        else:
            watch_events.append(_article_to_watch_event(stock_code, art))

    return watch_events


async def run_watchlist_monitoring() -> dict:
    """执行一次完整监控流程

    Returns:
        {"collected": int, "written": int, "report": dict}
    """
    watchlist = await _load_watchlist()
    logger.info("[Monitor] Watchlist monitoring start | stocks=%d", len(watchlist))

    existing = await _existing_keys()
    all_watch_events: list[dict] = []
    written = 0

    for item in watchlist:
        stock_code = item["stock_code"]
        stock_name = item["stock_name"]
        events = await _collect_and_analyze_stock(stock_code, stock_name)

        for ev in events:
            key = (stock_code, str(ev["news_id"])) if ev.get("news_id") else None
            if key and key in existing:
                continue
            all_watch_events.append(ev)
            if key:
                existing.add(key)

    # 批量写入
    if all_watch_events:
        rows = [
            (
                ev["stock_code"], ev["news_id"], ev["event_id"], ev["importance"],
                ev["sentiment"], ev["confidence"], ev["impact_horizon"],
                ev["summary"], ev["source_type"], ev["event_time"],
            )
            for ev in all_watch_events
        ]
        await postgres_tool.execute_many(
            """
            INSERT INTO watchlist.watchlist_events
                (stock_code, news_id, event_id, importance, sentiment, confidence,
                 impact_horizon, summary, source_type, event_time)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
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

    # 生成每日报告
    report = await generate_daily_report()

    logger.info("[Monitor] Watchlist monitoring done | collected=%d | written=%d",
                len(all_watch_events), written)
    return {"collected": len(all_watch_events), "written": written, "report": report}