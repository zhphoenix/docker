"""增量变更检测模块

基于 Crawl4AI 集成设计规范 第18.3节 Phase 2:
- 内容 Hash 对比检测变化
- 变更状态判定（unchanged / changed / new / removed）
- 页面下线检测

用法:
    detector = DiffDetector.from_config(config)

    # 检测单个 URL 的变更状态
    status = await detector.detect_change(
        url="https://...",
        new_content_hash="abc123...",
        pg_pool=pool
    )

    if status == ChangeStatus.CHANGED:
        # 触发重新 Chunk + Embedding
        ...
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ChangeStatus(Enum):
    """变更状态枚举"""

    NEW = "new"              # 新页面（首次抓取）
    UNCHANGED = "unchanged"  # 内容未变化
    CHANGED = "changed"      # 内容已变化
    REMOVED = "removed"      # 页面已下线（404 等）
    ERROR = "error"          # 检测出错


@dataclass
class ChangeDetectionResult:
    """变更检测结果"""

    url: str
    status: ChangeStatus
    old_hash: str | None = None
    new_hash: str | None = None
    old_version: int = 0
    new_version: int = 1
    message: str = ""
    detected_at: datetime = None

    def __post_init__(self):
        if self.detected_at is None:
            self.detected_at = datetime.now(timezone.utc)

    @property
    def needs_sync(self) -> bool:
        """是否需要同步到向量库"""
        return self.status in (ChangeStatus.NEW, ChangeStatus.CHANGED)

    @property
    def needs_cleanup(self) -> bool:
        """是否需要清理向量库"""
        return self.status == ChangeStatus.REMOVED


class DiffDetector:
    """增量变更检测器

    职责:
    - 对比新旧 content_hash 判定变更状态
    - 管理 content_version 递增
    - 检测页面下线（404/持续 dead）
    """

    def __init__(
        self,
        hash_algorithm: str = "sha256",
        on_page_removed: str = "archive",
    ):
        """
        Args:
            hash_algorithm: Hash 算法（sha256/md5）
            on_page_removed: 页面下线处理策略（archive/delete/ignore）
        """
        self.hash_algorithm = hash_algorithm
        self.on_page_removed = on_page_removed

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "DiffDetector":
        """从 crawl4ai.yaml 的 incremental 段构建"""
        inc_cfg = config.get("incremental", {})
        return cls(
            hash_algorithm=inc_cfg.get("hash_algorithm", "sha256"),
            on_page_removed=inc_cfg.get("on_page_removed", "archive"),
        )

    async def detect_change(
        self,
        url: str,
        new_content_hash: str | None,
        pg_pool,
        http_status: int | None = None,
    ) -> ChangeDetectionResult:
        """检测 URL 的变更状态

        Args:
            url: 目标 URL
            new_content_hash: 新抓取内容的 Hash（None 表示抓取失败）
            pg_pool: asyncpg 连接池
            http_status: HTTP 状态码（用于检测 404）

        Returns:
            ChangeDetectionResult 检测结果
        """
        # 页面下线检测（404 或持续失败）
        if http_status == 404:
            return await self._handle_removed(url, pg_pool, "HTTP 404")

        # 抓取失败（无 Hash）
        if new_content_hash is None:
            return ChangeDetectionResult(
                url=url,
                status=ChangeStatus.ERROR,
                message="抓取失败，无内容 Hash",
            )

        # 查询数据库中的现有记录
        row = await pg_pool.fetchrow(
            """
            SELECT content_hash, content_version, page_status, sync_status
            FROM web_pages
            WHERE url = $1
            """,
            url,
        )

        # 新页面（首次抓取）
        if row is None:
            logger.info(f"新页面: {url}")
            return ChangeDetectionResult(
                url=url,
                status=ChangeStatus.NEW,
                new_hash=new_content_hash,
                new_version=1,
                message="首次抓取",
            )

        old_hash = row["content_hash"]
        old_version = row["content_version"] or 1

        # 内容未变化
        if old_hash == new_content_hash:
            logger.debug(f"内容未变化: {url}")
            return ChangeDetectionResult(
                url=url,
                status=ChangeStatus.UNCHANGED,
                old_hash=old_hash,
                new_hash=new_content_hash,
                old_version=old_version,
                new_version=old_version,
                message="内容 Hash 一致",
            )

        # 内容已变化
        new_version = old_version + 1
        logger.info(f"内容已变化: {url} (v{old_version} -> v{new_version})")
        return ChangeDetectionResult(
            url=url,
            status=ChangeStatus.CHANGED,
            old_hash=old_hash,
            new_hash=new_content_hash,
            old_version=old_version,
            new_version=new_version,
            message=f"内容更新 v{old_version} -> v{new_version}",
        )

    async def _handle_removed(
        self,
        url: str,
        pg_pool,
        reason: str,
    ) -> ChangeDetectionResult:
        """处理页面下线"""
        # 查询现有记录
        row = await pg_pool.fetchrow(
            """
            SELECT content_hash, content_version, qdrant_point_ids
            FROM web_pages
            WHERE url = $1
            """,
            url,
        )

        if row is None:
            # 从未抓取过的页面返回 404，忽略
            return ChangeDetectionResult(
                url=url,
                status=ChangeStatus.ERROR,
                message=f"页面不存在且无历史记录: {reason}",
            )

        # 根据配置处理
        if self.on_page_removed == "ignore":
            return ChangeDetectionResult(
                url=url,
                status=ChangeStatus.UNCHANGED,
                old_hash=row["content_hash"],
                message=f"页面下线但配置为 ignore: {reason}",
            )

        logger.warning(f"页面下线: {url} ({reason}), 策略={self.on_page_removed}")
        return ChangeDetectionResult(
            url=url,
            status=ChangeStatus.REMOVED,
            old_hash=row["content_hash"],
            old_version=row["content_version"] or 1,
            message=f"页面下线: {reason}",
        )

    async def update_sync_status(
        self,
        url: str,
        pg_pool,
        sync_status: str,
        qdrant_point_ids: list[str] | None = None,
    ) -> None:
        """更新同步状态

        Args:
            url: 目标 URL
            pg_pool: asyncpg 连接池
            sync_status: 同步状态（synced/pending_sync/stale/archived）
            qdrant_point_ids: 关联的 Qdrant point ID 列表
        """
        if qdrant_point_ids is not None:
            await pg_pool.execute(
                """
                UPDATE web_pages
                SET sync_status = $2,
                    qdrant_point_ids = $3,
                    last_synced_at = NOW()
                WHERE url = $1
                """,
                url, sync_status, qdrant_point_ids,
            )
        else:
            await pg_pool.execute(
                """
                UPDATE web_pages
                SET sync_status = $2,
                    last_synced_at = NOW()
                WHERE url = $1
                """,
                url, sync_status,
            )

    async def get_stale_pages(self, pg_pool, limit: int = 100) -> list[dict[str, Any]]:
        """获取需要同步的页面（pending_sync 或 stale）"""
        rows = await pg_pool.fetch(
            """
            SELECT url, domain, content_hash, content_version, sync_status
            FROM web_pages
            WHERE sync_status IN ('pending_sync', 'stale')
              AND page_status = 'success'
            ORDER BY crawl_time DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]

    def __repr__(self) -> str:
        return (
            f"DiffDetector(hash={self.hash_algorithm}, "
            f"on_removed={self.on_page_removed})"
        )
