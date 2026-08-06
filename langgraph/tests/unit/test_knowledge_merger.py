"""DP-C3 Merger 解耦单测

验证：knowledge_merger 写入目标可注入（Package 草稿 or core.*）。
  - 默认 CoreMergerStorage 直写 core.*（现状回归）
  - 注入 PackageDraftMergerStorage 时写 KnowledgePackage 草稿
  - 两种模式下低置信实体仍进 knowledge_inbox（HITL 触发逻辑保持不变）

隔离策略：mock 全部外部依赖（embedding/qdrant/age/approval/policy/knowledge_storage），
专门验证 merger 编排 + 写入目标注入。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nodes.knowledge.merger import (
    CoreMergerStorage,
    PackageDraftMergerStorage,
    knowledge_merger,
)
from schemas.knowledge_package import KnowledgePackage, SourceMetadata, SourceType


def _make_state() -> dict:
    return {
        "document_id": "11111111-2222-3333-4444-555555555555",
        "source_metadata": {
            "source": "annual_report",
            "document_type": "annual_report",
        },
        "entities": [
            {
                "name": "腾讯控股",
                "entity_type": "company",
                "description": "互联网科技公司",
                "aliases": ["Tencent"],
                "properties": {"industry": "tech"},
                "confidence": 0.9,
            },
            {
                "name": "马化腾",
                "entity_type": "person",
                "description": "董事会主席",
                "aliases": [],
                "properties": {},
                "confidence": 0.5,  # 低置信度 → 应进 READY_REVIEW
            },
        ],
        "relations": [
            {
                "source": "腾讯控股",
                "target": "马化腾",
                "relation_type": "owns",
                "confidence": 0.9,
                "properties": {},
            },
        ],
        "facts": [
            {
                "subject": "腾讯控股",
                "predicate": "营收",
                "object_value": 6000,
                "unit": "亿元",
                "confidence": 0.9,
            },
        ],
        "evidence": [
            {
                "location": "chunk_1",
                "quote": "2024年度营收6000亿元",
                "confidence": 0.9,
            },
        ],
        "entity_embeddings": [[0.1] * 8, [0.2] * 8],  # 复用 Validator 缓存，避免重复 embed
    }


@pytest.fixture
def patched_deps():
    """mock 全部外部依赖，返回 knowledge_storage mock 供断言"""
    with patch("nodes.knowledge.merger.embedding_tool") as emb, \
         patch("nodes.knowledge.merger.knowledge_qdrant") as qdrant, \
         patch("nodes.knowledge.merger.knowledge_age") as age, \
         patch("nodes.knowledge.merger.create_approval") as approval, \
         patch("nodes.knowledge.merger.get_policy") as get_policy, \
         patch("nodes.knowledge.merger.knowledge_storage") as ks:
        emb.embed = AsyncMock(return_value=[[0.1] * 8, [0.2] * 8])
        qdrant.index_entities = AsyncMock(return_value=None)
        qdrant.index_facts = AsyncMock(return_value=None)
        age.available = False  # 跳过 AGE 同步
        approval.side_effect = AsyncMock(return_value="approval-1")
        get_policy.return_value = 0.85

        # 无已存在实体、无向量相似 → 全部按新建处理
        ks.find_entities_by_names = AsyncMock(return_value=[])
        ks.search_entity_by_embedding = AsyncMock(return_value=[])
        ks.bulk_upsert_entities = AsyncMock(return_value=["e-1", "e-2"])
        ks.bulk_insert_relations = AsyncMock(return_value=["r-1"])
        ks.bulk_insert_facts = AsyncMock(return_value=["f-1"])
        ks.bulk_insert_evidence = AsyncMock(return_value=None)
        ks.insert_inbox = AsyncMock(return_value="inbox-1")
        ks.update_inbox_status = AsyncMock(return_value=None)

        yield ks


@pytest.mark.asyncio
async def test_merger_default_writes_core(patched_deps):
    """默认 CoreMergerStorage：直写 core.*，低置信实体进 READY_REVIEW"""
    ks = patched_deps

    result = await knowledge_merger(_make_state())

    # core.* 写入被调用
    ks.bulk_upsert_entities.assert_awaited_once()
    records = ks.bulk_upsert_entities.await_args.args[0]
    assert len(records) == 2
    ks.bulk_insert_relations.assert_awaited_once()
    ks.bulk_insert_facts.assert_awaited_once()

    assert len(result["stored_entity_ids"]) == 2

    # 低置信实体（马化腾 0.5）→ READY_REVIEW 并创建人工审批
    assert ks.insert_inbox.await_count == 2
    assert ks.update_inbox_status.await_count == 2
    # 高置信（腾讯控股 0.9, annual_report 可信源）自动 APPROVED；低置信 READY_REVIEW
    # status 以位置参数传入（args[1]）
    approved_calls = [c for c in ks.update_inbox_status.await_args_list if c.args[1] == "APPROVED"]
    review_calls = [c for c in ks.update_inbox_status.await_args_list if c.args[1] == "READY_REVIEW"]
    assert len(approved_calls) == 1
    assert len(review_calls) == 1


@pytest.mark.asyncio
async def test_merger_package_draft_backend(patched_deps):
    """注入 PackageDraftMergerStorage：写 Package 草稿，core.* 写入不被调用，低置信实体仍进 inbox"""
    ks = patched_deps

    package = KnowledgePackage(
        id="pkg-1",
        source_type=SourceType.ANNUAL_REPORT,
        source=SourceMetadata(source_type=SourceType.ANNUAL_REPORT, source_id="00700"),
    )
    storage = PackageDraftMergerStorage(package, core_storage=ks)

    result = await knowledge_merger(_make_state(), storage=storage)

    # core.* 的 bulk 写入不被调用（写入目标切到草稿）
    ks.bulk_upsert_entities.assert_not_awaited()
    ks.bulk_insert_relations.assert_not_awaited()
    ks.bulk_insert_facts.assert_not_awaited()

    # Package 草稿四项非空
    assert len(package.entities) == 2
    assert len(package.relations) == 1
    assert len(package.facts) == 1
    assert len(package.evidence) == 1

    # 关系/事实引用解析为草稿实体 id
    entity_ids = {e.id for e in package.entities}
    assert package.relations[0].source_entity in entity_ids
    assert package.relations[0].target_entity in entity_ids
    assert package.facts[0].subject_entity in entity_ids
    assert package.facts[0].source_document == _make_state()["document_id"]

    # 返回的 id 列表与草稿一致
    assert len(result["stored_entity_ids"]) == 2

    # 低置信实体仍进 knowledge_inbox（HITL 不变）
    assert ks.insert_inbox.await_count == 2
    review_calls = [c for c in ks.update_inbox_status.await_args_list if c.args[1] == "READY_REVIEW"]
    assert len(review_calls) == 1


@pytest.mark.asyncio
async def test_merger_low_confidence_goes_to_inbox_both_modes(patched_deps):
    """两种写入模式下低置信实体均进入 knowledge_inbox READY_REVIEW"""
    ks = patched_deps

    # mode 1: default core
    await knowledge_merger(_make_state())
    core_review = [c for c in ks.update_inbox_status.await_args_list if c.args[1] == "READY_REVIEW"]
    assert len(core_review) == 1

    ks.reset_mock()
    ks.find_entities_by_names = AsyncMock(return_value=[])
    ks.search_entity_by_embedding = AsyncMock(return_value=[])
    ks.insert_inbox = AsyncMock(return_value="inbox-1")
    ks.update_inbox_status = AsyncMock(return_value=None)

    # mode 2: package draft
    package = KnowledgePackage(
        id="pkg-2",
        source_type=SourceType.ANNUAL_REPORT,
        source=SourceMetadata(source_type=SourceType.ANNUAL_REPORT, source_id="00700"),
    )
    await knowledge_merger(_make_state(), storage=PackageDraftMergerStorage(package, core_storage=ks))
    draft_review = [c for c in ks.update_inbox_status.await_args_list if c.args[1] == "READY_REVIEW"]
    assert len(draft_review) == 1

    # 草稿模式下低置信实体仍写入 inbox
    assert ks.insert_inbox.await_count == 2