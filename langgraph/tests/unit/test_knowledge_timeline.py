"""KOC-D3 Entity Timeline 单测

覆盖：
  - get_entity_timeline：versions/facts/events 三类时间线结构完整
  - 实体不存在 → 404
  - 无效 UUID → 400
  - 子查询异常 → 对应类别降级为空列表（不崩溃）

隔离策略：mock postgres_tool，不触真实 DB。
"""

import uuid

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, patch

from api.knowledge import get_entity_timeline

ENTITY_ID = str(uuid.uuid4())


def _build_side_effect():
    """按 SQL 特征返回对应查询结果"""

    async def side_effect(sql, *args):
        if "FROM core.entities WHERE id = $1" in sql:
            return [{"id": ENTITY_ID}]
        if "FROM audit.knowledge_versions" in sql:
            return [
                {
                    "version": 1,
                    "content": {"name": "盐城福德", "entity_type": "Company"},
                    "created_by": "system",
                    "created_at": "2026-08-05 22:45:05+00:00",
                },
                {
                    "version": 2,
                    "content": {"name": "盐城新城福德汽车销售服务有限公司", "entity_type": "Company"},
                    "created_by": "knowledge_merger",
                    "created_at": "2026-08-05 23:57:10+00:00",
                },
            ]
        if "FROM core.facts WHERE subject_entity" in sql:
            return [
                {
                    "id": uuid.uuid4(),
                    "predicate": "营业收入",
                    "object_value": {"value": 100},
                    "unit": "亿元",
                    "time_start": "2025-12-31",
                    "time_end": None,
                    "confidence": 0.9,
                    "verification_status": "unverified",
                    "created_at": "2026-08-05 22:45:05+00:00",
                }
            ]
        return []  # events（空表）

    return side_effect


@pytest.mark.asyncio
async def test_timeline_structure():
    """versions/facts/events 三类时间线结构完整"""
    fake_pg = AsyncMock()
    fake_pg.query.side_effect = _build_side_effect()

    with patch("api.knowledge.postgres_tool", fake_pg):
        result = await get_entity_timeline(ENTITY_ID)

    assert result["entity_id"] == ENTITY_ID
    # versions
    assert len(result["versions"]) == 2
    assert result["versions"][0]["version"] == 1
    assert result["versions"][0]["content"]["name"] == "盐城福德"
    assert result["versions"][1]["created_by"] == "knowledge_merger"
    # facts
    assert len(result["facts"]) == 1
    assert result["facts"][0]["predicate"] == "营业收入"
    assert result["facts"][0]["time_start"] == "2025-12-31"
    assert result["facts"][0]["object_value"] == {"value": 100}
    # events
    assert result["events"] == []


@pytest.mark.asyncio
async def test_timeline_entity_not_found():
    """实体不存在 → 404"""
    fake_pg = AsyncMock()
    fake_pg.query.side_effect = [(), []]

    with patch("api.knowledge.postgres_tool", fake_pg):
        with pytest.raises(HTTPException) as exc:
            await get_entity_timeline(ENTITY_ID)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_timeline_invalid_uuid():
    """无效 UUID → 400"""
    fake_pg = AsyncMock()

    with patch("api.knowledge.postgres_tool", fake_pg):
        with pytest.raises(HTTPException) as exc:
            await get_entity_timeline("not-a-uuid")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_timeline_subquery_degraded():
    """versions/facts 查询异常 → 对应类别降级为空列表"""
    fake_pg = AsyncMock()

    async def side_effect(sql, *args):
        if "FROM core.entities WHERE id = $1" in sql:
            return [{"id": ENTITY_ID}]
        raise RuntimeError("db down")

    fake_pg.query.side_effect = side_effect

    with patch("api.knowledge.postgres_tool", fake_pg):
        result = await get_entity_timeline(ENTITY_ID)

    assert result["versions"] == []
    assert result["facts"] == []
    assert result["events"] == []