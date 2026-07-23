"""Web Search Tool - 预留，Web 搜索"""

import logging

logger = logging.getLogger(__name__)


class WebSearchTool:
    """Web 搜索工具（预留）"""

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        """搜索

        Args:
            query: 搜索查询
            limit: 返回结果数量

        Returns:
            [{"title": str, "url": str, "snippet": str}, ...]
        """
        raise NotImplementedError("Web search tool not yet implemented")


web_search_tool = WebSearchTool()
