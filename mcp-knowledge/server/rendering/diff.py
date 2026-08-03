"""版本 Diff — 基于 audit.knowledge_versions 计算变更 Section

设计：Section 级增量，仅刷新变更区，避免全量重渲染。
Diff 依据：实体已同步版本（sync_version）与最新版本的差值。
"""

from __future__ import annotations

import logging
from typing import Any

from server.storage.postgres import pg_storage

logger = logging.getLogger(__name__)


class KnowledgeDiff:
    """基于 audit.knowledge_versions 的版本差异计算"""

    async def latest_version(self, entity_id: str) -> int:
        """实体最新版本号（无则 0）"""
        row = await pg_storage.query_one(
            "SELECT COALESCE(MAX(version), 0) AS v FROM audit.knowledge_versions WHERE object_id = $1",
            entity_id,
        )
        return int(row["v"]) if row else 0

    async def get_sections_after(
        self, entity_id: str, synced_version: int, limit: int = 200
    ) -> list[dict]:
        """返回 synced_version 之后新增版本的 Section 数据列表

        按最新版本优先去重（同一 section 仅保留最新版），并限制总数避免无界查询。

        Section 约定：content JSONB 中 {"sections": [{"id", "title", "content"}]}
        """
        rows = await pg_storage.query(
            """
            SELECT content FROM audit.knowledge_versions
            WHERE object_id = $1 AND version > $2
            ORDER BY version DESC
            """,
            entity_id, synced_version,
        )
        sections: list[dict] = []
        seen: set[str] = set()
        for r in rows:
            content = r["content"]
            if not isinstance(content, dict):
                continue
            for s in content.get("sections", []):
                if isinstance(s, dict) and s.get("id") and s["id"] not in seen:
                    seen.add(s["id"])
                    sections.append(s)
                    if len(sections) >= limit:
                        return sections
        return sections

    async def get_section_ids(self, entity_id: str) -> set[str]:
        """实体全部 Section 标识集合"""
        rows = await pg_storage.query(
            "SELECT content FROM audit.knowledge_versions WHERE object_id = $1",
            entity_id,
        )
        ids: set[str] = set()
        for r in rows:
            content = r["content"]
            if isinstance(content, dict):
                for s in content.get("sections", []):
                    if isinstance(s, dict) and s.get("id"):
                        ids.add(s["id"])
        return ids

    async def changed_sections(
        self, entity_id: str, synced_version: int
    ) -> list[dict]:
        """对外入口：返回需渲染的变更 Section"""
        return await self.get_sections_after(entity_id, synced_version)


# 模块级单例
knowledge_diff = KnowledgeDiff()