"""KOC-C2 统一搜索入口（Hybrid Search）单元测试

验证：
  1. _fulltext_search 三通道查询（实体/文档/事件，Postgres ILIKE）
  2. /search 统一响应：Entity/Fact/Event/Document 混合结果 + source_channels 标注
  3. vector 与 fulltext 命中同一实体时去重合并（vector 优先）
  4. 兼容字段保留（graph_results / vector_results / entity_ids_used）

隔离策略：mock postgres_tool / knowledge_qdrant / knowledge_storage。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import knowledge as api


@pytest.fixture
def mock_deps():
    """mock 三个外部依赖，返回可控数据"""
    with patch("api.knowledge.postgres_tool") as pg, \
         patch("api.knowledge.knowledge_qdrant") as qdrant, \
         patch("api.knowledge.knowledge_storage") as storage:
        # 默认：无图检索、向量空、全文空
        storage.find_entity_by_name = AsyncMock(return_value=[])
        qdrant.hybrid_search = AsyncMock(return_value={"entities": [], "facts": []})
        pg.query = AsyncMock(return_value=[])
        yield pg, qdrant, storage


# ── _fulltext_search ────────────────────────────────────────


@pytest.mark.asyncio
async def test_fulltext_search_three_channels(mock_deps):
    """全文检索三通道：实体/文档/事件分别查询"""
    pg, _qdrant, _storage = mock_deps
    pg.query.side_effect = [
        [{"id": "e1", "name": "药明康德", "entity_type": "Company", "description": "CXO"}],
        [{"id": "d1", "title": "药明康德年报", "document_type": "annual_report", "source": "stock_a"}],
        [{"id": "ev1", "title": "药明康德发布年报", "event_type": "report", "event_date": "2025-04-01", "description": "发布"}],
    ]

    result = await api._fulltext_search("药明康德", limit=5)

    assert pg.query.await_count == 3
    # 实体查询
    sql0 = pg.query.await_args_list[0].args[0]
    assert "core.entities" in sql0 and "ILIKE $1" in sql0
    assert pg.query.await_args_list[0].args[1] == "%药明康德%"
    # 文档查询
    sql1 = pg.query.await_args_list[1].args[0]
    assert "document.documents" in sql1
    # 事件查询
    sql2 = pg.query.await_args_list[2].args[0]
    assert "core.events" in sql2
    assert result["entities"][0]["name"] == "药明康德"
    assert result["documents"][0]["title"] == "药明康德年报"
    assert result["events"][0]["event_date"] == "2025-04-01"


@pytest.mark.asyncio
async def test_fulltext_search_degrades_on_error(mock_deps):
    """单通道失败不影响其他通道（独立 try/except）"""
    pg, _qdrant, _storage = mock_deps
    pg.query.side_effect = [Exception("boom"), [], []]

    result = await api._fulltext_search("query", limit=3)

    assert result["entities"] == []
    assert result["documents"] == []
    assert result["events"] == []


# ── /search 统一响应 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_unified_response(mock_deps):
    """统一响应：四类结果 + source_channels 标注 + 兼容字段"""
    pg, qdrant, storage = mock_deps
    # 向量：实体 + 事实
    qdrant.hybrid_search = AsyncMock(
        return_value={
            "entities": [
                {"id": "e1", "score": 0.92, "payload": {"name": "药明康德", "entity_type": "Company", "description": "CXO 龙头"}}
            ],
            "facts": [
                {"id": "f1", "score": 0.88, "payload": {"subject_name": "药明康德", "predicate": "营收", "object_value": "400亿", "time_start": "2025-12-31"}}
            ],
        }
    )
    # 全文：事件 + 文档 + 实体（与 vector 同 id → 应合并）
    pg.query.side_effect = [
        [{"id": "e1", "name": "药明康德", "entity_type": "Company", "description": None}],
        [{"id": "d1", "title": "药明康德年报", "document_type": "annual_report", "source": "stock_a"}],
        [{"id": "ev1", "title": "药明康德年报发布", "event_type": "report", "event_date": "2025-04-01", "description": "发布"}],
    ]

    resp = await api.hybrid_search(
        MagicMock(query="药明康德", entity_name="", limit=5)
    )

    # 四类结果齐全
    r = resp["results"]
    assert len(r["entities"]) == 1
    assert len(r["facts"]) == 1
    assert len(r["events"]) == 1
    assert len(r["documents"]) == 1

    # 来源通道标注
    assert r["entities"][0]["source_channels"] == ["fulltext", "vector"]
    assert r["facts"][0]["source_channels"] == ["vector"]
    assert r["events"][0]["source_channels"] == ["fulltext"]
    assert r["documents"][0]["source_channels"] == ["fulltext"]

    # vector 优先：description 保留 vector 的较全值
    assert r["entities"][0]["description"] == "CXO 龙头"
    assert r["entities"][0]["score"] == 0.92

    # source_channels 顶层汇总
    assert resp["source_channels"]["vector"] is True
    assert resp["source_channels"]["fulltext"] is True
    assert resp["source_channels"]["graph"] is False

    # 兼容字段保留
    assert resp["graph_results"] == []
    assert resp["vector_results"]["entities"][0]["score"] == 0.92
    assert resp["entity_ids_used"] == []


@pytest.mark.asyncio
async def test_search_fulltext_only_entity(mock_deps):
    """仅全文命中时实体标注 fulltext 通道（无 vector 合并）"""
    pg, qdrant, storage = mock_deps
    qdrant.hybrid_search = AsyncMock(return_value={"entities": [], "facts": []})
    pg.query.side_effect = [
        [{"id": "e2", "name": "宁德时代", "entity_type": "Company", "description": "电池"}],
        [], [],
    ]

    resp = await api.hybrid_search(
        MagicMock(query="宁德时代", entity_name="", limit=5)
    )

    ents = resp["results"]["entities"]
    assert len(ents) == 1
    assert ents[0]["source_channels"] == ["fulltext"]
    assert ents[0]["score"] is None


@pytest.mark.asyncio
async def test_search_with_graph_channel(mock_deps):
    """entity_name 提供时触发图通道（graph_results 非空 + graph 标志）"""
    pg, qdrant, storage = mock_deps
    storage.find_entity_by_name = AsyncMock(
        return_value=[{"id": "e1", "name": "腾讯"}]
    )
    graph_rows = [
        {"source_entity": "e1", "target_entity": "e2", "source_name": "腾讯",
         "target_name": "阿里巴巴", "relation_type": "competes_with", "depth": 1}
    ]
    storage.get_entity_neighbors = AsyncMock(return_value=graph_rows)
    qdrant.hybrid_search = AsyncMock(return_value={"entities": [], "facts": []})
    pg.query.side_effect = [[], [], []]

    resp = await api.hybrid_search(
        MagicMock(query="腾讯", entity_name="腾讯", limit=5)
    )

    assert resp["source_channels"]["graph"] is True
    assert len(resp["graph_results"]) == 1
    assert resp["graph_results"][0]["target_name"] == "阿里巴巴"
    assert resp["entity_ids_used"] == ["e1"]