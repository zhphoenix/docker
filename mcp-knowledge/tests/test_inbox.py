"""Inbox Tools 单元测试

覆盖 Knowledge Inbox 状态机：
  - list_inbox 状态过滤与非法状态校验
  - review_inbox 审核通过/拒绝 + 审核日志
  - archive_inbox 归档
  - 状态机非法跳转校验
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from server.tools import inbox as inbox_module


@pytest.fixture
def fake_pg():
    """mock pg_storage：query / query_one / execute"""
    pg = MagicMock()
    pg.query = AsyncMock(return_value=[])
    pg.query_one = AsyncMock(return_value=None)
    pg.execute = AsyncMock(return_value="ok")
    return pg


@pytest.fixture
def fake_cache():
    cache = MagicMock()
    cache.invalidate = MagicMock()
    return cache


@pytest.fixture
def mcp():
    """模拟 FastMCP：mcp.tool 作为装饰器返回原函数并记录"""
    m = MagicMock()
    registered = {}

    def _tool(name_or_fn=None, **kwargs):
        # 实际代码用 @mcp.tool()（带括号），此时 name_or_fn 为 None，返回装饰器
        def deco(fn):
            registered[fn.__name__] = fn
            return fn
        if name_or_fn is None:
            return deco
        # 兼容 @mcp.tool 直接用法
        return deco(name_or_fn)

    m.tool.side_effect = _tool
    m._registered = registered
    return m


def _capture_tools(mcp):
    """收集 @mcp.tool() 注册的函数"""
    return mcp._registered


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_list_inbox_valid(mcp, fake_pg, fake_cache):
    fake_pg.query.return_value = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "object_type": "entity",
            "status": "READY_REVIEW",
            "confidence": 0.6,
            "content": {"name": "TestCo"},
        }
    ]
    with patch.object(inbox_module, "pg_storage", fake_pg), \
         patch.object(inbox_module, "knowledge_cache", fake_cache):
        inbox_module.register_inbox_tools(mcp)
        tools = _capture_tools(mcp)
        result = _run(tools["list_inbox"](status="READY_REVIEW", limit=10))

    assert result["total"] == 1
    assert result["items"][0]["status"] == "READY_REVIEW"


def test_list_inbox_invalid_status(mcp, fake_pg, fake_cache):
    with patch.object(inbox_module, "pg_storage", fake_pg), \
         patch.object(inbox_module, "knowledge_cache", fake_cache):
        inbox_module.register_inbox_tools(mcp)
        tools = _capture_tools(mcp)
        result = _run(tools["list_inbox"](status="BAD_STATUS"))
    assert "error" in result


def test_review_inbox_approve(mcp, fake_pg, fake_cache):
    fake_pg.query_one.return_value = {"status": "READY_REVIEW"}
    with patch.object(inbox_module, "pg_storage", fake_pg), \
         patch.object(inbox_module, "knowledge_cache", fake_cache):
        inbox_module.register_inbox_tools(mcp)
        tools = _capture_tools(mcp)
        result = _run(tools["review_inbox"](
            "11111111-1111-1111-1111-111111111111", "approve", reviewer="tester"
        ))
    assert result["status"] == "APPROVED"
    # 校验 execute 被调用两次（update + insert 审核日志）
    assert fake_pg.execute.await_count == 2


def test_review_inbox_reject(mcp, fake_pg, fake_cache):
    fake_pg.query_one.return_value = {"status": "READY_REVIEW"}
    with patch.object(inbox_module, "pg_storage", fake_pg), \
         patch.object(inbox_module, "knowledge_cache", fake_cache):
        inbox_module.register_inbox_tools(mcp)
        tools = _capture_tools(mcp)
        result = _run(tools["review_inbox"](
            "11111111-1111-1111-1111-111111111111", "reject", reason="low quality"
        ))
    assert result["status"] == "REJECTED"
    assert fake_pg.execute.await_count == 2


def test_review_inbox_invalid_action(mcp, fake_pg, fake_cache):
    with patch.object(inbox_module, "pg_storage", fake_pg), \
         patch.object(inbox_module, "knowledge_cache", fake_cache):
        inbox_module.register_inbox_tools(mcp)
        tools = _capture_tools(mcp)
        result = _run(tools["review_inbox"](
            "11111111-1111-1111-1111-111111111111", "force"
        ))
    assert "error" in result


def test_review_inbox_wrong_state(mcp, fake_pg, fake_cache):
    # 已归档/已审记录不可再审
    fake_pg.query_one.return_value = {"status": "ARCHIVED"}
    with patch.object(inbox_module, "pg_storage", fake_pg), \
         patch.object(inbox_module, "knowledge_cache", fake_cache):
        inbox_module.register_inbox_tools(mcp)
        tools = _capture_tools(mcp)
        result = _run(tools["review_inbox"](
            "11111111-1111-1111-1111-111111111111", "approve"
        ))
    assert "error" in result


def test_archive_inbox(mcp, fake_pg, fake_cache):
    fake_pg.query_one.return_value = {"status": "APPROVED"}
    with patch.object(inbox_module, "pg_storage", fake_pg), \
         patch.object(inbox_module, "knowledge_cache", fake_cache):
        inbox_module.register_inbox_tools(mcp)
        tools = _capture_tools(mcp)
        result = _run(tools["archive_inbox"](
            "11111111-1111-1111-1111-111111111111"
        ))
    assert result["status"] == "ARCHIVED"


def test_archive_inbox_normal_status(mcp, fake_pg, fake_cache):
    # 未审记录不可归档
    fake_pg.query_one.return_value = {"status": "READY_REVIEW"}
    with patch.object(inbox_module, "pg_storage", fake_pg), \
         patch.object(inbox_module, "knowledge_cache", fake_cache):
        inbox_module.register_inbox_tools(mcp)
        tools = _capture_tools(mcp)
        result = _run(tools["archive_inbox"](
            "11111111-1111-1111-1111-111111111111"
        ))
    assert "error" in result