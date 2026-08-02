"""Retrieve Node 单元测试"""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_retrieve_returns_documents():
    """测试 Retrieve 返回文档列表"""
    with patch("rag_nodes.retrieve.embedding_tool") as mock_emb, \
         patch("rag_nodes.retrieve.qdrant_tool") as mock_qdrant:

        mock_emb.embed = AsyncMock(return_value=[[0.1] * 2560])
        mock_qdrant.search = AsyncMock(return_value=[
            {
                "id": "1",
                "score": 0.9,
                "payload": {
                    "content": "测试内容",
                    "source": "documents/cn/600519/annual_report/2025/report.pdf",
                    "market": "cn",
                    "symbol": "600519",
                    "year": 2025,
                },
            }
        ])

        from rag_nodes.retrieve import retrieve

        state = {
            "question": "分析贵州茅台",
            "messages": [],
            "plan": {"market": "cn", "symbol": "600519"},
            "documents": [],
            "tool_results": {},
            "answer": "",
            "reflect": {},
            "metadata": {},
        }

        result = await retrieve(state)

        assert "documents" in result
        assert len(result["documents"]) == 1
        assert result["documents"][0]["content"] == "测试内容"


@pytest.mark.asyncio
async def test_retrieve_empty_results():
    """测试 Retrieve 无结果时返回空列表"""
    with patch("rag_nodes.retrieve.embedding_tool") as mock_emb, \
         patch("rag_nodes.retrieve.qdrant_tool") as mock_qdrant:

        mock_emb.embed = AsyncMock(return_value=[[0.1] * 2560])
        mock_qdrant.search = AsyncMock(return_value=[])

        from rag_nodes.retrieve import retrieve

        state = {
            "question": "不存在的内容",
            "messages": [],
            "plan": {},
            "documents": [],
            "tool_results": {},
            "answer": "",
            "reflect": {},
            "metadata": {},
        }

        result = await retrieve(state)

        assert "documents" in result
        assert len(result["documents"]) == 0
