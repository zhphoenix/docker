"""AC-P3-5 Agent Logs 单测

覆盖：
  - _build_filters / _build_runs_filters 过滤 SQL 与参数
  - list_logs：联合视图返回结构 + 分页
  - get_run_trace：404 语义（非法 UUID / 不存在）
  - export_logs：CSV 内容与表头

隔离策略：mock postgres_tool，不触真实 DB。
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from api.logs import (
    _build_filters,
    _build_runs_filters,
    export_logs,
    get_run_trace,
    list_logs,
)


def test_build_filters_no_criteria():
    """无筛选 → 两段均为 TRUE，参数为空"""
    runs_where, task_where, params = _build_filters("", "", "")
    assert runs_where == "TRUE"
    assert task_where == "TRUE"
    assert params == []


def test_build_filters_agent_only():
    """仅 agent 筛选：agent_runs 段 $1，task_logs 段映射 ANY($2)"""
    runs_where, task_where, params = _build_filters("knowledge_ingestion", "", "")
    assert runs_where == "r.agent_id = $1"
    assert "t.task_type = ANY($2)" in task_where
    assert params[0] == "knowledge_ingestion"
    assert isinstance(params[1], list) and "doc_pipeline" in params[1]


def test_build_filters_unknown_agent_task_false():
    """agent 无 task_type 映射 → task_logs 段 FALSE（不返回任务日志）"""
    _, task_where, _ = _build_filters("chat", "", "")
    assert task_where == "FALSE"


def test_build_runs_filters_keyword():
    """keyword 同时匹配 question 与 error"""
    where, params = _build_runs_filters("", "failed", "extraction")
    assert "r.status = $1" in where
    assert "r.question ILIKE $2" in where
    assert "r.error ILIKE $2" in where
    assert params == ["failed", "%extraction%"]


@pytest.mark.asyncio
async def test_list_logs_structure():
    """联合视图返回 items/total/page，行含 run_id 与错误分类"""
    fake_pg = AsyncMock()
    fake_pg.query.side_effect = [
        [{"total": 5}],  # COUNT
        [  # 数据行
            {
                "source": "agent_run",
                "ts": datetime(2026, 8, 5, 12, 0, 0),
                "entity": "knowledge_ingestion",
                "level": "failed",
                "message": "doc_pipeline extraction doc=abc",
                "duration_ms": 1000,
                "error_category": "dataerror",
                "run_id": "11111111-1111-1111-1111-111111111111",
                "task_id": None,
            }
        ],
    ]

    with patch("api.logs.postgres_tool", fake_pg):
        result = await list_logs(agent_id="knowledge_ingestion", status="failed", page=1, page_size=20)

    assert result["total"] == 5
    assert result["page"] == 1
    item = result["items"][0]
    assert item["source"] == "agent_run"
    assert item["time"] == "2026-08-05 12:00:00"
    assert item["level"] == "failed"
    assert item["error_category"] == "dataerror"
    assert item["run_id"] == "11111111-1111-1111-1111-111111111111"


@pytest.mark.asyncio
async def test_get_run_trace_invalid_uuid_404():
    """非法 UUID → 404（不触 DB）"""
    from fastapi import HTTPException

    with patch("api.logs.postgres_tool") as fake_pg:
        with pytest.raises(HTTPException) as exc:
            await get_run_trace("not-a-uuid")
    assert exc.value.status_code == 404
    fake_pg.query.assert_not_called()


@pytest.mark.asyncio
async def test_get_run_trace_not_found_404():
    """合法 UUID 但无记录 → 404"""
    from fastapi import HTTPException

    fake_pg = AsyncMock()
    fake_pg.query.side_effect = [[]]
    with patch("api.logs.postgres_tool", fake_pg):
        with pytest.raises(HTTPException) as exc:
            await get_run_trace("11111111-1111-1111-1111-111111111111")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_export_logs_csv():
    """CSV 行含表头 + 转义的错误信息"""
    fake_pg = AsyncMock()
    fake_pg.query.side_effect = [
        [
            {
                "created_at": datetime(2026, 8, 5, 12, 0, 0),
                "agent_id": "news_intelligence",
                "status": "failed",
                "duration_ms": 500,
                "error_category": "mcp_error",
                "question": "source=abc",
                "error": "timeout on line1\nline2",
            }
        ]
    ]

    with patch("api.logs.postgres_tool", fake_pg):
        resp = await export_logs(agent_id="news_intelligence", status="failed")

    body = "".join([chunk async for chunk in resp.body_iterator])
    assert "time,agent_id,status,duration_ms,error_category,question,error" in body
    assert "news_intelligence,failed,500,mcp_error,source=abc" in body
    assert "timeout on line1 line2" in body  # 换行被替换为空格
    assert resp.headers["content-type"].startswith("text/csv")