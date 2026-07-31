"""Fact Tools - 事实查询 / 版本历史 / 事件时间线

Tools:
  4. search_facts    — 查询实体事实
  5. get_fact_history — 获取事实版本历史
  6. get_timeline    — 获取实体事件时间线
"""

from fastmcp import FastMCP

from server.storage.postgres import pg_storage


def register_fact_tools(mcp: FastMCP) -> None:
    """注册 Fact 相关 MCP Tools"""

    @mcp.tool()
    async def search_facts(entity: str, topic: str = "", limit: int = 20) -> dict:
        """搜索实体相关的结构化事实

        查询实体的事实记录，支持按主题（predicate）过滤。

        Args:
            entity: 实体名称（如 "NVIDIA"、"腾讯"）
            topic: 主题/谓词过滤（如 "revenue"、"growth"）
            limit: 返回数量上限

        Returns:
            {entity: {id, name}, facts: [{predicate, object_value, unit, time_start, confidence, source_title}]}
        """
        # 解析实体
        entities = await pg_storage.find_entity_by_name(entity, limit=1)
        if not entities:
            return {"error": f"Entity '{entity}' not found", "facts": []}

        root = entities[0]
        entity_id = str(root["id"])

        facts = await pg_storage.search_facts(entity_id, predicate=topic, limit=limit)

        # 序列化
        serialized_facts = []
        for f in facts:
            serialized_facts.append({
                "id": str(f["id"]),
                "predicate": f["predicate"],
                "object_value": f["object_value"],
                "unit": f.get("unit"),
                "time_start": str(f["time_start"]) if f.get("time_start") else None,
                "time_end": str(f["time_end"]) if f.get("time_end") else None,
                "confidence": f.get("confidence"),
                "verification_status": f.get("verification_status"),
                "source_title": f.get("source_title"),
            })

        return {
            "entity": {"id": entity_id, "name": root["name"]},
            "facts": serialized_facts,
            "count": len(serialized_facts),
        }

    @mcp.tool()
    async def get_fact_history(fact_id: str) -> dict:
        """获取事实的版本历史

        金融知识必须可追溯。返回事实的所有历史版本快照。

        Args:
            fact_id: 事实 UUID

        Returns:
            {fact_id, versions: [{version, content, created_by, created_at}]}
        """
        versions = await pg_storage.get_fact_history(fact_id)

        serialized = []
        for v in versions:
            serialized.append({
                "version": v["version"],
                "content": v["content"],
                "created_by": v.get("created_by"),
                "created_at": str(v["created_at"]) if v.get("created_at") else None,
            })

        return {
            "fact_id": fact_id,
            "versions": serialized,
            "count": len(serialized),
        }

    @mcp.tool()
    async def get_timeline(entity: str, limit: int = 20) -> dict:
        """获取实体事件时间线

        用于宏观研究和事件分析。

        Args:
            entity: 实体名称（如 "NVIDIA"）
            limit: 返回事件数量

        Returns:
            {entity: {id, name}, events: [{event_type, title, event_date, impact, confidence}]}
        """
        # 解析实体
        entities = await pg_storage.find_entity_by_name(entity, limit=1)
        if not entities:
            return {"error": f"Entity '{entity}' not found", "events": []}

        root = entities[0]
        entity_id = str(root["id"])

        events = await pg_storage.get_timeline(entity_id, limit=limit)

        serialized_events = []
        for ev in events:
            serialized_events.append({
                "id": str(ev["id"]),
                "event_type": ev.get("event_type"),
                "title": ev.get("title"),
                "description": ev.get("description"),
                "event_date": str(ev["event_date"]) if ev.get("event_date") else None,
                "impact": ev.get("impact"),
                "confidence": ev.get("confidence"),
            })

        return {
            "entity": {"id": entity_id, "name": root["name"]},
            "events": serialized_events,
            "count": len(serialized_events),
        }
