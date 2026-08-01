"""Article Tools - 新闻搜索 / 详情

Tools:
  1. search_news      — 关键词 + 时间范围 + 分类搜索新闻
  2. get_news_article — 获取文章详情（含实体/事件）
"""

from fastmcp import FastMCP

from server.storage.postgres import news_pg_storage


def _serialize(row: dict) -> dict:
    """序列化 UUID/时间字段为字符串"""
    result = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        elif hasattr(v, "hex"):  # UUID
            result[k] = str(v)
        else:
            result[k] = v
    return result


def register_article_tools(mcp: FastMCP) -> None:
    """注册 Article 相关 MCP Tools"""

    @mcp.tool()
    async def search_news(keyword: str = "", category: str = "",
                          days: int = 7, limit: int = 20) -> list[dict]:
        """搜索新闻文章

        支持关键词模糊匹配、分类过滤和时间范围限制。

        Args:
            keyword: 搜索关键词（标题和内容模糊匹配）
            category: 分类过滤（macro/stock/company/geopolitics/policy/technology）
            days: 时间范围（最近 N 天，默认 7）
            limit: 返回数量上限（默认 20）

        Returns:
            新闻列表 [{id, title, summary, url, category, published_at, source_name, importance}]
        """
        results = await news_pg_storage.search_articles(
            keyword=keyword, category=category, days=days, limit=limit,
        )
        return [_serialize(r) for r in results]

    @mcp.tool()
    async def get_news_article(article_id: str) -> dict:
        """获取新闻文章详情

        按 ID 获取完整文章信息，包含关联的实体和事件。

        Args:
            article_id: 文章 UUID

        Returns:
            文章完整信息 {id, title, content, summary, entities[], events[], ...}
        """
        result = await news_pg_storage.get_article_by_id(article_id)
        if not result:
            return {"error": f"Article '{article_id}' not found"}
        # 序列化嵌套结构
        serialized = _serialize(result)
        if "entities" in serialized:
            serialized["entities"] = [_serialize(e) for e in serialized["entities"]]
        if "events" in serialized:
            serialized["events"] = [_serialize(e) for e in serialized["events"]]
        return serialized
