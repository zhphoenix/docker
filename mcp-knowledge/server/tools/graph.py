"""Graph Tools - 事件影响链 / 事件搜索（Apache AGE Cypher）

Tools:
  16. trace_event_impact — 事件影响链追踪
  17. search_event       — 事件搜索 + 影响实体

依赖: Apache AGE 图存储（不可用时返回错误提示）
"""

from fastmcp import FastMCP

from server.storage.age import age_storage


def register_graph_tools(mcp: FastMCP) -> None:
    """注册 Graph 相关 MCP Tools（需要 AGE）"""

    @mcp.tool()
    async def trace_event_impact(event: str, depth: int = 3) -> dict:
        """事件影响链追踪

        从事件节点出发，追踪其对实体网络的影响传播路径。
        Event → Companies → Suppliers → Industries → Market Impact

        需要 Apache AGE 图数据库支持。

        Args:
            event: 事件名称或关键词（如 "AI Chip Export Restriction"、"台积电地震"）
            depth: 影响链追踪深度（1-4，默认 3）

        Returns:
            {event, direct_entities, impact_chain: [{entity, entity_id, entity_type}], total_impacted}
        """
        if not age_storage.available:
            return {
                "error": "Apache AGE not available. Event impact tracing requires graph database.",
                "hint": "Ensure AGE is initialized (postgres/init/08-age-init.sql)",
            }

        try:
            return await age_storage.trace_event_impact(event, depth)
        except Exception as e:
            return {"error": f"Event impact trace failed: {str(e)}"}

    @mcp.tool()
    async def search_event(query: str, event_type: str = "", limit: int = 10) -> dict:
        """搜索事件 + 影响实体

        在知识图谱中搜索事件节点，并返回每个事件影响的实体列表。

        需要 Apache AGE 图数据库支持。

        Args:
            query: 搜索关键词（匹配事件名称和描述）
            event_type: 事件类型过滤（earnings/regulation/merger/acquisition/product_launch/macro_policy/geopolitical/supply_chain/technology）
            limit: 返回数量上限（默认 10）

        Returns:
            {count, events: [{name, event_type, description, date, impacted_entities}]}
        """
        if not age_storage.available:
            return {
                "error": "Apache AGE not available. Event search requires graph database.",
                "hint": "Ensure AGE is initialized (postgres/init/08-age-init.sql)",
            }

        try:
            events = await age_storage.search_events(query, event_type, limit)
            return {"count": len(events), "events": events}
        except Exception as e:
            return {"error": f"Event search failed: {str(e)}"}
