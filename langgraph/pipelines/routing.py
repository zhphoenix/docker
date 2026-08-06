"""Routing 策略 - 文档处理管道的路由决策

DP-B3：根据文档类型 / 采集元数据决定本文档的处理路径（routing_strategy）。

当前支持两策略：
  - annual_report：年报（PDF）→ 需 MinIO 下载 → Docling 解析 → 分片
  - general：通用 / markdown → 已可读文本 → 直接分片（跳过文档解析）

routing_strategy 随后被 DP-B4 写入 documents.metadata.processing。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RoutingStrategy(str, Enum):
    """路由策略"""

    ANNUAL_REPORT = "annual_report"
    GENERAL = "general"


@dataclass
class RoutingPlan:
    """某文档的路由决策结果"""

    strategy: RoutingStrategy
    parser: str = "docling"      # 解析器：docling / direct
    needs_download: bool = True  # 是否需要从对象存储下载原始文件
    source_type: str = "general"  # 有效源类型（映射后）
    label: str = "通用文档"

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "parser": self.parser,
            "needs_download": self.needs_download,
            "source_type": self.source_type,
            "label": self.label,
        }


# 文档类型 → 有效源类型 归一化映射
_DOC_TYPE_TO_SOURCE: dict[str, str] = {
    "annual_report": "annual_report",
    "markdown": "markdown",
    "news": "news",
    "web": "web",
}

# 源类型 → 默认路由策略
_SOURCE_TO_STRATEGY: dict[str, RoutingStrategy] = {
    "annual_report": RoutingStrategy.ANNUAL_REPORT,
}


def _normalize_source_type(document_type: str | None, source_type: str | None) -> str:
    """优先取采集元数据里的 source_type，其次由 document_type 归一化得来"""
    if source_type:
        return source_type
    return _DOC_TYPE_TO_SOURCE.get(document_type or "", "general")


def resolve_routing(
    document_type: str | None = None,
    source_type: str | None = None,
    object_key: str | None = None,
) -> RoutingPlan:
    """根据文档信息决定路由策略

    Args:
        document_type: documents.document_type（annual_report/markdown/...）
        source_type: documents.metadata.acquire.source_type（第三方采集元数据）
        object_key: MinIO 对象 key（用于补充判断 PDF/md）

    Returns:
        RoutingPlan: 本文档的处理路径
    """
    src = _normalize_source_type(document_type, source_type)

    # 按源类型选择策略
    strategy = _SOURCE_TO_STRATEGY.get(src, RoutingStrategy.GENERAL)

    if strategy is RoutingStrategy.ANNUAL_REPORT:
        return RoutingPlan(
            strategy=RoutingStrategy.ANNUAL_REPORT,
            parser="docling",
            needs_download=True,
            source_type="annual_report",
            label="年报（PDF → Docling 解析）",
        )

    # general 策略：markdown / 其他可读文本
    parser = "direct"
    needs_download = True
    if object_key and object_key.lower().endswith(".md"):
        needs_download = True  # 仍需从对象存储取文本，但跳过文档解析
    return RoutingPlan(
        strategy=RoutingStrategy.GENERAL,
        parser=parser,
        needs_download=needs_download,
        source_type=src,
        label=f"通用文档（{src}，直接分片）",
    )