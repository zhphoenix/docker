"""DP-D3 Web 源接入单元测试

验证：
  1. Web 抓取产物封装为 source_type=GENERAL 的 Package（url/domain/hash/minio_path 映射）
  2. auto_publish 开启时草稿保存后自动发布
  3. 失败不阻塞实时链路（调用方捕获异常）

隔离策略：直接测试 _publish_web_package（mock package_storage + get_policy）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from pipelines.web_pipeline import WebPipeline


def _make_pipeline() -> WebPipeline:
    return WebPipeline(provider=None, minio_client=None, pg_pool=None)


def _fake_policy(auto_publish: bool = False):
    def _inner(key, default=None):
        if key == "pipeline.publish.auto_publish":
            return auto_publish
        return default
    return _inner


@pytest.mark.asyncio
async def test_web_package_maps_source_metadata():
    """封装为 GENERAL Package：source metadata 完整映射"""
    pipe = _make_pipeline()
    with patch("storage.knowledge.package.package_storage") as mock_pkg, \
         patch("pipelines.web_pipeline.get_policy", side_effect=_fake_policy(False)):
        mock_pkg.save_draft = AsyncMock(return_value="pkg-1")
        mock_pkg.publish = AsyncMock(return_value=True)

        pid = await pipe._publish_web_package(
            "https://example.com/news", "示例新闻", "example.com",
            "abc12345", "website/example.com/abc12345.md",
        )

        assert pid == "pkg-1"
        pkg = mock_pkg.save_draft.await_args.args[0]
        assert pkg.source_type.value == "general"
        assert pkg.source.source_id == "example.com"
        assert pkg.source.title == "示例新闻"
        assert pkg.source.url == "https://example.com/news"
        assert pkg.source.hash == "abc12345"
        assert pkg.source.file_path == "website/example.com/abc12345.md"
        assert pkg.entities == []
        mock_pkg.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_web_package_auto_publish_when_enabled():
    """auto_publish 开启：草稿保存后自动 publish"""
    pipe = _make_pipeline()
    with patch("storage.knowledge.package.package_storage") as mock_pkg, \
         patch("pipelines.web_pipeline.get_policy", side_effect=_fake_policy(True)):
        mock_pkg.save_draft = AsyncMock(return_value="pkg-1")
        mock_pkg.publish = AsyncMock(return_value=True)

        pid = await pipe._publish_web_package(
            "https://example.com", None, "", None, "website/x.md",
        )

        assert pid == "pkg-1"
        mock_pkg.publish.assert_awaited_once_with("pkg-1")


@pytest.mark.asyncio
async def test_web_package_failure_returns_none():
    """保存失败返回 None（调用方 fire-and-forget 不阻塞）"""
    pipe = _make_pipeline()
    with patch("storage.knowledge.package.package_storage") as mock_pkg, \
         patch("pipelines.web_pipeline.get_policy", side_effect=_fake_policy(False)):
        mock_pkg.save_draft = AsyncMock(return_value=None)
        mock_pkg.publish = AsyncMock(return_value=True)

        pid = await pipe._publish_web_package(
            "https://example.com", "标题", "example.com", "hash1", "website/x.md",
        )

        assert pid is None
        mock_pkg.publish.assert_not_awaited()