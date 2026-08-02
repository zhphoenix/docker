"""Write Tools - 知识写入（创建实体/事实/关系 + 版本化更新）

Tools:
  9.  create_entity    — 创建实体
  10. create_fact      — 创建事实
  11. create_relation  — 创建关系
  12. update_knowledge — 版本化更新
"""

from fastmcp import FastMCP

from server.storage.postgres import pg_storage
from server.cache import knowledge_cache


def register_write_tools(mcp: FastMCP) -> None:
    """注册 Write 相关 MCP Tools"""

    @mcp.tool()
    async def create_entity(
        name: str,
        entity_type: str,
        description: str = "",
        canonical_name: str = "",
        aliases: list[str] | None = None,
        properties: dict | None = None,
        confidence: float = 1.0,
    ) -> dict:
        """创建知识实体

        Args:
            name: 实体名称（必填）
            entity_type: 实体类型（Company/Person/Product/Technology/Industry/Country/Organization/Event/Metric/Concept）
            description: 实体描述
            canonical_name: 规范名称（默认同 name）
            aliases: 别名列表
            properties: 扩展属性（如 ticker, market）
            confidence: 置信度 (0-1)

        Returns:
            {id, name, status: "created"}
        """
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

        # 写后缓存失效
        knowledge_cache.invalidate("entity:")
        knowledge_cache.invalidate("graph:")
        knowledge_cache.invalidate("profile:")

        return {"id": eid, "name": name, "status": "created"}

    @mcp.tool()
    async def create_fact(
        subject_entity: str,
        predicate: str,
        object_value: dict,
        unit: str = "",
        time_start: str = "",
        time_end: str = "",
        source_document: str = "",
        confidence: float = 1.0,
    ) -> dict:
        """创建结构化事实

        Args:
            subject_entity: 主体实体 ID（UUID）
            predicate: 谓词（如 "Revenue Growth"）
            object_value: 值对象（如 {"value": 56, "unit": "%"}）
            unit: 单位
            time_start: 起始时间（YYYY-MM-DD）
            time_end: 结束时间
            source_document: 来源文档 ID
            confidence: 置信度

        Returns:
            {id, predicate, status: "created"}
        """
        fact = {
            "subject_entity": subject_entity,
            "predicate": predicate,
            "object_value": object_value,
            "unit": unit or None,
            "time_start": time_start or None,
            "time_end": time_end or None,
            "source_document": source_document or None,
            "confidence": confidence,
        }

        fid = await pg_storage.create_fact(fact)

        # 写后缓存失效
        knowledge_cache.invalidate("profile:")

        return {"id": fid, "predicate": predicate, "status": "created"}

    @mcp.tool()
    async def create_relation(
        source_entity: str,
        target_entity: str,
        relation_type: str,
        confidence: float = 1.0,
        properties: dict | None = None,
        valid_from: str = "",
        valid_to: str = "",
    ) -> dict:
        """创建实体关系

        Args:
            source_entity: 源实体 ID（UUID）
            target_entity: 目标实体 ID（UUID）
            relation_type: 关系类型（supplier/customer/competitor/depends_on/owns/uses/invests_in/located_in/impacts/causes/partner/belongs_to）
            confidence: 置信度
            properties: 扩展属性
            valid_from: 关系生效起始时间（YYYY-MM-DD）
            valid_to: 关系失效时间（YYYY-MM-DD，空=仍有效）

        Returns:
            {id, relation_type, status: "created"}
        """
        relation = {
            "source_entity": source_entity,
            "target_entity": target_entity,
            "relation_type": relation_type,
            "confidence": confidence,
            "properties": properties or {},
            "valid_from": valid_from or None,
            "valid_to": valid_to or None,
        }

        rid = await pg_storage.create_relation(relation)

        # 写后缓存失效
        knowledge_cache.invalidate("graph:")
        knowledge_cache.invalidate("supply:")

        return {"id": rid, "relation_type": relation_type, "status": "created"}

    @mcp.tool()
    async def update_knowledge(
        object_type: str,
        object_id: str,
        updates: dict,
    ) -> dict:
        """版本化更新知识对象

        更新前自动保存当前版本快照到 audit.knowledge_versions。

        Args:
            object_type: 对象类型（entity / fact）
            object_id: 对象 UUID
            updates: 更新字段字典（如 {"description": "new desc", "confidence": 0.9}）

        Returns:
            {object_id, version, status: "updated"} 或 {error: "..."}
        """
        success = await pg_storage.update_knowledge(object_type, object_id, updates)

        if not success:
            return {"error": f"Object '{object_type}:{object_id}' not found or unsupported type"}

        # 写后缓存失效
        knowledge_cache.invalidate("entity:")
        knowledge_cache.invalidate("graph:")
        knowledge_cache.invalidate("profile:")

        return {"object_id": object_id, "object_type": object_type, "status": "updated"}
