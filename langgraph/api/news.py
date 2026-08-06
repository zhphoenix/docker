"""News API Router - 新闻智能管线 REST 端点

提供新闻搜索、文章详情、事件浏览、影响分析、时间线等接口。
数据来源: PostgreSQL news schema（通过 services/news_storage.py）。
"""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.news_storage import news_storage
from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)

news_router = APIRouter(prefix="/api/news", tags=["news"])


def _serialize(row: dict) -> dict:
    """序列化 UUID/时间字段为字符串"""
    result = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        elif isinstance(v, uuid.UUID):  # UUID
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


@news_router.get("/feed")
async def live_feed(
    hours: int = Query(24, ge=1, le=168, description="Breaking 时间窗口（小时）"),
    limit: int = Query(10, ge=1, le=50, description="每区条数"),
):
    """NIC-A1 Live Feed 分层视图

    - breaking：importance_score >= 0.8 且近 hours 小时发布（高影响 + 新鲜）
    - high_impact：importance_score >= 0.8 或 tier=1（分类器高重要度 / 永久价值）
    - hot_topics：近 hours 小时被提及文章数 Top N（热点实体）
    各查询独立 try/except，单故障不影响整体返回（对应区降级为空）。
    """
    result: dict = {"hours": hours, "breaking": [], "high_impact": [], "hot_topics": []}

    _ARTICLE_SELECT = (
        "SELECT a.id, a.title, a.summary, a.url, a.category, a.language, "
        "a.importance_score, a.tier, a.published_at, a.collected_at, a.status, "
        "s.name AS source_name "
        "FROM news.articles a LEFT JOIN news.sources s ON s.id = a.source_id "
    )

    # ── Breaking：高影响且新鲜（近 hours 小时） ──
    try:
        rows = await postgres_tool.query(
            _ARTICLE_SELECT
            + "WHERE a.importance_score >= 0.8 "
            "AND a.published_at >= NOW() - INTERVAL '1 hour' * $1 "
            "ORDER BY a.importance_score DESC, a.published_at DESC LIMIT $2",
            hours,
            limit,
        )
        result["breaking"] = [_serialize(r) for r in rows]
    except Exception:
        logger.warning("feed: breaking query failed, degraded")

    # ── 高影响：classifier importance 高 或 tier=1（永久价值） ──
    try:
        rows = await postgres_tool.query(
            _ARTICLE_SELECT
            + "WHERE a.importance_score >= 0.8 OR a.tier = 1 "
            "ORDER BY a.importance_score DESC, a.published_at DESC LIMIT $1",
            limit,
        )
        result["high_impact"] = [_serialize(r) for r in rows]
    except Exception:
        logger.exception("feed: high_impact query failed, degraded")
        result["high_impact"] = []

    # ── 热点实体：近 hours 小时实体提及文章数 Top N ──
    try:
        rows = await postgres_tool.query(
            "SELECT e.name, COUNT(DISTINCT e.article_id) AS mentions "
            "FROM news.entities e "
            "JOIN news.articles a ON a.id = e.article_id "
            "WHERE a.published_at >= NOW() - INTERVAL '1 hour' * $1 "
            "GROUP BY e.name ORDER BY mentions DESC LIMIT $2",
            hours,
            limit,
        )
        result["hot_topics"] = [
            {"name": r["name"], "mentions": int(r["mentions"] or 0)} for r in rows
        ]
    except Exception:
        logger.warning("feed: hot_topics query failed, degraded")

    result["summary"] = {
        "breaking": len(result["breaking"]),
        "high_impact": len(result["high_impact"]),
        "hot_topics": len(result["hot_topics"]),
    }
    return result


# ──────────────────────────────────────────────
# Intelligence Queue（NIC-A2）
# ──────────────────────────────────────────────

_IQ_JOIN = (
    "FROM news.articles a "
    "LEFT JOIN news.sources s ON s.id = a.source_id "
    "LEFT JOIN knowledge_packages kp "
    "  ON kp.source_type = 'news' "
    "  AND (kp.document_id = a.id OR kp.payload->'source'->>'url' = a.url) "
)


def _iq_state(package_status: str | None) -> str:
    """Package 状态 → 四态"""
    if package_status is None:
        return "waiting"
    if package_status == "draft":
        return "processing"
    if package_status in ("published", "consumed"):
        return "published"
    return "failed"


def _iq_error(processing_metadata) -> str | None:
    """从 processing_metadata 提取 Package 失败原因（jsonb 可能是 str）"""
    if not processing_metadata:
        return None
    meta = processing_metadata
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (ValueError, TypeError):
            return str(processing_metadata)[:300]
    publish = meta.get("publish") or {}
    if isinstance(publish, dict):
        return publish.get("last_error")
    return None


@news_router.get("/intelligence-queue")
async def intelligence_queue(
    days: int = Query(7, ge=1, le=90, description="统计时间范围（天）"),
    limit: int = Query(20, ge=1, le=100, description="明细条数"),
    state: str = Query("", description="按四态过滤: waiting/processing/published/failed"),
):
    """NIC-A2 Intelligence Queue 四态联查

    联查 news.articles → knowledge_packages（source_type='NEWS'）：
      - waiting：已采集但无对应 Package（未进入发布链路）
      - processing：Package 已生成但 status=draft（处理/待发布中）
      - published：Package 已发布或已消费（published/consumed）
      - failed：Package 发布/消费失败（含失败原因，可经 retry 重投）

    关联键：kp.document_id = a.id（DP-D2 升级后），
    兼容存量 Package（document_id 为 NULL）按 payload.source.url 匹配。
    各查询独立 try/except，单故障不影响整体返回（对应字段降级）。
    """
    # 防御：直接调用（非 FastAPI 注入）时 Query 默认值是对象而非字符串
    state = state if isinstance(state, str) else ""

    result: dict = {
        "days": days,
        "summary": {"waiting": 0, "processing": 0, "published": 0, "failed": 0},
        "items": [],
        "total": 0,
    }

    # ── 四态计数（单查询聚合，避免 JOIN 重复行膨胀） ──
    try:
        rows = await postgres_tool.query(
            "SELECT "
            "COUNT(*) FILTER (WHERE kp.id IS NULL) AS waiting, "
            "COUNT(*) FILTER (WHERE kp.status = 'draft') AS processing, "
            "COUNT(*) FILTER (WHERE kp.status IN ('published', 'consumed')) AS published, "
            "COUNT(*) FILTER (WHERE kp.status = 'failed') AS failed "
            + _IQ_JOIN
            + "WHERE a.published_at >= NOW() - INTERVAL '1 day' * $1",
            days,
        )
        if rows:
            for k in ("waiting", "processing", "published", "failed"):
                result["summary"][k] = int(rows[0].get(k) or 0)
    except Exception:
        logger.warning("intelligence-queue: summary query failed, degraded")

    # ── 明细（含四态派生与失败原因） ──
    try:
        rows = await postgres_tool.query(
            "SELECT a.id AS article_id, a.title, a.published_at, a.importance_score, "
            "s.name AS source_name, "
            "kp.id AS package_id, kp.status AS package_status, kp.retry_count, "
            "kp.processing_metadata "
            + _IQ_JOIN
            + "WHERE a.published_at >= NOW() - INTERVAL '1 day' * $1 "
            "ORDER BY a.published_at DESC LIMIT $2",
            days,
            limit,
        )
        items = []
        for r in rows:
            st = _iq_state(r.get("package_status"))
            if state and st != state:
                continue
            pub = r.get("published_at")
            items.append({
                "article_id": str(r["article_id"]),
                "title": r.get("title"),
                "source_name": r.get("source_name"),
                "published_at": pub.isoformat() if hasattr(pub, "isoformat") else pub,
                "importance_score": r.get("importance_score"),
                "package_id": str(r["package_id"]) if r.get("package_id") else None,
                "package_status": r.get("package_status"),
                "retry_count": r.get("retry_count") or 0,
                "state": st,
                "error": _iq_error(r.get("processing_metadata")) if st == "failed" else None,
            })
        result["items"] = items
        result["total"] = len(items)
    except Exception:
        logger.exception("intelligence-queue: items query failed, degraded")

    return result


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
    """聚合分析实体近期新闻影响

    DEPRECATED（NIC-B2）：Impact Monitor 已改为消费 KOC 分析结果
    （/api/knowledge/events/top-impact | core.events），不再触发实时重算。
    本端点保留供过渡期兼容。
    """
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
    from collectors.health_metrics import record_collect_run
    from graphs.news_analysis_graph import get_news_graph
    from monitoring.agent_center import invoke_tracked
    import time

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
            collect_start = time.monotonic()
            try:
                if source.source_type == "rss":
                    articles = await collect_rss(source)
                elif source.source_type == "crawler":
                    articles = await collect_web(source)
                else:
                    continue

                if not articles:
                    # 采集成功但无文章，仍记录指标
                    await record_collect_run(
                        source.id, source.name, True,
                        latency_ms=int((time.monotonic() - collect_start) * 1000),
                        articles_fetched=0, articles_stored=0,
                    )
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

                result = await invoke_tracked(
                    graph,
                    {
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
                    },
                    agent_id="news_intelligence",
                    question=f"manual collect source={source.id} keyword={keyword}",
                )

                stored = len(result.get("stored_article_ids", []))
                # 采集健康指标（Latency/Articles/Duplicates）
                await record_collect_run(
                    source.id, source.name, True,
                    latency_ms=int((time.monotonic() - collect_start) * 1000),
                    articles_fetched=len(articles),
                    articles_stored=stored,
                )
                logger.info("[Collect] Processed | source=%s | stored=%d", source.id, stored)

            except Exception as e:
                logger.error("[Collect] Source failed | %s | %s", source.id, e)
                # 采集失败指标（Errors）
                await record_collect_run(
                    source.id, source.name, False,
                    latency_ms=int((time.monotonic() - collect_start) * 1000),
                    articles_fetched=0, articles_stored=0,
                    error=str(e)[:500],
                )

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


@news_router.get("/sources/health")
async def get_sources_health(
    days: int = Query(30, ge=1, le=365, description="指标统计时间范围（天）"),
):
    """Source Health 面板数据

    按源展示 Latency/Errors/Articles/Duplicates 四项指标 + 覆盖率；
    异常源（最近失败或连续失败）红色标记。
    """
    result = await news_storage.get_source_health(days=days)
    result["sources"] = [_serialize(s) for s in result["sources"]]
    return result


class SourceEnabledRequest(BaseModel):
    enabled: bool = Field(..., description="是否启用该源")


@news_router.post("/sources/{source_id}/enabled")
async def set_source_enabled(source_id: str, req: SourceEnabledRequest):
    """启停一个新闻源（NIC-C3）

    UI 停用后下一采集周期不再采集该源（持久化到 news_sources.yaml）。
    """
    from collectors.source_registry import source_registry

    ok = source_registry.set_enabled(source_id, req.enabled)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found")
    return {
        "source_id": source_id,
        "enabled": req.enabled,
        "status": "ok",
        "message": "源已" + ("启用" if req.enabled else "停用"),
    }
