"""NIC-B2 Top Impact Events 端点单测（KOC 分析结果展示）

覆盖：星级映射（score→stars）、score 缺失/空串处理、company 过滤 SQL、
列表解析（jsonb）、整体降级。
"""

import json
import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from api.knowledge import top_impact_events

_UUID_A = uuid.uuid4()
_UUID_B = uuid.uuid4()


def _rows() -> list:
    return [
        {
            "id": _UUID_A,
            "event_type": "earnings",
            "title": "Amazon tops $3 trillion market cap",
            "description": "市值突破 3 万亿美元",
            "event_date": date(2026, 8, 4),
            "entities": json.dumps(["Amazon"], ensure_ascii=False),
            "impact": json.dumps({"score": 0.95, "direction": "positive"}),
            "confidence": 0.95,
        },
        {
            "id": _UUID_B,
            "event_type": "regulation",
            "title": "美国禁止出口钨废料",
            "description": "",
            "event_date": date(2026, 8, 5),
            "entities": json.dumps([], ensure_ascii=False),
            "impact": json.dumps({"score": -0.6, "direction": "negative"}),
            "confidence": 0.92,
        },
    ]


@pytest.mark.asyncio
async def test_top_impact_structure_and_stars():
    fake = AsyncMock()
    fake.query.return_value = _rows()
    with patch("api.knowledge.postgres_tool", fake):
        res = await top_impact_events(days=30, limit=10)
    assert res["source"] == "core.events"
    assert res["total"] == 2
    first = res["items"][0]
    assert first["score"] == 0.95
    assert first["stars"] == 5  # round(0.95 * 5)
    assert first["companies"] == ["Amazon"]
    assert first["company_count"] == 1
    second = res["items"][1]
    assert second["stars"] == 0  # round(-0.6 * 5) = -3 → 0 下限保护前为 -3，此处按 round 结果
    assert second["companies"] == []


@pytest.mark.asyncio
async def test_company_filter_builds_sql():
    captured = {}

    async def _query(sql, *args):
        captured["sql"] = sql
        captured["args"] = list(args)
        return _rows()

    fake = AsyncMock()
    fake.query.side_effect = _query
    with patch("api.knowledge.postgres_tool", fake):
        await top_impact_events(company="Amazon", days=7, limit=5)
    assert "EXISTS (SELECT 1 FROM jsonb_array_elements_text(e.entities) c(name)" in captured["sql"]
    assert captured["args"][1] == "Amazon"
    assert captured["args"][-1] == 5
    assert "NULLIF(e.impact->>'score', '')::float" in captured["sql"]


@pytest.mark.asyncio
async def test_score_missing_degrades_to_zero_stars():
    rows = _rows()
    rows[0]["impact"] = json.dumps({}, ensure_ascii=False)  # 无 score
    fake = AsyncMock()
    fake.query.return_value = rows
    with patch("api.knowledge.postgres_tool", fake):
        res = await top_impact_events(days=30, limit=10)
    assert res["items"][0]["score"] is None
    assert res["items"][0]["stars"] == 0


@pytest.mark.asyncio
async def test_degradation_on_db_failure():
    fake = AsyncMock()
    fake.query.side_effect = RuntimeError("db down")
    with patch("api.knowledge.postgres_tool", fake):
        res = await top_impact_events(days=30, limit=10)
    assert res["items"] == []
    assert res["total"] == 0