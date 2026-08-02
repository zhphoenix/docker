"""Analysis Tools - 公司全景 / 供应链 / 风险因素

Tools:
  13. get_company_profile — 公司全景（并行聚合）
  14. get_supply_chain    — 供应链分析
  15. get_risk_factors    — 风险因素
"""

import asyncio

from fastmcp import FastMCP

from server.storage.postgres import pg_storage
from server.storage.age import age_storage
from server.cache import knowledge_cache
from server.utils import serialize

# 供应链相关关系类型
_SUPPLY_CHAIN_TYPES = ["supplier", "customer", "depends_on"]


def register_analysis_tools(mcp: FastMCP) -> None:
    """注册 Analysis 相关 MCP Tools"""

    @mcp.tool()
    @knowledge_cache.cached("profile", lambda entity: entity)
    async def get_company_profile(entity: str) -> dict:
        """获取公司全景信息

        并行聚合：基本信息 + 关系 + 事实 + 事件（asyncio.gather 优化）。

        Args:
            entity: 公司名称（如 "NVIDIA"、"腾讯"）

        Returns:
            {entity, relations, facts, events}
        """
        # 解析实体
        entities = await pg_storage.find_entity_by_name(entity, limit=1)
        if not entities:
            return {"error": f"Entity '{entity}' not found"}

        root = entities[0]
        eid = str(root["id"])

        # 并行 4 路查询
        info_task = pg_storage.get_entity_by_id(eid)
        relations_task = pg_storage.get_entity_graph(eid, depth=1)
        facts_task = pg_storage.search_facts(eid, limit=20)
        events_task = pg_storage.get_timeline(eid, limit=10)

        info, relations, facts, events = await asyncio.gather(
            info_task, relations_task, facts_task, events_task,
            return_exceptions=True,
        )

        # 处理异常
        if isinstance(info, Exception):
            info = root
        if isinstance(relations, Exception):
            relations = []
        if isinstance(facts, Exception):
            facts = []
        if isinstance(events, Exception):
            events = []

        # 序列化
        entity_info = serialize(info) if info else serialize(root)

        serialized_relations = [
            {
                "target": str(r["target_entity"]),
                "relation_type": r["relation_type"],
                "confidence": r.get("confidence"),
            }
            for r in relations
        ] if relations else []

        serialized_facts = [
            {
                "predicate": f["predicate"],
                "object_value": f["object_value"],
                "time_start": str(f["time_start"]) if f.get("time_start") else None,
                "confidence": f.get("confidence"),
            }
            for f in facts
        ] if facts else []

        serialized_events = [
            {
                "title": ev.get("title"),
                "event_date": str(ev["event_date"]) if ev.get("event_date") else None,
                "event_type": ev.get("event_type"),
            }
            for ev in events
        ] if events else []

        return {
            "entity": entity_info,
            "relations": serialized_relations,
            "facts": serialized_facts,
            "events": serialized_events,
        }

    @mcp.tool()
    @knowledge_cache.cached("supply", lambda entity: entity)
    async def get_supply_chain(entity: str) -> dict:
        """获取供应链分析

        查询实体的供应商、客户、依赖关系。
        优先使用 AGE 多跳遍历（性能更优），AGE 不可用时降级为 PG 查询。

        Args:
            entity: 公司名称

        Returns:
            {entity, suppliers: [...], customers: [...], dependencies: [...]}
        """
        # 尝试 AGE Cypher 多跳遍历
        if age_storage.available:
            try:
                cypher = f"""
                    MATCH (e)-[r]-(related)
                    WHERE (e.name = '{age_storage._escape(entity)}'
                           OR e.canonical_name = '{age_storage._escape(entity)}')
                      AND type(r) IN {list(_SUPPLY_CHAIN_TYPES)}
                    RETURN related, type(r) AS rel_type, r.confidence AS confidence
                    LIMIT 50
                """
                results = await age_storage.execute_cypher(
                    cypher, ["related", "rel_type", "confidence"]
                )
                if results:
                    suppliers, customers, dependencies = [], [], []
                    for row in results:
                        node = row.get("related", {})
                        rel_type = row.get("rel_type", "")
                        item = {
                            "id": node.get("entity_id", "") if isinstance(node, dict) else "",
                            "name": node.get("name", "") if isinstance(node, dict) else "",
                            "type": node.get("entity_type", "") if isinstance(node, dict) else "",
                            "relation": rel_type,
                            "confidence": row.get("confidence"),
                        }
                        if rel_type == "supplier":
                            suppliers.append(item)
                        elif rel_type == "customer":
                            customers.append(item)
                        elif rel_type == "depends_on":
                            dependencies.append(item)
                    return {
                        "entity": {"name": entity},
                        "suppliers": suppliers,
                        "customers": customers,
                        "dependencies": dependencies,
                        "source": "age",
                    }
            except Exception:
                pass  # Fallback to PG

        # Fallback: PostgreSQL 查询
        entities = await pg_storage.find_entity_by_name(entity, limit=1)
        if not entities:
            return {"error": f"Entity '{entity}' not found"}

        root = entities[0]
        eid = str(root["id"])

        relations = await pg_storage.get_relations_by_types(
            eid, _SUPPLY_CHAIN_TYPES, limit=50
        )

        # 按类型分组
        suppliers = []
        customers = []
        dependencies = []

        for r in relations:
            item = {
                "id": str(r["target_entity"]),
                "name": r.get("target_name", ""),
                "type": r.get("target_type", ""),
                "relation": r["relation_type"],
                "confidence": r.get("confidence"),
            }
            if r["relation_type"] == "supplier":
                suppliers.append(item)
            elif r["relation_type"] == "customer":
                customers.append(item)
            elif r["relation_type"] == "depends_on":
                dependencies.append(item)

        return {
            "entity": {"id": eid, "name": root["name"]},
            "suppliers": suppliers,
            "customers": customers,
            "dependencies": dependencies,
            "source": "postgres",
        }

    @mcp.tool()
    async def get_risk_factors(entity: str) -> dict:
        """获取风险因素

        聚合：低置信度事实 + 知识冲突 + 负面事件。

        Args:
            entity: 公司名称

        Returns:
            {entity, low_confidence_facts, conflicts, summary}
        """
        # 解析实体
        entities = await pg_storage.find_entity_by_name(entity, limit=1)
        if not entities:
            return {"error": f"Entity '{entity}' not found"}

        root = entities[0]
        eid = str(root["id"])

        risk_data = await pg_storage.get_risk_factors(eid)

        # 序列化
        low_conf = [
            {
                "id": str(f["id"]),
                "predicate": f["predicate"],
                "object_value": f["object_value"],
                "confidence": f.get("confidence"),
                "time_start": str(f["time_start"]) if f.get("time_start") else None,
            }
            for f in risk_data.get("low_confidence_facts", [])
        ]

        conflicts = [
            {
                "id": str(c["id"]),
                "conflict_type": c.get("conflict_type"),
                "status": c.get("status"),
                "fact_a": c.get("fact_a_predicate"),
                "fact_b": c.get("fact_b_predicate"),
            }
            for c in risk_data.get("conflicts", [])
        ]

        total_risks = len(low_conf) + len(conflicts)

        return {
            "entity": {"id": eid, "name": root["name"]},
            "low_confidence_facts": low_conf,
            "conflicts": conflicts,
            "summary": f"发现 {total_risks} 个潜在风险项（{len(low_conf)} 低置信度事实, {len(conflicts)} 知识冲突）",
        }
