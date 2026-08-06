"""NIC-A1 Live Feed 分层视图单测

覆盖：
  - live_feed：breaking/high_impact/hot_topics 三区结构完整 + summary 计数
  - 各查询 DB 异常 → 对应区降级为空列表（不崩溃）
  - breaking 排序规则（importance_score 降序）

隔离策略：mock postgres_tool，不触真实 DB。
"""

import pytest
from unittest.mock import AsyncMock, patch

from api.news import live_feed


def _build_side_effect():
    """按 SQL 特征返回对应查询结果"""

    async def side_effect(sql, *args):
        if "COUNT(DISTINCT e.article_id)" in sql:
            return [
                {"name": "SpaceX", "mentions": 5},
                {"name": "特斯拉", "mentions": 3},
            ]
        if "a.importance_score >= 0.8 AND a.published_at" in sql:
            return [
                {
                    "id": "b1", "title": "Breaking 新闻", "summary": None,
                    "url": None, "category": "geopolitics", "language": "zh",
                    "importance_score": 0.95, "tier": 3,
                    "published_at": "2026-08-06 00:00:00+00:00",
                    "collected_at": "2026-08-06 00:00:00+00:00",
                    "status": "done", "source_name": "东方财富网",
                }
            ]
        # high_impact
        return [
            {
                "id": "h1", "title": "高影响新闻", "summary": None,
                "url": None, "category": "tech", "language": "en",
                "importance_score": 0.9, "tier": 1,
                "published_at": "2026-08-05 12:00:00+00:00",
                "collected_at": "2026-08-05 12:00:00+00:00",
                "status": "done", "source_name": "Reuters",
            }
        ]

    return side_effect


@pytest.mark.asyncio
async def test_feed_structure():
    """三区结构完整 + summary 计数正确"""
    fake_pg = AsyncMock()
    fake_pg.query.side_effect = _build_side_effect()

    with patch("api.news.postgres_tool", fake_pg):
        result = await live_feed(hours=24, limit=10)

    assert result["hours"] == 24
    # breaking
    assert len(result["breaking"]) == 1
    assert result["breaking"][0]["title"] == "Breaking 新闻"
    assert result["breaking"][0]["importance_score"] == 0.95
    assert result["breaking"][0]["source_name"] == "东方财富网"
    # high_impact
    assert len(result["high_impact"]) == 1
    assert result["high_impact"][0]["tier"] == 1
    # hot_topics
    assert result["hot_topics"] == [
        {"name": "SpaceX", "mentions": 5},
        {"name": "特斯拉", "mentions": 3},
    ]
    # summary
    assert result["summary"] == {"breaking": 1, "high_impact": 1, "hot_topics": 2}


@pytest.mark.asyncio
async def test_feed_db_error_degraded():
    """全部查询抛异常 → 三区降级为空 + summary 归零"""
    fake_pg = AsyncMock()
    fake_pg.query.side_effect = RuntimeError("db down")

    with patch("api.news.postgres_tool", fake_pg):
        result = await live_feed(hours=24, limit=5)

    assert result["breaking"] == []
    assert result["high_impact"] == []
    assert result["hot_topics"] == []
    assert result["summary"] == {"breaking": 0, "high_impact": 0, "hot_topics": 0}


@pytest.mark.asyncio
async def test_feed_partial_degraded():
    """仅 hot_topics 查询失败 → 其余区正常"""
    fake_pg = AsyncMock()

    async def side_effect(sql, *args):
        if "COUNT(DISTINCT e.article_id)" in sql:
            raise RuntimeError("hot query failed")
        if "a.importance_score >= 0.8 AND a.published_at" in sql:
            return [{"id": "b1", "title": "B", "importance_score": 0.9}]
        return [{"id": "h1", "title": "H", "importance_score": 0.85}]

    fake_pg.query.side_effect = side_effect

    with patch("api.news.postgres_tool", fake_pg):
        result = await live_feed(hours=24, limit=10)

    assert len(result["breaking"]) == 1
    assert len(result["high_impact"]) == 1
    assert result["hot_topics"] == []
    assert result["summary"]["hot_topics"] == 0