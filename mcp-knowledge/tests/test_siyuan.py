"""SiYuan / Knowledge Object Tools 单元测试

覆盖 Phase 6 的 6 个工具：
  - search_notes / get_note          检索与详情（含 SiYuan 展示路径）
  - create_knowledge_object          创建 + 渲染到 SiYuan
  - update_knowledge_object          版本化更新 + 增量同步
  - create_research_report           研究报告文档
  - create_event_note                事件笔记
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from server.tools import siyuan as siyuan_module


@pytest.fixture
def mcp():
    """模拟 FastMCP：mcp.tool 作为装饰器返回原函数并记录"""
    m = MagicMock()
    registered = {}

    def _tool(name_or_fn=None, **kwargs):
        def deco(fn):
            registered[fn.__name__] = fn
            return fn
        if name_or_fn is None:
            return deco
        return deco(name_or_fn)

    m.tool.side_effect = _tool
    m._registered = registered
    return m


@pytest.fixture
def fake_pg():
    """mock pg_storage 相关方法"""
    pg = MagicMock()
    pg.search_entities = AsyncMock(return_value=[])
    pg.get_entity_by_id = AsyncMock(return_value=None)
    pg.create_entity = AsyncMock(return_value="11111111-1111-1111-1111-111111111111")
    pg.update_knowledge = AsyncMock(return_value=True)
    return pg


@pytest.fixture
def fake_cache():
    """mock knowledge_cache：cached 恒等装饰器，invalidate 记录"""
    cache = MagicMock()
    cache.invalidate = MagicMock()

    def _cached(prefix, key_builder):
        def deco(fn):
            return fn
        return deco

    cache.cached.side_effect = _cached
    return cache


@pytest.fixture
def fake_sync():
    """mock siyuan_sync.sync_entity"""
    sync = MagicMock()
    sync.sync_entity = AsyncMock(
        return_value={"status": "synced", "action": "created", "path": "/Company/TestCo"}
    )
    return sync


@pytest.fixture
def fake_client():
    """mock siyuan_client"""
    client = MagicMock()
    client.is_available_url = MagicMock(return_value=True)
    client.upsert_doc = AsyncMock(
        return_value={"action": "created", "id": "doc-1", "path": "/Company/TestCo/Research"}
    )
    return client


def _run(coro):
    return asyncio.run(coro)


ENTITY = {
    "id": "11111111-1111-1111-1111-111111111111",
    "name": "TestCo",
    "entity_type": "Company",
    "description": "A test company",
    "canonical_name": "TestCo",
    "aliases": ["TC"],
    "properties": {"ticker": "TST"},
    "confidence": 0.9,
    "source_count": 3,
    "status": "active",
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-01T00:00:00",
}


import contextlib


def _patch(spec):
    """返回一个 ExitStack 上下文管理器，mock 多个模块属性"""
    stack = contextlib.ExitStack()
    for name, value in (
        ("pg_storage", spec.pg),
        ("knowledge_cache", spec.cache),
        ("siyuan_sync", spec.sync),
        ("siyuan_client", spec.client),
    ):
        stack.enter_context(patch.object(siyuan_module, name, value))
    return stack


class _Spec:
    def __init__(self, pg, cache, sync, client):
        self.pg = pg
        self.cache = cache
        self.sync = sync
        self.client = client


def test_search_notes(mcp, fake_pg, fake_cache, fake_sync, fake_client):
    fake_pg.search_entities.return_value = [ENTITY]
    spec = _Spec(fake_pg, fake_cache, fake_sync, fake_client)
    with _patch(spec):
        siyuan_module.register_siyuan_tools(mcp)
        tools = mcp._registered
        result = _run(tools["search_notes"](name="Test", entity_type="Company", limit=10))

    assert result["total"] == 1
    item = result["items"][0]
    assert item["name"] == "TestCo"
    assert item["siyuan"]["notebook"] == "Companies"
    assert item["siyuan"]["available"] is True
    fake_pg.search_entities.assert_awaited_once_with(name="Test", entity_type="Company", limit=10)


def test_get_note_found(mcp, fake_pg, fake_cache, fake_sync, fake_client):
    fake_pg.get_entity_by_id.return_value = ENTITY
    spec = _Spec(fake_pg, fake_cache, fake_sync, fake_client)
    with _patch(spec):
        siyuan_module.register_siyuan_tools(mcp)
        tools = mcp._registered
        result = _run(tools["get_note"](ENTITY["id"]))

    assert result["id"] == ENTITY["id"]
    assert result["siyuan"]["path"]
    fake_pg.get_entity_by_id.assert_awaited_once_with(ENTITY["id"])


def test_get_note_not_found(mcp, fake_pg, fake_cache, fake_sync, fake_client):
    fake_pg.get_entity_by_id.return_value = None
    spec = _Spec(fake_pg, fake_cache, fake_sync, fake_client)
    with _patch(spec):
        siyuan_module.register_siyuan_tools(mcp)
        tools = mcp._registered
        result = _run(tools["get_note"]("missing-id"))

    assert "error" in result


def test_create_knowledge_object(mcp, fake_pg, fake_cache, fake_sync, fake_client):
    fake_pg.get_entity_by_id.return_value = ENTITY
    spec = _Spec(fake_pg, fake_cache, fake_sync, fake_client)
    with _patch(spec):
        siyuan_module.register_siyuan_tools(mcp)
        tools = mcp._registered
        result = _run(tools["create_knowledge_object"](
            name="TestCo", entity_type="Company", description="A test company"
        ))

    assert result["status"] == "created"
    assert result["sync"]["status"] == "synced"
    fake_pg.create_entity.assert_awaited_once()
    fake_sync.sync_entity.assert_awaited_once()


def test_create_knowledge_object_invalid_type(mcp, fake_pg, fake_cache, fake_sync, fake_client):
    spec = _Spec(fake_pg, fake_cache, fake_sync, fake_client)
    with _patch(spec):
        siyuan_module.register_siyuan_tools(mcp)
        tools = mcp._registered
        result = _run(tools["create_knowledge_object"](
            name="X", entity_type="NotAType"
        ))

    assert "error" in result
    fake_pg.create_entity.assert_not_awaited()


def test_create_knowledge_object_no_render(mcp, fake_pg, fake_cache, fake_sync, fake_client):
    spec = _Spec(fake_pg, fake_cache, fake_sync, fake_client)
    with _patch(spec):
        siyuan_module.register_siyuan_tools(mcp)
        tools = mcp._registered
        result = _run(tools["create_knowledge_object"](
            name="TestCo", entity_type="Company", render_to_siyuan=False
        ))

    assert result["status"] == "created"
    assert result["sync"]["status"] == "skipped"
    fake_sync.sync_entity.assert_not_awaited()


def test_update_knowledge_object(mcp, fake_pg, fake_cache, fake_sync, fake_client):
    fake_pg.get_entity_by_id.return_value = ENTITY
    spec = _Spec(fake_pg, fake_cache, fake_sync, fake_client)
    with _patch(spec):
        siyuan_module.register_siyuan_tools(mcp)
        tools = mcp._registered
        result = _run(tools["update_knowledge_object"](
            ENTITY["id"], {"description": "updated"}
        ))

    assert result["status"] == "updated"
    assert result["sync"]["status"] == "synced"
    fake_pg.update_knowledge.assert_awaited_once_with("entity", ENTITY["id"], {"description": "updated"})


def test_update_knowledge_object_not_found(mcp, fake_pg, fake_cache, fake_sync, fake_client):
    fake_pg.update_knowledge.return_value = False
    spec = _Spec(fake_pg, fake_cache, fake_sync, fake_client)
    with _patch(spec):
        siyuan_module.register_siyuan_tools(mcp)
        tools = mcp._registered
        result = _run(tools["update_knowledge_object"]("missing-id", {"name": "x"}))

    assert "error" in result
    fake_sync.sync_entity.assert_not_awaited()


def test_create_research_report(mcp, fake_pg, fake_cache, fake_sync, fake_client):
    fake_pg.get_entity_by_id.return_value = ENTITY
    spec = _Spec(fake_pg, fake_cache, fake_sync, fake_client)
    with _patch(spec):
        siyuan_module.register_siyuan_tools(mcp)
        tools = mcp._registered
        result = _run(tools["create_research_report"](
            ENTITY["id"], title="Q1 Report", content="## Overview\nGrowth."
        ))

    assert result["title"] == "Q1 Report"
    assert result["sync"]["action"] == "created"
    fake_client.upsert_doc.assert_awaited_once()


def test_create_research_report_not_found(mcp, fake_pg, fake_cache, fake_sync, fake_client):
    fake_pg.get_entity_by_id.return_value = None
    spec = _Spec(fake_pg, fake_cache, fake_sync, fake_client)
    with _patch(spec):
        siyuan_module.register_siyuan_tools(mcp)
        tools = mcp._registered
        result = _run(tools["create_research_report"]("missing-id", title="R", content="c"))

    assert "error" in result
    fake_client.upsert_doc.assert_not_awaited()


def test_create_event_note(mcp, fake_pg, fake_cache, fake_sync, fake_client):
    event = dict(ENTITY, entity_type="Event")
    fake_pg.get_entity_by_id.return_value = event
    spec = _Spec(fake_pg, fake_cache, fake_sync, fake_client)
    with _patch(spec):
        siyuan_module.register_siyuan_tools(mcp)
        tools = mcp._registered
        result = _run(tools["create_event_note"](
            event["id"], summary="Earnings", event_date="2026-03-01"
        ))

    assert result["id"] == event["id"]
    assert result["siyuan"]["notebook"] == "Events"
    assert result["sync"]["status"] == "synced"
    fake_sync.sync_entity.assert_awaited_once()


def test_create_event_note_not_found(mcp, fake_pg, fake_cache, fake_sync, fake_client):
    fake_pg.get_entity_by_id.return_value = None
    spec = _Spec(fake_pg, fake_cache, fake_sync, fake_client)
    with _patch(spec):
        siyuan_module.register_siyuan_tools(mcp)
        tools = mcp._registered
        result = _run(tools["create_event_note"]("missing-id", summary="s"))

    assert "error" in result
    fake_sync.sync_entity.assert_not_awaited()