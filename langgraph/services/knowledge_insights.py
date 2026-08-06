"""KOC-D2 Knowledge Insights 计算服务

基于近期入库统计产出运营洞察（设计 §7 Knowledge Insights）：
  - hot_topics          今日热点话题（近期新增 Facts/Events 关键词 + 实体名关键词共现 Top N）
  - trending_companies  热门公司（Company 实体按 source_count 排序）
  - trending_industries 热门行业（Industry 实体按 source_count 排序）
  - emerging_concepts   新兴概念（Concept/Technology 近期新增，按置信度排序）
  - top_growing         增长最快知识类型（近窗口新增实体按 entity_type 分组）
  - top_mentioned       被提及最多的公司（facts.subject_entity 关联统计，数据少时降级为 source_count）
  - heatmap             知识热度（近 7 天每日新增 entities/facts）

设计原则（延续 KOC-D1 analytics）：
  - 各子查询独立 try/except，单故障不影响整体返回（对应字段降级为空列表）
  - 不引入新表，全部基于 core.entities / core.facts / core.events 现有结构
  - NIC-D1 Trend Discovery 复用本服务的 hot_topics 数据源
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import date

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)

# 平台杂词（英文公司后缀/通用词、中文公司常见后缀），不参与热点关键词
_STOPWORDS = {
    "co", "ltd", "inc", "llc", "corp", "corporation", "the", "of", "and", "or",
    "for", "in", "on", "at", "group", "holdings", "holding", "limited", "company",
    "company", "inc", "公司", "集团", "有限", "股份", "控股", "国际",
}

# 热点关键词来源：近期新增实体名（按窗口取前 N 条）
_HOT_TOPIC_SAMPLE = 500


def _iso(value):
    """date/datetime → ISO 字符串（避免 asyncpg 返回对象无法 JSON 序列化）"""
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _extract_keywords(name: str) -> list[str]:
    """从实体名提取候选关键词

    英文名按空格/标点拆分（Beijing Hongjun Asset → Beijing/Hongjun/Asset），
    中文名整体保留（盐城福德 → 盐城福德），过滤停用词与纯数字。
    """
    if not name:
        return []
    tokens = []
    for part in re.split(r"[\s,，、()（）/|_-]+", name):
        part = part.strip().strip(".")
        if not part or part.isdigit() or len(part) < 2:
            continue
        if part.lower() not in _STOPWORDS:
            tokens.append(part)
    return tokens


async def compute_insights(range_days: int = 7, limit: int = 10) -> dict:
    """计算 Knowledge Insights（KOC-D2）

    参数：
      range_days: 近期窗口（天），默认 7
      limit:      各榜单返回条数，默认 10
    返回：
      hot_topics / trending_companies / trending_industries / emerging_concepts /
      top_growing / top_mentioned / heatmap
    """
    result: dict = {"range_days": range_days, "limit": limit}

    # ── Hot Topics：近期新增实体名关键词共现统计 ──
    try:
        rows = await postgres_tool.query(
            "SELECT name FROM core.entities "
            "WHERE status='active' AND created_at >= CURRENT_DATE - INTERVAL '1 day' * $1 "
            "ORDER BY created_at DESC LIMIT $2",
            range_days,
            _HOT_TOPIC_SAMPLE,
        )
        counter: Counter[str] = Counter()
        for r in rows:
            counter.update(_extract_keywords(r["name"]))
        result["hot_topics"] = [
            {"topic": kw, "count": cnt}
            for kw, cnt in counter.most_common(limit)
        ]
    except Exception:
        logger.warning("insights: hot_topics query failed, degraded")
        result["hot_topics"] = []

    # ── Trending Companies：Company 按 source_count 排序 ──
    try:
        rows = await postgres_tool.query(
            "SELECT name, source_count, confidence, created_at FROM core.entities "
            "WHERE status='active' AND entity_type='Company' "
            "ORDER BY source_count DESC NULLS LAST, created_at DESC LIMIT $1",
            limit,
        )
        result["trending_companies"] = [
            {
                "name": r["name"],
                "source_count": int(r["source_count"] or 0),
                "confidence": round(float(r["confidence"]), 3) if r.get("confidence") is not None else None,
                "created_at": _iso(r.get("created_at")),
            }
            for r in rows
        ]
    except Exception:
        logger.warning("insights: trending_companies query failed, degraded")
        result["trending_companies"] = []

    # ── Trending Industries：Industry 按 source_count 排序 ──
    try:
        rows = await postgres_tool.query(
            "SELECT name, source_count, created_at FROM core.entities "
            "WHERE status='active' AND entity_type='Industry' "
            "ORDER BY source_count DESC NULLS LAST, created_at DESC LIMIT $1",
            limit,
        )
        result["trending_industries"] = [
            {
                "name": r["name"],
                "source_count": int(r["source_count"] or 0),
                "created_at": _iso(r.get("created_at")),
            }
            for r in rows
        ]
    except Exception:
        logger.warning("insights: trending_industries query failed, degraded")
        result["trending_industries"] = []

    # ── Emerging Concepts：Concept/Technology 近期新增按置信度排序 ──
    try:
        rows = await postgres_tool.query(
            "SELECT name, entity_type, confidence, source_count, created_at FROM core.entities "
            "WHERE status='active' AND entity_type IN ('Concept','Technology') "
            "AND created_at >= CURRENT_DATE - INTERVAL '1 day' * $1 "
            "ORDER BY confidence DESC NULLS LAST, created_at DESC LIMIT $2",
            range_days,
            limit,
        )
        result["emerging_concepts"] = [
            {
                "name": r["name"],
                "entity_type": r["entity_type"],
                "confidence": round(float(r["confidence"]), 3) if r.get("confidence") is not None else None,
                "source_count": int(r["source_count"] or 0),
                "created_at": _iso(r.get("created_at")),
            }
            for r in rows
        ]
    except Exception:
        logger.warning("insights: emerging_concepts query failed, degraded")
        result["emerging_concepts"] = []

    # ── Top Growing：近窗口新增实体按类型分组 ──
    try:
        rows = await postgres_tool.query(
            "SELECT entity_type, COUNT(*) AS cnt FROM core.entities "
            "WHERE status='active' AND created_at >= CURRENT_DATE - INTERVAL '1 day' * $1 "
            "GROUP BY entity_type ORDER BY cnt DESC LIMIT $2",
            range_days,
            limit,
        )
        result["top_growing"] = [
            {"entity_type": r["entity_type"], "count": int(r["cnt"] or 0)}
            for r in rows
        ]
    except Exception:
        logger.warning("insights: top_growing query failed, degraded")
        result["top_growing"] = []

    # ── Top Mentioned：facts.subject_entity 关联公司被提及次数 ──
    try:
        rows = await postgres_tool.query(
            "SELECT e.name, COUNT(f.id) AS cnt FROM core.facts f "
            "JOIN core.entities e ON e.id = f.subject_entity "
            "WHERE e.status='active' "
            "GROUP BY e.name ORDER BY cnt DESC LIMIT $1",
            limit,
        )
        mentioned = [{"name": r["name"], "count": int(r["cnt"] or 0)} for r in rows]
    except Exception:
        logger.warning("insights: top_mentioned query failed, degraded")
        mentioned = []
    # 事实数据不足（< limit/2）时，降级为 source_count 最高的公司（保证卡片有真实来源）
    if len(mentioned) < max(1, limit // 2):
        try:
            rows = await postgres_tool.query(
                "SELECT name, source_count AS cnt FROM core.entities "
                "WHERE status='active' AND entity_type='Company' "
                "ORDER BY source_count DESC NULLS LAST LIMIT $1",
                limit,
            )
            mentioned = [
                {"name": r["name"], "count": int(r["cnt"] or 0)} for r in rows
            ]
        except Exception:
            logger.warning("insights: top_mentioned fallback query failed, degraded")
    result["top_mentioned"] = mentioned

    # ── Heatmap：近 7 天每日新增 entities/facts ──
    try:
        rows = await postgres_tool.query(
            "SELECT d, "
            "COALESCE(SUM(CASE WHEN src='e' THEN cnt END), 0) AS entities, "
            "COALESCE(SUM(CASE WHEN src='f' THEN cnt END), 0) AS facts "
            "FROM ("
            "  SELECT created_at::date AS d, COUNT(*) AS cnt, 'e' AS src FROM core.entities "
            "    WHERE created_at >= CURRENT_DATE - INTERVAL '7 days' GROUP BY d "
            "  UNION ALL "
            "  SELECT created_at::date AS d, COUNT(*) AS cnt, 'f' AS src FROM core.facts "
            "    WHERE created_at >= CURRENT_DATE - INTERVAL '7 days' GROUP BY d"
            ") t GROUP BY d ORDER BY d"
        )
        result["heatmap"] = [
            {
                "date": _iso(r["d"]),
                "entities": int(r["entities"] or 0),
                "facts": int(r["facts"] or 0),
            }
            for r in rows
        ]
    except Exception:
        logger.warning("insights: heatmap query failed, degraded")
        result["heatmap"] = []

    return result