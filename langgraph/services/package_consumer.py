"""Knowledge Package Consumer - KOC-A1 Package 消费器

轮询 knowledge_packages status='published' → 解析 payload → 置 consumed/failed。

职责（KOC-A1）：
  - 拉取 published Package（借用 package_storage.list_by_status）
  - 校验 schema_version：未知版本拒绝消费并置 failed、记录告警
  - 消费成功置 consumed；失败置 failed（可经 package_storage.retry 重投）

消费语义（KOC-A2 完成前的最小闭环）：
  - 本消费器当前仅负责状态流转与 payload 解析校验；
    实体校验（Validation）与落 core.*（Merge）由 KOC-A2/A3 接入。
  - 消费成功回调由调用方注册（consume_published 返回已消费/失败清单）。

与 DP-C3 的关系：合并落库复用 nodes/knowledge/merger.py 的写入目标抽象，
本文件不重复实现合并逻辑，仅编排状态流转。
"""

from __future__ import annotations

import logging

from config.policy_loader import get_policy
from storage.knowledge.package import package_storage

logger = logging.getLogger(__name__)

# 当前支持的契约 schema 版本（与 knowledge_package.schema_version 对齐）
SUPPORTED_SCHEMA_VERSIONS = {"1.0"}


def _validate_schema_version(payload: dict) -> bool:
    """校验 payload 的 schema_version 是否受支持

    未知版本返回 False（拒绝消费），由调用方置 failed 并告警。
    """
    version = payload.get("schema_version") or "1.0"
    supported = set(get_policy("koc.supported_schema_versions", list(SUPPORTED_SCHEMA_VERSIONS)))
    return str(version) in supported


async def _consume_one(row: dict) -> bool:
    """消费单条 published Package

    Returns:
        True=消费成功（已置 consumed）；False=消费失败（已置 failed）
    """
    package_id = str(row["id"])
    payload = row.get("payload") or {}

    # 1. schema_version 校验：未知版本拒绝并置 failed（KOC-A1 验收）
    if not _validate_schema_version(payload):
        logger.warning(
            "[PackageConsumer] Reject unknown schema_version | id=%s | version=%s",
            package_id[:8], payload.get("schema_version"),
        )
        await package_storage.mark_failed(package_id)
        return False

    # 2. payload 解析：缺 id 视为格式非法
    if not payload.get("id"):
        logger.warning(
            "[PackageConsumer] Invalid payload (missing id) | id=%s", package_id[:8]
        )
        await package_storage.mark_failed(package_id)
        return False

    # 3. 消费成功 → consumed
    #    （实体校验 KOC-A2、Merge 落库 KOC-A3 在此之后接入）
    ok = await package_storage.mark_consumed(package_id)
    if ok:
        logger.info(
            "[PackageConsumer] Consumed | id=%s | source_type=%s | entities=%d",
            package_id[:8], payload.get("source_type"),
            len(payload.get("entities", []) or []),
        )
    return ok


async def consume_published(limit: int | None = None) -> dict:
    """消费一批 published Package（轮询入口，供 scheduler job 调用）

    Args:
        limit: 单次最多消费条数（默认取 policy koc.consume_batch_size）

    Returns:
        {"fetched": int, "consumed": int, "failed": int}
    """
    if limit is None:
        limit = int(get_policy("koc.consume_batch_size", 50))

    rows = await package_storage.list_by_status("published", limit=limit)
    if not rows:
        return {"fetched": 0, "consumed": 0, "failed": 0}

    consumed = 0
    failed = 0
    for row in rows:
        try:
            if await _consume_one(row):
                consumed += 1
            else:
                failed += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            logger.error(
                "[PackageConsumer] Consume error | id=%s | %s",
                str(row.get("id", ""))[:8], e,
            )
            await package_storage.mark_failed(str(row["id"]))

    logger.info(
        "[PackageConsumer] Poll done | fetched=%d | consumed=%d | failed=%d",
        len(rows), consumed, failed,
    )
    return {"fetched": len(rows), "consumed": consumed, "failed": failed}