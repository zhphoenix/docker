"""匹配防误配回归测试（消费股不得误匹配到光模块等无关概念）

背景：graphrag_search 曾无向量相似度阈值，低相关结果（如查询"茅台"
时检索出"光模块"实体）会直接进入 LLM 推理证据，导致幻觉关联。

本测试覆盖：
  1. graphrag_search 对低分向量证据的过滤（双保险：阈值 + 组装过滤）
  2. qdrant search/parallel_search 正确透传 score_threshold
  3. 阈值常量的合理性
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from server.tools import graph as graph_module
from server.storage import qdrant as qdrant_module


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


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


def _ent(name: str, score: float) -> dict:
    return {
        "id": name,
        "score": score,
        "payload": {"name": name, "entity_type": "concept", "description": f"{name}描述"},
    }


class TestVectorEvidenceGuard:
    """graphrag_search 不得把低相似度实体作为推理证据"""

    def test_maotai_query_must_not_include_optical_module_evidence(self, mcp):
        """回归用例：查询"茅台"时，低分"光模块"实体不得出现在证据或 prompt 中"""
        graph_module.register_graph_tools(mcp)
        graphrag_search = mcp._registered["graphrag_search"]

        fake_pg = MagicMock()
        fake_pg.find_entity_by_name = AsyncMock(return_value=[{"id": 1, "name": "贵州茅台"}])
        fake_pg.get_entity_graph = AsyncMock(return_value=[])

        # 向量检索返回：茅台(高分) + 光模块(低分 0.21)
        fake_qdrant = MagicMock()
        fake_qdrant.parallel_search = AsyncMock(return_value={
            qdrant_module.COLLECTION_ENTITIES: [
                _ent("贵州茅台", 0.82),
                _ent("光模块", 0.21),
            ],
            qdrant_module.COLLECTION_FACTS: [
                {"id": "f1", "score": 0.19, "payload": {
                    "subject_name": "光模块", "predicate": "属于",
                    "object_value": "AI硬件", "time_start": "",
                }},
            ],
        })

        fake_llm = MagicMock()
        captured_prompts = []

        async def fake_chat(messages, temperature=0.1):
            captured_prompts.append(messages[-1]["content"])
            return {"choices": [{"message": {"content": '{"summary": "ok", "key_findings": []}'}}]}

        fake_llm.chat = AsyncMock(side_effect=fake_chat)

        with patch.object(graph_module, "pg_storage", fake_pg), \
             patch.object(graph_module, "qdrant_storage", fake_qdrant), \
             patch.object(graph_module, "llm_client", fake_llm):
            result = _run(graphrag_search(query="茅台的护城河如何？"))

        # 证据集不得包含光模块
        evidence_names = [e.get("name") for e in result["evidence"]["vector"] if e["kind"] == "entity"]
        assert "贵州茅台" in evidence_names
        assert "光模块" not in evidence_names, "低分实体'光模块'不应进入证据集"
        fact_subjects = [e.get("subject") for e in result["evidence"]["vector"] if e["kind"] == "fact"]
        assert "光模块" not in fact_subjects, "低分事实'光模块'不应进入证据集"

        # LLM prompt 也不得包含光模块（防止幻觉关联）
        assert all("光模块" not in p for p in captured_prompts)

    def test_search_forwards_score_threshold(self, mcp):
        """parallel_search 必须收到 graphrag_search 传入的相似度阈值"""
        graph_module.register_graph_tools(mcp)
        graphrag_search = mcp._registered["graphrag_search"]

        fake_pg = MagicMock()
        fake_pg.find_entity_by_name = AsyncMock(return_value=[])
        fake_qdrant = MagicMock()
        fake_qdrant.parallel_search = AsyncMock(return_value={
            qdrant_module.COLLECTION_ENTITIES: [],
            qdrant_module.COLLECTION_FACTS: [],
        })
        fake_llm = MagicMock()
        fake_llm.chat = AsyncMock(
            return_value={"choices": [{"message": {"content": '{"summary": "", "key_findings": []}'}}]}
        )

        with patch.object(graph_module, "pg_storage", fake_pg), \
             patch.object(graph_module, "qdrant_storage", fake_qdrant), \
             patch.object(graph_module, "llm_client", fake_llm):
            _run(graphrag_search(query="茅台"))

        kwargs = fake_qdrant.parallel_search.call_args.kwargs
        assert kwargs.get("score_threshold") == graph_module.VECTOR_EVIDENCE_MIN_SCORE


class TestThresholdConstants:
    def test_min_score_is_reasonable(self):
        """阈值过低会放行无关概念，过高会误杀相关证据；0.5~0.7 为合理区间"""
        assert 0.5 <= graph_module.VECTOR_EVIDENCE_MIN_SCORE <= 0.7

    def test_qdrant_search_accepts_score_threshold_param(self):
        """search() 签名必须支持 score_threshold（透传给 Qdrant query_points）"""
        storage = qdrant_module.QdrantStorage.__new__(qdrant_module.QdrantStorage)
        fake_client = MagicMock()
        fake_client.query_points.return_value = MagicMock(points=[])
        storage._get_qdrant_client = MagicMock(return_value=fake_client)

        _run(storage.search(
            collection="entities", vector=[0.1, 0.2], limit=5, score_threshold=0.5,
        ))
        kwargs = fake_client.query_points.call_args.kwargs
        assert kwargs["score_threshold"] == 0.5
