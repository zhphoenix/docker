"""KOC-A3 Merge 落库单测

覆盖：
  - bulk_upsert_entities 批内同名消歧（同一实体重复入库不产生重复行，alias 合并正确）
  - record_knowledge_version 版本审计（audit.knowledge_versions 自动递增版本号）

隔离策略：mock postgres_tool 与 get_policy，验证 SQL 调用与消歧语义，不触真实 DB。
"""

import json

import pytest
from unittest.mock import AsyncMock, patch

from storage.knowledge.postgres import KnowledgePostgresStorage


def _make_storage() -> KnowledgePostgresStorage:
    return KnowledgePostgresStorage()


@pytest.mark.asyncio
async def test_bulk_upsert_dedupes_same_name_in_batch():
    """同批内两个同名实体 → 只写一条唯一记录（id 相同），aliases/properties 合并，confidence 取最大"""
    storage = _make_storage()
    entities = [
        {
            "name": "腾讯控股", "entity_type": "company",
            "aliases": ["Tencent"], "properties": {"industry": "tech"}, "confidence": 0.8,
        },
        {
            "name": "腾讯控股", "entity_type": "company",
            "aliases": ["tengxun"], "properties": {"hq": "Shenzhen"}, "confidence": 0.9,
        },
    ]
    with patch("storage.knowledge.postgres.postgres_tool") as mock_pg, \
         patch("storage.knowledge.postgres.get_policy", return_value=50):
        mock_pg.execute_many = AsyncMock(return_value=None)
        ids = await storage.bulk_upsert_entities(entities)

    # 只执行一次批量写入，且只写一条唯一记录（不产生重复行）
    mock_pg.execute_many.assert_awaited_once()
    args = mock_pg.execute_many.await_args.args[1]
    assert len(args) == 1

    # 同名实体复用同一 id，返回列表按输入顺序对齐
    assert ids == [ids[0], ids[0]]
    row = args[0]
    assert row[0] == ids[0]

    # alias 合并（去重）正确
    aliases = json.loads(row[4])
    assert "Tencent" in aliases and "tengxun" in aliases

    # properties 合并、confidence 取最大（args 顺序：id,name,entity_type,description,aliases,properties,canonical_name,confidence,embedding）
    props = json.loads(row[5])
    assert props["industry"] == "tech" and props["hq"] == "Shenzhen"
    assert row[7] == 0.9


@pytest.mark.asyncio
async def test_bulk_upsert_distinct_names_kept():
    """不同名实体不合并，各自保留独立 id"""
    storage = _make_storage()
    entities = [
        {"name": "腾讯控股", "entity_type": "company", "aliases": ["Tencent"], "properties": {}, "confidence": 0.8},
        {"name": "阿里巴巴", "entity_type": "company", "aliases": [], "properties": {}, "confidence": 0.7},
    ]
    with patch("storage.knowledge.postgres.postgres_tool") as mock_pg, \
         patch("storage.knowledge.postgres.get_policy", return_value=50):
        mock_pg.execute_many = AsyncMock(return_value=None)
        ids = await storage.bulk_upsert_entities(entities)

    args = mock_pg.execute_many.await_args.args[1]
    assert len(args) == 2
    assert ids[0] != ids[1]


@pytest.mark.asyncio
async def test_bulk_upsert_empty_input():
    """空输入直接返回空列表，不触发写库"""
    storage = _make_storage()
    with patch("storage.knowledge.postgres.postgres_tool") as mock_pg:
        mock_pg.execute_many = AsyncMock(return_value=None)
        ids = await storage.bulk_upsert_entities([])
    assert ids == []
    mock_pg.execute_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_version_first_version_is_1():
    """首次写入 audit.knowledge_versions → version=1"""
    storage = _make_storage()
    oid = "11111111-2222-3333-4444-555555555555"
    with patch("storage.knowledge.postgres.postgres_tool") as mock_pg:
        mock_pg.query = AsyncMock(return_value=[{"next_version": 1}])
        mock_pg.execute = AsyncMock(return_value="INSERT 0 1")
        v = await storage.record_knowledge_version("entity", oid, {"name": "腾讯控股"})

    assert v == 1
    mock_pg.execute.assert_awaited_once()
    sql = mock_pg.execute.await_args.args[0]
    assert "audit.knowledge_versions" in sql
    assert "INSERT INTO" in sql
    # (sql, object_type, oid, version, content_json, created_by)
    assert mock_pg.execute.await_args.args[1] == "entity"
    assert mock_pg.execute.await_args.args[3] == 1
    assert mock_pg.execute.await_args.args[5] == "system"


@pytest.mark.asyncio
async def test_record_version_increments():
    """已有历史版本时自动递增（MAX(version)+1）"""
    storage = _make_storage()
    oid = "11111111-2222-3333-4444-555555555555"
    with patch("storage.knowledge.postgres.postgres_tool") as mock_pg:
        mock_pg.query = AsyncMock(return_value=[{"next_version": 3}])
        mock_pg.execute = AsyncMock(return_value="INSERT 0 1")
        v = await storage.record_knowledge_version(
            "entity", oid, {"name": "腾讯控股"}, created_by="knowledge_merger"
        )

    assert v == 3
    assert mock_pg.execute.await_args.args[3] == 3
    assert mock_pg.execute.await_args.args[5] == "knowledge_merger"


@pytest.mark.asyncio
async def test_record_version_empty_rows_defaults_1():
    """查询无历史行（返回空）时兜底 version=1"""
    storage = _make_storage()
    with patch("storage.knowledge.postgres.postgres_tool") as mock_pg:
        mock_pg.query = AsyncMock(return_value=[])
        mock_pg.execute = AsyncMock(return_value="INSERT 0 1")
        v = await storage.record_knowledge_version("fact", "11111111-2222-3333-4444-555555555555", {})

    assert v == 1