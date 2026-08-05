"""Knowledge Object ↔ SiYuan 文档映射

定义：
  - Notebook 命名约定（Companies/Industries/Events/Knowledge Inbox）
  - 对象类型 → 文档路径规则
  - 对象字段 → 模板上下文映射

设计红线：PG 为 SoT，SiYuan 仅展示。本模块只负责"如何展示"，
不含任何业务状态写入。
"""

from __future__ import annotations

import json
import re
from typing import Any


def _as_props(entity: dict[str, Any]) -> dict[str, Any]:
    """安全解析 properties 字段为 dict（asyncpg 对 JSONB 默认返回 str）。"""
    p = entity.get("properties") or {}
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except (ValueError, TypeError):
            p = {}
    return p or {}

# ──────────────────────────────
# Notebook 约定
# ──────────────────────────────
NOTEBOOK_COMPANIES = "Companies"
NOTEBOOK_INDUSTRIES = "Industries"
NOTEBOOK_EVENTS = "Events"
NOTEBOOK_INBOX = "Knowledge Inbox"

# 对象类型 → 归属 Notebook
OBJECT_NOTEBOOK: dict[str, str] = {
    "Company": NOTEBOOK_COMPANIES,
    "Industry": NOTEBOOK_INDUSTRIES,
    "Event": NOTEBOOK_EVENTS,
}


def _sanitize_path_segment(seg: str) -> str:
    """清理路径段：去空格、去非法字符（SiYuan 路径限制）"""
    seg = re.sub(r"[\s/\\:*?\"<>|]+", "_", seg).strip("_")
    return seg or "untitled"


def entity_to_path(entity: dict[str, Any]) -> str:
    """由实体构建文档路径（相对 notebook 根）。

    规则：
      - Company:  {ticker}_{canonical_name}（如 000001_平安银行）
      - Industry: {canonical_name}
      - Event:    {event_date}_{canonical_name}
    """
    etype = entity.get("entity_type", "Company")
    name = entity.get("canonical_name") or entity.get("name", "untitled")
    props = _as_props(entity)

    if etype == "Company":
        ticker = props.get("ticker") or ""
        base = f"{ticker}_{name}" if ticker else name
        return _sanitize_path_segment(base)
    if etype == "Event":
        date = props.get("event_date") or props.get("date") or ""
        base = f"{date}_{name}" if date else name
        return _sanitize_path_segment(base)
    return _sanitize_path_segment(name)


def notebook_for(object_type: str) -> str:
    """对象类型 → Notebook 名"""
    return OBJECT_NOTEBOOK.get(object_type, NOTEBOOK_COMPANIES)


def section_path(entity_path: str, section: str) -> str:
    """按 Section 增量渲染的文档路径（如 000001_平安银行/Financial）"""
    return f"{entity_path}/{_sanitize_path_segment(section)}"


def neighbor_to_link(neighbor: dict[str, Any]) -> str:
    """生成 SiYuan 块引用链接文本 [[name]]（基于文档标题，模板首行 # {{ name }}）。

    用于让 SiYuan 内置关系图能基于文档链接自动生成关联图谱。
    """
    name = neighbor.get("neighbor_name") or neighbor.get("canonical_name") or ""
    return f"[[{name}]]" if name else ""


def entity_to_template_context(
    entity: dict[str, Any],
    sections: list[dict] | None = None,
    neighbors: list[dict] | None = None,
) -> dict:
    """实体 → 模板上下文（统一字段，供 Jinja2 使用）。

    Args:
        entity: core.entities 一行
        sections: 需渲染的 Section 列表（增量同步用）
        neighbors: 一跳邻居列表（get_entity_neighbors_for_render 输出），注入 related_entities
    """
    props = _as_props(entity)
    related: list[dict] = []
    for n in neighbors or []:
        name = n.get("neighbor_name") or n.get("canonical_name") or ""
        if name:
            related.append({"name": name, "relation_type": n.get("relation_type", "")})
    return {
        "name": entity.get("canonical_name") or entity.get("name", ""),
        "entity_type": entity.get("entity_type", "Company"),
        "ticker": props.get("ticker", ""),
        "market": props.get("market", ""),
        "description": entity.get("description", ""),
        "aliases": entity.get("aliases") or [],
        "confidence": entity.get("confidence", 0.0),
        "sections": sections or [],
        "related_entities": related,
        "updated_at": entity.get("updated_at", ""),
    }


def fact_to_section(fact: dict[str, Any]) -> dict[str, Any]:
    """事实 → Section 数据（供模板渲染单个事实行）"""
    obj = fact.get("object_value") or {}
    return {
        "predicate": fact.get("predicate", ""),
        "value": obj.get("value", ""),
        "unit": obj.get("unit", fact.get("unit", "")),
        "time_start": fact.get("time_start", ""),
        "time_end": fact.get("time_end", ""),
        "source": fact.get("source_document", ""),
        "confidence": fact.get("confidence", 0.0),
    }