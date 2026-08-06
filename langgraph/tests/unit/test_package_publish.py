"""DP-D1 Publish 实现单元测试

覆盖：
  1. 校验通过 → published（写 publish metadata + destination，retry_count 重置）
  2. 校验失败（非法 payload）→ retry_count + 1，不置 published
  3. 校验失败达上限 → 置 failed（人工 Re-Publish）
  4. validate_for_publish 对不存在记录返回 False
  5. 非 draft 状态不可发布

隔离策略：mock postgres_tool（query 返回 payload 行，execute 检查 SQL）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from storage.knowledge.package import PackageStorage

VALID_PAYLOAD_JSON = (
    '{"id":"abc-123","source_type":"news","status":"draft",'
    '"source":{"source_type":"news","source_id":"reuters"}}'
)


def _draft_row(payload_json: str = VALID_PAYLOAD_JSON, status: str = "draft") -> list[dict]:
    return [{"id": "abc-123", "status": status, "payload": payload_json}]


@pytest.mark.asyncio
async def test_publish_valid_payload_sets_published_with_destination():
    """校验通过：published + destination 写入 + retry_count 重置"""
    storage = PackageStorage()
    with patch("storage.knowledge.package.postgres_tool") as mock_pg:
        mock_pg.query = AsyncMock(return_value=_draft_row())
        mock_pg.execute = AsyncMock(return_value="UPDATE 1")

        ok = await storage.publish("abc-123", destination="koc_inbox")

        assert ok is True
        sql = mock_pg.execute.await_args.args[0]
        args = mock_pg.execute.await_args.args
        assert "status = 'published'" in sql
        assert "retry_count = 0" in sql
        assert "destination" in sql
        assert args[1] == "abc-123"
        assert args[2] == "koc_inbox"


@pytest.mark.asyncio
async def test_publish_invalid_payload_increments_retry():
    """校验失败：retry_count + 1，不置 published，返回 False"""
    storage = PackageStorage()
    bad_payload = '{"id":"abc-123","source_type":"news","source":{"source_id":"reuters"}}'
    with patch("storage.knowledge.package.postgres_tool") as mock_pg:
        mock_pg.query = AsyncMock(return_value=_draft_row(bad_payload))
        mock_pg.execute = AsyncMock(return_value="UPDATE 1")

        ok = await storage.publish("abc-123")

        assert ok is False
        sql = mock_pg.execute.await_args.args[0]
        assert "retry_count = retry_count + 1" in sql
        assert "status = 'published'" not in sql


@pytest.mark.asyncio
async def test_publish_invalid_payload_reaches_max_sets_failed():
    """校验失败达上限：状态置 failed（可经 retry 重投）"""
    storage = PackageStorage()
    bad_payload = '{"id":"abc-123","source_type":"news","source":{"source_id":"reuters"}}'
    with patch("storage.knowledge.package.postgres_tool") as mock_pg, \
         patch("storage.knowledge.package.get_policy", return_value=3) as mock_policy:
        mock_pg.query = AsyncMock(return_value=_draft_row(bad_payload))
        mock_pg.execute = AsyncMock(return_value="UPDATE 1")

        ok = await storage.publish("abc-123")

        assert ok is False
        mock_policy.assert_called_with("pipeline.publish.max_failed_retries", 3)
        sql = mock_pg.execute.await_args.args[0]
        assert "CASE WHEN retry_count + 1 >= $2 THEN 'failed'" in sql
        assert mock_pg.execute.await_args.args[2] == 3


@pytest.mark.asyncio
async def test_validate_for_publish_missing_returns_false():
    """记录不存在：校验不通过"""
    storage = PackageStorage()
    with patch("storage.knowledge.package.postgres_tool") as mock_pg:
        mock_pg.query = AsyncMock(return_value=[])
        ok, errors = await storage.validate_for_publish("nope")
    assert ok is False
    assert "not found" in errors[0]


@pytest.mark.asyncio
async def test_validate_for_publish_non_draft_rejected():
    """非 draft 状态不可发布"""
    storage = PackageStorage()
    with patch("storage.knowledge.package.postgres_tool") as mock_pg:
        mock_pg.query = AsyncMock(return_value=_draft_row(status="published"))
        ok, errors = await storage.validate_for_publish("abc-123")
    assert ok is False
    assert "not publishable" in errors[0]


@pytest.mark.asyncio
async def test_validate_for_publish_valid():
    """合法 payload 校验通过"""
    storage = PackageStorage()
    with patch("storage.knowledge.package.postgres_tool") as mock_pg:
        mock_pg.query = AsyncMock(return_value=_draft_row())
        ok, errors = await storage.validate_for_publish("abc-123")
    assert ok is True
    assert errors == []