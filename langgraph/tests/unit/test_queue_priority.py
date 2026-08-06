"""DP-D4 优先级队列单元测试

验证：
  1. create_task 支持 high/normal/low 三级字符串优先级（映射 10/0/-10）
  2. 整数优先级直传；未知字符串回退 normal(0)；默认不传为 normal(0)
  3. get_pending_tasks 按 priority DESC, created_at ASC 排序（HIGH 优先被 Worker 认领）
  4. document_pipeline 按批内文档类型设置优先级：纯年报=LOW，混合=NORMAL

隔离策略：mock postgres_tool（queue）与 task_queue + _process_single_document（pipeline）。
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from pipelines.document_pipeline import DocumentPipeline
from runtime.queue import PRIORITY_LEVELS, TaskQueue, task_queue


def _make_doc(document_type: str = "annual_report") -> dict:
    return {
        "id": uuid.uuid4(),
        "market": "cn",
        "symbol": "00700",
        "company": "腾讯控股",
        "year": 2024,
        "document_type": document_type,
        "bucket": "documents",
        "object_key": "cn/00700/annual_report/2024/report.pdf",
        "language": "zh",
        "metadata": {"acquire": {"source_type": "annual_report"}},
    }


# ─── queue.create_task 优先级映射 ─────────────────────────────


@pytest.mark.asyncio
async def test_create_task_priority_string_maps_to_levels():
    """字符串优先级映射：high→10 / normal→0 / low→-10"""
    with patch("runtime.queue.postgres_tool") as pg:
        pg.execute = AsyncMock(return_value=None)
        q = TaskQueue()

        for level, expected in (("high", 10), ("normal", 0), ("low", -10)):
            await q.create_task("doc_pipeline", f"t-{level}", priority=level)
            args = pg.execute.await_args.args
            assert args[7] == expected, f"{level} 应映射为 {expected}"

        assert PRIORITY_LEVELS == {"high": 10, "normal": 0, "low": -10}


@pytest.mark.asyncio
async def test_create_task_priority_int_passthrough():
    """整数优先级直传（不映射）"""
    with patch("runtime.queue.postgres_tool") as pg:
        pg.execute = AsyncMock(return_value=None)
        await task_queue.create_task("doc_pipeline", "t", priority=5)
        assert pg.execute.await_args.args[7] == 5


@pytest.mark.asyncio
async def test_create_task_default_priority_normal():
    """不传 priority 时默认 normal(0)，兼容既有调用方"""
    with patch("runtime.queue.postgres_tool") as pg:
        pg.execute = AsyncMock(return_value=None)
        await task_queue.create_task("doc_pipeline", "t")
        assert pg.execute.await_args.args[7] == 0


def test_normalize_priority_unknown_falls_back_normal():
    """未知字符串回退 normal(0)；非 int/str 类型回退 0"""
    assert TaskQueue._normalize_priority("urgent") == 0
    assert TaskQueue._normalize_priority(None) == 0
    assert TaskQueue._normalize_priority(3.7) == 0


@pytest.mark.asyncio
async def test_get_pending_tasks_orders_by_priority_desc():
    """pending 任务按 priority DESC, created_at ASC 排序（HIGH 先被认领）"""
    with patch("runtime.queue.postgres_tool") as pg:
        pg.query = AsyncMock(return_value=[])
        await task_queue.get_pending_tasks(limit=1)
        sql = pg.query.await_args.args[0]
        assert "ORDER BY priority DESC, created_at ASC" in sql


# ─── document_pipeline 按文档类型设优先级 ─────────────────────


@pytest.mark.asyncio
async def test_process_pending_annual_report_batch_low_priority():
    """纯年报批处理 → 任务优先级 LOW（不挤占实时任务）"""
    docs = [_make_doc() for _ in range(3)]
    captured = {}

    with patch("pipelines.document_pipeline.postgres_tool") as pg, \
         patch("pipelines.document_pipeline.task_queue") as tq, \
         patch.object(DocumentPipeline, "_process_single_document",
                      new=AsyncMock(return_value="indexed")):
        pg.query = AsyncMock(return_value=docs)
        pg.execute = AsyncMock(return_value=None)
        tq.create_task = AsyncMock(side_effect=lambda **kw: captured.update(kw) or "task-1")
        tq.start_task = AsyncMock(return_value=None)
        tq.complete_task = AsyncMock(return_value=None)
        tq.update_progress = AsyncMock(return_value=None)
        tq.log_task = AsyncMock(return_value=None)

        pipe = DocumentPipeline()
        stats = await pipe.process_pending_documents(limit=10)

    assert stats["processed"] == 3
    assert captured["priority"] == "low"


@pytest.mark.asyncio
async def test_process_pending_mixed_batch_normal_priority():
    """混合批次（含非年报）→ 任务优先级 NORMAL"""
    docs = [_make_doc("annual_report"), _make_doc("markdown")]
    captured = {}

    with patch("pipelines.document_pipeline.postgres_tool") as pg, \
         patch("pipelines.document_pipeline.task_queue") as tq, \
         patch.object(DocumentPipeline, "_process_single_document",
                      new=AsyncMock(return_value="indexed")):
        pg.query = AsyncMock(return_value=docs)
        pg.execute = AsyncMock(return_value=None)
        tq.create_task = AsyncMock(side_effect=lambda **kw: captured.update(kw) or "task-1")
        tq.start_task = AsyncMock(return_value=None)
        tq.complete_task = AsyncMock(return_value=None)
        tq.update_progress = AsyncMock(return_value=None)
        tq.log_task = AsyncMock(return_value=None)

        pipe = DocumentPipeline()
        await pipe.process_pending_documents(limit=10)

    assert captured["priority"] == "normal"