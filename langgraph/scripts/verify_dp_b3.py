"""DP-B3 端到端验收：Routing 策略在真实管道链路生效

验收点：
  1. annual_report 文档（acquire.source_type=annual_report）→ 选择 docling 解析器
     （调用 docling_tool.convert_file，且 MinIO 下载返回的原始 bytes 交给 docling）
  2. markdown 文档 → 选择 direct 解析（直接 decode 文本，不调用 docling）
  3. routing 阶段日志写入 task_queue
  4. 录制 routing 决策日志，验证 routing 阶段在 parse 之前发生

说明：全部外部依赖（postgres/minio/docling/embedding/qdrant/task_queue）均 mock，
      聚焦验证 routing 决策与解析器选择，不依赖真实 DB。
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

from pipelines.document_pipeline import doc_pipeline  # noqa: E402


def _doc(key: str, document_type: str, source_type: str) -> dict:
    return {
        "id": "00000000-0000-0000-0000-00000000" + ("0001" if "pdf" in key else "0002"),
        "market": "cn",
        "symbol": "TEST",
        "bucket": "documents",
        "object_key": key,
        "document_type": document_type,
        "year": 2025,
        "metadata": json.dumps({"acquire": {"source_type": source_type}}),
    }


@contextmanager
def _base_patches():
    """提供公共 mock（pg, minio, docling, chunk, embed, qdrant, tq）"""
    with ExitStack() as stack:
        pg = stack.enter_context(patch("pipelines.document_pipeline.postgres_tool"))
        minio = stack.enter_context(patch("pipelines.document_pipeline.minio_tool"))
        docling = stack.enter_context(patch("pipelines.document_pipeline.docling_tool"))
        stack.enter_context(patch(
            "pipelines.document_pipeline.chunk_markdown",
            return_value=[{"content": "内容", "heading": ""}],
        ))
        embed = stack.enter_context(patch(
            "pipelines.document_pipeline.embedding_tool.embed",
            new=AsyncMock(return_value=[[0.1, 0.2]]),
        ))
        qdrant = stack.enter_context(patch("pipelines.document_pipeline.qdrant_tool"))
        qdrant.upsert = AsyncMock()
        tq = stack.enter_context(patch("pipelines.document_pipeline.task_queue"))
        tq.log_task = AsyncMock()
        tq.update_progress = AsyncMock()
        # StageTracker（DP-B4）内部延迟导入 runtime.queue.task_queue，需一并 patch
        stack.enter_context(patch("runtime.queue.task_queue", tq))
        # DP-B4 _save_package_draft 落库路径，避免真实 DB
        pkg = stack.enter_context(patch("pipelines.document_pipeline.package_storage"))
        pkg.save_draft = AsyncMock(return_value="00000000-0000-0000-0000-0000000000aa")
        yield pg, minio, docling, tq



async def verify_annual_report_uses_docling() -> bool:
    calls = {"convert": 0}
    with _base_patches() as (pg, minio, docling, _tq):
        pg.query = AsyncMock(return_value=[])          # 无已有 chunks
        pg.execute = AsyncMock()
        minio.download = AsyncMock(return_value=b"%PDF-1.4 fake pdf bytes")
        docling.convert_file = AsyncMock(
            side_effect=lambda data, fn: calls.update(
                convert=calls["convert"] + 1
            ) or "# 年报内容"
        )

        doc = _doc("cn/TEST/annual_report/2025/report.pdf",
                   "annual_report", "annual_report")
        result = await doc_pipeline._process_single_document(doc, "task-1", 1)

    assert result == "indexed", f"annual_report 应完成索引，实际 {result}"
    assert calls["convert"] == 1, "annual_report 应调用 docling convert_file"
    print("[PASS] annual_report → docling 解析器")
    return True


async def verify_markdown_uses_direct() -> bool:
    with _base_patches() as (pg, minio, docling, _tq):
        pg.query = AsyncMock(return_value=[])
        pg.execute = AsyncMock()
        minio.download = AsyncMock(
            return_value="# 标题\n\n正文内容 markdown".encode("utf-8")
        )
        docling.convert_file = AsyncMock()

        doc = _doc("cn/TEST/2025/note.md", "markdown", "markdown")
        result = await doc_pipeline._process_single_document(doc, "task-2", 1)

    assert result == "indexed", f"markdown 应完成索引，实际 {result}"
    assert docling.convert_file.call_count == 0, "markdown 不应调用 docling"
    print("[PASS] markdown → direct 直接解码（跳过 docling）")
    return True


async def verify_routing_stage_logged() -> bool:
    log_calls: list[tuple] = []
    with _base_patches() as (pg, minio, docling, tq):
        pg.query = AsyncMock(return_value=[])
        pg.execute = AsyncMock()
        minio.download = AsyncMock(return_value=b"%PDF-1.4")
        docling.convert_file = AsyncMock(return_value="# 年报")

        # 捕获 task_queue.log_task 调用
        async def _log(task_id, level, message, stage):
            log_calls.append((task_id, level, message, stage))
        tq.log_task.side_effect = _log

        doc = _doc("cn/TEST/annual_report/2025/report.pdf",
                   "annual_report", "annual_report")
        await doc_pipeline._process_single_document(doc, "task-3", 1)

    stages = [c[3] for c in log_calls]
    assert "routing" in stages, f"应记录 routing 阶段日志，实际 stages={stages}"
    routing_idx = stages.index("routing")
    parse_idx = stages.index("parse")
    assert routing_idx < parse_idx, "routing 阶段日志应先于 parse"
    print("[PASS] routing 阶段日志写入，且先于 parse 阶段")
    return True


async def main() -> int:
    await verify_annual_report_uses_docling()
    await verify_markdown_uses_direct()
    await verify_routing_stage_logged()
    print("\n[DP-B3] Routing 策略端到端验收全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))