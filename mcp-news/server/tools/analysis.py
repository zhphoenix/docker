"""Analysis Tools - 新闻影响分析 / 时间线

Tools:
  5. analyze_news_impact — 聚合分析实体近期新闻影响
  6. get_news_timeline   — 获取实体新闻时间线
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


def register_analysis_tools(mcp: FastMCP) -> None:
    """注册 Analysis 相关 MCP Tools"""

    @mcp.tool()
    async def analyze_news_impact(entity_name: str, days: int = 30) -> dict:
        """聚合分析实体近期新闻影响

        汇总指定实体在近期新闻中的事件和影响评估。

        Args:
            entity_name: 实体名称（如 "NVIDIA"、"腾讯"）
            days: 分析时间范围（最近 N 天，默认 30）

        Returns:
            影响聚合 {entity_name, total_events, positive_count, negative_count,
                      avg_impact_score, events[]}
        """
        results = await news_pg_storage.get_entity_news_impact(entity_name, days=days)

        if not results:
            return {
                "entity_name": entity_name,
                "total_events": 0,
                "message": f"No news found for '{entity_name}' in last {days} days",
            }

        # 聚合统计
        positive = sum(1 for r in results if r.get("impact_direction") == "positive")
        negative = sum(1 for r in results if r.get("impact_direction") == "negative")
        scores = [r["impact_score"] for r in results if r.get("impact_score") is not None]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        return {
            "entity_name": entity_name,
            "days": days,
            "total_events": len(results),
            "positive_count": positive,
            "negative_count": negative,
            "neutral_count": len(results) - positive - negative,
            "avg_impact_score": round(avg_score, 3),
            "events": [_serialize(r) for r in results[:20]],
        }

    @mcp.tool()
    async def get_news_timeline(entity_name: str, days: int = 90,
                                limit: int = 50) -> list[dict]:
        """获取实体新闻时间线

        按时间倒序返回与指定实体相关的所有新闻。

        Args:
            entity_name: 实体名称（如 "NVIDIA"、"台积电"）
            days: 时间范围（最近 N 天，默认 90）
            limit: 返回数量上限（默认 50）

        Returns:
            新闻时间线 [{title, category, published_at, url, importance, source_name}]
        """
        results = await news_pg_storage.get_entity_news_timeline(
            entity_name, days=days, limit=limit,
        )
        return [_serialize(r) for r in results]
