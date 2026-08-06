"""KOC-F1 审核→渲染编排单测

覆盖：
  - enqueue_render_job 写入 core.knowledge_render_jobs（status=pending）
  - 优先级映射：Company/Event 优先（priority 越小越优先）
  - 显式 priority 覆盖默认推导
  - 审核通过回调完整链路：approve → 更新 inbox + 审核日志 + 入 Render Queue

隔离策略：mock postgres_tool，验证行为语义，不触真实 DB。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from storage.knowledge.postgres import KnowledgePostgresStorage, RENDER_TYPE_PRIORITY


def _make_storage() -> KnowledgePostgresStorage:
    return KnowledgePostgresStorage()


@pytest.mark.asyncio
async def test_enqueue_render_job_writes_pending():
    """enqueue_render_job 写入 core.knowledge_render_jobs，status=pending"""
    storage = _make_storage()
    with patch("storage.knowledge.postgres.postgres_tool") as mock_pg:
        mock_pg.execute = AsyncMock(return_value="INSERT 0 1")
        job_id = await storage.enqueue_render_job("eid-1", "company")

    assert isinstance(job_id, str) and job_id
    mock_pg.execute.assert_awaited_once()
    sql = mock_pg.execute.await_args.args[0]
    assert "core.knowledge_render_jobs" in sql
    # (sql, job_id, entity_id, entity_type, section, priority)
    args = mock_pg.execute.await_args.args
    assert args[2] == "eid-1"
    assert args[3] == "company"
    assert args[4] is None  # section
    assert args[5] == RENDER_TYPE_PRIORITY["company"]  # 1


@pytest.mark.asyncio
async def test_enqueue_render_job_priority_map():
    """Company/Event 优先：priority 越小越优先"""
    storage = _make_storage()

    async def _run(etype):
        with patch("storage.knowledge.postgres.postgres_tool") as mock_pg:
            mock_pg.execute = AsyncMock(return_value="INSERT 0 1")
            await storage.enqueue_render_job("e", etype)
            return mock_pg.execute.await_args.args[5]

    assert await _run("Company") == 1
    assert await _run("event") == 2
    assert await _run("person") == 3
    assert await _run("Security") == 3
    assert await _run("industry") == 4
    assert await _run("Document") == 5
    # 未知类型默认 5
    assert await _run("UnknownType") == 5


@pytest.mark.asyncio
async def test_enqueue_render_job_explicit_priority():
    """显式 priority 覆盖默认推导"""
    storage = _make_storage()
    with patch("storage.knowledge.postgres.postgres_tool") as mock_pg:
        mock_pg.execute = AsyncMock(return_value="INSERT 0 1")
        await storage.enqueue_render_job("eid-1", "document", priority=1)

    args = mock_pg.execute.await_args.args
    assert args[5] == 1  # 显式 1 覆盖 document 默认 5


@pytest.mark.asyncio
async def test_enqueue_render_job_section_supported():
    """增量更新支持 section 参数"""
    storage = _make_storage()
    with patch("storage.knowledge.postgres.postgres_tool") as mock_pg:
        mock_pg.execute = AsyncMock(return_value="INSERT 0 1")
        await storage.enqueue_render_job("eid-1", "company", section="Financial")

    args = mock_pg.execute.await_args.args
    assert args[4] == "Financial"


@pytest.mark.asyncio
async def test_approve_callback_enqueues_render_job():
    """审核通过完整链路：approve → 更新 inbox + 审核日志 + 入 Render Queue"""
    from api.approvals import _approve_knowledge_inbox

    mock_storage = MagicMock()
    mock_storage.update_inbox_status = AsyncMock()
    mock_storage.record_review_log = AsyncMock(return_value="log-id")
    mock_storage.get_inbox = AsyncMock(return_value={
        "object_id": "eid-1",
        "content": {"name": "腾讯控股", "entity_type": "company"},
    })
    mock_storage.enqueue_render_job = AsyncMock(return_value="job-id")

    with patch("api.approvals.knowledge_storage", mock_storage):
        await _approve_knowledge_inbox({"inbox_id": "inbox-1"})

    mock_storage.enqueue_render_job.assert_awaited_once_with("eid-1", "company")


@pytest.mark.asyncio
async def test_approve_callback_no_inbox_returns():
    """审核通过回调无 inbox 记录时不入队、不报错"""
    from api.approvals import _approve_knowledge_inbox

    mock_storage = MagicMock()
    mock_storage.update_inbox_status = AsyncMock()
    mock_storage.record_review_log = AsyncMock()
    mock_storage.get_inbox = AsyncMock(return_value=None)
    mock_storage.enqueue_render_job = AsyncMock()

    with patch("api.approvals.knowledge_storage", mock_storage):
        await _approve_knowledge_inbox({"inbox_id": "inbox-1"})

    mock_storage.enqueue_render_job.assert_not_awaited()