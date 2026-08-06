"""KOC-A1 Package 消费器单测

验证：
  1. 合法 published Package 被消费后置 consumed
  2. 未知 schema_version 被拒绝并置 failed、可重试（retry 已存在）
  3. 空队列返回 fetched=0
  4. 消费异常兜底置 failed

隔离策略：mock package_storage（list_by_status / mark_consumed / mark_failed）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.package_consumer import _validate_schema_version, consume_published


def _published_row(package_id: str = "11111111-1111-1111-1111-111111111111",
                   schema_version: str = "1.0") -> dict:
    return {
        "id": package_id,
        "source_type": "annual_report",
        "status": "published",
        "payload": {
            "id": package_id,
            "schema_version": schema_version,
            "source_type": "annual_report",
            "entities": [{"id": "e-1", "name": "腾讯控股"}],
        },
    }


@pytest.fixture
def mock_storage():
    with patch("services.package_consumer.package_storage") as ms:
        ms.list_by_status = AsyncMock(return_value=[])
        ms.mark_consumed = AsyncMock(return_value=True)
        ms.mark_failed = AsyncMock(return_value=True)
        yield ms


@pytest.mark.asyncio
async def test_consume_valid_published_marks_consumed(mock_storage):
    """合法 published Package 消费成功后置 consumed"""
    mock_storage.list_by_status.return_value = [_published_row()]

    stats = await consume_published(limit=10)

    assert stats == {"fetched": 1, "consumed": 1, "failed": 0}
    mock_storage.list_by_status.assert_awaited_once_with("published", limit=10)
    mock_storage.mark_consumed.assert_awaited_once()
    mock_storage.mark_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_consume_unknown_schema_version_marks_failed(mock_storage):
    """未知 schema_version 被拒绝并置 failed（可经 retry 重投）"""
    mock_storage.list_by_status.return_value = [_published_row(schema_version="9.9")]

    stats = await consume_published(limit=10)

    assert stats == {"fetched": 1, "consumed": 0, "failed": 1}
    mock_storage.mark_failed.assert_awaited_once()
    mock_storage.mark_consumed.assert_not_awaited()


@pytest.mark.asyncio
async def test_consume_empty_queue(mock_storage):
    """空 published 队列返回 fetched=0，不调用状态流转"""
    stats = await consume_published(limit=10)

    assert stats == {"fetched": 0, "consumed": 0, "failed": 0}
    mock_storage.mark_consumed.assert_not_awaited()
    mock_storage.mark_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_consume_error_falls_back_to_failed(mock_storage):
    """消费抛异常时兜底置 failed 并计入 failed 计数"""
    bad_row = _published_row()
    mock_storage.list_by_status.return_value = [bad_row]
    mock_storage.mark_consumed.side_effect = RuntimeError("boom")

    stats = await consume_published(limit=10)

    assert stats == {"fetched": 1, "consumed": 0, "failed": 1}
    mock_storage.mark_failed.assert_awaited_once_with(bad_row["id"])


def test_validate_schema_version_supported():
    """受支持 schema_version 通过校验"""
    assert _validate_schema_version({"schema_version": "1.0"}) is True
    assert _validate_schema_version({}) is True  # 缺省默认 1.0


@patch("services.package_consumer.get_policy")
def test_validate_schema_version_unknown(mock_policy):
    """未知 schema_version 拒绝"""
    mock_policy.return_value = ["1.0"]
    assert _validate_schema_version({"schema_version": "2.0"}) is False