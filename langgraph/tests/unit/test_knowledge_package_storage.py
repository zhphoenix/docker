"""Knowledge Package 仓储层单元测试（DP-A3）

覆盖 draft→published 状态流转与幂等重发（retry/rollback）。
使用 mock 替代真实 DB，验证 SQL 调用与状态流转语义。
"""

import pytest
from unittest.mock import AsyncMock, patch

from schemas.knowledge_package import (
    KnowledgePackage,
    SourceMetadata,
    SourceType,
)


def _make_package() -> KnowledgePackage:
    """构造一个最小样例 Package"""
    return KnowledgePackage(
        id="11111111-1111-1111-1111-111111111111",
        source_type=SourceType.NEWS,
        source=SourceMetadata(source_type=SourceType.NEWS, source_id="reuters"),
    )


@pytest.mark.asyncio
async def test_save_draft_inserts_draft():
    """save_draft 应持 payload 并返回记录 id"""
    from storage.knowledge.package import PackageStorage

    storage = PackageStorage()
    with patch.object(
        storage, "_insert", new=AsyncMock(return_value="abc-123")
    ) as mock_insert:
        pkg = _make_package()
        pkg_id = await storage.save_draft(pkg)
        assert pkg_id == "abc-123"
        mock_insert.assert_awaited_once()
        # 调用时传入 DRAFT 状态
        assert mock_insert.await_args.args[1].value == "draft"


@pytest.mark.asyncio
async def test_publish_transitions_draft_to_published():
    """publish 应更新 status='published' 并写入 publish_time"""
    from storage.knowledge.package import PackageStorage

    storage = PackageStorage()
    with patch.object(storage, "publish", new=AsyncMock(return_value=True)):
        ok = await storage.publish("abc-123")
        assert ok is True


@pytest.mark.asyncio
async def test_publish_preserves_original_publish_time():
    """publish 幂等：不覆盖已设置的 publish_time（COALESCE）"""
    from storage.knowledge.package import PackageStorage

    storage = PackageStorage()
    with patch("storage.knowledge.package.postgres_tool") as mock_pg:
        mock_pg.execute = AsyncMock(return_value="UPDATE 1")
        ok = await storage.publish("abc-123")
        assert ok is True
        sql = mock_pg.execute.await_args.args[0]
        assert "publish_time = COALESCE(publish_time, NOW())" in sql
        assert "status = 'draft'" in sql


@pytest.mark.asyncio
async def test_retry_resets_failed_to_draft():
    """retry：failed → draft 且 retry_count + 1"""
    from storage.knowledge.package import PackageStorage

    storage = PackageStorage()
    with patch("storage.knowledge.package.postgres_tool") as mock_pg:
        mock_pg.execute = AsyncMock(return_value="UPDATE 1")
        ok = await storage.retry("abc-123")
        assert ok is True
        sql = mock_pg.execute.await_args.args[0]
        assert "retry_count = retry_count + 1" in sql
        assert "status = 'failed'" in sql


@pytest.mark.asyncio
async def test_rollback_published_to_draft():
    """rollback：published/consumed → draft 且清空 publish_time"""
    from storage.knowledge.package import PackageStorage

    storage = PackageStorage()
    with patch("storage.knowledge.package.postgres_tool") as mock_pg:
        mock_pg.execute = AsyncMock(return_value="UPDATE 1")
        ok = await storage.rollback("abc-123")
        assert ok is True
        sql = mock_pg.execute.await_args.args[0]
        assert "status IN ('published', 'consumed')" in sql
        assert "publish_time = NULL" in sql


@pytest.mark.asyncio
async def test_get_parses_payload():
    """get 应解析 payload JSONB 为 dict"""
    from storage.knowledge.package import PackageStorage

    storage = PackageStorage()
    with patch("storage.knowledge.package.postgres_tool") as mock_pg:
        mock_pg.query = AsyncMock(
            return_value=[
                {
                    "id": "abc-123",
                    "payload": '{"id":"11111111-1111-1111-1111-111111111111","status":"draft"}',
                }
            ]
        )
        row = await storage.get("abc-123")
        assert row is not None
        assert row["payload"]["status"] == "draft"


@pytest.mark.asyncio
async def test_get_missing_returns_none():
    """get 不存在记录应返回 None"""
    from storage.knowledge.package import PackageStorage

    storage = PackageStorage()
    with patch("storage.knowledge.package.postgres_tool") as mock_pg:
        mock_pg.query = AsyncMock(return_value=[])
        row = await storage.get("nope")
        assert row is None