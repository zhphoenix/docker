"""Pipeline 八阶段枚举与阶段记录追踪单元测试（DP-B1）

覆盖：
  - Stage 枚举含 8 阶段且顺序正确
  - 进入/完成/失败均写 documents.metadata.processing（JSONB）
  - 进入/完成/失败均写 task_logs（stage 字段）
  - 断点续传 load、processing 元字段设置、track_stage 上下文管理器

使用 mock 替代真实 DB，验证 SQL 调用与阶段记录语义。
"""

import pytest
from unittest.mock import AsyncMock, patch

from pipelines.stages import (
    Stage,
    StageStatus,
    STAGE_ORDER,
    StageTracker,
    track_stage,
)


def _make_tracker(task_id: str | None = "task-123"):
    return StageTracker("doc-11111111-1111-1111-1111-111111111111", task_id=task_id)


@patch("runtime.queue.task_queue")
def test_stage_enum_has_eight_stages(mock_tq):
    """Stage 枚举应包含 8 个阶段且顺序符合契约"""
    expected = [
        "acquire", "routing", "parse", "chunk",
        "extraction", "embedding", "package", "publish",
    ]
    assert STAGE_ORDER == expected
    assert [s.value for s in Stage] == expected
    assert Stage.PARSE.label == "解析"


@patch("runtime.queue.task_queue")
@pytest.mark.asyncio
async def test_enter_writes_running_and_task_log(mock_tq):
    """进入阶段：processing.stages 置 running + started_at，写 task_logs(stage=parse)"""
    tracker = _make_tracker()
    mock_pg = AsyncMock()  # execute 记录
    mock_tq.log_task = AsyncMock()

    await tracker.enter(mock_pg, Stage.PARSE, "解析开始")

    rec = tracker.stage_records()[0]
    assert rec["stage"] == "parse"
    assert rec["status"] == StageStatus.RUNNING.value
    assert rec["started_at"] is not None
    assert rec["finished_at"] is None

    mock_pg.execute.assert_awaited()
    sql = mock_pg.execute.await_args.args[0]
    assert "jsonb_set" in sql and "'{processing}'" in sql
    # task_logs 使用 stage=parse
    mock_tq.log_task.assert_awaited()
    assert mock_tq.log_task.await_args.args[3] == "parse"


@patch("runtime.queue.task_queue")
@pytest.mark.asyncio
async def test_complete_writes_success_and_duration(mock_tq):
    """完成阶段：success + finished_at + duration_ms，写 task_logs"""
    tracker = _make_tracker()
    mock_pg = AsyncMock()
    mock_tq.log_task = AsyncMock()

    await tracker.enter(mock_pg, Stage.PARSE)
    await tracker.complete(mock_pg, Stage.PARSE, "解析完成")

    rec = tracker.stage_records()[0]
    assert rec["status"] == StageStatus.SUCCESS.value
    assert rec["finished_at"] is not None
    assert rec["duration_ms"] >= 0
    assert rec["error"] is None

    # 仅一条阶段记录（enter/complete 复用同一 stage 槽位）
    assert len(tracker.stage_records()) == 1
    mock_tq.log_task.assert_awaited()


@patch("runtime.queue.task_queue")
@pytest.mark.asyncio
async def test_fail_writes_failed_and_error(mock_tq):
    """失败阶段：failed + error，task_logs level=error"""
    tracker = _make_tracker()
    mock_pg = AsyncMock()
    mock_tq.log_task = AsyncMock()

    await tracker.enter(mock_pg, Stage.CHUNK)
    await tracker.fail(mock_pg, Stage.CHUNK, "chunk exploded")

    rec = tracker.stage_records()[0]
    assert rec["status"] == StageStatus.FAILED.value
    assert rec["error"] == "chunk exploded"
    assert rec["finished_at"] is not None

    await_args = mock_tq.log_task.await_args_list[-1]
    assert await_args.args[1] == "error"


@patch("runtime.queue.task_queue")
@pytest.mark.asyncio
async def test_load_resumes_existing_stages(mock_tq):
    """断点续传：load 应加载已有 processing 的 stages"""
    tracker = _make_tracker()
    fake_pg = AsyncMock()
    fake_pg.query = AsyncMock(
        return_value=[
            {
                "processing": {
                    "parser": "docling",
                    "stages": [
                        {"stage": "parse", "status": "success", "started_at": "2026-01-01T00:00:00+00:00"},
                    ],
                }
            }
        ]
    )

    await tracker.load(fake_pg)
    assert tracker._processing["parser"] == "docling"
    assert [s["stage"] for s in tracker.stage_records()] == ["parse"]

    # 追加新阶段不覆盖已有
    await tracker.enter(fake_pg, Stage.CHUNK, "分块")
    assert [s["stage"] for s in tracker.stage_records()] == ["parse", "chunk"]


@patch("runtime.queue.task_queue")
@pytest.mark.asyncio
async def test_set_metadata_fields(mock_tq):
    """set_metadata 应写入 parser/routing_strategy/embedding_model 等元字段"""
    tracker = _make_tracker()
    tracker.set_metadata(
        parser="docling",
        routing_strategy="annual_report",
        embedding_model="bge-m3",
        llm_model="qwen-max",
    )
    assert tracker._processing["parser"] == "docling"
    assert tracker._processing["routing_strategy"] == "annual_report"
    assert tracker._processing["embedding_model"] == "bge-m3"
    assert tracker._processing["llm_model"] == "qwen-max"


@patch("runtime.queue.task_queue")
@pytest.mark.asyncio
async def test_track_stage_success(mock_tq):
    """track_stage 上下文管理器：无异常时进入→完成"""
    tracker = _make_tracker(task_id=None)
    mock_pg = AsyncMock()

    async def _do():
        async with track_stage(tracker, mock_pg, Stage.PARSE, "解析"):
            pass

    await _do()
    rec = tracker.stage_records()[0]
    assert rec["status"] == StageStatus.SUCCESS.value
    assert rec["started_at"] is not None and rec["finished_at"] is not None


@patch("runtime.queue.task_queue")
@pytest.mark.asyncio
async def test_track_stage_exception(mock_tq):
    """track_stage 上下文管理器：异常时进入→失败并向上抛出"""
    tracker = _make_tracker(task_id=None)
    mock_pg = AsyncMock()

    async def _do():
        async with track_stage(tracker, mock_pg, Stage.PARSE, "解析"):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await _do()

    rec = tracker.stage_records()[0]
    assert rec["status"] == StageStatus.FAILED.value
    assert rec["error"] == "boom"


@patch("runtime.queue.task_queue")
@pytest.mark.asyncio
async def test_no_task_id_skips_task_log(mock_tq):
    """无 task_id 时不应写 task_logs，但仍写 documents.metadata.processing"""
    tracker = _make_tracker(task_id=None)
    mock_pg = AsyncMock()

    await tracker.enter(mock_pg, Stage.PARSE)
    mock_tq.log_task.assert_not_called()
    mock_pg.execute.assert_awaited()  # processing 仍落库