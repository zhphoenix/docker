"""DP-B4 端到端验收：Processing Metadata 落库

验收点：
  1. 处理完一篇 annual_report 后，捕获 package_storage.save_draft 收到的 KnowledgePackage：
     - source_type == annual_report
     - processing_metadata.parser == docling
     - processing_metadata.routing_strategy == annual_report
     - embedding_model / llm_model / ocr_engine 已填充（非空）
     - processing_time 非空
     - stages 含 routing/parse/chunk/embedding 且全部 success
  2. 处理一篇 markdown general 文档：
     - source_type == general
     - processing_metadata.parser == direct
     - routing_strategy == general
  3. StageTracker 通过 jsonb_set 把 processing 写回 documents.metadata（persist 被调用）

说明：全部外部依赖（postgres/minio/docling/embedding/qdrant/task_queue/package_storage）
     均 mock，聚焦验证 processing 元数据构造与落库参数，不依赖真实 DB。
"""

import asyncio
import json
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

_LANGGRAPH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_LANGGRAPH))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(_LANGGRAPH).parent / ".env", override=False)

from config.settings import settings  # noqa: E402
from pipelines.document_pipeline import doc_pipeline  # noqa: E402


def _doc(key: str, document_type: str, source_type: str) -> dict:
    return {
        "id": "00000000-0000-0000-0000-00000000" + ("0001" if "pdf" in key else "0002"),
        "market": "cn",
        "symbol": "TEST",
        "company": "测试公司",
        "bucket": "documents",
        "object_key": key,
        "document_type": document_type,
        "year": 2025,
        "metadata": json.dumps({"acquire": {"source_type": source_type}}),
    }


@contextmanager
def _base_patches():
    """提供公共 mock，yield (pg, minio, pkg, tq)"""
    with ExitStack() as stack:
        pg = stack.enter_context(patch("pipelines.document_pipeline.postgres_tool"))
        minio = stack.enter_context(patch("pipelines.document_pipeline.minio_tool"))
        docling = stack.enter_context(patch("pipelines.document_pipeline.docling_tool"))
        docling.convert_file = AsyncMock(return_value="# 年报内容")
        stack.enter_context(patch(
            "pipelines.document_pipeline.chunk_markdown",
            return_value=[{"content": "内容", "heading": ""}],
        ))
        stack.enter_context(patch(
            "pipelines.document_pipeline.embedding_tool.embed",
            new=AsyncMock(return_value=[[0.1, 0.2]]),
        ))
        qdrant = stack.enter_context(patch("pipelines.document_pipeline.qdrant_tool"))
        qdrant.upsert = AsyncMock()
        tq = stack.enter_context(patch("pipelines.document_pipeline.task_queue"))
        tq.log_task = AsyncMock()
        tq.update_progress = AsyncMock()
        stack.enter_context(patch("runtime.queue.task_queue", tq))
        pkg = stack.enter_context(patch("pipelines.document_pipeline.package_storage"))
        pkg.save_draft = AsyncMock(return_value="pk-draft-1")
        yield pg, minio, docling, pkg, tq


async def verify_annual_report_metadata() -> bool:
    saved = {}
    with _base_patches() as (pg, minio, _docling, pkg, _tq):
        pg.query = AsyncMock(return_value=[])
        pg.execute = AsyncMock()
        minio.download = AsyncMock(return_value=b"%PDF-1.4 fake")

        async def _save(pkg_obj):
            saved["pkg"] = pkg_obj
            return "pk-draft-1"
        pkg.save_draft.side_effect = _save

        doc = _doc("cn/TEST/annual_report/2025/report.pdf",
                   "annual_report", "annual_report")
        result = await doc_pipeline._process_single_document(doc, "task-1", 1)

    assert result == "indexed", f"annual_report 应完成索引，实际 {result}"
    pkg_obj = saved["pkg"]
    pm = pkg_obj.processing_metadata
    assert pkg_obj.source_type.value == "annual_report", pkg_obj.source_type
    assert pm.parser == "docling", pm.parser
    assert pm.routing_strategy == "annual_report", pm.routing_strategy
    assert pm.embedding_model == settings.EMBEDDING_MODEL, pm.embedding_model
    assert pm.llm_model == settings.MODEL_NAME, pm.llm_model
    assert pm.ocr_engine == "paddleocr", pm.ocr_engine
    assert pm.processing_time is not None and pm.processing_time > 0, pm.processing_time
    stage_names = [s.stage for s in pm.stages]
    for name in ("routing", "parse", "chunk", "embedding"):
        assert name in stage_names, (name, stage_names)
    assert all(s.status == "success" for s in pm.stages), [s.status for s in pm.stages]
    print("[PASS] annual_report → processing 元数据落库（docling/embedding/llm/ocr/routing + 阶段全 success）")
    return True


async def verify_general_metadata() -> bool:
    saved = {}
    with _base_patches() as (pg, minio, _docling, pkg, _tq):
        pg.query = AsyncMock(return_value=[])
        pg.execute = AsyncMock()
        minio.download = AsyncMock(
            return_value="# 标题\n\n正文内容 markdown".encode("utf-8")
        )

        async def _save(pkg_obj):
            saved["pkg"] = pkg_obj
            return "pk-draft-2"
        pkg.save_draft.side_effect = _save

        doc = _doc("cn/TEST/2025/note.md", "markdown", "markdown")
        result = await doc_pipeline._process_single_document(doc, "task-2", 1)

    assert result == "indexed", f"markdown 应完成索引，实际 {result}"
    pkg_obj = saved["pkg"]
    pm = pkg_obj.processing_metadata
    assert pkg_obj.source_type.value == "general", pkg_obj.source_type
    assert pm.parser == "direct", pm.parser
    assert pm.routing_strategy == "general", pm.routing_strategy
    print("[PASS] general/markdown → source_type=general, parser=direct")
    return True


async def verify_persist_jsonb_set() -> bool:
    """StageTracker 通过 jsonb_set 写回 documents.metadata.processing"""
    execute_calls = []
    with _base_patches() as (pg, minio, _docling, pkg, _tq):
        pg.query = AsyncMock(return_value=[])

        async def _execute(sql, *args, **kwargs):
            execute_calls.append(sql)
        pg.execute = _execute
        pkg.save_draft = AsyncMock(return_value="pk-draft-3")
        minio.download = AsyncMock(return_value=b"%PDF-1.4 fake")

        doc = _doc("cn/TEST/annual_report/2025/report.pdf",
                   "annual_report", "annual_report")
        await doc_pipeline._process_single_document(doc, "task-3", 1)

    jsonb_sets = [s for s in execute_calls if "jsonb_set" in s and "'{processing}'" in s]
    assert jsonb_sets, "应存在 jsonb_set ... '{processing}' 的 persist 写回"
    print("[PASS] StageTracker 通过 jsonb_set + '{processing}' 写回 documents.metadata")
    return True


async def main() -> int:
    await verify_annual_report_metadata()
    await verify_general_metadata()
    await verify_persist_jsonb_set()
    print("\n[DP-B4] Processing Metadata 落库端到端验收全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))