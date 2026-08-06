"""DP-C1 Extraction 编入 Stage 5 单测

验证：doc_pipeline 的 _process_single_document 在 Chunk 之后、Embedding 之前
调用知识抽取（build_knowledge_ingestion_graph + invoke_tracked），并把
entities/relations/facts/evidence 写入 KnowledgePackage 草稿。

验收标准（DP-C1）：一篇年报处理后 Package 草稿含非空 Entities/Relations/Facts/Evidence。

隔离策略：mock 全部外部依赖（postgres/minio/docling/embedding/qdrant/task_queue/
package_storage），并 mock 知识图谱构建与 invoke_tracked 返回固定 extraction 结果，
专门验证 pipeline 编排 + Package 落库链路（graph 内部正确性由其它测试覆盖）。
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipelines.document_pipeline import DocumentPipeline


# 模拟知识抽取图返回的固定结果（字段与 entity/relation/fact/evidence 节点输出契约一致）
EXTRACTION_RESULT = {
    "entities": [
        {
            "name": "腾讯控股",
            "entity_type": "company",
            "aliases": ["Tencent"],
            "properties": {"industry": "tech"},
        },
        {
            "name": "马化腾",
            "entity_type": "person",
            "aliases": [],
            "properties": {},
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
    "confidence_score": 0.9,
    "stored_entity_ids": [],
    "stored_fact_ids": [],
    "errors": [],
}


def _make_doc() -> dict:
    return {
        "id": uuid.uuid4(),
        "market": "cn",
        "symbol": "00700",
        "company": "腾讯控股",
        "year": 2024,
        "document_type": "annual_report",
        "bucket": "documents",
        "object_key": "cn/00700/annual_report/2024/report.pdf",
        "language": "zh",
        "metadata": {"acquire": {"source_type": "annual_report"}},
    }


def _make_markdown() -> str:
    return (
        "# 腾讯控股 2024 年度报告\n\n"
        "腾讯控股 2024 年度实现营业收入 6000 亿元，同比增长 10%。\n\n"
        "马化腾先生担任公司董事会主席。\n\n"
        "公司持续加大在人工智能领域的投入。\n"
    )


@pytest.fixture
def patched_pipeline():
    """mock 全部外部依赖，返回可断言 save_draft 收到的 package 的封装"""
    captured = {}

    async def fake_query(sql, *args, **kwargs):
        # chunks 断点续传检查 → 无 chunks；StageTracker.load 的 processing 查询 → 空
        if "COUNT(*) as cnt" in sql:
            return [{"cnt": 0}]
        return []

    async def fake_embed(texts, *args, **kwargs):
        return [[0.1] * 8 for _ in texts]

    with patch("pipelines.document_pipeline.postgres_tool") as pg, \
         patch("pipelines.document_pipeline.minio_tool") as minio, \
         patch("pipelines.document_pipeline.docling_tool") as docling, \
         patch("pipelines.document_pipeline.embedding_tool") as emb, \
         patch("pipelines.document_pipeline.qdrant_tool") as qdrant, \
         patch("pipelines.document_pipeline.task_queue") as task_queue, \
         patch("pipelines.document_pipeline.package_storage") as pkg_storage, \
         patch("graphs.knowledge_graph.build_knowledge_ingestion_graph") as build_graph, \
         patch("monitoring.agent_center.invoke_tracked") as invoke:
        pg.query = AsyncMock(side_effect=fake_query)
        pg.execute = AsyncMock(return_value=None)

        minio.download = AsyncMock(return_value=b"%PDF-1.4 fake")
        docling.convert_file = AsyncMock(return_value=_make_markdown())

        emb.embed = AsyncMock(side_effect=fake_embed)
        qdrant.upsert = AsyncMock(return_value=None)
        qdrant.delete_points = AsyncMock(return_value=None)

        task_queue.create_task = AsyncMock(return_value="task-1")
        task_queue.start_task = AsyncMock(return_value=None)
        task_queue.complete_task = AsyncMock(return_value=None)
        task_queue.update_progress = AsyncMock(return_value=None)
        task_queue.log_task = AsyncMock(return_value=None)
        task_queue.set_total_items = AsyncMock(return_value=None)

        async def fake_save_draft(package):
            captured["package"] = package
            return "pkg-1"

        pkg_storage.save_draft = AsyncMock(side_effect=fake_save_draft)

        build_graph.return_value = MagicMock(name="fake_graph")
        invoke.return_value = dict(EXTRACTION_RESULT)

        yield captured, pg, invoke, build_graph


@pytest.mark.asyncio
async def test_extraction_written_to_package_draft(patched_pipeline):
    """DP-C2 package 模式：年报处理后 Package 草稿含非空 Entities/Relations/Facts/Evidence"""
    captured, pg, invoke, build_graph = patched_pipeline

    doc = _make_doc()
    pipeline = DocumentPipeline()
    pipeline.extraction_mode = "package"  # DP-C2 切换到 package 通道
    result = await pipeline._process_single_document(doc, task_id=None)

    assert result == "indexed"
    # 知识抽取被调用且传入正确 agent_id
    invoke.assert_awaited_once()
    _, kwargs = invoke.call_args
    assert kwargs["agent_id"] == "knowledge_ingestion"

    package = captured.get("package")
    assert package is not None
    assert len(package.entities) == 2
    assert len(package.relations) == 1
    assert len(package.facts) == 1
    assert len(package.evidence) == 1

    # 关系/事实引用已解析为实体 id
    rel = package.relations[0]
    entity_names = {e.name for e in package.entities}
    assert rel.source_entity in {e.id for e in package.entities}
    assert rel.target_entity in {e.id for e in package.entities}
    fact = package.facts[0]
    assert fact.subject_entity in {e.id for e in package.entities}
    assert fact.object_value == 6000
    assert fact.unit == "亿元"
    assert fact.source_document == str(doc["id"])


@pytest.mark.asyncio
async def test_extraction_stage_recorded_in_processing(patched_pipeline):
    """Extraction 阶段应写入 processing.metadata.stages 且 status=success"""
    captured, pg, invoke, build_graph = patched_pipeline

    pipeline = DocumentPipeline()
    pipeline.extraction_mode = "package"
    await pipeline._process_single_document(_make_doc(), task_id=None)

    package = captured.get("package")
    stages = package.processing_metadata.stages
    stage_names = [s.stage for s in stages]
    assert "extraction" in stage_names
    # Extraction 位于 embedding 之前（八阶段顺序）
    assert stage_names.index("extraction") < stage_names.index("embedding")
    ext = next(s for s in stages if s.stage == "extraction")
    assert ext.status == "success"


@pytest.mark.asyncio
async def test_extraction_failure_non_fatal(patched_pipeline):
    """package 模式抽取失败自动回退 direct：不阻塞主流程，Package 草稿仍可生成（四项为空）"""
    captured, pg, invoke, build_graph = patched_pipeline

    invoke.side_effect = RuntimeError("graph down")

    pipeline = DocumentPipeline()
    pipeline.extraction_mode = "package"
    result = await pipeline._process_single_document(_make_doc(), task_id=None)

    assert result == "indexed"
    package = captured.get("package")
    assert package is not None
    assert package.entities == []
    assert package.relations == []
    assert package.facts == []
    assert package.evidence == []


@pytest.mark.asyncio
async def test_direct_mode_skips_inline_graph(patched_pipeline):
    """DP-C2 direct 模式：跳过内嵌图调用，四项为空（由独立任务直写 core.*）"""
    captured, pg, invoke, build_graph = patched_pipeline

    pipeline = DocumentPipeline()
    # 默认 extraction_mode=direct（policies.yaml 默认）；此处显式声明以作双向验证
    assert pipeline.extraction_mode == "direct"
    result = await pipeline._process_single_document(_make_doc(), task_id=None)

    assert result == "indexed"
    # direct 通道不调用内嵌图，也不构建知识图谱
    invoke.assert_not_awaited()
    build_graph.assert_not_called()

    package = captured.get("package")
    assert package is not None
    assert package.entities == []
    assert package.relations == []
    assert package.facts == []
    assert package.evidence == []

    # extraction 阶段仍被记录（链路完整），位于 embedding 之前
    stages = package.processing_metadata.stages
    stage_names = [s.stage for s in stages]
    assert "extraction" in stage_names
    assert stage_names.index("extraction") < stage_names.index("embedding")