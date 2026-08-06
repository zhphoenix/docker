"""KOC-A4 Inbox 审核流打通单测

覆盖：
  - record_review_log 写入 audit.knowledge_review_log
  - api/approvals.py _approve_knowledge_inbox 回调：approve → 更新 inbox 状态 + 写审核日志
  - api/approvals.py reject 端点：reject → 更新 inbox 状态 + 写审核日志（含 reason）
  - merger.py auto-approve 分支：写 auto_approve 审核日志

隔离策略：mock storage/postgres_tool，验证行为语义，不触真实 DB。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from storage.knowledge.postgres import KnowledgePostgresStorage


def _make_storage() -> KnowledgePostgresStorage:
    return KnowledgePostgresStorage()


@pytest.mark.asyncio
async def test_record_review_log_writes_audit_table():
    """record_review_log 写入 audit.knowledge_review_log，字段正确"""
    storage = _make_storage()
    inbox_id = "11111111-2222-3333-4444-555555555555"
    with patch("storage.knowledge.postgres.postgres_tool") as mock_pg:
        mock_pg.execute = AsyncMock(return_value="INSERT 0 1")
        log_id = await storage.record_review_log(
            inbox_id, "approve", reviewer="human", reason=""
        )

    assert isinstance(log_id, str) and log_id
    mock_pg.execute.assert_awaited_once()
    sql = mock_pg.execute.await_args.args[0]
    assert "audit.knowledge_review_log" in sql
    # (sql, log_id, inbox_id, action, reviewer, reason)
    args = mock_pg.execute.await_args.args
    assert args[2] == inbox_id
    assert args[3] == "approve"
    assert args[4] == "human"


@pytest.mark.asyncio
async def test_record_review_log_reject_with_reason():
    """reject 动作带拒绝原因写入"""
    storage = _make_storage()
    with patch("storage.knowledge.postgres.postgres_tool") as mock_pg:
        mock_pg.execute = AsyncMock(return_value="INSERT 0 1")
        await storage.record_review_log(
            "11111111-2222-3333-4444-555555555555",
            "reject", reviewer="human", reason="证据不足，待补充",
        )

    args = mock_pg.execute.await_args.args
    assert args[3] == "reject"
    assert args[5] == "证据不足，待补充"


@pytest.mark.asyncio
async def test_approve_callback_updates_inbox_and_logs():
    """_approve_knowledge_inbox：approve → 更新 inbox 状态 APPROVED + 写审核日志 + 入 Render Queue（KOC-F1）"""
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

    mock_storage.update_inbox_status.assert_awaited_once_with(
        "inbox-1", "APPROVED", reviewer="human"
    )
    mock_storage.record_review_log.assert_awaited_once_with(
        "inbox-1", "approve", reviewer="human", reason=""
    )
    # KOC-F1: 审核通过 → render_jobs pending
    mock_storage.enqueue_render_job.assert_awaited_once_with("eid-1", "company")


@pytest.mark.asyncio
async def test_approve_callback_no_inbox_id_is_noop():
    """approve 回调无 inbox_id 时不报错、不写日志"""
    from api.approvals import _approve_knowledge_inbox

    mock_storage = MagicMock()
    mock_storage.update_inbox_status = AsyncMock()
    mock_storage.record_review_log = AsyncMock()
    mock_storage.get_inbox = AsyncMock()
    mock_storage.enqueue_render_job = AsyncMock()

    with patch("api.approvals.knowledge_storage", mock_storage):
        await _approve_knowledge_inbox({})

    mock_storage.update_inbox_status.assert_not_awaited()
    mock_storage.record_review_log.assert_not_awaited()


@pytest.mark.asyncio
async def test_reject_endpoint_updates_inbox_and_logs():
    """reject 端点：approve 审批拒绝 → 更新 inbox REJECTED + 写审核日志（含 reason）"""
    from api.approvals import reject_task, RejectRequest

    mock_storage = MagicMock()
    mock_storage.update_inbox_status = AsyncMock()
    mock_storage.record_review_log = AsyncMock(return_value="log-id")

    mock_pg = MagicMock()
    # _get_approval_params 查询 tasks.params
    mock_pg.query = AsyncMock(return_value=[{
        "params": '{"action_type": "knowledge_inbox_approve", '
                  '"params": {"inbox_id": "inbox-1"}}'
    }])

    # reject() 内部查询 tasks 校验
    reject_rows = [{"id": "approval-1"}]

    with patch("api.approvals.knowledge_storage", mock_storage), \
         patch("api.approvals.postgres_tool", mock_pg), \
         patch("api.approvals.reject") as mock_reject:
        # reject 返回成功
        async def _fake_reject(*a, **k):
            mock_pg.query.return_value = reject_rows
            return {"status": "rejected", "reason": "证据不足"}
        mock_reject.side_effect = _fake_reject

        req = RejectRequest(reason="证据不足")
        # 直接调用端点函数
        resp = await reject_task("approval-1", req)

    assert resp["status"] == "rejected"
    mock_storage.update_inbox_status.assert_awaited_once_with(
        "inbox-1", "REJECTED", reviewer="human"
    )
    mock_storage.record_review_log.assert_awaited_once_with(
        "inbox-1", "reject", reviewer="human", reason="证据不足"
    )


@pytest.mark.asyncio
async def test_merger_auto_approve_writes_log():
    """merger.py auto-approve 分支：高置信度+可信来源 → 写 auto_approve 审核日志"""
    from nodes.knowledge.merger import knowledge_merger

    # 构建最小 state：单实体高置信度 + 可信来源
    state = {
        "entities": [
            {"name": "腾讯控股", "entity_type": "company",
             "aliases": [], "properties": {}, "confidence": 0.9},
        ],
        "relations": [], "facts": [],
        "entity_embeddings": [[0.1, 0.2]],
        "source_metadata": {"source": "annual_report"},
        "document_id": "doc-1",
    }

    mock_storage = MagicMock()
    mock_storage.find_entities_by_names = AsyncMock(return_value=[])
    mock_storage.search_entity_by_embedding = AsyncMock(return_value=[])
    mock_storage.bulk_upsert_entities = AsyncMock(return_value=["eid-1"])
    mock_storage.bulk_insert_relations = AsyncMock(return_value=[])
    mock_storage.bulk_insert_facts = AsyncMock(return_value=[])
    mock_storage.bulk_insert_evidence = AsyncMock(return_value=None)
    mock_storage.insert_inbox = AsyncMock(return_value="inbox-1")
    mock_storage.update_inbox_status = AsyncMock(return_value=None)
    mock_storage.record_knowledge_version = AsyncMock(return_value=1)
    mock_storage.record_review_log = AsyncMock(return_value="log-id")
    mock_storage.enqueue_render_job = AsyncMock(return_value="job-id")

    with patch("nodes.knowledge.merger.knowledge_qdrant") as _qdrant, \
         patch("nodes.knowledge.merger.knowledge_age") as _age, \
         patch("nodes.knowledge.merger.create_approval", new=AsyncMock()) as _ca, \
         patch("nodes.knowledge.merger.get_policy", return_value=0.85):
        _age.available = False
        _qdrant.index_entities = AsyncMock()
        _qdrant.index_facts = AsyncMock()
        await knowledge_merger(state, storage=mock_storage)

    # 高置信度 → 自动 APPROVED，不创建人工审批
    mock_storage.update_inbox_status.assert_awaited_once_with(
        "inbox-1", "APPROVED", reviewer="system"
    )
    _ca.assert_not_awaited()
    mock_storage.record_review_log.assert_awaited_once_with(
        "inbox-1", "auto_approve", reviewer="system", reason=""
    )
    # KOC-F1: 审核通过 → 入 Render Queue（company 优先 priority=1）
    mock_storage.enqueue_render_job.assert_awaited_once_with("eid-1", "company")