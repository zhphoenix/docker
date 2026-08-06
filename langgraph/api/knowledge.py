"""Knowledge API - 知识库管理（Collection 统计 + 知识图谱查询 + Hybrid 检索）"""

import asyncio
import json
import logging
import os
import uuid as uuid_mod
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from config.settings import settings
from tools.postgres import postgres_tool
from tools.llm import llm_tool
from config.policy_loader import get_policy
from storage.knowledge.postgres import knowledge_storage
from storage.knowledge.package import package_storage
from storage.knowledge.qdrant import knowledge_qdrant
from runtime.queue import task_queue
from pipelines.document_pipeline import doc_pipeline
from pipelines.acquire import (
    AcquireOrigin,
    AcquirePriority,
    AcquireTrigger,
    build_acquire_metadata,
    merge_acquire_into_metadata,
    sha256_hex,
)
from api.path_utils import normalize_path, get_volume_mapping_info
from services.knowledge_governance import governance
from services.knowledge_insights import compute_insights

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/collections")
async def list_collections():
    """知识库 Collection 列表

    合并 collections 表元数据 + chunks 实际计数 + Qdrant points 统计。
    Qdrant 不可达时 qdrant_points 字段为 null（降级）。
    """
    try:
        rows = await postgres_tool.query(
            """
            SELECT c.id, c.name, c.description, c.vector_size, c.distance, c.domain,
                   COUNT(ch.id) AS chunk_count,
                   COUNT(ch.qdrant_point_id) AS embedded_count
            FROM collections c
            LEFT JOIN chunks ch ON ch.collection_name = c.name
            GROUP BY c.id, c.name, c.description, c.vector_size, c.distance, c.domain
            ORDER BY c.name
            """
        )
    except Exception as e:
        logger.exception("Failed to query collections")
        raise HTTPException(status_code=500, detail=str(e))

    # Qdrant points 统计（独立降级，不影响主数据）
    # 并行查询避免 collection 数量多时串行等待拖慢接口
    qdrant_stats: dict[str, int] = {}
    try:
        async def _query_points(name: str) -> tuple[str, int | None]:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(
                        f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}/collections/{name}"
                    )
                    if resp.status_code == 200:
                        return name, resp.json().get("result", {}).get("points_count", 0)
            except Exception:
                pass  # 单个 collection 查询失败不影响其他
            return name, None

        results = await asyncio.gather(*[_query_points(r["name"]) for r in rows])
        qdrant_stats = {name: cnt for name, cnt in results if cnt is not None}
    except Exception:
        logger.warning("Qdrant unreachable, qdrant_points will be null")

    collections = []
    for r in rows:
        collections.append({
            "id": str(r["id"]),
            "name": r["name"],
            "description": r.get("description"),
            "vector_size": r["vector_size"],
            "distance": r.get("distance"),
            "domain": r.get("domain"),
            "chunk_count": r["chunk_count"],
            "embedded_count": r["embedded_count"],
            "qdrant_points": qdrant_stats.get(r["name"]),  # None 表示不可用
        })

    return {"collections": collections, "total": len(collections)}


@router.get("/stats")
async def knowledge_stats():
    """Knowledge Hub 聚合统计 - 一次返回 Dashboard 全部数据

    各子查询独立 try/catch，单故障不影响整体返回（对应字段降级为 0/空）。
    """
    stats: dict = {}

    # documents / chunks / embedded
    try:
        rows = await postgres_tool.query(
            "SELECT "
            "(SELECT COUNT(*) FROM documents) AS documents, "
            "(SELECT COUNT(*) FROM chunks) AS chunks, "
            "(SELECT COUNT(*) FROM chunks WHERE qdrant_point_id IS NOT NULL) AS embedded"
        )
        r = rows[0]
        stats["documents"] = r["documents"]
        stats["chunks"] = r["chunks"]
        stats["embedded"] = r["embedded"]
    except Exception:
        logger.warning("stats: documents/chunks query failed, degraded")
        stats["documents"] = stats["chunks"] = stats["embedded"] = 0

    # entities / facts（显式 schema 前缀，与现有代码一致）
    try:
        rows = await postgres_tool.query(
            "SELECT "
            "(SELECT COUNT(*) FROM core.entities WHERE status='active') AS entities, "
            "(SELECT COUNT(*) FROM core.facts) AS facts"
        )
        r = rows[0]
        stats["entities"] = r["entities"]
        stats["facts"] = r["facts"]
    except Exception:
        logger.warning("stats: entities/facts query failed, degraded")
        stats["entities"] = stats["facts"] = 0

    # 任务队列（按状态分组）
    try:
        rows = await postgres_tool.query(
            "SELECT status, COUNT(*) AS cnt FROM tasks GROUP BY status"
        )
        counts = {r["status"]: r["cnt"] for r in rows}
        stats["task_queue"] = {
            "pending": counts.get("pending", 0),
            "running": counts.get("running", 0),
            "done": counts.get("done", 0),
            "failed": counts.get("failed", 0),
        }
    except Exception:
        logger.warning("stats: task_queue query failed, degraded")
        stats["task_queue"] = {"pending": 0, "running": 0, "done": 0, "failed": 0}

    # 最近任务
    try:
        rows = await postgres_tool.query(
            "SELECT id, title, task_type, status, progress, created_at "
            "FROM tasks ORDER BY created_at DESC LIMIT 8"
        )
        stats["recent_tasks"] = [
            {
                "id": str(r["id"]),
                "title": r["title"],
                "task_type": r["task_type"],
                "status": r["status"],
                "progress": float(r["progress"] or 0),
                "created_at": str(r["created_at"]) if r.get("created_at") else None,
            }
            for r in rows
        ]
    except Exception:
        logger.warning("stats: recent_tasks query failed, degraded")
        stats["recent_tasks"] = []

    # 最近更新文档
    try:
        rows = await postgres_tool.query(
            "SELECT id, market, symbol, company, status, chunk_count, updated_at "
            "FROM documents ORDER BY updated_at DESC LIMIT 8"
        )
        stats["recent_updates"] = [
            {
                "id": str(r["id"]),
                "market": r["market"],
                "symbol": r["symbol"],
                "company": r.get("company"),
                "status": r["status"],
                "chunk_count": r["chunk_count"],
                "updated_at": str(r["updated_at"]) if r.get("updated_at") else None,
            }
            for r in rows
        ]
    except Exception:
        logger.warning("stats: recent_updates query failed, degraded")
        stats["recent_updates"] = []

    # 知识质量：chunk 平均长度 / embedding 覆盖率 / 实体置信度
    try:
        rows = await postgres_tool.query(
            "SELECT AVG(token_count) AS avg_token_count, "
            "COUNT(qdrant_point_id)::float / NULLIF(COUNT(*), 0) AS embed_coverage "
            "FROM chunks"
        )
        r = rows[0]
        avg_token = r["avg_token_count"]
        coverage = r["embed_coverage"]
        stats["quality"] = {
            "avg_chunk_length": round(float(avg_token), 1) if avg_token is not None else None,
            "embedding_coverage": round(float(coverage) * 100, 1) if coverage is not None else None,
            "entity_confidence": None,
        }
        # 实体置信度（独立降级，失败不影响其他质量指标）
        try:
            erows = await postgres_tool.query(
                "SELECT AVG(confidence) AS avg_confidence FROM core.entities WHERE status='active'"
            )
            ec = erows[0]["avg_confidence"]
            stats["quality"]["entity_confidence"] = round(float(ec) * 100, 1) if ec is not None else None
        except Exception:
            logger.warning("stats: entity_confidence query failed, degraded")
    except Exception:
        logger.warning("stats: quality query failed, degraded")
        stats["quality"] = {
            "avg_chunk_length": None,
            "embedding_coverage": None,
            "entity_confidence": None,
        }

    # Collections 概览（复用 list_collections 逻辑）
    try:
        coll_data = await list_collections()
        stats["collections"] = coll_data["collections"]
    except Exception:
        logger.warning("stats: collections query failed, degraded")
        stats["collections"] = []

    return stats


# ============================================================
# KOC-D1 Analytics（Growth/Coverage/Usage/Quality/Freshness + 趋势）
# ============================================================

_TREND_SOURCES = {
    "entities": ("core.entities", "status='active'"),
    "facts": ("core.facts", "TRUE"),
    "events": ("core.events", "TRUE"),
}


def _iso(value):
    """date/datetime → ISO 字符串（None 原样）"""
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


@router.get("/analytics")
async def knowledge_analytics(range_days: int = Query(7, ge=7, le=90)):
    """KOC-D1 Analytics：Knowledge Growth/Coverage/Usage/Quality/Freshness + 7/30/90 天趋势

    五维（设计 §10）+ 趋势（7/30/90 天每日新增）：
      - growth：entities/relations/facts/events 总数（communities 未启用固定 0）
      - coverage：entity_fact_coverage（有事实的实体占比）/ entity_types / embedding_coverage
      - usage：agent_runs 运行量（近 range 天 + 今日 + 消费侧 Agent 排行）
      - quality：实体置信度 / conflicts open / facts verified
      - freshness：最后入库时间 / expired facts / 区间新增
      - trends：entities/facts/events 按天新增序列
    各子查询独立 try/except，单故障不影响整体返回。
    """
    result: dict = {"range_days": range_days}

    # ── Growth：四类资产总数 ──
    try:
        rows = await postgres_tool.query(
            "SELECT "
            "(SELECT COUNT(*) FROM core.entities WHERE status='active') AS entities, "
            "(SELECT COUNT(*) FROM core.relations WHERE status='active') AS relations, "
            "(SELECT COUNT(*) FROM core.facts) AS facts, "
            "(SELECT COUNT(*) FROM core.events) AS events"
        )
        r = rows[0]
        result["growth"] = {
            "entities": int(r["entities"] or 0),
            "relations": int(r["relations"] or 0),
            "facts": int(r["facts"] or 0),
            "events": int(r["events"] or 0),
            "communities": 0,  # §15 指标，当前未启用社区发现
        }
    except Exception:
        logger.warning("analytics: growth query failed, degraded")
        result["growth"] = {"entities": 0, "relations": 0, "facts": 0, "events": 0, "communities": 0}

    # ── Coverage：实体-事实覆盖 / 类型覆盖 / 向量覆盖 ──
    try:
        rows = await postgres_tool.query(
            "SELECT "
            "(SELECT COUNT(*) FROM core.entities WHERE status='active') AS entities, "
            "(SELECT COUNT(DISTINCT subject_entity) FROM core.facts) AS entities_with_facts, "
            "(SELECT COUNT(*) FROM taxonomy.entity_types) AS entity_types"
        )
        r = rows[0]
        entities = int(r["entities"] or 0)
        with_facts = int(r["entities_with_facts"] or 0)
        entity_fact_coverage = round(with_facts / entities * 100, 1) if entities else 0.0
        try:
            erows = await postgres_tool.query(
                "SELECT COUNT(qdrant_point_id)::float / NULLIF(COUNT(*), 0) AS embed_coverage FROM chunks"
            )
            ec = erows[0]["embed_coverage"]
            embedding_coverage = round(float(ec) * 100, 1) if ec is not None else None
        except Exception:
            logger.warning("analytics: embedding_coverage query failed, degraded")
            embedding_coverage = None
        result["coverage"] = {
            "knowledge_coverage": entity_fact_coverage,
            "entity_fact_coverage": entity_fact_coverage,
            "entity_types": int(r["entity_types"] or 0),
            "embedding_coverage": embedding_coverage,
        }
    except Exception:
        logger.warning("analytics: coverage query failed, degraded")
        result["coverage"] = {
            "knowledge_coverage": 0.0,
            "entity_fact_coverage": 0.0,
            "entity_types": 0,
            "embedding_coverage": None,
        }

    # ── Usage：Agent 运行量（近 range 天 + 今日 + 排行） ──
    try:
        rows = await postgres_tool.query(
            "SELECT agent_id, "
            "COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE) AS today, "
            "COUNT(*) AS total "
            "FROM agent_runs "
            f"WHERE created_at >= CURRENT_DATE - INTERVAL '{range_days} days' "
            "GROUP BY agent_id ORDER BY total DESC LIMIT 10"
        )
        top_agents = [
            {"agent_id": r["agent_id"], "today": int(r["today"] or 0), "total": int(r["total"] or 0)}
            for r in rows
        ]
        result["usage"] = {
            "runs": sum(x["total"] for x in top_agents),
            "runs_today": sum(x["today"] for x in top_agents),
            "top_agents": top_agents,
        }
    except Exception:
        logger.warning("analytics: usage query failed, degraded")
        result["usage"] = {"runs": 0, "runs_today": 0, "top_agents": []}

    # ── Quality：置信度 / 治理冲突 / 事实核验 ──
    try:
        rows = await postgres_tool.query(
            "SELECT "
            "(SELECT AVG(confidence) FROM core.entities WHERE status='active') AS entity_conf, "
            "(SELECT COUNT(*) FROM core.knowledge_conflicts WHERE status='open') AS conflicts_open, "
            "(SELECT COUNT(*) FROM core.facts WHERE verification_status='verified') AS facts_verified, "
            "(SELECT COUNT(*) FROM core.facts) AS facts_total"
        )
        r = rows[0]
        ec = r["entity_conf"]
        result["quality"] = {
            "entity_confidence": round(float(ec) * 100, 1) if ec is not None else None,
            "conflicts_open": int(r["conflicts_open"] or 0),
            "facts_verified": int(r["facts_verified"] or 0),
            "facts_total": int(r["facts_total"] or 0),
        }
    except Exception:
        logger.warning("analytics: quality query failed, degraded")
        result["quality"] = {"entity_confidence": None, "conflicts_open": 0, "facts_verified": 0, "facts_total": 0}

    # ── Freshness：最后更新 / 过期事实 / 区间新增 ──
    try:
        rows = await postgres_tool.query(
            "SELECT "
            "(SELECT MAX(updated_at) FROM core.entities) AS last_entity_at, "
            "(SELECT MAX(created_at) FROM core.facts) AS last_fact_at, "
            "(SELECT MAX(created_at) FROM core.events) AS last_event_at, "
            "(SELECT COUNT(*) FROM core.facts WHERE lifecycle_status IN ('expired','archived')) AS facts_expired, "
            f"(SELECT COUNT(*) FROM core.entities WHERE status='active' AND created_at >= CURRENT_DATE - INTERVAL '{range_days} days') AS new_entities, "
            f"(SELECT COUNT(*) FROM core.facts WHERE created_at >= CURRENT_DATE - INTERVAL '{range_days} days') AS new_facts, "
            f"(SELECT COUNT(*) FROM core.events WHERE created_at >= CURRENT_DATE - INTERVAL '{range_days} days') AS new_events"
        )
        r = rows[0]
        result["freshness"] = {
            "last_entity_at": _iso(r.get("last_entity_at")),
            "last_fact_at": _iso(r.get("last_fact_at")),
            "last_event_at": _iso(r.get("last_event_at")),
            "facts_expired": int(r["facts_expired"] or 0),
            "new_entities": int(r["new_entities"] or 0),
            "new_facts": int(r["new_facts"] or 0),
            "new_events": int(r["new_events"] or 0),
        }
    except Exception:
        logger.warning("analytics: freshness query failed, degraded")
        result["freshness"] = {
            "last_entity_at": None, "last_fact_at": None, "last_event_at": None,
            "facts_expired": 0, "new_entities": 0, "new_facts": 0, "new_events": 0,
        }

    # ── Trends：按天新增序列 ──
    trends: dict = {"range_days": range_days, "entities": [], "facts": [], "events": []}
    for key, (table, cond) in _TREND_SOURCES.items():
        try:
            rows = await postgres_tool.query(
                f"SELECT created_at::date AS d, COUNT(*) AS cnt FROM {table} "
                f"WHERE {cond} AND created_at >= CURRENT_DATE - INTERVAL '{range_days} days' "
                "GROUP BY d ORDER BY d"
            )
            trends[key] = [
                {"date": _iso(r["d"]), "count": int(r["cnt"] or 0)} for r in rows
            ]
        except Exception:
            logger.warning(f"analytics: trend {key} query failed, degraded")
    result["trends"] = trends

    return result


# ============================================================
# 知识图谱查询 API
# ============================================================


@router.get("/insights")
async def knowledge_insights(
    range_days: int = Query(7, ge=1, le=90),
    limit: int = Query(10, ge=1, le=50),
):
    """KOC-D2 Insights：基于近期入库统计的运营洞察（设计 §7）

    - hot_topics：近期新增实体名关键词共现 Top N（NIC-D1 Trend Discovery 数据源）
    - trending_companies / trending_industries：按 source_count 排序
    - emerging_concepts：Concept/Technology 近期新增按置信度排序
    - top_growing：近窗口新增实体按类型分组
    - top_mentioned：事实关联公司提及次数（数据少时降级为 source_count 排行）
    - heatmap：近 7 天每日新增 entities/facts
    各子查询独立 try/except，单故障不影响整体返回。
    """
    return await compute_insights(range_days=range_days, limit=limit)


def _json_or_empty(value) -> list:
    """jsonb 列（asyncpg 无 codec 时返回 str）统一解析为 list"""
    if value is None or isinstance(value, list):
        return value or []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


@router.get("/events/monitor")
async def event_monitor(
    event_type: str = Query("", description="事件类型过滤"),
    company: str = Query("", description="受影响公司过滤（entities 数组包含）"),
    days: int = Query(30, ge=1, le=365, description="窗口（天）"),
    limit: int = Query(30, ge=1, le=100, description="事件列表条数"),
):
    """NIC-B1 Event Monitor：读 core.events（KOC 侧聚合端点）

    - today_new：今日新增事件数（event_date = CURRENT_DATE）
    - window_total：窗口内事件总数
    - avg_score / direction 分布：窗口内影响评分均值与方向分布
    - affected_companies / company_mentions：Top 受影响公司（entities 展开）
    - events：事件列表（含影响公司数、impact、confidence），与 core.events 一致
    各子查询独立 try/except，单故障不影响整体返回（对应字段降级）。
    """
    # 防御：直接调用（非 FastAPI 注入）时 Query 默认值是对象而非字符串
    event_type = event_type if isinstance(event_type, str) else ""
    company = company if isinstance(company, str) else ""

    result: dict = {
        "source": "core.events",
        "days": days,
        "today_new": 0,
        "window_total": 0,
        "avg_score": None,
        "direction": {"positive": 0, "negative": 0, "neutral": 0},
        "affected_companies": [],
        "company_mentions": [],
        "events": [],
        "total": 0,
    }

    # ── 今日新增 + 窗口统计（单查询） ──
    try:
        rows = await postgres_tool.query(
            "SELECT "
            "COUNT(*) FILTER (WHERE e.event_date = CURRENT_DATE) AS today_new, "
            "COUNT(*) FILTER (WHERE e.event_date >= CURRENT_DATE - INTERVAL '1 day' * $1) AS window_total, "
            "AVG((e.impact->>'score')::float) FILTER "
            "  (WHERE (e.impact->>'score') ~ '^[0-9]+(\\.[0-9]+)?$') AS avg_score, "
            "COUNT(*) FILTER (WHERE e.impact->>'direction' = 'positive') AS positive_count, "
            "COUNT(*) FILTER (WHERE e.impact->>'direction' = 'negative') AS negative_count, "
            "COUNT(*) FILTER (WHERE e.impact->>'direction' = 'neutral') AS neutral_count "
            "FROM core.events e ",
            days,
        )
        if rows:
            row = rows[0]
            result["today_new"] = int(row.get("today_new") or 0)
            result["window_total"] = int(row.get("window_total") or 0)
            result["avg_score"] = round(float(row["avg_score"]), 3) if row.get("avg_score") is not None else None
            result["direction"] = {
                "positive": int(row.get("positive_count") or 0),
                "negative": int(row.get("negative_count") or 0),
                "neutral": int(row.get("neutral_count") or 0),
            }
    except Exception:
        logger.warning("event-monitor: stats query failed, degraded")

    # ── 受影响公司聚合（entities 数组展开） ──
    try:
        rows = await postgres_tool.query(
            "SELECT c.name AS company, COUNT(*) AS event_count "
            "FROM core.events e, jsonb_array_elements_text(e.entities) AS c(name) "
            "WHERE e.event_date >= CURRENT_DATE - INTERVAL '1 day' * $1 "
            "GROUP BY c.name ORDER BY event_count DESC, c.name LIMIT 10",
            days,
        )
        result["company_mentions"] = [
            {"company": r["company"], "event_count": int(r["event_count"] or 0)}
            for r in rows
        ]
    except Exception:
        logger.warning("event-monitor: company mentions query failed, degraded")

    # ── 事件列表（窗口内，与 core.events 一致） ──
    try:
        sql = (
            "SELECT e.id, e.event_type, e.title, e.description, e.event_date, "
            "e.entities, e.impact, e.confidence, e.created_at "
            "FROM core.events e "
            "WHERE e.event_date >= CURRENT_DATE - INTERVAL '1 day' * $1 "
        )
        params: list = [days]
        if event_type:
            sql += "AND e.event_type = $" + str(len(params) + 1) + " "
            params.append(event_type)
        if company:
            sql += (
                "AND EXISTS (SELECT 1 FROM jsonb_array_elements_text(e.entities) c(name) "
                "WHERE c.name = $" + str(len(params) + 1) + ") "
            )
            params.append(company)
        sql += "ORDER BY e.event_date DESC NULLS LAST, e.created_at DESC LIMIT $" + str(len(params) + 1)
        params.append(limit)
        rows = await postgres_tool.query(sql, *params)
        items = []
        for r in rows:
            entities = _json_or_empty(r.get("entities"))
            impact_raw = r.get("impact")
            impact = impact_raw
            if isinstance(impact_raw, str):
                try:
                    parsed = json.loads(impact_raw)
                    impact = parsed if isinstance(parsed, dict) else {}
                except (ValueError, TypeError):
                    impact = {}
            elif not isinstance(impact_raw, dict):
                impact = {}
            event_date = r.get("event_date")
            created_at = r.get("created_at")
            items.append({
                "id": str(r["id"]),
                "event_type": r.get("event_type"),
                "title": r.get("title"),
                "description": r.get("description"),
                "event_date": event_date.isoformat() if hasattr(event_date, "isoformat") else event_date,
                "entities": entities if isinstance(entities, list) else [],
                "company_count": len(entities) if isinstance(entities, list) else 0,
                "impact": impact,
                "confidence": r.get("confidence"),
                "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
            })
        result["events"] = items
        result["total"] = len(items)
    except Exception:
        logger.exception("event-monitor: events query failed, degraded")

    return result


@router.get("/events/top-impact")
async def top_impact_events(
    company: str = Query("", description="受影响公司过滤"),
    days: int = Query(30, ge=1, le=365, description="窗口（天）"),
    limit: int = Query(10, ge=1, le=50, description="返回条数"),
):
    """NIC-B2 Top Impact Events：读 core.events 按影响评分排行（KOC 分析结果）

    - 星级 = round(score * 5)（影响评分的 0-5 星映射）
    - 数据来自 KOC 知识图谱（core.events），不触发 LLM 实时重算
    - 支持按受影响公司过滤
    """
    company = company if isinstance(company, str) else ""

    result: dict = {
        "source": "core.events",
        "days": days,
        "items": [],
        "total": 0,
    }
    try:
        sql = (
            "SELECT e.id, e.event_type, e.title, e.description, e.event_date, "
            "e.entities, e.impact, e.confidence "
            "FROM core.events e "
            "WHERE e.event_date >= CURRENT_DATE - INTERVAL '1 day' * $1 "
        )
        params: list = [days]
        if company:
            sql += (
                "AND EXISTS (SELECT 1 FROM jsonb_array_elements_text(e.entities) c(name) "
                "WHERE c.name = $" + str(len(params) + 1) + ") "
            )
            params.append(company)
        sql += (
            "ORDER BY (NULLIF(e.impact->>'score', '')::float) DESC NULLS LAST "
            "LIMIT $" + str(len(params) + 1)
        )
        params.append(limit)
        rows = await postgres_tool.query(sql, *params)
        items = []
        for r in rows:
            entities = _json_or_empty(r.get("entities"))
            impact_raw = r.get("impact")
            impact = impact_raw
            if isinstance(impact_raw, str):
                try:
                    parsed = json.loads(impact_raw)
                    impact = parsed if isinstance(parsed, dict) else {}
                except (ValueError, TypeError):
                    impact = {}
            elif not isinstance(impact_raw, dict):
                impact = {}
            score = impact.get("score") if isinstance(impact, dict) else None
            score_f = float(score) if score is not None else None
            event_date = r.get("event_date")
            items.append({
                "id": str(r["id"]),
                "event_type": r.get("event_type"),
                "title": r.get("title"),
                "description": r.get("description"),
                "event_date": event_date.isoformat() if hasattr(event_date, "isoformat") else event_date,
                "companies": entities if isinstance(entities, list) else [],
                "company_count": len(entities) if isinstance(entities, list) else 0,
                "impact": impact,
                "score": score_f,
                "stars": (
                    max(0, min(5, round(score_f * 5)))
                    if score_f is not None else 0
                ),
                "confidence": r.get("confidence"),
            })
        result["items"] = items
        result["total"] = len(items)
    except Exception:
        logger.exception("top-impact: query failed, degraded")

    return result


@router.get("/events/timeline")
async def event_timeline(
    entity_name: str = Query("", description="受影响实体/公司过滤"),
    days: int = Query(90, ge=1, le=365, description="窗口（天）"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
):
    """NIC-B3 事件时间线：读 core.events（Timeline 与 Event Monitor 同源）

    - 按 event_date 升序排列，支持按受影响实体/公司过滤（entities 数组包含）
    - 数据来自 KOC 知识图谱（core.events），新闻侧不再单独出时间线
    """
    entity_name = entity_name if isinstance(entity_name, str) else ""

    result: dict = {
        "source": "core.events",
        "entity_name": entity_name,
        "days": days,
        "items": [],
        "total": 0,
    }
    try:
        sql = (
            "SELECT e.id, e.event_type, e.title, e.description, e.event_date, "
            "e.entities, e.impact, e.confidence "
            "FROM core.events e "
            "WHERE e.event_date >= CURRENT_DATE - INTERVAL '1 day' * $1 "
        )
        params: list = [days]
        if entity_name:
            sql += (
                "AND EXISTS (SELECT 1 FROM jsonb_array_elements_text(e.entities) c(name) "
                "WHERE c.name = $" + str(len(params) + 1) + ") "
            )
            params.append(entity_name)
        sql += (
            "ORDER BY e.event_date ASC NULLS LAST "
            "LIMIT $" + str(len(params) + 1)
        )
        params.append(limit)
        rows = await postgres_tool.query(sql, *params)
        items = []
        for r in rows:
            entities = _json_or_empty(r.get("entities"))
            impact_raw = r.get("impact")
            impact = impact_raw
            if isinstance(impact_raw, str):
                try:
                    parsed = json.loads(impact_raw)
                    impact = parsed if isinstance(parsed, dict) else {}
                except (ValueError, TypeError):
                    impact = {}
            elif not isinstance(impact_raw, dict):
                impact = {}
            score = impact.get("score") if isinstance(impact, dict) else None
            score_f = float(score) if score is not None else None
            event_date = r.get("event_date")
            items.append({
                "id": str(r["id"]),
                "event_type": r.get("event_type"),
                "title": r.get("title"),
                "description": r.get("description"),
                "event_date": event_date.isoformat() if hasattr(event_date, "isoformat") else event_date,
                "companies": entities if isinstance(entities, list) else [],
                "company_count": len(entities) if isinstance(entities, list) else 0,
                "impact": impact,
                "score": score_f,
                "stars": (
                    max(0, min(5, round(score_f * 5)))
                    if score_f is not None else 0
                ),
                "confidence": r.get("confidence"),
            })
        result["items"] = items
        result["total"] = len(items)
    except Exception:
        logger.exception("event-timeline: query failed, degraded")

    return result


@router.get("/entities/types")
async def list_entity_types():
    """实体类型统计（Knowledge Explorer 类型统计卡）"""
    try:
        rows = await knowledge_storage.count_entities_by_type()
        return {
            "types": [
                {"entity_type": r["entity_type"], "count": int(r["count"] or 0)}
                for r in rows
            ],
            "total": len(rows),
        }
    except Exception as e:
        logger.exception("Failed to count entity types")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entities")
async def list_entities(
    name: str = Query("", description="实体名称搜索"),
    entity_type: str = Query("", description="实体类型过滤"),
    min_confidence: float | None = Query(None, ge=0, le=1, description="最低置信度"),
    min_source_count: int | None = Query(None, ge=0, description="最小来源数"),
    limit: int = Query(20, ge=1, le=100),
):
    """查询实体（by name/type/confidence/source_count，KOC-C1 快速筛选）"""
    try:
        entities = await knowledge_storage.search_entities(
            name=name,
            entity_type=entity_type,
            limit=limit,
            min_confidence=min_confidence,
            min_source_count=min_source_count,
        )
        return {
            "entities": [
                {
                    "id": str(e["id"]),
                    "name": e["name"],
                    "entity_type": e["entity_type"],
                    "description": e.get("description"),
                    "canonical_name": e.get("canonical_name"),
                    "confidence": e.get("confidence"),
                    "source_count": e.get("source_count", 0),
                }
                for e in entities
            ],
            "total": len(entities),
        }
    except Exception as e:
        logger.exception("Failed to query entities")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entities/{entity_id}")
async def get_entity_detail(entity_id: str):
    """实体详情（含 aliases、properties）"""
    try:
        import uuid as _uuid
        rows = await postgres_tool.query(
            """
            SELECT id, name, entity_type, description, canonical_name,
                   confidence, source_count, aliases, properties,
                   status, created_at, updated_at
            FROM core.entities
            WHERE id = $1 AND status = 'active'
            """,
            _uuid.UUID(entity_id),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Entity not found")
        e = rows[0]
        return {
            "id": str(e["id"]),
            "name": e["name"],
            "entity_type": e["entity_type"],
            "description": e.get("description"),
            "canonical_name": e.get("canonical_name"),
            "confidence": e.get("confidence"),
            "source_count": e.get("source_count", 0),
            "aliases": e.get("aliases") or [],
            "properties": e.get("properties") or {},
            "created_at": str(e["created_at"]) if e.get("created_at") else None,
            "updated_at": str(e["updated_at"]) if e.get("updated_at") else None,
        }
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entity ID format")
    except Exception as e:
        logger.exception("Failed to get entity detail")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entities/{entity_id}/neighbors")
async def get_entity_neighbors(
    entity_id: str,
    depth: int = Query(1, ge=1, le=2, description="遍历深度（最大 2）"),
):
    """图遍历：获取实体的关联实体"""
    try:
        neighbors = await knowledge_storage.get_entity_neighbors(entity_id, depth=depth)
        return {
            "entity_id": entity_id,
            "depth": depth,
            "neighbors": [
                {
                    "source_entity": str(n["source_entity"]),
                    "target_entity": str(n["target_entity"]),
                    "source_name": n.get("source_name"),
                    "target_name": n.get("target_name"),
                    "relation_type": n["relation_type"],
                    "depth": n["depth"],
                }
                for n in neighbors
            ],
            "total": len(neighbors),
        }
    except Exception as e:
        logger.exception("Failed to get neighbors")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entities/{entity_id}/timeline")
async def get_entity_timeline(entity_id: str):
    """KOC-D3 Evolution：实体时间线（版本历史 + 事实时间 + 相关事件）

    - versions：audit.knowledge_versions（object_type='entity'）版本链，展示名称/属性演变
    - facts：core.facts（subject_entity 关联）含 time_start/end 与入库时间
    - events：core.events（entities 数组包含实体 id 或名称）
    各子查询独立 try/except，单故障不影响整体返回。
    """
    import uuid as _uuid

    # 先校验实体存在
    try:
        rows = await postgres_tool.query(
            "SELECT id FROM core.entities WHERE id = $1 AND status = 'active'",
            _uuid.UUID(entity_id),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Entity not found")
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entity ID format")
    except Exception as e:
        logger.exception("Failed to check entity")
        raise HTTPException(status_code=500, detail=str(e))

    result: dict = {"entity_id": entity_id, "versions": [], "facts": [], "events": []}

    def _parse_json(value):
        """asyncpg jsonb 可能返回 str，统一解析为对象"""
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return {"raw": value}
        return value

    # ── 版本历史 ──
    try:
        vrows = await postgres_tool.query(
            "SELECT version, content, created_by, created_at "
            "FROM audit.knowledge_versions "
            "WHERE object_type='entity' AND object_id = $1 ORDER BY version",
            _uuid.UUID(entity_id),
        )
        result["versions"] = [
            {
                "version": int(r["version"] or 1),
                "created_by": r.get("created_by") or "system",
                "created_at": str(r["created_at"]) if r.get("created_at") else None,
                "content": _parse_json(r.get("content")) or {},
            }
            for r in vrows
        ]
    except Exception:
        logger.warning("timeline: versions query failed, degraded")

    # ── 事实（含时间窗口） ──
    try:
        frows = await postgres_tool.query(
            "SELECT id, predicate, object_value, unit, time_start, time_end, "
            "confidence, verification_status, created_at "
            "FROM core.facts WHERE subject_entity = $1 ORDER BY time_start NULLS LAST, created_at",
            _uuid.UUID(entity_id),
        )
        result["facts"] = [
            {
                "id": str(r["id"]),
                "predicate": r["predicate"],
                "object_value": _parse_json(r.get("object_value")),
                "unit": r.get("unit"),
                "time_start": _iso(r.get("time_start")),
                "time_end": _iso(r.get("time_end")),
                "confidence": r.get("confidence"),
                "verification_status": r.get("verification_status"),
                "created_at": _iso(r.get("created_at")),
            }
            for r in frows
        ]
    except Exception:
        logger.warning("timeline: facts query failed, degraded")

    # ── 相关事件（entities 数组含实体 id 或名称） ──
    try:
        erows = await postgres_tool.query(
            "SELECT id, event_type, title, description, event_date, created_at "
            "FROM core.events "
            "WHERE entities::text LIKE $1 OR entities::text LIKE $2 "
            "ORDER BY event_date NULLS LAST, created_at",
            f"%{entity_id}%",
            f"%{entity_id.split('-')[0]}%",
        )
        result["events"] = [
            {
                "id": str(r["id"]),
                "event_type": r["event_type"],
                "title": r["title"],
                "description": r.get("description"),
                "event_date": _iso(r.get("event_date")),
                "created_at": _iso(r.get("created_at")),
            }
            for r in erows
        ]
    except Exception:
        logger.warning("timeline: events query failed, degraded")

    return result


@router.get("/facts")
async def list_facts(
    subject: str = Query("", description="主体实体 ID"),
    predicate: str = Query("", description="谓词过滤"),
    limit: int = Query(50, ge=1, le=200),
):
    """查询事实（by subject/predicate）"""
    if not subject:
        raise HTTPException(status_code=400, detail="subject parameter required")

    try:
        facts = await knowledge_storage.get_facts_by_subject(
            subject_entity=subject,
            predicate=predicate or None,
            limit=limit,
        )
        return {
            "facts": [
                {
                    "id": str(f["id"]),
                    "predicate": f["predicate"],
                    "object_value": f["object_value"],
                    "unit": f.get("unit"),
                    "time_start": str(f["time_start"]) if f.get("time_start") else None,
                    "time_end": str(f["time_end"]) if f.get("time_end") else None,
                    "confidence": f.get("confidence"),
                    "verification_status": f.get("verification_status"),
                }
                for f in facts
            ],
            "total": len(facts),
        }
    except Exception as e:
        logger.exception("Failed to query facts")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Hybrid 检索 API
# ============================================================


class HybridSearchRequest(BaseModel):
    query: str
    entity_name: str = ""
    limit: int = 10


async def _fulltext_search(query: str, limit: int) -> dict:
    """全文检索通道（Postgres ILIKE）：实体 / 文档 / 事件

    Returns:
        {"entities": [...], "documents": [...], "events": [...]}
    """
    pattern = f"%{query.strip()}%"
    results: dict = {"entities": [], "documents": [], "events": []}

    # 实体全文（name / canonical_name）
    try:
        rows = await postgres_tool.query(
            """
            SELECT id, name, entity_type, description, confidence, source_count
            FROM core.entities
            WHERE status = 'active'
              AND (name ILIKE $1 OR canonical_name ILIKE $1)
            ORDER BY source_count DESC, confidence DESC NULLS LAST
            LIMIT $2
            """,
            pattern, limit,
        )
        results["entities"] = [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "entity_type": r["entity_type"],
                "description": r.get("description"),
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("fulltext entities failed: %s", e)

    # 文档全文（title）
    try:
        rows = await postgres_tool.query(
            """
            SELECT id, title, document_type, source
            FROM document.documents
            WHERE title ILIKE $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            pattern, limit,
        )
        results["documents"] = [
            {
                "id": str(r["id"]),
                "title": r.get("title"),
                "document_type": r.get("document_type"),
                "source": r.get("source"),
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("fulltext documents failed: %s", e)

    # 事件全文（title / description）
    try:
        rows = await postgres_tool.query(
            """
            SELECT id, title, event_type, event_date, description
            FROM core.events
            WHERE title ILIKE $1 OR description ILIKE $1
            ORDER BY event_date DESC NULLS LAST, created_at DESC
            LIMIT $2
            """,
            pattern, limit,
        )
        results["events"] = [
            {
                "id": str(r["id"]),
                "title": r["title"],
                "event_type": r.get("event_type"),
                "event_date": str(r["event_date"]) if r.get("event_date") else None,
                "description": r.get("description"),
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("fulltext events failed: %s", e)

    return results


@router.post("/search")
async def hybrid_search(request: HybridSearchRequest):
    """统一搜索入口（KOC-C2）：向量 + 全文 + 图 三通道混合检索

    一次查询返回 Entity / Fact / Event / Document 混合结果，
    每项标注来源通道（vector / fulltext / graph）。
    """
    try:
        # 1. 图查询（结构化，entity_name 可选）
        graph_results = []
        entity_ids = []

        if request.entity_name:
            entities = await knowledge_storage.find_entity_by_name(
                request.entity_name, limit=1
            )
            if entities:
                entity_id = str(entities[0]["id"])
                entity_ids = [entity_id]
                graph_results = await knowledge_storage.get_entity_neighbors(
                    entity_id, depth=2
                )

        # 2. 向量检索（语义）
        vector_results = await knowledge_qdrant.hybrid_search(
            query=request.query,
            entity_ids=entity_ids if entity_ids else None,
            limit=request.limit,
        )

        # 3. 全文检索（实体/文档/事件）
        fulltext = await _fulltext_search(request.query, request.limit)

        # 4. 合并统一结果（去重，vector 优先，标注来源通道）
        merged_entities: dict[str, dict] = {}
        for ent in vector_results.get("entities", []):
            payload = ent.get("payload", {}) or {}
            merged_entities[str(ent["id"])] = {
                "id": str(ent["id"]),
                "name": payload.get("name", ""),
                "entity_type": payload.get("entity_type", ""),
                "description": payload.get("description"),
                "score": ent.get("score"),
                "source_channels": ["vector"],
            }
        for ent in fulltext.get("entities", []):
            eid = ent["id"]
            if eid in merged_entities:
                merged_entities[eid]["source_channels"] = sorted(
                    set(merged_entities[eid]["source_channels"]) | {"fulltext"}
                )
                if not merged_entities[eid].get("description"):
                    merged_entities[eid]["description"] = ent.get("description")
            else:
                merged_entities[eid] = {
                    "id": eid,
                    "name": ent["name"],
                    "entity_type": ent.get("entity_type", ""),
                    "description": ent.get("description"),
                    "score": None,
                    "source_channels": ["fulltext"],
                }

        # 5. 统一响应（保留 graph_results / vector_results 兼容旧前端）
        return {
            "query": request.query,
            "source_channels": {
                "vector": len(vector_results.get("entities", [])) > 0 or len(vector_results.get("facts", [])) > 0,
                "fulltext": any(
                    len(fulltext.get(k, [])) > 0 for k in ("entities", "documents", "events")
                ),
                "graph": len(graph_results) > 0,
            },
            "results": {
                "entities": list(merged_entities.values()),
                "facts": [
                    {
                        "id": str(f["id"]),
                        "subject_name": (f.get("payload") or {}).get("subject_name", ""),
                        "predicate": (f.get("payload") or {}).get("predicate", ""),
                        "object_value": (f.get("payload") or {}).get("object_value", ""),
                        "time_start": (f.get("payload") or {}).get("time_start"),
                        "score": f.get("score"),
                        "source_channels": ["vector"],
                    }
                    for f in vector_results.get("facts", [])
                ],
                "events": [
                    {**e, "source_channels": ["fulltext"]}
                    for e in fulltext.get("events", [])
                ],
                "documents": [
                    {**d, "source_channels": ["fulltext"]}
                    for d in fulltext.get("documents", [])
                ],
            },
            "graph_results": [
                {
                    "source_entity": str(r["source_entity"]),
                    "target_entity": str(r["target_entity"]),
                    "source_name": r.get("source_name"),
                    "target_name": r.get("target_name"),
                    "relation_type": r["relation_type"],
                    "depth": r["depth"],
                }
                for r in graph_results
            ],
            "vector_results": vector_results,
            "entity_ids_used": entity_ids,
        }
    except Exception as e:
        logger.exception("Hybrid search failed")
        raise HTTPException(status_code=500, detail=str(e))


class GraphRAGRequest(BaseModel):
    query: str = Field(..., min_length=1, description="自然语言查询")
    entity_name: str = ""
    limit: int = Field(10, ge=1, le=30)


def _build_rag_context(
    query: str,
    graph_results: list[dict],
    vector_results: dict,
    entity_ids: list[str],
) -> dict:
    """组装 GraphRAG 上下文（图证据 + 向量证据）

    Returns:
        {"graph_evidence": [...], "vector_evidence": [...]}
    """
    # 图证据：关系边（含实体 id，供引用）
    graph_evidence = [
        {
            "source_entity": str(r["source_entity"]),
            "target_entity": str(r["target_entity"]),
            "relation_type": r["relation_type"],
            "depth": r["depth"],
        }
        for r in graph_results
    ]

    # 向量证据：实体描述 + 事实
    vector_evidence: list[dict] = []
    for ent in vector_results.get("entities", []):
        payload = ent.get("payload", {}) or {}
        vector_evidence.append({
            "kind": "entity",
            "name": payload.get("name", ""),
            "entity_type": payload.get("entity_type", ""),
            "description": (payload.get("description") or "")[:600],
        })
    for fact in vector_results.get("facts", []):
        payload = fact.get("payload", {}) or {}
        vector_evidence.append({
            "kind": "fact",
            "subject": payload.get("subject_name", ""),
            "predicate": payload.get("predicate", ""),
            "value": (payload.get("object_value") or "")[:400],
            "time_start": payload.get("time_start", ""),
        })

    # 限制上下文量，避免超出模型 context
    graph_evidence = graph_evidence[:30]
    vector_evidence = vector_evidence[:30]

    return {"graph_evidence": graph_evidence, "vector_evidence": vector_evidence}


@router.post("/search/rag")
async def graphrag_search(request: GraphRAGRequest):
    """GraphRAG 增强检索：图遍历 + 向量检索 + LLM 融合推理

    与 /search 的区别：在混合检索基础上叠加 LLM 推理，
    产出带引用（图证据 + 向量证据）的可解释答案段落。
    """
    try:
        # 1. 结构化图检索
        graph_results = []
        vector_results = []
        entity_ids = []

        if request.entity_name:
            entities = await knowledge_storage.find_entity_by_name(
                request.entity_name, limit=1
            )
            if entities:
                entity_id = str(entities[0]["id"])
                entity_ids = [entity_id]
                graph_results = await knowledge_storage.get_entity_neighbors(
                    entity_id, depth=2
                )

        # 2. 语义向量检索
        vector_results = await knowledge_qdrant.hybrid_search(
            query=request.query,
            entity_ids=entity_ids if entity_ids else None,
            limit=request.limit,
        )

        # 3. 组装推理上下文
        context = _build_rag_context(
            request.query, graph_results, vector_results, entity_ids
        )

        graph_txt = "\n".join(
            f"- [{e['relation_type']}] {e['source_entity'][:8]} → {e['target_entity'][:8]} (depth={e['depth']})"
            for e in context["graph_evidence"]
        ) or "(无图证据)"
        vec_txt = "\n".join(
            f"- ({e['kind']}) "
            + (
                f"{e.get('name', '')}({e.get('entity_type', '')}): {e.get('description', '')}"
                if e["kind"] == "entity"
                else f"{e.get('subject', '')} - {e.get('predicate', '')}: {e.get('value', '')} @ {e.get('time_start', '')}"
            )
            for e in context["vector_evidence"]
        ) or "(无向量证据)"

        prompt = (
            "你是投资研究知识问答助手，基于以下证据回答用户问题。\n"
            "要求：\n"
            "1. 只能基于给出的证据推理，不得编造；证据不足时明确说明。\n"
            "2. 输出纯 JSON（不要 markdown 代码块）：{\"summary\": "
            "\"一段完整、连贯的中文答案\", \"key_findings\": [{\"finding\": "
            "\"结论要点\", \"cited_evidence\": [\"对应证据原文片段\"]}]}.\n\n"
            f"## 用户问题\n{request.query}\n\n"
            f"## 图证据（结构化关系，entity_id 唯一标识）\n{graph_txt}\n\n"
            f"## 向量证据（实体/事实描述）\n{vec_txt}\n"
            "## 输出\n"
        )

        messages = [
            {"role": "system", "content": "你是严谨的投资知识图谱推理助手，支持证据引用，输出结构化 JSON。"},
            {"role": "user", "content": prompt},
        ]

        temperature = get_policy("knowledge.rag.temperature", 0.1)

        # 4. LLM 融合推理（失败时降级为原始检索结果）
        fusion = {"summary": "", "key_findings": []}
        try:
            result = await llm_tool.chat(messages, temperature=temperature)
            raw = (result.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
            # 去除可能的代码围栏
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()
            try:
                import json as _json
                parsed = _json.loads(raw)
                if isinstance(parsed, dict):
                    fusion = {
                        "summary": str(parsed.get("summary", "")),
                        "key_findings": parsed.get("key_findings", []) or [],
                    }
            except Exception:
                fusion = {"summary": raw, "key_findings": []}
        except Exception as e:
            logger.warning("GraphRAG LLM fusion failed (degraded): %s", e)
            fusion = {"summary": "", "key_findings": []}

        return {
            "query": request.query,
            "fusion": fusion,
            "entity_ids_used": entity_ids,
            "evidence": {
                "graph": context["graph_evidence"],
                "vector": context["vector_evidence"],
            },
            "degraded": fusion["summary"] == "",
        }
    except Exception as e:
        logger.exception("GraphRAG search failed")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 知识提取任务 API
# ============================================================


class ExtractRequest(BaseModel):
    document_ids: list[str]
    raw_texts: dict[str, str] = {}  # 可选：直接传入文本


@router.post("/extract")
async def trigger_extraction(request: ExtractRequest):
    """触发知识提取任务（创建 task → worker 处理）"""
    if not request.document_ids:
        raise HTTPException(status_code=400, detail="document_ids required")

    try:
        task_id = await task_queue.create_task(
            task_type="knowledge_extraction",
            title=f"知识提取 ({len(request.document_ids)} docs)",
            total_items=len(request.document_ids),
            params={
                "document_ids": request.document_ids,
                "raw_texts": request.raw_texts,
            },
        )
        return {
            "task_id": task_id,
            "status": "pending",
            "document_count": len(request.document_ids),
        }
    except Exception as e:
        logger.exception("Failed to create extraction task")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 目录浏览 API
# ============================================================


# 允许浏览的根路径白名单（安全限制）
ALLOWED_BROWSE_ROOTS = ["/data", "/app"]


@router.get("/browse-dirs")
async def browse_dirs(path: str = Query("/data/minio/documents", description="要浏览的目录路径（支持 Windows/WSL/容器格式）")):
    """浏览服务器目录结构（仅返回目录，用于目录选择器）

    自动转换 Windows (E:\\...) 和 WSL (/mnt/e/...) 路径为容器路径。
    """
    # 路径转换：Windows/WSL → 容器路径
    path = normalize_path(path)
    target = Path(path).resolve()

    # 安全检查：路径必须在允许的根目录下
    if not any(str(target).startswith(root) for root in ALLOWED_BROWSE_ROOTS):
        raise HTTPException(
            status_code=403,
            detail=f"路径不在允许范围内，允许的根路径: {', '.join(ALLOWED_BROWSE_ROOTS)}"
        )

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"路径不存在: {path}")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"不是目录: {path}")

    # 获取子目录列表
    subdirs = []
    try:
        for item in sorted(target.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                subdirs.append({
                    "name": item.name,
                    "path": str(item),
                })
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"无权限访问: {path}")

    # 计算父级路径
    parent = target.parent
    can_go_up = any(str(parent).startswith(root) for root in ALLOWED_BROWSE_ROOTS) and parent != target

    return {
        "current_path": str(target),
        "parent_path": str(parent) if can_go_up else None,
        "can_go_up": can_go_up,
        "directories": subdirs,
        "total": len(subdirs),
    }


@router.get("/path-mapping")
async def path_mapping():
    """返回卷映射信息，帮助前端用户理解路径转换关系"""
    return {
        "description": "路径映射关系：Windows → WSL → 容器",
        "examples": {
            "windows": "E:\\ai-platform\\data\\stock_a",
            "wsl": "/mnt/e/ai-platform/data/stock_a",
            "container": "/data/stock_a",
        },
        "volume_mounts": get_volume_mapping_info(),
        "tip": "建议使用目录浏览器选择路径，或手动输入容器路径（/data/... 格式）",
    }


# ============================================================
# MD 文件手动导入 API
# ============================================================


class MinioIngestRequest(BaseModel):
    bucket: str = Field("documents", description="MinIO bucket")
    prefix: str = Field("", description="对象前缀，如 cn/000002")
    market: str = Field("", description="市场过滤（cn/hk/us），空=全部")
    trigger: bool = Field(False, description="注册后是否立即入队 doc_pipeline")


@router.post("/ingest-minio")
async def trigger_ingest_minio(req: MinioIngestRequest):
    """从 MinIO 采集年报对象并注册为 pending documents（异步任务，支持进度/暂停/取消）

    调用 register_pending_from_minio 扫描 bucket 下的对象，识别
    /annual_report/{year}/report.{pdf|md} 形态的路径，写入 documents 表（幂等）。
    可选触发 doc_pipeline worker 处理。
    """
    task_id = await task_queue.create_task(
        task_type="ingest_minio",
        title=f"MinIO 导入: {req.bucket}/{req.prefix or '*'}"
        + (f" [{req.market}]" if req.market else ""),
        params={
            "bucket": req.bucket, "prefix": req.prefix,
            "market": req.market, "trigger": req.trigger,
        },
        created_by="api",
    )
    logger.info("[IngestMinio] async task created: %s | bucket=%s prefix=%r", task_id[:8], req.bucket, req.prefix)
    return {
        "status": "ok",
        "task_id": task_id,
        "async_mode": True,
    }


async def _run_ingest_minio_async(task_id: str, req: MinioIngestRequest) -> None:
    """异步任务：扫描 MinIO 并注册 pending 文档，支持暂停/恢复/终止"""
    try:
        result = await doc_pipeline.register_pending_from_minio(
            bucket=req.bucket, prefix=req.prefix, market=req.market,
            task_id=task_id,
        )
        if result.get("cancelled"):
            await task_queue.fail_task(
                task_id, "任务已终止（用户取消，部分文档可能已注册）"
            )
            await task_queue.log_task(
                task_id, "warn",
                f"MinIO 导入已终止，已注册 {result.get('added', 0)} 个文档",
            )
            return

        await task_queue.update_progress(
            task_id, result.get("found", 0),
            stage=f"完成 · 新增{result.get('added', 0)} 跳过{result.get('skipped', 0)} 重置{result.get('reset', 0)}",
            current_name="",
        )
        await task_queue.complete_task(task_id)
        await task_queue.log_task(
            task_id, "info",
            f"MinIO 导入完成: found={result.get('found', 0)} added={result.get('added', 0)} "
            f"skipped={result.get('skipped', 0)} reset={result.get('reset', 0)}",
        )

        if req.trigger and result.get("found", 0) > 0:
            # 只要扫描到对象即触发处理（已存在 pending 文档也会由
            # process_pending_documents 原子认领处理，避免因 added=0 永不触发）
            pipeline_task_id = await task_queue.create_task(
                task_type="doc_pipeline",
                title=f"文档处理 Pipeline ({result['found']} docs, MinIO)",
                params={"limit": result["found"]},
                total_items=result["found"],
                created_by="api",
            )
            await task_queue.log_task(task_id, "info", f"已触发 Pipeline: {pipeline_task_id}")
    except asyncio.CancelledError:
        logger.info("[IngestMinio] %s terminated", task_id[:8])
        await task_queue.fail_task(task_id, "任务已终止（用户取消）")
    except Exception as e:
        logger.exception("[IngestMinio] %s failed", task_id[:8])
        await task_queue.fail_task(task_id, str(e))
    finally:
        task_queue.purge_control(task_id)


class IngestRequest(BaseModel):
    path: str = Field(..., min_length=1, description="文件或目录路径")
    collection: str = Field("documents_cn", description="目标 Qdrant collection")


async def _run_ingest(path: str, collection: str, task_id: str = "") -> dict[str, int]:
    """后台执行 MD 文件导入处理管线（task_id 非空时同步更新任务队列进度）

    Returns:
        {"found": N, "added": M, "skipped": K}
    """
    from tools.chunker import chunk_markdown
    from tools.embedding import embedding_tool
    from tools.qdrant import qdrant_tool

    logger.info("[Ingest] Start | path=%s | collection=%s", path, collection)
    if task_id:
        await task_queue.start_task(task_id)

    stats = {"found": 0, "added": 0, "skipped": 0}

    try:
        target = Path(path)
        md_files: list[Path] = []

        if target.is_file() and target.suffix == ".md":
            md_files = [target]
        elif target.is_dir():
            md_files = sorted(target.rglob("*.md"))
        else:
            logger.warning("[Ingest] Invalid path: %s", path)
            if task_id:
                await task_queue.fail_task(task_id, f"Invalid path: {path}")
            return stats

        stats["found"] = len(md_files)

        if not md_files:
            logger.info("[Ingest] No .md files found at %s", path)
            if task_id:
                await task_queue.fail_task(task_id, f"No .md files found at {path}")
            return stats

        embed_batch_size = 16

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding="utf-8")
                if not content.strip():
                    stats["skipped"] += 1
                    continue

                # 去重检查：基于 source_path + 内容 checksum（DP-B2 统一判重）
                source_path_str = str(md_file)
                content_checksum = sha256_hex(content)
                exists = await postgres_tool.query(
                    "SELECT 1 FROM documents WHERE metadata->>'source_path' = $1 "
                    "OR metadata->'acquire'->>'checksum' = $2 LIMIT 1",
                    source_path_str, content_checksum,
                )
                if exists:
                    logger.info("[Ingest] Skip duplicate | %s", md_file.name)
                    stats["skipped"] += 1
                    continue

                # Chunking
                chunks = chunk_markdown(content)
                if not chunks:
                    stats["skipped"] += 1
                    continue

                # 创建 document 记录（携带统一 acquire metadata）
                doc_id = str(uuid_mod.uuid4())
                file_name = md_file.stem
                acquire_meta = merge_acquire_into_metadata(
                    {"source_path": source_path_str, "ingest": "manual"},
                    build_acquire_metadata(
                        source_type="markdown",
                        trigger=AcquireTrigger.MANUAL_INGEST,
                        priority=AcquirePriority.NORMAL,
                        checksum=content_checksum,
                        origin=AcquireOrigin.MANUAL,
                        source_path=source_path_str,
                    ),
                )
                await postgres_tool.execute(
                    """
                    INSERT INTO documents (id, market, symbol, company, year,
                                           document_type, status, parser,
                                           chunk_count, metadata)
                    VALUES ($1, 'cn', $2, '', 0, 'markdown', 'indexing',
                            'direct', $3, $4::jsonb)
                    """,
                    doc_id, file_name, len(chunks), json.dumps(acquire_meta),
                )

                # Embedding（分批）
                all_vectors: list[list[float]] = []
                for batch_start in range(0, len(chunks), embed_batch_size):
                    batch = chunks[batch_start:batch_start + embed_batch_size]
                    texts = [c["content"][:2000] for c in batch]
                    vectors = await embedding_tool.embed(texts)
                    all_vectors.extend(vectors)

                # 写入 Qdrant + PostgreSQL chunks
                points = []
                for i, (chunk, vector) in enumerate(zip(chunks, all_vectors)):
                    point_id = str(uuid_mod.uuid4())
                    points.append({
                        "id": point_id,
                        "vector": vector,
                        "payload": {
                            "content": chunk["content"],
                            "heading": chunk.get("heading", ""),
                            "symbol": file_name,
                            "market": "cn",
                            "document_type": "markdown",
                            "document_id": doc_id,
                            "chunk_index": i,
                            "source_path": source_path_str,
                        },
                    })
                    await postgres_tool.execute(
                        """
                        INSERT INTO chunks (document_id, chunk_index, content,
                                            heading, collection_name, qdrant_point_id)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (document_id, chunk_index) DO NOTHING
                        """,
                        doc_id, i, chunk["content"],
                        chunk.get("heading", ""), collection, point_id,
                    )

                # Upsert Qdrant
                for batch_start in range(0, len(points), 100):
                    batch = points[batch_start:batch_start + 100]
                    await qdrant_tool.upsert(collection, batch)

                # 更新文档状态
                await postgres_tool.execute(
                    "UPDATE documents SET status = 'indexed' WHERE id = $1",
                    doc_id,
                )

                stats["added"] += 1
                logger.info(
                    "[Ingest] Processed | %s | chunks=%d", md_file.name, len(chunks)
                )
                if task_id:
                    await task_queue.update_progress(
                        task_id,
                        current_item=stats["added"] + stats["skipped"],
                        stage="embedding",
                        current_name=md_file.name,
                    )

            except Exception as e:
                logger.error("[Ingest] File failed | %s | %s", md_file, e)
                stats["skipped"] += 1
                if task_id:
                    await task_queue.update_progress(
                        task_id,
                        current_item=stats["added"] + stats["skipped"],
                        stage="failed_file",
                        current_name=md_file.name,
                    )

        logger.info(
            "[Ingest] Complete | found=%d added=%d skipped=%d | collection=%s",
            stats["found"], stats["added"], stats["skipped"], collection,
        )

        # 更新任务标题包含最终统计
        if task_id:
            await postgres_tool.execute(
                "UPDATE tasks SET title = $1 WHERE id = $2",
                f"文档导入 {path} (found={stats['found']}, added={stats['added']}, skipped={stats['skipped']})",
                task_id,
            )
            await task_queue.complete_task(task_id)

    except Exception as e:
        logger.error("[Ingest] Fatal error: %s", e)
        if task_id:
            await task_queue.fail_task(task_id, str(e))

    return stats


@router.post("/ingest")
async def trigger_ingest(req: IngestRequest):
    """手动导入 MD 文件并执行处理管线（异步执行，立即返回）"""
    # 基本路径验证
    target = Path(req.path)
    if not target.exists():
        raise HTTPException(status_code=400, detail=f"路径不存在：{req.path}")

    # 只接受目录路径
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="请选择目录，而不是单个文件")

    # 快速检测是否存在 .md 文件（避免大目录全量递归扫描）
    file_count = 0
    for _ in target.rglob("*.md"):
        file_count += 1
        if file_count >= 9999:
            break

    if file_count == 0:
        raise HTTPException(status_code=400, detail=f"目录下无 .md 文件：{req.path}")

    # 创建任务队列记录，供「处理详情」页展示进度
    task_id = await task_queue.create_task(
        task_type="doc_pipeline",
        title=f"文档导入 {req.path} ({file_count} files)",
        params={"path": req.path, "collection": req.collection},
        total_items=file_count,
        created_by="api",
    )
    asyncio.create_task(_run_ingest(req.path, req.collection, task_id))
    count_label = f"{file_count}+" if file_count >= 9999 else str(file_count)
    return {
        "status": "accepted",
        "message": f"导入任务已启动（{count_label} 个文件 → {req.collection}）",
        "found": file_count,
        "collection": req.collection,
        "task_id": task_id,
    }


# ============================================================
# Render Queue 监控 API（KOC-F2）
# ============================================================


@router.get("/render-jobs")
async def list_render_jobs(
    status: str = Query("", description="状态过滤：pending/running/done/failed，空=全部"),
    limit: int = Query(50, ge=1, le=200),
):
    """Render Queue 任务列表（KOC-F2）

    按 priority 升序、created_at 升序返回，左侧优先展示高优先级任务。
    """
    try:
        rows = await knowledge_storage.list_render_jobs(
            status=status or None, limit=limit
        )
        return {
            "jobs": [
                {
                    "id": str(r["id"]),
                    "entity": str(r["entity"]) if r.get("entity") else None,
                    "entity_name": r.get("entity_name"),
                    "type": r["type"],
                    "section": r.get("section"),
                    "status": r["status"],
                    "retry": r.get("retry", 0),
                    "priority": r.get("priority", 5),
                    "error_message": r.get("error_message"),
                    "created_at": str(r["created_at"]) if r.get("created_at") else None,
                    "updated_at": str(r["updated_at"]) if r.get("updated_at") else None,
                }
                for r in rows
            ],
            "total": len(rows),
        }
    except Exception as e:
        logger.exception("Failed to list render jobs")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/render-jobs/{job_id}/retry")
async def retry_render_job(job_id: str):
    """手动重试失败的渲染任务（KOC-F2）

    failed → pending，清空 error_message，由 render worker 重新领取。
    """
    try:
        ok = await knowledge_storage.retry_render_job(job_id)
        if not ok:
            raise HTTPException(
                status_code=409,
                detail="仅 failed 状态的渲染任务可手动重试",
            )
        return {"status": "ok", "message": "渲染任务已重新入队", "job_id": job_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to retry render job %s", job_id)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────── Knowledge Package 管理（DP-D1 Publish） ───────────────

class PublishRequest(BaseModel):
    """发布请求体：destination 可选（默认取 policy pipeline.publish.destination）"""

    destination: str | None = Field(default=None, description="发布目标（如 koc_inbox）")


@router.get("/packages")
async def list_packages(
    status: str | None = Query(default=None, description="draft/published/consumed/failed"),
    source_type: str | None = Query(default=None, description="annual_report/news/web/general"),
    limit: int = Query(default=50, le=500),
):
    """Knowledge Package 列表（DP-D1，按状态/源类型筛选）"""
    try:
        where = []
        params: list = []
        if status:
            where.append("status = $" + str(len(params) + 1))
            params.append(status)
        if source_type:
            where.append("source_type = $" + str(len(params) + 1))
            params.append(source_type)
        sql = f"""
            SELECT id, package_version, schema_version, source_type, document_id,
                   status, publish_time, retry_count, created_at, updated_at
            FROM knowledge_packages
            {"WHERE " + " AND ".join(where) if where else ""}
            ORDER BY created_at DESC
            LIMIT ${len(params) + 1}
        """
        params.append(limit)
        rows = await postgres_tool.query(sql, *params)
        return {
            "packages": [
                {
                    "id": str(r["id"]),
                    "package_version": r["package_version"],
                    "schema_version": r["schema_version"],
                    "source_type": r["source_type"],
                    "document_id": str(r["document_id"]) if r.get("document_id") else None,
                    "status": r["status"],
                    "publish_time": str(r["publish_time"]) if r.get("publish_time") else None,
                    "retry_count": r.get("retry_count", 0),
                    "created_at": str(r["created_at"]) if r.get("created_at") else None,
                }
                for r in rows
            ],
            "total": len(rows),
        }
    except Exception as e:
        logger.exception("Failed to list packages")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/packages/{package_id}")
async def get_package(package_id: str):
    """Package 详情（含 payload 摘要与校验信息）"""
    try:
        row = await package_storage.get(package_id)
        if not row:
            raise HTTPException(status_code=404, detail="package not found")
        valid, errors = await package_storage.validate_for_publish(package_id)
        return {
            "id": str(row["id"]),
            "package_version": row["package_version"],
            "schema_version": row["schema_version"],
            "source_type": row["source_type"],
            "document_id": str(row["document_id"]) if row.get("document_id") else None,
            "status": row["status"],
            "publish_time": str(row["publish_time"]) if row.get("publish_time") else None,
            "retry_count": row.get("retry_count", 0),
            "payload": row.get("payload"),
            "publishable": valid,
            "validation_errors": errors,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get package %s", package_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/packages/{package_id}/publish")
async def publish_package(package_id: str, body: PublishRequest | None = None):
    """发布 Package 草稿：校验 → published（DP-D1）

    校验失败：retry_count + 1，达上限置 failed；成功：published（KOC Inbox 拉取消费）。
    """
    try:
        valid, errors = await package_storage.validate_for_publish(package_id)
        if not valid:
            raise HTTPException(
                status_code=422,
                detail={"message": "Package 校验未通过", "errors": errors},
            )
        ok = await package_storage.publish(
            package_id, destination=body.destination if body else None
        )
        if not ok:
            raise HTTPException(status_code=409, detail="发布失败（状态非 draft 或 DB 错误）")
        return {"status": "ok", "message": "Package 已发布", "package_id": package_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to publish package %s", package_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/packages/{package_id}/retry")
async def retry_package(package_id: str):
    """重投失败 Package：failed → draft（retry_count + 1，DP-D1 Re-Publish）"""
    try:
        ok = await package_storage.retry(package_id)
        if not ok:
            raise HTTPException(status_code=409, detail="仅 failed 状态的 Package 可重投")
        return {"status": "ok", "message": "Package 已重投为草稿", "package_id": package_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to retry package %s", package_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/packages/{package_id}/rollback")
async def rollback_package(package_id: str):
    """回退已发布 Package：published/consumed → draft（DP-D1）

    支持 Rollback 场景：重新处理或重新发布，回到上一版本。
    """
    try:
        ok = await package_storage.rollback(package_id)
        if not ok:
            raise HTTPException(status_code=409, detail="仅 published/consumed 状态可回退")
        return {"status": "ok", "message": "Package 已回退为草稿", "package_id": package_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to rollback package %s", package_id)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# KOC-B2 治理面板端点（Duplicate/Conflict/Low Confidence/Need Review）
# ============================================================


@router.get("/governance/summary")
async def governance_summary():
    """治理面板计数卡：四类 open 冲突计数 + 总览（KOC-B2）

    sync_conflict 为 KOC-F3 预留（core.entities.sync_status 冲突），
    与四类检测冲突同表同端点。
    """
    try:
        rows = await postgres_tool.query(
            """
            SELECT conflict_type, COUNT(*) AS cnt
            FROM core.knowledge_conflicts
            WHERE status = 'open'
            GROUP BY conflict_type
            """
        )
        counts = {r["conflict_type"]: r["cnt"] for r in rows}
        return {
            "summary": {
                "duplicate_entity": counts.get("duplicate_entity", 0),
                "value_mismatch": counts.get("value_mismatch", 0),
                "low_confidence": counts.get("low_confidence", 0),
                "stale_fact": counts.get("stale_fact", 0),
                "sync_conflict": counts.get("sync_conflict", 0),
                "total": sum(counts.values()),
            }
        }
    except Exception as e:
        logger.exception("Failed to get governance summary")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/governance/items")
async def governance_items(
    conflict_type: str | None = Query(
        default=None, description="duplicate_entity/value_mismatch/low_confidence/stale_fact"
    ),
    limit: int = Query(default=50, ge=1, le=200),
):
    """治理处理队列：open 状态治理项列表（含实体名/事实内容解析）"""
    try:
        rows = await postgres_tool.query(
            """
            SELECT c.id, c.conflict_type, c.entity_id, c.fact_a, c.fact_b,
                   c.resolution, c.created_at,
                   e.name AS entity_name, e.entity_type
            FROM core.knowledge_conflicts c
            LEFT JOIN core.entities e ON e.id = c.entity_id
            WHERE c.status = 'open'
              AND ($1::text IS NULL OR c.conflict_type = $1)
            ORDER BY c.created_at DESC
            LIMIT $2
            """,
            conflict_type,
            limit,
        )
        items = []
        for r in rows:
            item = {
                "id": str(r["id"]),
                "conflict_type": r["conflict_type"],
                "entity_id": str(r["entity_id"]) if r.get("entity_id") else None,
                "entity_name": r.get("entity_name"),
                "entity_type": r.get("entity_type"),
                "fact_a": str(r["fact_a"]) if r.get("fact_a") else None,
                "fact_b": str(r["fact_b"]) if r.get("fact_b") else None,
                "resolution": r.get("resolution"),
                "created_at": str(r["created_at"]) if r.get("created_at") else None,
            }
            # 解析 resolution JSON 供前端展示动作/详情
            try:
                item["resolution_obj"] = json.loads(item["resolution"]) if item["resolution"] else {}
            except (json.JSONDecodeError, TypeError):
                item["resolution_obj"] = {}
            items.append(item)
        return {"items": items, "total": len(items)}
    except Exception as e:
        logger.exception("Failed to get governance items")
        raise HTTPException(status_code=500, detail=str(e))


class ResolveRequest(BaseModel):
    """治理项处理请求体（KOC-B2）"""

    action: str = Field(description="merge/keep/dismiss（合并/保留/驳回）")
    note: str = Field(default="", description="处理备注")


@router.post("/governance/{conflict_id}/resolve")
async def resolve_conflict(conflict_id: str, body: ResolveRequest):
    """处理治理项：回写 status='resolved' + resolution.action（KOC-B2）

    merge 仅对 duplicate_entity 生效：真实合并重复实体（别名并入保留实体）。
    """
    try:
        ok = await governance.resolve_conflict(conflict_id, body.action, body.note)
        if not ok:
            raise HTTPException(status_code=404, detail="治理项不存在或已处理")
        return {
            "status": "ok",
            "message": f"治理项已处理（{body.action}）",
            "conflict_id": conflict_id,
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("Failed to resolve conflict %s", conflict_id)
        raise HTTPException(status_code=500, detail=str(e))
