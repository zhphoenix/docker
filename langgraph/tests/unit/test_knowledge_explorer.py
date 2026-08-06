"""KOC-C1 Knowledge Explorer 单元测试

验证：
  1. search_entities 支持置信度/来源数过滤（SQL 条件正确注入）
  2. count_entities_by_type 类型统计（GROUP BY entity_type）
  3. get_entity_neighbors 返回实体名（LEFT JOIN core.entities）

隔离策略：mock storage 模块的 postgres_tool.query。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from storage.knowledge.postgres import KnowledgePostgresStorage


@pytest.fixture
def storage():
    return KnowledgePostgresStorage()


@pytest.mark.asyncio
async def test_search_entities_name_and_type_only(storage):
    """仅 name/entity_type 时不含置信度/来源数条件"""
    with patch("storage.knowledge.postgres.postgres_tool") as pg:
        pg.query = AsyncMock(return_value=[])
        await storage.search_entities(name="腾讯", entity_type="Company", limit=20)

    sql = pg.query.await_args.args[0]
    assert "(name ILIKE $1 OR canonical_name ILIKE $1)" in sql
    assert "entity_type = $2" in sql
    assert "confidence >=" not in sql
    assert "source_count >=" not in sql
    assert pg.query.await_args.args[1] == "%腾讯%"
    assert pg.query.await_args.args[2] == "Company"
    assert pg.query.await_args.args[3] == 20


@pytest.mark.asyncio
async def test_search_entities_min_confidence_condition(storage):
    """min_confidence 注入 confidence >= 条件"""
    with patch("storage.knowledge.postgres.postgres_tool") as pg:
        pg.query = AsyncMock(return_value=[])
        await storage.search_entities(min_confidence=0.8, limit=10)

    sql = pg.query.await_args.args[0]
    assert "confidence >= $1" in sql
    assert pg.query.await_args.args[1] == 0.8
    assert pg.query.await_args.args[2] == 10


@pytest.mark.asyncio
async def test_search_entities_min_source_count_condition(storage):
    """min_source_count 注入 source_count >= 条件"""
    with patch("storage.knowledge.postgres.postgres_tool") as pg:
        pg.query = AsyncMock(return_value=[])
        await storage.search_entities(min_source_count=3, limit=10)

    sql = pg.query.await_args.args[0]
    assert "source_count >= $1" in sql
    assert pg.query.await_args.args[1] == 3


@pytest.mark.asyncio
async def test_search_entities_all_filters_combined(storage):
    """全部过滤条件组合时参数顺序正确"""
    with patch("storage.knowledge.postgres.postgres_tool") as pg:
        pg.query = AsyncMock(return_value=[])
        await storage.search_entities(
            name="茅台", entity_type="Company",
            min_confidence=0.7, min_source_count=2, limit=5,
        )

    sql = pg.query.await_args.args[0]
    assert "(name ILIKE $1 OR canonical_name ILIKE $1)" in sql
    assert "entity_type = $2" in sql
    assert "confidence >= $3" in sql
    assert "source_count >= $4" in sql
    assert "LIMIT $5" in sql
    args = pg.query.await_args.args
    assert args[1] == "%茅台%"
    assert args[2] == "Company"
    assert args[3] == 0.7
    assert args[4] == 2
    assert args[5] == 5


@pytest.mark.asyncio
async def test_count_entities_by_type(storage):
    """类型统计：GROUP BY entity_type 且仅 active"""
    rows = [
        {"entity_type": "Company", "count": 120},
        {"entity_type": "Person", "count": 30},
    ]
    with patch("storage.knowledge.postgres.postgres_tool") as pg:
        pg.query = AsyncMock(return_value=rows)
        result = await storage.count_entities_by_type()

    sql = pg.query.await_args.args[0]
    assert "GROUP BY entity_type" in sql
    assert "status = 'active'" in sql
    assert "ORDER BY count DESC" in sql
    assert result == rows


@pytest.mark.asyncio
async def test_get_entity_neighbors_includes_names(storage):
    """邻居查询 LEFT JOIN core.entities 返回 source_name/target_name"""
    rows = [
        {
            "source_entity": "aaa", "target_entity": "bbb",
            "source_name": "腾讯", "target_name": "阿里巴巴",
            "relation_type": "competes_with", "depth": 1,
        },
    ]
    with patch("storage.knowledge.postgres.postgres_tool") as pg:
        pg.query = AsyncMock(return_value=rows)
        result = await storage.get_entity_neighbors("aaa", depth=1)

    sql = pg.query.await_args.args[0]
    assert "LEFT JOIN core.entities s ON s.id = g.source_entity" in sql
    assert "s.name AS source_name" in sql
    assert "t.name AS target_name" in sql
    assert result[0]["target_name"] == "阿里巴巴"
    assert pg.query.await_args.args[1] == "aaa"
    assert pg.query.await_args.args[2] == 1