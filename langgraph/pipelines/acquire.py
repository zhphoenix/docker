"""Acquire 统一入口元数据 - 三种采集入口的统一 source metadata 契约

DP-B2 定义文档上传 / MinIO 扫描 / Web/手动导入统一产出的 Raw Document
source metadata：

  documents.metadata.acquire = {
      source_type: 源类型（annual_report / markdown / news / web / general）
      trigger:     触发方式（upload / minio_scan / manual_ingest / web_crawl）
      priority:    优先级（high / normal / low）
      checksum:    内容校验和（SHA-256 或对象 key），用于判重
      origin:      来源设备（minio / upload / manual / web）
      acquired_at: 采集时间（ISO）
      ...扩展字段
  }

三种入口产生的 documents 记录均携带该结构；checksum 判重据此生效。
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AcquireTrigger(str, Enum):
    """采集触发方式"""

    UPLOAD = "upload"
    MINIO_SCAN = "minio_scan"
    MANUAL_INGEST = "manual_ingest"
    WEB_CRAWL = "web_crawl"


class AcquirePriority(str, Enum):
    """采集优先级（与 DP-D4 三级队列对应）"""

    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class AcquireOrigin(str, Enum):
    """来源设备"""

    MINIO = "minio"
    UPLOAD = "upload"
    MANUAL = "manual"
    WEB = "web"


def sha256_hex(data: str | bytes) -> str:
    """计算内容 SHA-256（判重用）"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def build_acquire_metadata(
    source_type: str,
    trigger: str | AcquireTrigger,
    priority: str | AcquirePriority = AcquirePriority.NORMAL,
    checksum: str | None = None,
    origin: str | AcquireOrigin | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """构造统一 acquire metadata（documents.metadata.acquire）

    Args:
        source_type: 源类型（annual_report/markdown/news/web/general）
        trigger: 触发方式（upload/minio_scan/manual_ingest/web_crawl）
        priority: 优先级（high/normal/low）
        checksum: 内容校验和（SHA-256 或对象 key），用于判重
        origin: 来源设备（minio/upload/manual/web）；缺省取 trigger
        **extra: 额外字段（如 object_key / source_path / url）

    Returns:
        {"acquire": {...}} 可直接合并进 documents.metadata
    """
    trigger_val = trigger.value if isinstance(trigger, AcquireTrigger) else str(trigger)
    priority_val = priority.value if isinstance(priority, AcquirePriority) else str(priority)
    origin_val = origin.value if isinstance(origin, AcquireOrigin) else (origin or trigger_val)

    block: dict[str, Any] = {
        "source_type": str(source_type),
        "trigger": trigger_val,
        "priority": priority_val,
        "origin": origin_val,
        "acquired_at": _utcnow_iso(),
    }
    if checksum:
        block["checksum"] = checksum
    block.update(extra)

    return {"acquire": block}


def merge_acquire_into_metadata(base_metadata: dict | str, acquire: dict) -> dict:
    """把 acquire block 合并进 documents.metadata（幂等，保留既有字段）"""
    if isinstance(base_metadata, str):
        import json

        try:
            base_metadata = json.loads(base_metadata)
        except (ValueError, TypeError):
            base_metadata = {}
    merged = dict(base_metadata or {})
    merged["acquire"] = acquire["acquire"]
    return merged