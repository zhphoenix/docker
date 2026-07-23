"""Graph 集成测试 - 完整流程测试

注意：需要所有下游服务运行才能执行。
"""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_chat_graph_builds():
    """测试 Chat Graph 可以正常构建"""
    from graph.graph import build_chat_graph

    graph = build_chat_graph()
    assert graph is not None


@pytest.mark.asyncio
async def test_research_graph_builds():
    """测试 Research Graph 可以正常构建"""
    from graph.graph import build_research_graph

    graph = build_research_graph()
    assert graph is not None


@pytest.mark.asyncio
async def test_should_continue_good():
    """测试条件路由：quality=good → finish"""
    from graph.graph import should_continue

    state = {
        "reflect": {"quality": "good", "retry_count": 0},
    }
    result = should_continue(state)
    assert result == "finish"


@pytest.mark.asyncio
async def test_should_continue_bad_retry():
    """测试条件路由：quality=bad → retrieve"""
    from graph.graph import should_continue

    state = {
        "reflect": {"quality": "bad", "retry_count": 0},
    }
    result = should_continue(state)
    assert result == "retrieve"


@pytest.mark.asyncio
async def test_should_continue_force_finish():
    """测试条件路由：retry_count >= 2 → finish（强制结束）"""
    from graph.graph import should_continue

    state = {
        "reflect": {"quality": "bad", "retry_count": 2},
    }
    result = should_continue(state)
    assert result == "finish"
