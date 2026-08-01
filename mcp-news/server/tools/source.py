"""Source Tools - 新闻源管理

Tools:
  7. list_news_sources — 列出新闻源及状态
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


def register_source_tools(mcp: FastMCP) -> None:
    """注册 Source 相关 MCP Tools"""

    @mcp.tool()
    async def list_news_sources(enabled_only: bool = True) -> list[dict]:
        """列出新闻源及状态

        返回所有注册的新闻源信息。

        Args:
            enabled_only: 是否只返回启用的源（默认 true）

        Returns:
            新闻源列表 [{id, source_id, name, source_type, category, market, priority, enabled}]
        """
        results = await news_pg_storage.list_sources(enabled_only=enabled_only)
        return [_serialize(r) for r in results]
