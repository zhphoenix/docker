"""AC-P3-3 Agent Metrics 单测

覆盖：
  - 计价函数 _estimate_cost（有单价 / 无单价置 0）
  - _to_float 数值转换
  - get_agent_metrics 端点：汇总六项指标 + 按天趋势 + 404 语义

隔离策略：mock postgres_tool 与 list_agents，不触真实 DB。
"""

import pytest
from datetime import date
from unittest.mock import AsyncMock, patch

from api.metrics import _estimate_cost, _to_float, get_agent_metrics


def test_estimate_cost_priced():
    """已配置单价的 agent：按 per_mtok 正确计算"""
    # chat: input 0.15 / output 0.60 美元每百万 tokens
    cost = _estimate_cost("chat", 1_000_000, 500_000)
    assert cost == pytest.approx(0.45, abs=1e-6)


def test_estimate_cost_default_zero():
    """未配置单价的 agent：回退 default（0）→ 成本置 0"""
    assert _estimate_cost("unknown_agent", 1_000_000, 1_000_000) == 0.0


def test_estimate_cost_zero_tokens():
    """tokens 为 0 → 成本 0（避免除零/负值）"""
    assert _estimate_cost("news_intelligence", 0, 0) == 0.0


def test_to_float_conversions():
    """asyncpg numeric/None/异常值 → float"""
    assert _to_float(12.5) == 12.5
    assert _to_float("3.14") == 3.14
    assert _to_float(None) == 0.0
    assert _to_float("NaN") == 0.0


@pytest.mark.asyncio
async def test_get_agent_metrics_summary_and_trend():
    """汇总六项指标 + 按天趋势计算正确"""
    summary_rows = [
        {
            "runs": 10,
            "success": 7,
            "failed": 3,
            "avg_latency_ms": 1000.5,
            "avg_tokens": 250.25,
            "total_tokens_in": 2000,
            "total_tokens_out": 500,
        }
    ]
    trend_rows = [
        {"date": date(2026, 8, 5), "runs": 6, "avg_latency_ms": 900.0, "avg_tokens": 200.0, "error_rate": 33.33},
        {"date": date(2026, 8, 6), "runs": 4, "avg_latency_ms": 1150.5, "avg_tokens": 325.5, "error_rate": 25.0},
    ]

    fake_pg = AsyncMock()
    fake_pg.query.side_effect = [summary_rows, trend_rows]

    with patch("api.metrics.postgres_tool", fake_pg), \
         patch("api.agents.list_agents", new=AsyncMock(return_value={"agents": [{"id": "news_intelligence"}]})):
        result = await get_agent_metrics("news_intelligence", "7d")

    assert result["agent_id"] == "news_intelligence"
    assert result["range"] == "7d"
    s = result["summary"]
    assert s["runs"] == 10
    assert s["success"] == 7
    assert s["failed"] == 3
    assert s["success_rate"] == 70.0
    assert s["avg_latency_ms"] == pytest.approx(1000.5)
    # 成本 = (2000*0.15 + 500*0.60) / 1e6 = 0.0006；每次平均 = 6e-05
    assert s["avg_cost"] == pytest.approx(0.00006, abs=1e-9)
    assert len(result["trend"]) == 2
    assert result["trend"][0]["date"] == "2026-08-05"
    assert result["trend"][0]["error_rate"] == pytest.approx(33.33)


@pytest.mark.asyncio
async def test_get_agent_metrics_empty():
    """无运行记录 → 零值汇总 + 空趋势（不报错）"""
    fake_pg = AsyncMock()
    fake_pg.query.side_effect = [[{"runs": 0, "success": 0, "failed": 0, "avg_latency_ms": None, "avg_tokens": None, "total_tokens_in": 0, "total_tokens_out": 0}], []]

    with patch("api.metrics.postgres_tool", fake_pg), \
         patch("api.agents.list_agents", new=AsyncMock(return_value={"agents": [{"id": "chat"}]})):
        result = await get_agent_metrics("chat", "1d")

    assert result["summary"]["runs"] == 0
    assert result["summary"]["avg_cost"] == 0.0
    assert result["trend"] == []


@pytest.mark.asyncio
async def test_get_agent_metrics_404():
    """Agent 不存在 → 404"""
    from fastapi import HTTPException

    with patch("api.agents.list_agents", new=AsyncMock(return_value={"agents": [{"id": "chat"}]})):
        with pytest.raises(HTTPException) as exc:
            await get_agent_metrics("ghost_agent", "7d")
    assert exc.value.status_code == 404