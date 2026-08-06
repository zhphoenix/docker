"""KOC-F2 Render Queue 监控单测

覆盖：
  - list_render_jobs 按状态过滤 / 全部返回（含实体名 join）
  - retry_render_job：failed → pending，清空 error_message
  - retry_render_job：非 failed 状态返回 False（不误重置）
  - API /render-jobs 列表（按状态过滤）
  - API /render-jobs/{id}/retry 手动重试
  - API 重试非 failed 任务返回 409

隔离策略：mock postgres_tool / knowledge_storage，验证行为语义，不触真实 DB。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from storage.knowledge.postgres import KnowledgePostgresStorage


def _make_storage() -> KnowledgePostgresStorage:
    return KnowledgePostgresStorage()


def _job(**overrides) -> dict:
    base = {
        "id": "job-1",
        "entity": "eid-1",
        "entity_name": "腾讯控股",
        "type": "Company",
        "section": None,
        "status": "pending",
        "retry": 0,
        "priority": 1,
        "error_message": None,
        "created_at": __import__("datetime").datetime.now(),
        "updated_at": __import__("datetime").datetime.now(),
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_list_render_jobs_with_status():
    """list_render_jobs 按状态过滤并返回关联实体名"""
    storage = _make_storage()
    with patch("storage.knowledge.postgres.postgres_tool") as mock_pg:
        mock_pg.query = AsyncMock(return_value=[_job(status="failed")])
        rows = await storage.list_render_jobs(status="failed", limit=10)

    assert len(rows) == 1
    assert rows[0]["entity_name"] == "腾讯控股"
    sql = mock_pg.query.await_args.args[0]
    assert "core.knowledge_render_jobs" in sql
    assert "WHERE j.status = $1" in sql
    status_arg = mock_pg.query.await_args.args[1]
    assert status_arg == "failed"
    assert mock_pg.query.await_args.args[2] == 10


@pytest.mark.asyncio
async def test_list_render_jobs_all():
    """list_render_jobs 无状态过滤时返回全部（LEFT JOIN 实体名）"""
    storage = _make_storage()
    with patch("storage.knowledge.postgres.postgres_tool") as mock_pg:
        mock_pg.query = AsyncMock(return_value=[_job(status="pending")])
        rows = await storage.list_render_jobs(limit=50)

    assert len(rows) == 1
    sql = mock_pg.query.await_args.args[0]
    assert "LEFT JOIN core.entities" in sql
    assert "WHERE" not in sql


@pytest.mark.asyncio
async def test_retry_render_job_success():
    """retry_render_job：failed → pending，清空 error_message"""
    storage = _make_storage()
    with patch("storage.knowledge.postgres.postgres_tool") as mock_pg:
        mock_pg.query = AsyncMock(return_value=[{"id": "job-1"}])
        ok = await storage.retry_render_job("job-1")

    assert ok is True
    sql = mock_pg.query.await_args.args[0]
    assert "SET status = 'pending'" in sql
    assert "error_message = NULL" in sql
    assert "status = 'failed'" in sql
    assert mock_pg.query.await_args.args[1] == "job-1"


@pytest.mark.asyncio
async def test_retry_render_job_not_failed():
    """retry_render_job：非 failed 状态（返回空行）时返回 False"""
    storage = _make_storage()
    with patch("storage.knowledge.postgres.postgres_tool") as mock_pg:
        mock_pg.query = AsyncMock(return_value=[])
        ok = await storage.retry_render_job("job-1")

    assert ok is False


@pytest.mark.asyncio
async def test_api_list_render_jobs():
    """GET /api/knowledge/render-jobs 返回任务列表（按状态过滤）"""
    from api.knowledge import list_render_jobs

    mock_storage = MagicMock()
    mock_storage.list_render_jobs = AsyncMock(return_value=[
        {"id": "job-1", "entity": "eid-1", "entity_name": "腾讯控股",
         "type": "Company", "section": None, "status": "failed",
         "retry": 3, "priority": 1, "error_message": "boom",
         "created_at": None, "updated_at": None},
    ])

    with patch("api.knowledge.knowledge_storage", mock_storage):
        resp = await list_render_jobs(status="failed", limit=10)

    assert resp["total"] == 1
    job = resp["jobs"][0]
    assert job["entity_name"] == "腾讯控股"
    assert job["status"] == "failed"
    assert job["retry"] == 3
    assert job["error_message"] == "boom"
    mock_storage.list_render_jobs.assert_awaited_once_with(status="failed", limit=10)


@pytest.mark.asyncio
async def test_api_retry_render_job():
    """POST /api/knowledge/render-jobs/{id}/retry 手动重试成功"""
    from api.knowledge import retry_render_job

    mock_storage = MagicMock()
    mock_storage.retry_render_job = AsyncMock(return_value=True)

    with patch("api.knowledge.knowledge_storage", mock_storage):
        resp = await retry_render_job("job-1")

    assert resp["status"] == "ok"
    mock_storage.retry_render_job.assert_awaited_once_with("job-1")


@pytest.mark.asyncio
async def test_api_retry_render_job_conflict():
    """POST retry 非 failed 任务返回 409（HTTPException）"""
    from fastapi import HTTPException
    from api.knowledge import retry_render_job

    mock_storage = MagicMock()
    mock_storage.retry_render_job = AsyncMock(return_value=False)

    with patch("api.knowledge.knowledge_storage", mock_storage):
        with pytest.raises(HTTPException) as exc_info:
            await retry_render_job("job-1")

    assert exc_info.value.status_code == 409