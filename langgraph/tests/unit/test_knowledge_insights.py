"""KOC-D2 Knowledge Insights 单测

覆盖：
  - compute_insights：七类洞察结构完整、数值正确
  - _extract_keywords：中文整体保留 / 英文拆分 / 停用词与纯数字过滤
  - top_mentioned 降级逻辑（事实不足时降级为 source_count 排行）
  - 各查询 DB 异常 → 对应字段降级为空列表（不崩溃）
  - _iso 日期序列化

隔离策略：mock postgres_tool，不触真实 DB。
"""

from datetime import date

import pytest
from unittest.mock import AsyncMock, patch

from services.knowledge_insights import _extract_keywords, _iso, compute_insights


def _build_side_effect(mentioned_rows=None, mentioned_fallback=None):
    """按 SQL 特征返回对应查询结果"""

    async def side_effect(sql, *args):
        if "SUM(CASE WHEN src='e'" in sql:
            return [
                {"d": date(2026, 7, 31), "entities": 2, "facts": 0},
                {"d": date(2026, 8, 1), "entities": 5, "facts": 1},
            ]
        if "e.id = f.subject_entity" in sql:
            return mentioned_rows if mentioned_rows is not None else [
                {"name": "腾讯控股", "cnt": 3},
                {"name": "阿里巴巴", "cnt": 2},
                {"name": "宁德时代", "cnt": 2},
                {"name": "比亚迪", "cnt": 1},
                {"name": "美团", "cnt": 1},
                {"name": "小米集团", "cnt": 1},
            ]
        if "entity_type='Company'" in sql and "source_count AS cnt" in sql:
            return mentioned_fallback if mentioned_fallback is not None else [
                {"name": "盐城福德", "cnt": 4},
                {"name": "佳杉资产", "cnt": 4},
            ]
        if "entity_type='Company'" in sql:
            return [
                {"name": "盐城福德", "source_count": 4, "confidence": 0.95, "created_at": date(2026, 8, 1)},
                {"name": "SpaceX", "source_count": 3, "confidence": 0.9, "created_at": date(2026, 8, 5)},
            ]
        if "entity_type='Industry'" in sql:
            return [
                {"name": "新能源", "source_count": 2, "created_at": date(2026, 8, 2)},
            ]
        if "entity_type IN ('Concept','Technology')" in sql:
            return [
                {"name": "AI Agent", "entity_type": "Concept", "confidence": 0.88, "source_count": 1, "created_at": date(2026, 8, 5)},
            ]
        if "GROUP BY entity_type" in sql:
            return [
                {"entity_type": "Company", "cnt": 263},
                {"entity_type": "Metric", "cnt": 215},
            ]
        # hot_topics
        return [
            {"name": "SpaceX"},
            {"name": "Elon Musk"},
            {"name": "全新好"},
            {"name": "Beijing Hongjun Asset Management Co., Ltd."},
        ]

    return side_effect


@pytest.mark.asyncio
async def test_insights_structure():
    """七类洞察结构完整、数值正确"""
    fake_pg = AsyncMock()
    fake_pg.query.side_effect = _build_side_effect()

    with patch("services.knowledge_insights.postgres_tool", fake_pg):
        result = await compute_insights(range_days=7, limit=10)

    assert result["range_days"] == 7
    assert result["limit"] == 10

    # hot_topics：关键词提取 + 计数（SpaceX 出现 1 次）
    assert isinstance(result["hot_topics"], list)
    assert len(result["hot_topics"]) >= 1

    # trending_companies
    assert result["trending_companies"][0]["name"] == "盐城福德"
    assert result["trending_companies"][0]["source_count"] == 4
    assert result["trending_companies"][0]["confidence"] == 0.95

    # trending_industries
    assert result["trending_industries"][0]["name"] == "新能源"

    # emerging_concepts
    assert result["emerging_concepts"][0]["name"] == "AI Agent"
    assert result["emerging_concepts"][0]["entity_type"] == "Concept"

    # top_growing
    assert result["top_growing"][0] == {"entity_type": "Company", "count": 263}

    # top_mentioned：事实充足时直接使用事实统计
    assert result["top_mentioned"][0]["name"] == "腾讯控股"
    assert result["top_mentioned"][0]["count"] == 3

    # heatmap
    assert result["heatmap"][0]["date"] == "2026-07-31"
    assert result["heatmap"][0]["entities"] == 2


@pytest.mark.asyncio
async def test_top_mentioned_degraded():
    """事实不足（< limit/2）→ 降级为 source_count 排行"""
    fake_pg = AsyncMock()
    fake_pg.query.side_effect = _build_side_effect(
        mentioned_rows=[], mentioned_fallback=[{"name": "盐城福德", "cnt": 4}]
    )

    with patch("services.knowledge_insights.postgres_tool", fake_pg):
        result = await compute_insights(range_days=7, limit=10)

    assert result["top_mentioned"] == [{"name": "盐城福德", "count": 4}]


@pytest.mark.asyncio
async def test_insights_db_error_degraded():
    """全部查询抛异常 → 各类别降级为空列表"""
    fake_pg = AsyncMock()
    fake_pg.query.side_effect = RuntimeError("db down")

    with patch("services.knowledge_insights.postgres_tool", fake_pg):
        result = await compute_insights(range_days=30, limit=5)

    assert result["hot_topics"] == []
    assert result["trending_companies"] == []
    assert result["trending_industries"] == []
    assert result["emerging_concepts"] == []
    assert result["top_growing"] == []
    assert result["top_mentioned"] == []
    assert result["heatmap"] == []
    assert result["range_days"] == 30


def test_extract_keywords():
    """中文整体保留 / 英文拆分 / 停用词与纯数字过滤"""
    # 中文名整体保留
    assert _extract_keywords("盐城福德") == ["盐城福德"]
    # 英文按空格拆分，过滤 Co./Ltd. 等停用词（含句点后缀）
    kws = _extract_keywords("Beijing Hongjun Asset Management Co., Ltd.")
    assert "Beijing" in kws
    assert "Hongjun" in kws
    assert "Co" not in kws
    assert "Ltd" not in kws
    assert "Co." not in kws
    # 纯数字与单字符过滤
    assert _extract_keywords("2031") == []
    assert _extract_keywords("A") == []
    # 空值
    assert _extract_keywords(None) == []


def test_iso_serialization():
    """date/None 序列化"""
    assert _iso(date(2026, 8, 1)) == "2026-08-01"
    assert _iso(None) is None