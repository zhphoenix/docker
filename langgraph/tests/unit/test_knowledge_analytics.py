"""KOC-D1 Knowledge Analytics 单测

覆盖：
  - knowledge_analytics：五维统计 + 趋势结构完整
  - coverage：entity_fact_coverage 计算正确
  - 各维度 DB 异常 → 对应字段降级为 0/None（不崩溃）
  - _iso 日期序列化

隔离策略：mock postgres_tool，不触真实 DB。
"""

from datetime import date

import pytest
from unittest.mock import AsyncMock, patch

from api.knowledge import _iso, knowledge_analytics


def _fake_rows_sequence():
    """按调用顺序返回各查询结果（growth/coverage/embedding/usage/quality/freshness/trend×3）"""
    return [
        # 1. growth
        [{"entities": 100, "relations": 200, "facts": 300, "events": 40}],
        # 2. coverage 主查询
        [{"entities": 100, "entities_with_facts": 60, "entity_types": 12}],
        # 3. embedding_coverage（内层）
        [{"embed_coverage": 0.85}],
        # 4. usage
        [
            {"agent_id": "kb", "today": 3, "total": 10},
            {"agent_id": "research", "today": 1, "total": 5},
        ],
        # 5. quality
        [{"entity_conf": 0.9, "conflicts_open": 2, "facts_verified": 50, "facts_total": 300}],
        # 6. freshness
        [
            {
                "last_entity_at": None,
                "last_fact_at": None,
                "last_event_at": None,
                "facts_expired": 3,
                "new_entities": 5,
                "new_facts": 10,
                "new_events": 2,
            }
        ],
        # 7-9. trends（以 Mock 返回，重新构造）
    ]


@pytest.mark.asyncio
async def test_analytics_structure():
    """五维 + 趋势结构完整，数值正确"""
    fake_pg = AsyncMock()

    async def side_effect(sql, *args):
        if "entities_with_facts" in sql:
            return [{"entities": 100, "entities_with_facts": 60, "entity_types": 12}]
        if "embed_coverage" in sql:
            return [{"embed_coverage": 0.85}]
        if "agent_id" in sql:
            return [
                {"agent_id": "kb", "today": 3, "total": 10},
                {"agent_id": "research", "today": 1, "total": 5},
            ]
        if "entity_conf" in sql:
            return [{"entity_conf": 0.9, "conflicts_open": 2, "facts_verified": 50, "facts_total": 300}]
        if "facts_expired" in sql:
            return [
                {
                    "last_entity_at": None,
                    "last_fact_at": None,
                    "last_event_at": None,
                    "facts_expired": 3,
                    "new_entities": 5,
                    "new_facts": 10,
                    "new_events": 2,
                }
            ]
        if "COUNT(*) AS cnt" in sql:
            # 趋势查询
            table = "core.entities" if "core.entities" in sql else ("core.facts" if "core.facts" in sql else "core.events")
            if "core.entities" in table:
                return [{"d": date(2026, 8, 1), "cnt": 2}, {"d": date(2026, 8, 2), "cnt": 3}]
            if "core.facts" in table:
                return [{"d": date(2026, 8, 1), "cnt": 5}]
            return []
        # growth
        return [{"entities": 100, "relations": 200, "facts": 300, "events": 40}]

    fake_pg.query.side_effect = side_effect

    with patch("api.knowledge.postgres_tool", fake_pg):
        result = await knowledge_analytics(range_days=7)

    # growth
    assert result["growth"] == {"entities": 100, "relations": 200, "facts": 300, "events": 40, "communities": 0}
    # coverage
    assert result["coverage"]["knowledge_coverage"] == 60.0  # 60/100
    assert result["coverage"]["entity_fact_coverage"] == 60.0
    assert result["coverage"]["entity_types"] == 12
    assert result["coverage"]["embedding_coverage"] == 85.0
    # usage
    assert result["usage"]["runs"] == 15
    assert result["usage"]["runs_today"] == 4
    assert result["usage"]["top_agents"][0]["agent_id"] == "kb"
    # quality
    assert result["quality"]["entity_confidence"] == 90.0
    assert result["quality"]["conflicts_open"] == 2
    assert result["quality"]["facts_verified"] == 50
    # freshness
    assert result["freshness"]["facts_expired"] == 3
    assert result["freshness"]["new_entities"] == 5
    # trends
    assert result["trends"]["entities"] == [
        {"date": "2026-08-01", "count": 2},
        {"date": "2026-08-02", "count": 3},
    ]
    assert result["trends"]["events"] == []
    assert result["range_days"] == 7


@pytest.mark.asyncio
async def test_analytics_db_error_degraded():
    """全部查询抛异常 → 各维度降级不崩溃"""
    fake_pg = AsyncMock()
    fake_pg.query.side_effect = RuntimeError("db down")

    with patch("api.knowledge.postgres_tool", fake_pg):
        result = await knowledge_analytics(range_days=30)

    assert result["growth"] == {"entities": 0, "relations": 0, "facts": 0, "events": 0, "communities": 0}
    assert result["coverage"]["knowledge_coverage"] == 0.0
    assert result["coverage"]["embedding_coverage"] is None
    assert result["usage"]["runs"] == 0
    assert result["quality"]["conflicts_open"] == 0
    assert result["freshness"]["facts_expired"] == 0
    assert result["trends"]["entities"] == []


@pytest.mark.asyncio
async def test_analytics_no_entities_coverage_zero():
    """无实体时不除零"""
    fake_pg = AsyncMock()

    async def side_effect(sql, *args):
        if "entities_with_facts" in sql:
            return [{"entities": 0, "entities_with_facts": 0, "entity_types": 0}]
        if "embed_coverage" in sql:
            return [{"embed_coverage": None}]
        if "agent_id" in sql:
            return []
        if "entity_conf" in sql:
            return [{"entity_conf": None, "conflicts_open": 0, "facts_verified": 0, "facts_total": 0}]
        if "facts_expired" in sql:
            return [
                {
                    "last_entity_at": None,
                    "last_fact_at": None,
                    "last_event_at": None,
                    "facts_expired": 0,
                    "new_entities": 0,
                    "new_facts": 0,
                    "new_events": 0,
                }
            ]
        if "COUNT(*) AS cnt" in sql:
            return []
        return [{"entities": 0, "relations": 0, "facts": 0, "events": 0}]

    fake_pg.query.side_effect = side_effect

    with patch("api.knowledge.postgres_tool", fake_pg):
        result = await knowledge_analytics(range_days=7)

    assert result["coverage"]["knowledge_coverage"] == 0.0
    assert result["coverage"]["embedding_coverage"] is None
    assert result["quality"]["entity_confidence"] is None


def test_iso_serialization():
    """date/datetime/None 序列化"""
    assert _iso(date(2026, 8, 1)) == "2026-08-01"
    assert _iso(None) is None
    assert _iso("2026-08-01") == "2026-08-01"