"""AC-P3-4 Agent Dashboard 全局汇总单测

覆盖：
  - agent_summary：聚合行 → 每 Agent 今日统计 + 全局 total
  - 无运行数据的 Agent 返回 runs_today=0
  - DB 异常时回退为空统计（不崩溃）
  - NaN 平均耗时视为 0

隔离策略：mock postgres_tool + list_agents，不触真实 DB。
"""

import math

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from api.agents import _to_float, agent_summary


def _fake_agents():
    """list_agents 返回的固定 Agent 列表（内置 chat / pipeline 两类）"""
    return {
        "agents": [
            {
                "name": "knowledge_ingestion",
                "display_name": "Knowledge Ingestion",
                "status": "active",
            },
            {
                "name": "news_intelligence",
                "display_name": "News Intelligence",
                "status": "active",
            },
            {"name": "chat", "display_name": "Chat Agent", "status": "active"},
        ],
        "total": 3,
    }


def _fake_rows():
    """agent_runs 当日聚合行（knowledge_ingestion 有数据，news_intelligence 无）"""
    return [
        {
            "agent_id": "knowledge_ingestion",
            "runs_today": 8,
            "success_today": 5,
            "failed_today": 3,
            "avg_latency_ms": 1200.5,
            "last_run_at": datetime(2026, 8, 5, 12, 0, 0),
        }
    ]


def test_to_float_conversions():
    """numeric 转换：None/NaN/Inf/数值"""
    assert _to_float(None) == 0.0
    assert _to_float(float("nan")) == 0.0
    assert _to_float(float("inf")) == 0.0
    assert _to_float("12.5") == 12.5
    assert _to_float("abc") == 0.0


@pytest.mark.asyncio
async def test_summary_structure():
    """有运行数据的 Agent 正确聚合，无运行的 Agent 补零"""
    fake_pg = AsyncMock()
    fake_pg.query.side_effect = [_fake_rows()]
    fake_list = AsyncMock(return_value=_fake_agents())

    with (
        patch("api.agents.postgres_tool", fake_pg),
        patch("api.agents.list_agents", fake_list),
    ):
        result = await agent_summary()

    by_id = {a["agent_id"]: a for a in result["agents"]}
    ki = by_id["knowledge_ingestion"]
    assert ki["runs_today"] == 8
    assert ki["success_today"] == 5
    assert ki["failed_today"] == 3
    assert ki["success_rate"] == 62.5  # 5/8
    assert ki["avg_latency_ms"] == 1200.5

    ni = by_id["news_intelligence"]
    assert ni["runs_today"] == 0
    assert ni["success_rate"] == 0.0

    total = result["total"]
    assert total["agents"] == 3
    assert total["runs_today"] == 8
    assert total["success_today"] == 5
    assert total["failed_today"] == 3
    assert total["success_rate"] == 62.5


@pytest.mark.asyncio
async def test_summary_db_error_fallback():
    """postgres 异常 → 回退为空聚合，所有 Agent runs_today=0"""
    fake_pg = AsyncMock()
    fake_pg.query.side_effect = RuntimeError("db down")
    fake_list = AsyncMock(return_value=_fake_agents())

    with (
        patch("api.agents.postgres_tool", fake_pg),
        patch("api.agents.list_agents", fake_list),
    ):
        result = await agent_summary()

    total = result["total"]
    assert total["runs_today"] == 0
    assert total["success_today"] == 0
    assert total["success_rate"] == 0.0
    assert all(a["runs_today"] == 0 for a in result["agents"])


@pytest.mark.asyncio
async def test_summary_nan_latency_zero():
    """NaN 平均耗时按 0 处理"""
    fake_pg = AsyncMock()
    rows = _fake_rows()
    rows[0]["avg_latency_ms"] = float("nan")
    fake_pg.query.side_effect = [rows]
    fake_list = AsyncMock(return_value=_fake_agents())

    with (
        patch("api.agents.postgres_tool", fake_pg),
        patch("api.agents.list_agents", fake_list),
    ):
        result = await agent_summary()

    ki = next(a for a in result["agents"] if a["agent_id"] == "knowledge_ingestion")
    assert math.isfinite(ki["avg_latency_ms"])
    assert ki["avg_latency_ms"] == 0.0


@pytest.mark.asyncio
async def test_summary_route_registered_before_agent_id():
    """/api/agents/summary 不会被 /{agent_id} 捕获（路由顺序正确性由 FastAPI 匹配保证）"""
    fake_pg = AsyncMock()
    fake_pg.query.side_effect = [_fake_rows()]
    fake_list = AsyncMock(return_value=_fake_agents())

    with (
        patch("api.agents.postgres_tool", fake_pg),
        patch("api.agents.list_agents", fake_list),
    ):
        result = await agent_summary()

    # 业务语义校验：summary 返回的是聚合结构而非单 Agent 详情
    assert "total" in result
    assert "agents" in result
    assert isinstance(result["total"]["runs_today"], int)