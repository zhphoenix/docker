"""NIC-B1 Event Monitor 端点单测（读 core.events）

覆盖：今日新增/窗口统计解析、受影响公司聚合、事件列表 jsonb 解析、
event_type/company 过滤 SQL 拼接、整体降级、Query 默认值防御。
"""

import json
import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Query

from api.knowledge import event_monitor

_UUID = uuid.uuid4()


def _stats_row() -> list:
    return [{
        "today_new": 17,
        "window_total": 32,
        "avg_score": 0.72,
        "positive_count": 12,
        "negative_count": 6,
        "neutral_count": 14,
    }]


def _mentions_rows() -> list:
    return [
        {"company": "NVIDIA", "event_count": 5},
        {"company": "Amazon", "event_count": 3},
    ]


def _events_rows() -> list:
    return [{
        "id": _UUID,
        "event_type": "regulation",
        "title": "韩国芯片出口激增179%",
        "description": "半导体出口创纪录",
        "event_date": date(2026, 8, 5),
        "entities": json.dumps(["NVIDIA", "Samsung"], ensure_ascii=False),
        "impact": json.dumps({"score": 0.95, "direction": "positive"}),
        "confidence": 0.9,
        "created_at": datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc),
    }]


def _build_fake_pg(**overrides):
    fake = AsyncMock()
    default = {
        "today_new": _stats_row(),
        "jsonb_array_elements_text": _mentions_rows(),
        "e.entities @> jsonb_build_array": _events_rows(),
        None: _events_rows(),
    }
    default.update(overrides)

    async def _query(sql, *args):
        for key, rows in default.items():
            if key is not None and key in sql:
                return rows
        return default[None]

    fake.query.side_effect = _query
    return fake


@pytest.mark.asyncio
async def test_stats_parsing():
    fake = _build_fake_pg()
    with patch("api.knowledge.postgres_tool", fake):
        res = await event_monitor(days=30, limit=30)
    assert res["source"] == "core.events"
    assert res["today_new"] == 17
    assert res["window_total"] == 32
    assert res["avg_score"] == 0.72
    assert res["direction"] == {"positive": 12, "negative": 6, "neutral": 14}


@pytest.mark.asyncio
async def test_company_mentions_parsing():
    fake = _build_fake_pg()
    with patch("api.knowledge.postgres_tool", fake):
        res = await event_monitor(days=7, limit=30)
    assert res["company_mentions"] == [
        {"company": "NVIDIA", "event_count": 5},
        {"company": "Amazon", "event_count": 3},
    ]


@pytest.mark.asyncio
async def test_events_jsonb_parsing():
    fake = _build_fake_pg()
    with patch("api.knowledge.postgres_tool", fake):
        res = await event_monitor(days=30, limit=30)
    assert res["total"] == 1
    ev = res["events"][0]
    assert ev["id"] == str(_UUID)
    assert ev["event_date"] == "2026-08-05"
    assert ev["entities"] == ["NVIDIA", "Samsung"]
    assert ev["company_count"] == 2
    assert ev["impact"] == {"score": 0.95, "direction": "positive"}
    assert ev["confidence"] == 0.9


@pytest.mark.asyncio
async def test_event_type_filter_builds_sql():
    captured = {}

    async def _query(sql, *args):
        captured["sql"] = sql
        captured["args"] = list(args)
        if "today_new" in sql:
            return _stats_row()
        if "jsonb_array_elements_text" in sql:
            return _mentions_rows()
        return _events_rows()

    fake = AsyncMock()
    fake.query.side_effect = _query
    with patch("api.knowledge.postgres_tool", fake):
        await event_monitor(event_type="earnings", days=7, limit=10)
    assert "e.event_type = $2" in captured["sql"]
    assert captured["args"][1] == "earnings"
    assert captured["args"][-1] == 10


@pytest.mark.asyncio
async def test_company_filter_builds_sql():
    captured = {}

    async def _query(sql, *args):
        captured["sql"] = sql
        captured["args"] = list(args)
        if "today_new" in sql:
            return _stats_row()
        if "jsonb_array_elements_text" in sql:
            return _mentions_rows()
        return _events_rows()

    fake = AsyncMock()
    fake.query.side_effect = _query
    with patch("api.knowledge.postgres_tool", fake):
        await event_monitor(company="NVIDIA", days=7, limit=10)
    assert "EXISTS (SELECT 1 FROM jsonb_array_elements_text(e.entities) c(name)" in captured["sql"]
    assert captured["args"][1] == "NVIDIA"


@pytest.mark.asyncio
async def test_query_default_guard_accepts_query_object():
    """直接调用时 Query('') 默认值是对象 → 防御为 ''，不抛异常"""
    fake = _build_fake_pg()
    with patch("api.knowledge.postgres_tool", fake):
        res = await event_monitor(
            event_type=Query(""), company=Query(""), days=7, limit=10
        )
    assert res["total"] == 1
    assert res["today_new"] == 17


@pytest.mark.asyncio
async def test_degradation_on_db_failure():
    fake = AsyncMock()
    fake.query.side_effect = RuntimeError("db down")
    with patch("api.knowledge.postgres_tool", fake):
        res = await event_monitor(days=30, limit=30)
    assert res["today_new"] == 0
    assert res["window_total"] == 0
    assert res["avg_score"] is None
    assert res["events"] == []
    assert res["company_mentions"] == []