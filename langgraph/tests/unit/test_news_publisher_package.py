"""DP-D2 News 发布封装单元测试

验证：
  1. 新闻抽取结果封装为 source_type=NEWS 的 Package（实体/关系/事件映射正确）
  2. 草稿保存成功返回 Package id
  3. auto_publish 开启时草稿保存后自动发布
  4. 无文章存储时返回 None（不产生 Package）

隔离策略：mock package_storage（save_draft / publish）与 get_policy。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from nodes.news.publisher import _publish_news_package

ARTICLES = [{"title": "央行降准 25bp", "url": "https://x.com/a", "published_at": "2026-08-01T09:00:00Z"}]
ENTITIES = [
    {"name": "央行", "entity_type": "Org", "confidence": 0.9},
    {"name": "商业银行", "entity_type": "Org", "confidence": 0.85},
]
RELATIONS = [{"source_name": "央行", "target_name": "商业银行", "relation_type": "regulates", "confidence": 0.88}]
EVENTS = [{"title": "央行降准", "event_type": "macro_policy", "event_time": "2026-08-01T09:00:00Z", "confidence": 0.9}]


@pytest.mark.asyncio
async def test_news_package_maps_entities_relations_events():
    """封装为 NEWS Package：实体/关系/事件映射到契约模型"""
    with patch("storage.knowledge.package.package_storage") as mock_pkg, \
         patch("nodes.news.publisher.get_policy", side_effect=_fake_policy(False)):
        mock_pkg.save_draft = AsyncMock(return_value="pkg-1")
        mock_pkg.publish = AsyncMock(return_value=True)

        pid = await _publish_news_package(
            ARTICLES, ENTITIES, EVENTS, RELATIONS,
            ["art-1"], ["ent-1", "ent-2"], ["evt-1"], "crawler-1",
        )

        assert pid == "pkg-1"
        pkg = mock_pkg.save_draft.await_args.args[0]
        assert pkg.source_type.value == "news"
        assert pkg.source.source_id == "crawler-1"
        assert pkg.source.title == "央行降准 25bp"
        assert len(pkg.entities) == 2
        assert pkg.entities[0].id == "ent-1"
        assert pkg.entities[0].name == "央行"
        assert len(pkg.relations) == 1
        assert pkg.relations[0].source_entity == "ent-1"
        assert pkg.relations[0].target_entity == "ent-2"
        assert pkg.relations[0].relation_type == "regulates"
        assert len(pkg.events) == 1
        assert pkg.events[0].id == "evt-1"
        assert pkg.events[0].name == "央行降准"
        assert pkg.events[0].start_time is not None
        mock_pkg.publish.assert_not_awaited()  # auto_publish=False


def _fake_policy(auto_publish: bool = False):
    """mock get_policy：只对 auto_publish 返回指定值，其余返回默认"""
    def _inner(key, default=None):
        if key == "pipeline.publish.auto_publish":
            return auto_publish
        return default
    return _inner


@pytest.mark.asyncio
async def test_news_package_auto_publish_when_enabled():
    """auto_publish 开启：草稿保存后自动 publish"""
    with patch("storage.knowledge.package.package_storage") as mock_pkg, \
         patch("nodes.news.publisher.get_policy", side_effect=_fake_policy(True)):
        mock_pkg.save_draft = AsyncMock(return_value="pkg-1")
        mock_pkg.publish = AsyncMock(return_value=True)

        pid = await _publish_news_package(
            ARTICLES, ENTITIES, [], [], ["art-1"], ["ent-1"], [], "crawler-1",
        )

        assert pid == "pkg-1"
        mock_pkg.publish.assert_awaited_once_with("pkg-1")


@pytest.mark.asyncio
async def test_news_package_no_articles_returns_none():
    """无文章落库：不产生 Package"""
    with patch("storage.knowledge.package.package_storage") as mock_pkg:
        mock_pkg.save_draft = AsyncMock(return_value="pkg-1")
        pid = await _publish_news_package(
            ARTICLES, ENTITIES, [], [], [], [], [], "crawler-1",
        )
        assert pid is None
        mock_pkg.save_draft.assert_not_awaited()


@pytest.mark.asyncio
async def test_news_package_skips_unresolvable_relations():
    """关系无法解析（缺实体）时跳过"""
    with patch("storage.knowledge.package.package_storage") as mock_pkg, \
         patch("nodes.news.publisher.get_policy", side_effect=_fake_policy(False)):
        mock_pkg.save_draft = AsyncMock(return_value="pkg-1")
        # 实体只有 1 个，关系引用不存在的 target
        pid = await _publish_news_package(
            ARTICLES, ENTITIES[:1], [], RELATIONS, ["art-1"], ["ent-1"], [], "crawler-1",
        )
        assert pid == "pkg-1"
        pkg = mock_pkg.save_draft.await_args.args[0]
        assert pkg.relations == []