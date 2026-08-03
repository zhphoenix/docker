"""News API Router - 新闻智能管线 REST 端点

提供新闻搜索、文章详情、事件浏览、影响分析、时间线等接口。
数据来源: PostgreSQL news schema（通过 services/news_storage.py）。
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.news_storage import news_storage

logger = logging.getLogger(__name__)

news_router = APIRouter(prefix="/api/news", tags=["news"])


def _serialize(row: dict) -> dict:
    """序列化 UUID/时间字段为字符串"""
    result = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        elif hasattr(v, "hex"):  # UUID
            result[k] = str(v)
        else:
            result[k] = v
    return result


# ──────────────────────────────────────────────
# Articles
# ──────────────────────────────────────────────

@news_router.get("/articles")
async def list_articles(
    keyword: str = Query("", description="搜索关键词"),
    category: str = Query("", description="分类过滤"),
    days: int = Query(7, ge=1, le=365, description="时间范围（天）"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    """搜索新闻文章列表"""
    articles = await news_storage.search_articles(
        keyword=keyword, category=category, days=days, limit=limit, offset=offset,
    )
    total = await news_storage.count_articles(
        keyword=keyword, category=category, days=days,
    )
    return {
        "articles": [_serialize(a) for a in articles],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@news_router.get("/articles/{article_id}")
async def get_article(article_id: str):
    """获取文章详情（含实体/事件）"""
    article = await news_storage.get_article_by_id(article_id)
    if not article:
        raise HTTPException(status_code=404, detail=f"Article '{article_id}' not found")
    serialized = _serialize(article)
    if "entities" in serialized:
        serialized["entities"] = [_serialize(e) for e in serialized["entities"]]
    if "events" in serialized:
        serialized["events"] = [_serialize(e) for e in serialized["events"]]
    return serialized


# ──────────────────────────────────────────────
# Events
# ──────────────────────────────────────────────

@news_router.get("/events")
async def list_events(
    event_type: str = Query("", description="事件类型过滤"),
    entity_name: str = Query("", description="关联实体名称"),
    days: int = Query(30, ge=1, le=365, description="时间范围（天）"),
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
):
    """搜索新闻事件"""
    events = await news_storage.search_events(
        event_type=event_type, entity_name=entity_name, days=days, limit=limit,
    )
    return {
        "events": [_serialize(e) for e in events],
        "total": len(events),
    }


@news_router.get("/events/{event_id}/impact")
async def get_event_impact(event_id: str):
    """获取事件影响评估"""
    result = await news_storage.get_event_impact(event_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")
    return _serialize(result)


# ──────────────────────────────────────────────
# Analysis
# ──────────────────────────────────────────────

@news_router.get("/impact")
async def analyze_impact(
    entity_name: str = Query(..., min_length=1, description="实体名称"),
    days: int = Query(30, ge=1, le=365, description="分析时间范围（天）"),
):
    """聚合分析实体近期新闻影响"""
    results = await news_storage.get_entity_news_impact(entity_name, days=days)

    if not results:
        return {
            "entity_name": entity_name,
            "total_events": 0,
            "positive_count": 0,
            "negative_count": 0,
            "neutral_count": 0,
            "avg_impact_score": 0.0,
            "events": [],
            "message": f"No news found for '{entity_name}' in last {days} days",
        }

    positive = sum(1 for r in results if r.get("impact_direction") == "positive")
    negative = sum(1 for r in results if r.get("impact_direction") == "negative")
    scores = [r["impact_score"] for r in results if r.get("impact_score") is not None]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    return {
        "entity_name": entity_name,
        "days": days,
        "total_events": len(results),
        "positive_count": positive,
        "negative_count": negative,
        "neutral_count": len(results) - positive - negative,
        "avg_impact_score": round(avg_score, 3),
        "events": [_serialize(r) for r in results[:20]],
    }


@news_router.get("/timeline")
async def get_timeline(
    entity_name: str = Query(..., min_length=1, description="实体名称"),
    days: int = Query(90, ge=1, le=365, description="时间范围（天）"),
    limit: int = Query(50, ge=1, le=200, description="返回数量"),
):
    """获取实体新闻时间线"""
    results = await news_storage.get_entity_news_timeline(
        entity_name, days=days, limit=limit,
    )
    return {
        "entity_name": entity_name,
        "items": [_serialize(r) for r in results],
        "total": len(results),
    }


# ──────────────────────────────────────────────
# Collect (Manual Trigger)
# ──────────────────────────────────────────────

class CollectRequest(BaseModel):
    keyword: str = Field("", description="搜索/采集关键词（可选，用于过滤采集结果）")
    priority: str = Field("high", description="采集优先级: high/normal/low")


async def _run_collection(keyword: str, priority: str) -> None:
    """后台执行新闻采集任务（不阻塞请求）"""
    from collectors.source_registry import source_registry
    from collectors.rss_collector import collect_rss
    from collectors.web_collector import collect_web
    from graphs.news_analysis_graph import get_news_graph

    logger.info("[Collect] Manual trigger | keyword=%r | priority=%s", keyword, priority)
    try:
        sources = source_registry.get_enabled(priority=priority)
        if not sources:
            # 回退：尝试所有已启用源
            sources = source_registry.get_enabled()
        if not sources:
            logger.warning("[Collect] No enabled sources found")
            return

        graph = get_news_graph()
        keyword_lower = keyword.strip().lower()

        for source in sources:
            try:
                if source.source_type == "rss":
                    articles = await collect_rss(source)
                elif source.source_type == "crawler":
                    articles = await collect_web(source)
                else:
                    continue

                if not articles:
                    continue

                # 关键词过滤（若提供）
                if keyword_lower:
                    articles = [
                        a for a in articles
                        if keyword_lower in (a.get("title", "") + " " + a.get("content", "")).lower()
                    ]
                    if not articles:
                        logger.info("[Collect] No matching articles for keyword in source=%s", source.id)
                        continue

                result = await graph.ainvoke({
                    "source_id": source.id,
                    "raw_articles": articles,
                    "cleaned_articles": [],
                    "unique_articles": [],
                    "classified_articles": [],
                    "entities": [],
                    "events": [],
                    "relations": [],
                    "impact_assessments": [],
                    "stored_article_ids": [],
                    "stored_event_ids": [],
                    "knowledge_agent_triggered": False,
                    "errors": [],
                })

                stored = len(result.get("stored_article_ids", []))
                logger.info("[Collect] Processed | source=%s | stored=%d", source.id, stored)

            except Exception as e:
                logger.error("[Collect] Source failed | %s | %s", source.id, e)

        logger.info("[Collect] Manual collection complete | keyword=%r", keyword)

    except Exception as e:
        logger.error("[Collect] Collection failed | %s", e)


@news_router.post("/collect")
async def trigger_collect(req: CollectRequest):
    """手动触发新闻采集任务（异步执行，立即返回）"""
    if req.priority not in ("high", "normal", "low"):
        raise HTTPException(status_code=400, detail="priority must be high/normal/low")

    asyncio.create_task(_run_collection(req.keyword, req.priority))
    return {
        "status": "accepted",
        "message": f"采集任务已启动（priority={req.priority}"
                   + (f", keyword={req.keyword}" if req.keyword else "")
                   + "）",
    }


# ──────────────────────────────────────────────
# Sources
# ──────────────────────────────────────────────

@news_router.get("/sources")
async def list_sources(
    enabled_only: bool = Query(True, description="仅返回启用的源"),
):
    """列出新闻源"""
    sources = await news_storage.list_sources(enabled_only=enabled_only)
    return {
        "sources": [_serialize(s) for s in sources],
        "total": len(sources),
    }
