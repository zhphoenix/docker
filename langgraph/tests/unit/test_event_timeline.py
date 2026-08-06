"""NIC-B3 事件时间线端点单测（Timeline 与 Event Monitor 同源 core.events）

覆盖：升序排列 SQL、entity 过滤 SQL、jsonb 解析、整体降级。
"""

import json
import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from api.knowledge import event_timeline

_UUID = uuid.uuid4()


def _rows() -> list:
    return [
        {
            "id": _UUID,
            "event_type": "earnings",
            "title": "Amazon 市值突破 3 万亿美元",
            "description": "股价创历史新高",
            "event_date": date(2026, 8, 2),
            "entities": json.dumps(["Amazon"], ensure_ascii=False),
            "impact": json.dumps({"score": 0.95, "direction": "positive"}),
            "confidence": 0.95,
        }
    ]


@pytest.mark.asyncio
async def test_timeline_structure():
    fake = AsyncMock()
    fake.query.return_value = _rows()
    with patch("api.knowledge.postgres_tool", fake):
        res = await event_timeline(entity_name="Amazon", days=90, limit=50)
    assert res["source"] == "core.events"
    assert res["entity_name"] == "Amazon"
    assert res["total"] == 1
    item = res["items"][0]
    assert item["event_date"] == "2026-08-02"
    assert item["stars"] == 5
    assert item["companies"] == ["Amazon"]
    assert item["company_count"] == 1


@pytest.mark.asyncio
async def test_timeline_entity_filter_and_order():
    captured = {}

    async def _query(sql, *args):
        captured["sql"] = sql
        captured["args"] = list(args)
        return _rows()

    fake = AsyncMock()
    fake.query.side_effect = _query
    with patch("api.knowledge.postgres_tool", fake):
        await event_timeline(entity_name="NVIDIA", days=30, limit=10)
    assert "EXISTS (SELECT 1 FROM jsonb_array_elements_text(e.entities) c(name)" in captured["sql"]
    assert captured["args"][1] == "NVIDIA"
    assert "ORDER BY e.event_date ASC NULLS LAST" in captured["sql"]
    assert captured["args"][-1] == 10


@pytest.mark.asyncio
async def test_timeline_no_entity_returns_all():
    captured = {}

    async def _query(sql, *args):
        captured["sql"] = sql
        captured["args"] = list(args)
        return _rows()

    fake = AsyncMock()
    fake.query.side_effect = _query
    with patch("api.knowledge.postgres_tool", fake):
        await event_timeline(days=7, limit=50)
    assert "EXISTS (SELECT 1 FROM jsonb_array_elements_text" not in captured["sql"]
    assert captured["args"][0] == 7


@pytest.mark.asyncio
async def test_timeline_degradation_on_db_failure():
    fake = AsyncMock()
    fake.query.side_effect = RuntimeError("db down")
    with patch("api.knowledge.postgres_tool", fake):
        res = await event_timeline(entity_name="Amazon", days=90, limit=50)
    assert res["items"] == []
    assert res["total"] == 0