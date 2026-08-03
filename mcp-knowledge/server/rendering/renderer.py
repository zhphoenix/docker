"""Renderer — 从 PostgreSQL 取数并渲染知识页面

职责：
  - 读取实体 + 事实 + 关系，构建模板上下文
  - 按对象类型渲染完整文档或单个 Section
  - 只读 PG，经 SiYuan Adapter 输出
"""

from __future__ import annotations

import logging
from typing import Any

from server.adapters.siyuan.mapper import entity_to_template_context, fact_to_section
from server.adapters.siyuan.templates import renderer as template_renderer
from server.storage.postgres import pg_storage

logger = logging.getLogger(__name__)

# 事实→Section 分组谓词（Financial 等）
FINANCIAL_PREDICATES = {
    "Revenue", "Revenue Growth", "Net Profit", "Net Income", "ROE", "ROIC",
    "Debt Ratio", "Cash Flow", "EPS", "PE Ratio", "PB Ratio", "Dividend",
    "Operating Margin", "Gross Margin", "Total Assets", "Total Liabilities",
}
OPERATIONS_PREDICATES = {"Production", "Capacity", "Utilization", "Shipment", "Output"}


def _group_facts(facts: list[dict]) -> list[dict]:
    """将事实按财务/经营/其他分组为 Section 数据"""
    sections: list[dict] = []
    fin = [f for f in facts if f.get("predicate") in FINANCIAL_PREDICATES]
    ops = [f for f in facts if f.get("predicate") in OPERATIONS_PREDICATES]
    other = [f for f in facts if f not in fin and f not in ops]

    def _to_section(title: str, items: list[dict]) -> dict | None:
        if not items:
            return None
        rows = "\n".join(_fact_row(f) for f in items)
        return {"id": title.lower().replace(" ", "_"), "title": title, "content": rows}

    for s in (_to_section("Financial", fin), _to_section("Operations", ops), _to_section("Facts", other)):
        if s:
            sections.append(s)
    return sections


def _fact_row(f: dict[str, Any]) -> str:
    """单条事实 → Markdown 行"""
    seg = fact_to_section(f)
    val = seg["value"]
    unit = seg["unit"]
    time = seg["time_start"]
    line = f"- **{seg['predicate']}**: {val}{(' ' + unit) if unit else ''}"
    if time:
        line += f" ({time})"
    if seg["confidence"] is not None:
        line += f" — 置信度 {seg['confidence'] * 100:.0f}%"
    return line


class KnowledgeRenderer:
    """从 PG 取数渲染知识页面"""

    async def render_entity(self, entity: dict[str, Any], sections: list[dict] | None = None) -> str:
        """渲染实体完整文档 Markdown"""
        etype = entity.get("entity_type", "Company")
        if sections is None:
            sections = await self.fetch_sections(entity)
        context = entity_to_template_context(entity, sections=sections)
        return template_renderer.render(etype, context)

    async def render_section(self, entity: dict[str, Any], section: str) -> str:
        """渲染单个 Section Markdown（增量）"""
        sections = await self.fetch_sections(entity)
        target = next((s for s in sections if s.get("id") == section), None)
        context = entity_to_template_context(entity, sections=[target] if target else [])
        return template_renderer.render_section(section, context)

    async def fetch_sections(self, entity: dict[str, Any]) -> list[dict]:
        """从 PG 取实体的事实并分组为 Section 数据"""
        entity_id = str(entity["id"])
        facts = await pg_storage.search_facts(entity_id=entity_id, limit=200)
        return _group_facts(facts)

    async def render_document(self, entity: dict[str, Any]) -> str:
        """渲染文档（含来源文档信息，供 Document 类型页面）"""
        return await self.render_entity(entity)


# 模块级单例
renderer = KnowledgeRenderer()