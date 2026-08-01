"""Event Tools - 事件搜索 / 影响评估

Tools:
  3. search_news_event — 按类型/时间/实体搜索事件
  4. get_event_impact  — 获取事件影响评估
"""

from fastmcp import FastMCP

from server.storage.postgres import news_pg_storage


def _serialize(row: dict) -> dict:
    """序列化 UUID/时间字段为字符串"""
    result = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        elif hasattr(v, "hex"):
            result[k] = str(v)
        else:
            result[k] = v
    return result


def register_event_tools(mcp: FastMCP) -> None:
    """注册 Event 相关 MCP Tools"""

    @mcp.tool()
    async def search_news_event(event_type: str = "", entity_name: str = "",
                                days: int = 30, limit: int = 20) -> list[dict]:
        """搜索新闻事件

        按事件类型、关联实体和时间范围搜索。

        Args:
            event_type: 事件类型过滤（earnings/regulation/merger/acquisition/product_launch/macro_policy/geopolitical/supply_chain/technology）
            entity_name: 关联实体名称（模糊匹配）
            days: 时间范围（最近 N 天，默认 30）
            limit: 返回数量上限（默认 20）

        Returns:
            事件列表 [{id, event_type, title, summary, event_time, impact_score, impact_direction, ...}]
        """
        results = await news_pg_storage.search_events(
            event_type=event_type, entity_name=entity_name, days=days, limit=limit,
        )
        return [_serialize(r) for r in results]

    @mcp.tool()
    async def get_event_impact(event_id: str) -> dict:
        """获取事件影响评估

        按 ID 获取事件详情及其影响评估。

        Args:
            event_id: 事件 UUID

        Returns:
            事件影响信息 {id, event_type, title, impact_score, impact_direction, market, sector, ...}
        """
        result = await news_pg_storage.get_event_impact(event_id)
        if not result:
            return {"error": f"Event '{event_id}' not found"}
        return _serialize(result)
