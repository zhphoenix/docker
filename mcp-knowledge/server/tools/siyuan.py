"""SiYuan / Knowledge Object Tools - 知识对象与展示层交互

Tools:
  16. search_notes            — 搜索知识笔记（基于 PG SoT，返回笔记元数据）
  17. get_note                — 获取知识笔记详情（含 SiYuan 展示路径）
  18. create_knowledge_object — 创建知识对象并渲染到 SiYuan
  19. update_knowledge_object — 版本化更新知识对象并增量同步到 SiYuan
  20. create_research_report  — 创建研究报告文档
  21. create_event_note       — 创建事件笔记

设计红线：PostgreSQL 为唯一 SoT，SiYuan 仅展示层。所有写入经
Knowledge MCP Server；渲染经 SiYuan Sync adapter（模板驱动，非 LLM 拼接）。
"""

from fastmcp import FastMCP

from server.storage.postgres import pg_storage
from server.cache import knowledge_cache
from server.adapters.siyuan.mapper import (
    entity_to_path,
    notebook_for,
    section_path,
)
from server.adapters.siyuan.sync import siyuan_sync
from server.adapters.siyuan.client import siyuan_client
from server.adapters.siyuan.config import get_siyuan_config
from server.utils import serialize

# 合法对象类型（知识对象模板）
VALID_OBJECT_TYPES = {
    "Company", "Industry", "Event", "Person", "Product",
    "Technology", "Country", "Organization", "Metric", "Concept",
}


def _escape_markdown(text: str) -> str:
    """转义 Markdown 特殊字符，防止标题注入破坏文档结构"""
    return (
        text.replace("\\", "\\\\")
        .replace("#", "\\#")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("<", "\\<")
        .replace(">", "\\>")
    )


def _render_entity(entity: dict) -> dict:
    """实体 → 对外展示结构（含 SiYuan 路径）"""
    base = serialize(entity)
    base["siyuan"] = {
        "notebook": notebook_for(entity.get("entity_type", "Company")),
        "path": entity_to_path(entity),
        "available": siyuan_client.is_available_url(get_siyuan_config().base_url),
    }
    return base


def register_siyuan_tools(mcp: FastMCP) -> None:
    """注册 SiYuan / Knowledge Object 相关 MCP Tools"""

    @mcp.tool()
    async def search_notes(name: str = "", entity_type: str = "", limit: int = 20) -> dict:
        """搜索知识笔记（展示层视图）

        基于 PostgreSQL（唯一 SoT）检索知识对象，返回含 SiYuan 展示路径的笔记元数据。

        Args:
            name: 名称关键词（模糊匹配）
            entity_type: 对象类型过滤（Company/Industry/Event/Person/...）
            limit: 返回数量上限

        Returns:
            {total, items: [{id, name, entity_type, description, siyuan: {notebook, path}}]}
        """
        rows = await pg_storage.search_entities(name=name, entity_type=entity_type, limit=limit)
        items = [_render_entity(r) for r in rows]
        return {"total": len(items), "items": items}

    @mcp.tool()
    @knowledge_cache.cached("note", lambda object_id: object_id)
    async def get_note(object_id: str) -> dict:
        """获取知识笔记详情

        按 ID 获取知识对象完整信息，含 aliases/properties 与 SiYuan 展示路径。

        Args:
            object_id: 知识对象 UUID

        Returns:
            笔记详情 {id, name, entity_type, description, canonical_name,
                      aliases, properties, confidence, siyuan: {notebook, path}}
        """
        entity = await pg_storage.get_entity_by_id(object_id)
        if not entity:
            return {"error": f"Knowledge object '{object_id}' not found"}
        return _render_entity(entity)

    @mcp.tool()
    async def create_knowledge_object(
        name: str,
        entity_type: str = "Company",
        description: str = "",
        canonical_name: str = "",
        aliases: list[str] | None = None,
        properties: dict | None = None,
        confidence: float = 1.0,
        render_to_siyuan: bool = True,
    ) -> dict:
        """创建知识对象并渲染到 SiYuan 展示层

        先写入 PostgreSQL（SoT），再经 SiYuan Sync adapter 渲染页面。

        Args:
            name: 对象名称（必填）
            entity_type: 对象类型（Company/Industry/Event/Person/Product/Technology/Country/Organization/Metric/Concept）
            description: 描述
            canonical_name: 规范名称（默认同 name）
            aliases: 别名列表
            properties: 扩展属性（如 ticker, market, event_date）
            confidence: 置信度 (0-1)
            render_to_siyuan: 是否立即渲染到 SiYuan（默认 True）

        Returns:
            {id, name, entity_type, status: "created", sync: {status, action, path}}
        """
        if entity_type not in VALID_OBJECT_TYPES:
            return {"error": f"Invalid entity_type '{entity_type}'. Valid: {sorted(VALID_OBJECT_TYPES)}"}

        entity = {
            "name": name,
            "entity_type": entity_type,
            "description": description or None,
            "canonical_name": canonical_name or name,
            "aliases": aliases or [],
            "properties": properties or {},
            "confidence": confidence,
        }
        eid = await pg_storage.create_entity(entity)

        knowledge_cache.invalidate("entity:")
        knowledge_cache.invalidate("graph:")
        knowledge_cache.invalidate("profile:")
        knowledge_cache.invalidate("note:")

        sync_result: dict = {"status": "skipped", "action": "noop", "path": ""}
        if render_to_siyuan:
            try:
                # 读取完整实体（含 sync 字段）后渲染
                full = await pg_storage.get_entity_by_id(eid)
                if full:
                    sync_result = await siyuan_sync.sync_entity(full)
            except Exception as e:  # noqa: BLE001
                sync_result = {"status": "error", "action": "failed", "error": str(e)}

        return {"id": eid, "name": name, "entity_type": entity_type, "status": "created", "sync": sync_result}

    @mcp.tool()
    async def update_knowledge_object(
        object_id: str,
        updates: dict,
        render_to_siyuan: bool = True,
    ) -> dict:
        """版本化更新知识对象并增量同步到 SiYuan

        更新前自动保存当前版本快照到 audit.knowledge_versions，
        再按变更 Section 增量渲染到 SiYuan 展示层。

        Args:
            object_id: 知识对象 UUID
            updates: 更新字段字典（如 {"description": "...", "confidence": 0.9, "properties": {...}}）
            render_to_siyuan: 是否增量同步到 SiYuan（默认 True）

        Returns:
            {object_id, status: "updated", sync: {status, action, changed_sections, path}}
        """
        success = await pg_storage.update_knowledge("entity", object_id, updates)
        if not success:
            return {"error": f"Knowledge object '{object_id}' not found"}

        knowledge_cache.invalidate("entity:")
        knowledge_cache.invalidate("graph:")
        knowledge_cache.invalidate("profile:")
        knowledge_cache.invalidate("note:")

        sync_result: dict = {"status": "skipped", "action": "noop", "path": ""}
        if render_to_siyuan:
            try:
                full = await pg_storage.get_entity_by_id(object_id)
                if full:
                    sync_result = await siyuan_sync.sync_entity(full)
            except Exception as e:  # noqa: BLE001
                sync_result = {"status": "error", "action": "failed", "error": str(e)}

        return {"object_id": object_id, "status": "updated", "sync": sync_result}

    @mcp.tool()
    async def create_research_report(
        entity_id: str,
        title: str,
        content: str,
        section: str = "Research",
    ) -> dict:
        """创建研究报告文档（渲染到 SiYuan）

        将研究报告内容渲染为知识对象下的 Section 文档，写入 SiYuan 展示层。
        注意：报告正文仅写入 SiYuan 展示层，不入 PG（PG 为知识 SoT，报告为衍生视图）。

        Args:
            entity_id: 关联知识对象 UUID
            title: 报告标题
            content: 报告 Markdown 正文
            section: Section 名（默认 Research）

        Returns:
            {id, title, section, sync: {action, path}}
        """
        entity = await pg_storage.get_entity_by_id(entity_id)
        if not entity:
            return {"error": f"Knowledge object '{entity_id}' not found"}

        notebook = notebook_for(entity.get("entity_type", "Company"))
        path = section_path(entity_to_path(entity), section)
        # 清洗标题，避免 Markdown 特殊字符注入破坏文档结构
        markdown = f"# {_escape_markdown(title)}\n\n{content}\n"

        try:
            result = await siyuan_client.upsert_doc(notebook, path, markdown)
        except Exception as e:  # noqa: BLE001
            return {"error": f"SiYuan render failed: {e}"}

        return {"id": entity_id, "title": title, "section": section, "sync": result}

    @mcp.tool()
    async def create_event_note(
        event_id: str,
        summary: str = "",
        event_date: str = "",
    ) -> dict:
        """创建事件笔记（渲染到 SiYuan）

        将事件对象渲染为 SiYuan Events 笔记本下的笔记文档。

        Args:
            event_id: 事件对象 UUID
            summary: 事件摘要（附加到笔记）
            event_date: 事件日期（YYYY-MM-DD，用于路径）

        Returns:
            {id, siyuan: {notebook, path}, sync: {status, action, path}}
        """
        entity = await pg_storage.get_entity_by_id(event_id)
        if not entity:
            return {"error": f"Event object '{event_id}' not found"}

        # 若提供 event_date，合并进 properties 供路径映射使用
        if event_date:
            props = dict(entity.get("properties") or {})
            props["event_date"] = event_date
            entity["properties"] = props

        sync_result: dict = {"status": "skipped", "action": "noop", "path": ""}
        try:
            sync_result = await siyuan_sync.sync_entity(entity)
        except Exception as e:  # noqa: BLE001
            sync_result = {"status": "error", "action": "failed", "error": str(e)}

        return {
            "id": event_id,
            "siyuan": {"notebook": notebook_for("Event"), "path": entity_to_path(entity)},
            "sync": sync_result,
        }