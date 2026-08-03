"""SiYuan 增量同步 + 版本 Diff

将 PostgreSQL 中的知识对象增量同步到 SiYuan 展示层。

核心流程：
  1. 读取实体及其最新版本（audit.knowledge_versions）
  2. 计算"已同步版本"与"最新版本"的差值 → 变更 Section
  3. 仅渲染变更 Section，经 SiYuanClient 幂等写入
  4. 更新 core.entities 的 last_synced_at / sync_version / sync_status

设计红线：PG 为唯一 SoT，SiYuan 仅展示；本模块只读 PG、只写 SiYuan。
"""

from __future__ import annotations

import logging
from typing import Any

from server.adapters.siyuan.client import SiYuanClient
from server.adapters.siyuan.config import get_siyuan_config
from server.adapters.siyuan.mapper import (
    entity_to_path,
    entity_to_template_context,
    notebook_for,
    section_path,
)
from server.adapters.siyuan.templates import renderer
from server.rendering.diff import knowledge_diff
from server.storage.postgres import pg_storage

logger = logging.getLogger(__name__)

# 同步状态枚举（与 core.entities.sync_status 一致，见 Phase 1 迁移）
SYNC_STATUS_SYNCED = "Synced"
SYNC_STATUS_PENDING = "Pending Review"
SYNC_STATUS_CONFLICT = "Conflict"


class SiYuanSync:
    """增量同步器（渲染 + 幂等写入 + 状态更新）"""

    def __init__(self, client: SiYuanClient | None = None):
        self.client = client or SiYuanClient()
        self.cfg = get_siyuan_config()

    async def sync_entity(self, entity: dict[str, Any]) -> dict:
        """同步单个实体到 SiYuan（增量）。

        Args:
            entity: core.entities 一行（含 id, entity_type, canancing_name, properties, sync_version, sync_status）

        Returns:
            {status, action, changed_sections, path}
        """
        entity_id = str(entity["id"])
        etype = entity.get("entity_type", "Company")
        notebook = notebook_for(etype)
        path = entity_to_path(entity)
        synced_version = int(entity.get("sync_version") or 0)
        latest_version = await knowledge_diff.latest_version(entity_id)

        # 无新版本 → 无需同步
        if latest_version <= synced_version:
            return {"status": SYNC_STATUS_SYNCED, "action": "noop", "changed_sections": [], "path": path}

        # 计算变更 Section（复用 knowledge_diff 做 Section 级增量，仅刷变更区）
        changed_sections = await knowledge_diff.get_sections_after(entity_id, synced_version)

        # 构建展示上下文并渲染
        context = entity_to_template_context(entity, sections=changed_sections)
        markdown = renderer.render(etype, context)

        # 幂等写入（存在则更新，否则创建）
        result = await self.client.upsert_doc(notebook, path, markdown)

        # 更新同步元数据
        await self._mark_synced(entity_id, latest_version)

        return {
            "status": SYNC_STATUS_SYNCED,
            "action": result["action"],
            "changed_sections": [s.get("id") for s in changed_sections],
            "path": path,
        }

    async def _mark_synced(self, entity_id: str, version: int) -> None:
        """更新 sync 元数据（幂等）"""
        await pg_storage.execute(
            """
            UPDATE core.entities
            SET last_synced_at = NOW(),
                last_modified_by = $2,
                sync_version = $3,
                sync_status = $4
            WHERE id = $1
            """,
            entity_id, self.cfg.sync_user, version, SYNC_STATUS_SYNCED,
        )

    async def sync_section(self, entity: dict[str, Any], section: str) -> dict:
        """按 Section 增量同步单个文档（用于针对性刷新）"""
        entity_id = str(entity["id"])
        etype = entity.get("entity_type", "Company")
        notebook = notebook_for(etype)
        path = section_path(entity_to_path(entity), section)

        context = entity_to_template_context(entity)
        markdown = renderer.render_section(section, context)

        result = await self.client.upsert_doc(notebook, path, markdown)
        return {"action": result["action"], "section": section, "path": path}


# 模块级单例
siyuan_sync = SiYuanSync()