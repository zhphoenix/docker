"""Entity Tools - 实体搜索 / 详情 / 关系图谱

Tools:
  1. search_entity  — 搜索实体（名称 + 类型）
  2. get_entity     — 获取实体详情
  3. get_entity_graph — 获取关系图谱
"""

from fastmcp import FastMCP

from server.storage.postgres import pg_storage
from server.cache import knowledge_cache
from server.utils import serialize


def register_entity_tools(mcp: FastMCP) -> None:
    """注册 Entity 相关 MCP Tools"""

    @mcp.tool()
    async def search_entity(name: str = "", entity_type: str = "", limit: int = 10) -> list[dict]:
        """搜索知识实体

        支持名称模糊匹配和类型过滤。

        Args:
            name: 实体名称（模糊匹配）
            entity_type: 实体类型过滤（Company/Person/Product/Technology/Industry/Country/Organization/Event/Metric/Concept）
            limit: 返回数量上限

        Returns:
            实体列表 [{id, name, entity_type, description, canonical_name, confidence, source_count}]
        """
        return await pg_storage.search_entities(name=name, entity_type=entity_type, limit=limit)

    @mcp.tool()
    @knowledge_cache.cached("entity", lambda entity_id: entity_id)
    async def get_entity(entity_id: str) -> dict:
        """获取实体详情

        按 ID 获取完整实体信息，包含 aliases 和 properties。

        Args:
            entity_id: 实体 UUID

        Returns:
            实体完整信息 {id, name, entity_type, description, canonical_name, aliases, properties, confidence, ...}
        """
        result = await pg_storage.get_entity_by_id(entity_id)
        if not result:
            return {"error": f"Entity '{entity_id}' not found"}
        # 序列化 UUID/时间字段
        return serialize(result)

    @mcp.tool()
    @knowledge_cache.cached("graph", lambda entity, depth=2: f"{entity}:{depth}")
    async def get_entity_graph(entity: str, depth: int = 2) -> dict:
        """获取实体关系图谱

        从指定实体出发，递归遍历关系网络（最大深度 2）。

        Args:
            entity: 实体名称（如 "NVIDIA"、"腾讯"）
            depth: 遍历深度（1-2）

        Returns:
            {nodes: [{id, name, entity_type}], edges: [{source, target, relation_type, confidence, depth}]}
        """
        # 先解析实体名 → ID
        entities = await pg_storage.find_entity_by_name(entity, limit=1)
        if not entities:
            return {"nodes": [], "edges": [], "message": f"Entity '{entity}' not found"}

        root = entities[0]
        root_id = str(root["id"])

        # 图遍历
        edges_raw = await pg_storage.get_entity_graph(root_id, depth=depth)

        # 收集所有节点 ID
        node_ids = {root_id}
        for e in edges_raw:
            node_ids.add(str(e["source_entity"]))
            node_ids.add(str(e["target_entity"]))

        # 批量获取节点信息（避免 N+1 查询）
        node_records = await pg_storage.get_entities_by_ids(list(node_ids))
        nodes = [
            {
                "id": str(n["id"]),
                "name": n["name"],
                "entity_type": n["entity_type"],
            }
            for n in node_records
        ]

        edges = [
            {
                "source": str(e["source_entity"]),
                "target": str(e["target_entity"]),
                "relation_type": e["relation_type"],
                "confidence": e.get("confidence"),
                "depth": e["depth"],
            }
            for e in edges_raw
        ]

        return {"nodes": nodes, "edges": edges}
