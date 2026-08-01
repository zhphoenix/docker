"""MCP News Server - FastMCP 入口

News Intelligence Pipeline 对外查询接口，7 个 Tools。
Transport: Streamable HTTP (:8201)
"""

import logging
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from server.config import settings
from server.storage.postgres import news_pg_storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(server):
    """生命周期管理：启动初始化 / 关闭释放"""
    logger.info("MCP News Server starting...")
    await news_pg_storage.connect()
    logger.info("MCP News Server ready (port=%d)", settings.MCP_PORT)
    yield
    await news_pg_storage.close()
    logger.info("MCP News Server stopped")


# 创建 FastMCP 实例
mcp = FastMCP(
    "news-server",
    lifespan=lifespan,
    instructions=(
        "新闻智能系统查询接口。提供新闻搜索、事件查询、影响分析、"
        "实体时间线和新闻源管理工具。"
    ),
)

# ──────────────────────────────────────────────
# 注册 Tools（按模块导入）
# ──────────────────────────────────────────────
from server.tools.article import register_article_tools  # noqa: E402
from server.tools.event import register_event_tools  # noqa: E402
from server.tools.analysis import register_analysis_tools  # noqa: E402
from server.tools.source import register_source_tools  # noqa: E402

register_article_tools(mcp)
register_event_tools(mcp)
register_analysis_tools(mcp)
register_source_tools(mcp)


# ──────────────────────────────────────────────
# 健康检查
# ──────────────────────────────────────────────
@mcp.tool()
async def health_check() -> dict:
    """服务健康检查"""
    return {
        "status": "healthy",
        "service": "mcp-news",
        "pg_pool_size": news_pg_storage.pool.get_size() if news_pg_storage.pool else 0,
    }


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=settings.MCP_HOST,
        port=settings.MCP_PORT,
    )
