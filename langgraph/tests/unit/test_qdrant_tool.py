"""Qdrant Tool 单元测试"""

import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.asyncio
async def test_qdrant_search():
    """测试 Qdrant 搜索"""
    with patch("tools.qdrant.QdrantClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client

        # Mock search 返回
        mock_result = MagicMock()
        mock_result.id = "1"
        mock_result.score = 0.9
        mock_result.payload = {"content": "test"}
        mock_client.search.return_value = [mock_result]

        from tools.qdrant import QdrantTool
        tool = QdrantTool()

        results = await tool.search("documents_cn", [0.1] * 2560)

        assert len(results) == 1
        assert results[0]["score"] == 0.9
        assert results[0]["payload"]["content"] == "test"


@pytest.mark.asyncio
async def test_qdrant_search_empty():
    """测试 Qdrant 搜索无结果"""
    with patch("tools.qdrant.QdrantClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.search.return_value = []

        from tools.qdrant import QdrantTool
        tool = QdrantTool()

        results = await tool.search("documents_cn", [0.1] * 2560)

        assert len(results) == 0
