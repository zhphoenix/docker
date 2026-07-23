"""Planner Node 单元测试"""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_planner_generates_plan():
    """测试 Planner 生成执行计划"""
    with patch("nodes.planner.llm_tool") as mock_llm:
        mock_llm.chat = AsyncMock(return_value='{"steps": ["step1"], "tools": ["qdrant"]}')

        from nodes.planner import planner

        state = {
            "question": "分析宁德时代",
            "messages": [],
            "plan": {},
            "documents": [],
            "tool_results": {},
            "answer": "",
            "reflect": {},
            "metadata": {},
        }

        result = await planner(state)

        assert "plan" in result
        assert "steps" in result["plan"]
        assert len(result["plan"]["steps"]) > 0


@pytest.mark.asyncio
async def test_planner_handles_invalid_json():
    """测试 Planner 处理无效 JSON 输出"""
    with patch("nodes.planner.llm_tool") as mock_llm:
        mock_llm.chat = AsyncMock(return_value="这不是 JSON")

        from nodes.planner import planner

        state = {
            "question": "你好",
            "messages": [],
            "plan": {},
            "documents": [],
            "tool_results": {},
            "answer": "",
            "reflect": {},
            "metadata": {},
        }

        result = await planner(state)

        # 应该返回默认 plan
        assert "plan" in result
        assert "steps" in result["plan"]
