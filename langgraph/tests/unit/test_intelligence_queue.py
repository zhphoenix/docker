"""NIC-A2 Intelligence Queue 四态联查单测

覆盖：
  - 四态派生规则（waiting/processing/published/failed）与 summary 计数
  - state 过滤（仅返回指定四态）
  - failed 项 error 从 processing_metadata 提取失败原因
  - 各查询 DB 异常 → 对应字段降级（不崩溃）

隔离策略：mock postgres_tool，不触真实 DB。
"""

from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, patch

from api.news import intelligence_queue, _iq_state, _iq_error


def _summary_row():
    return [{"waiting": 5, "processing": 2, "published": 3, "failed": 1}]


def _detail_rows():
    """四条明细：四态各一"""
    return [
        {
            "article_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "title": "无包新闻", "source_name": "Reuters",
            "published_at": datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc),
            "importance_score": 0.5,
            "package_id": None, "package_status": None, "retry_count": 0,
            "processing_metadata": None,
        },
        {
            "article_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "title": "处理中新闻", "source_name": "eastmoney",
            "published_at": datetime(2026, 8, 6, 7, 0, tzinfo=timezone.utc),
            "importance_score": 0.6,
            "package_id": "22222222-2222-2222-2222-222222222222",
            "package_status": "draft", "retry_count": 0,
            "processing_metadata": None,
        },
        {
            "article_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
            "title": "已发布新闻", "source_name": "cls",
            "published_at": datetime(2026, 8, 6, 6, 0, tzinfo=timezone.utc),
            "importance_score": 0.7,
            "package_id": "33333333-3333-3333-3333-333333333333",
            "package_status": "published", "retry_count": 0,
            "processing_metadata": None,
        },
        {
            "article_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
            "title": "失败新闻", "source_name": "cnbc_top",
            "published_at": datetime(2026, 8, 6, 5, 0, tzinfo=timezone.utc),
            "importance_score": 0.8,
            "package_id": "44444444-4444-4444-4444-444444444444",
            "package_status": "failed", "retry_count": 3,
            "processing_metadata": (
                '{"publish": {"last_error": "schema validation failed: title", '
                '"last_error_at": "2026-08-06T05:01:00+00:00"}}'
            ),
        },
    ]


def _build_side_effect(detail_rows=None):
    """按 SQL 特征返回计数 / 明细结果"""
    detail_rows = _detail_rows() if detail_rows is None else detail_rows

    async def side_effect(sql, *args):
        if "FILTER (WHERE kp.id IS NULL)" in sql:
            return _summary_row()
        if "kp.processing_metadata" in sql:
            return detail_rows
        return []

    return side_effect


@pytest.mark.asyncio
async def test_iq_structure_and_states():
    """四态派生 + summary 计数 + failed 失败原因"""
    fake_pg = AsyncMock()
    fake_pg.query.side_effect = _build_side_effect()

    with patch("api.news.postgres_tool", fake_pg):
        result = await intelligence_queue(days=7, limit=20)

    assert result["days"] == 7
    assert result["summary"] == {"waiting": 5, "processing": 2, "published": 3, "failed": 1}
    assert result["total"] == 4

    states = [i["state"] for i in result["items"]]
    assert states == ["waiting", "processing", "published", "failed"]

    # 字段完整
    it = result["items"][0]
    assert it["article_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert it["package_id"] is None and it["package_status"] is None
    assert "published_at" in it and "importance_score" in it

    # failed 项：失败原因提取 + retry_count
    failed = result["items"][3]
    assert failed["error"] == "schema validation failed: title"
    assert failed["retry_count"] == 3


@pytest.mark.asyncio
async def test_iq_state_filter():
    """state 过滤只返回指定四态"""
    fake_pg = AsyncMock()
    fake_pg.query.side_effect = _build_side_effect()

    with patch("api.news.postgres_tool", fake_pg):
        result = await intelligence_queue(days=7, limit=20, state="processing")

    assert result["total"] == 1
    assert result["items"][0]["state"] == "processing"
    assert result["summary"] == {"waiting": 5, "processing": 2, "published": 3, "failed": 1}


@pytest.mark.asyncio
async def test_iq_db_error_degraded():
    """全部查询抛异常 → summary 归零 + items 空（不崩溃）"""
    fake_pg = AsyncMock()
    fake_pg.query.side_effect = RuntimeError("db down")

    with patch("api.news.postgres_tool", fake_pg):
        result = await intelligence_queue(days=7, limit=20)

    assert result["summary"] == {"waiting": 0, "processing": 0, "published": 0, "failed": 0}
    assert result["items"] == []
    assert result["total"] == 0


def test_iq_state_unit():
    """四态派生规则单测"""
    assert _iq_state(None) == "waiting"
    assert _iq_state("draft") == "processing"
    assert _iq_state("published") == "published"
    assert _iq_state("consumed") == "published"
    assert _iq_state("failed") == "failed"
    assert _iq_state("unknown") == "failed"


def test_iq_error_unit():
    """失败原因提取：dict / JSON 字符串 / 空"""
    assert _iq_error(None) is None
    assert _iq_error({}) is None
    assert _iq_error({"publish": {"last_error": "boom"}}) == "boom"
    assert _iq_error('{"publish": {"last_error": "boom"}}') == "boom"
    assert _iq_error("not-json") == "not-json"