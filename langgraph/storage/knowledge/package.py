"""Knowledge Package 仓储层 - knowledge_packages 表的读写

DP-A3 定义接口：save_draft / publish / get / retry / rollback。
复用 tools.postgres.postgres_tool 单例，payload 以 JSONB 存完整 KnowledgePackage。

状态流转：
  save_draft  → status=draft
  publish     → draft → published（记 publish_time）
  mark_consumed → published → consumed（KOC-A1 消费成功）
  mark_failed   → published → failed（KOC-A1 消费失败，可 retry）
  retry       → failed → draft（retry_count + 1，供重投）
  rollback    → published/consumed → draft（版本回退，支持重处理）
"""

from __future__ import annotations

import json
import logging
import uuid

from pydantic import ValidationError

from config.policy_loader import get_policy
from schemas.knowledge_package import KnowledgePackage, PackageStatus
from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)


class PackageStorage:
    """knowledge_packages 表仓储

    所有方法均返回可序列化结构；失败返回 None 并记录日志，
    遵循 fire-and-forget 不阻塞主流程的原则。
    """

    # ─────────────── 写入 ───────────────

    async def _insert(
        self,
        package: KnowledgePackage,
        status: PackageStatus,
    ) -> str | None:
        """写入一条 Package 记录

        Args:
            package: KnowledgePackage 契约对象
            status: 初始状态（draft）

        Returns:
            记录 id（UUID 字符串），失败返回 None
        """
        package_id = str(uuid.uuid4())
        payload_json = package.model_dump_json()
        # mode="json" 使 datetime 序列化为 ISO 字符串，避免 json.dumps 报错
        processing_meta = package.processing_metadata.model_dump(mode="json")
        try:
            await postgres_tool.execute(
                """
                INSERT INTO knowledge_packages
                    (id, package_version, schema_version, source_type, document_id,
                     status, payload, processing_metadata, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, NOW())
                """,
                package_id,
                package.package_version,
                package.schema_version,
                package.source_type.value,
                package.document_id,
                status.value,
                payload_json,
                json.dumps(processing_meta, ensure_ascii=False),
            )
            logger.info("Package saved: id=%s status=%s", package_id, status.value)
            return package_id
        except Exception as e:
            logger.warning("Package save failed: %s", e)
            return None

    async def save_draft(self, package: KnowledgePackage) -> str | None:
        """保存草稿 Package

        Args:
            package: KnowledgePackage 契约对象

        Returns:
            Package 记录 id（UUID 字符串），失败返回 None
        """
        return await self._insert(package, PackageStatus.DRAFT)

    # ─────────────── 状态流转 ───────────────

    async def validate_for_publish(self, package_id: str) -> tuple[bool, list[str]]:
        """发布前校验 Package 草稿（DP-D1）

        加载 payload 后用 KnowledgePackage 契约模型整体校验
        （结构合法性：source/entities/relations/facts 字段类型与必填项）。

        Returns:
            (是否通过, 错误信息列表)
        """
        row = await self.get(package_id)
        if not row:
            return False, ["package not found"]
        if row.get("status") != "draft":
            return False, [f"status={row.get('status')} not publishable (expect draft)"]
        payload = row.get("payload") or {}
        try:
            KnowledgePackage.model_validate(payload)
            return True, []
        except ValidationError as e:
            errors = []
            for err in e.errors():
                loc = ".".join(str(p) for p in err.get("loc", []))
                errors.append(f"{loc}: {err.get('msg', 'invalid')}")
            logger.warning(
                "Package validate failed | id=%s | errors=%d", package_id[:8], len(errors)
            )
            return False, errors

    async def publish(
        self, package_id: str, destination: str | None = None,
    ) -> bool:
        """发布 Package：draft → published（DP-D1）

        发布前先做契约校验（validate_for_publish）：
        - 校验通过 → 置 published，写 publish metadata
          （publish_time / destination 写 processing_metadata.publish），retry_count 重置 0
        - 校验失败 → retry_count + 1；达上限（policy pipeline.publish.max_failed_retries）
          置 failed（人工 Re-Publish 经 retry 重投）

        Args:
            package_id: Package 记录 id
            destination: 发布目标（默认取 policy pipeline.publish.destination）

        Returns:
            是否发布成功
        """
        ok, errors = await self.validate_for_publish(package_id)
        if not ok:
            await self._mark_publish_failed(package_id, "; ".join(errors))
            logger.warning(
                "Package publish rejected | id=%s | errors=%s", package_id[:8], errors[:3]
            )
            return False

        if destination is None:
            destination = get_policy("pipeline.publish.destination", "koc_inbox")
        try:
            await postgres_tool.execute(
                """
                UPDATE knowledge_packages
                SET status = 'published',
                    publish_time = COALESCE(publish_time, NOW()),
                    retry_count = 0,
                    processing_metadata = COALESCE(processing_metadata, '{}'::jsonb)
                        || jsonb_build_object('publish', jsonb_build_object(
                               'destination', $2::text,
                               'publish_time', NOW()::text
                           )),
                    updated_at = NOW()
                WHERE id = $1 AND status = 'draft'
                """,
                package_id,
                destination,
            )
            logger.info("Package published | id=%s | destination=%s", package_id[:8], destination)
            return True
        except Exception as e:
            logger.warning("Package publish failed: %s", e)
            await self._mark_publish_failed(package_id, f"db error: {e}")
            return False

    async def _mark_publish_failed(self, package_id: str, reason: str) -> None:
        """发布失败：retry_count + 1，达上限置 failed（DP-D1 重试契约）

        上限 policy pipeline.publish.max_failed_retries（默认 3），
        达上限后 status='failed'，需人工 retry 重投。
        """
        max_retries = int(get_policy("pipeline.publish.max_failed_retries", 3))
        try:
            await postgres_tool.execute(
                """
                UPDATE knowledge_packages
                SET retry_count = retry_count + 1,
                    status = CASE WHEN retry_count + 1 >= $2 THEN 'failed' ELSE status END,
                    processing_metadata = COALESCE(processing_metadata, '{}'::jsonb)
                        || jsonb_build_object('publish', jsonb_build_object(
                               'last_error', $3::text,
                               'last_error_at', NOW()::text
                           )),
                    updated_at = NOW()
                WHERE id = $1 AND status = 'draft'
                """,
                package_id,
                max_retries,
                reason,
            )
        except Exception as e:
            logger.warning("Package mark publish failed: %s", e)

    async def mark_consumed(self, package_id: str) -> bool:
        """标记 Package 已消费：published → consumed（KOC-A1）

        消费器成功处理一条 published Package 后调用，幂等。

        Returns:
            是否成功
        """
        try:
            await postgres_tool.execute(
                """
                UPDATE knowledge_packages
                SET status = 'consumed',
                    updated_at = NOW()
                WHERE id = $1 AND status = 'published'
                """,
                package_id,
            )
            return True
        except Exception as e:
            logger.warning("Package mark_consumed failed: %s", e)
            return False

    async def mark_failed(self, package_id: str) -> bool:
        """标记 Package 消费失败：published → failed（KOC-A1）

        消费器处理失败（含未知 schema_version 拒绝）后调用，可经 retry 重投。

        Returns:
            是否成功
        """
        try:
            await postgres_tool.execute(
                """
                UPDATE knowledge_packages
                SET status = 'failed',
                    updated_at = NOW()
                WHERE id = $1 AND status = 'published'
                """,
                package_id,
            )
            return True
        except Exception as e:
            logger.warning("Package mark_failed failed: %s", e)
            return False

    async def retry(self, package_id: str) -> bool:
        """重试失败 Package：failed → draft（retry_count + 1）

        供消费/发布失败后重投。

        Returns:
            是否成功
        """
        try:
            await postgres_tool.execute(
                """
                UPDATE knowledge_packages
                SET status = 'draft',
                    retry_count = retry_count + 1,
                    updated_at = NOW()
                WHERE id = $1 AND status = 'failed'
                """,
                package_id,
            )
            return True
        except Exception as e:
            logger.warning("Package retry failed: %s", e)
            return False

    async def rollback(self, package_id: str) -> bool:
        """回退 Package：published/consumed → draft

        支持 Rollback/Diff 场景，允许重新处理或重新发布。

        Returns:
            是否成功
        """
        try:
            await postgres_tool.execute(
                """
                UPDATE knowledge_packages
                SET status = 'draft',
                    publish_time = NULL,
                    updated_at = NOW()
                WHERE id = $1 AND status IN ('published', 'consumed')
                """,
                package_id,
            )
            return True
        except Exception as e:
            logger.warning("Package rollback failed: %s", e)
            return False

    # ─────────────── 查询 ───────────────

    async def get(self, package_id: str) -> dict | None:
        """按 id 查询 Package 完整记录

        payload 自动解析为 dict。

        Returns:
            记录 dict（含 payload），不存在或出错返回 None
        """
        try:
            rows = await postgres_tool.query(
                """
                SELECT id, package_version, schema_version, source_type, document_id,
                       status, payload, processing_metadata, publish_time, retry_count,
                       created_at, updated_at
                FROM knowledge_packages
                WHERE id = $1
                """,
                package_id,
            )
            if not rows:
                return None
            row = rows[0]
            row["payload"] = json.loads(row.get("payload") or "{}")
            return row
        except Exception as e:
            logger.warning("Package get failed: %s", e)
            return None

    async def get_by_document(self, document_id: str) -> list[dict]:
        """按 document_id 查询该文档的全部 Package 版本（最新在前）

        Returns:
            记录 dict 列表
        """
        try:
            rows = await postgres_tool.query(
                """
                SELECT id, package_version, schema_version, source_type, status,
                       publish_time, retry_count, created_at, updated_at
                FROM knowledge_packages
                WHERE document_id = $1
                ORDER BY created_at DESC, package_version DESC
                """,
                document_id,
            )
            return rows
        except Exception as e:
            logger.warning("Package get_by_document failed: %s", e)
            return []

    async def list_by_status(self, status: str, limit: int = 50) -> list[dict]:
        """按状态轮询（KOC Inbox 消费入口）

        Args:
            status: draft / published / consumed / failed
            limit: 返回数量上限

        Returns:
            Package 记录列表（含 payload）
        """
        try:
            rows = await postgres_tool.query(
                """
                SELECT id, package_version, schema_version, source_type, status,
                       payload, publish_time, retry_count, created_at
                FROM knowledge_packages
                WHERE status = $1
                ORDER BY created_at ASC
                LIMIT $2
                """,
                status,
                limit,
            )
            for row in rows:
                row["payload"] = json.loads(row.get("payload") or "{}")
            return rows
        except Exception as e:
            logger.warning("Package list_by_status failed: %s", e)
            return []


# 模块级单例
package_storage = PackageStorage()