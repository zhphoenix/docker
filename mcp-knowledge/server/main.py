"""MCP Knowledge Server - FastMCP 入口

基于 32_Knowledge_Agent接口规范.md 实现 16 个知识工具。
Transport: Streamable HTTP (:8200)
"""

import logging
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from server.config import settings
from server.storage.postgres import pg_storage
from server.storage.qdrant import qdrant_storage
from server.storage.age import age_storage
from server.llm import llm_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(server):
    """生命周期管理：启动初始化 / 关闭释放"""
    logger.info("MCP Knowledge Server starting...")
    await pg_storage.connect()
    # AGE 图存储（可选，失败不阻塞启动）
    try:
        await age_storage.connect()
    except Exception as e:
        logger.warning("AGE storage init failed (non-fatal): %s", e)
    logger.info(
        "MCP Knowledge Server ready (port=%d, age=%s)",
        settings.MCP_PORT,
        "available" if age_storage.available else "unavailable",
    )
    yield
    await age_storage.close()
    await pg_storage.close()
    await qdrant_storage.close()
    await llm_client.close()
    logger.info("MCP Knowledge Server stopped")


# 创建 FastMCP 实例
mcp = FastMCP(
    "knowledge-server",
    lifespan=lifespan,
    instructions=(
        "知识系统统一访问接口。提供实体搜索、关系图谱、事实查询、"
        "语义检索、知识写入和分析工具。"
    ),
)

# ──────────────────────────────────────────────
# 注册 Tools（按模块导入）
# ──────────────────────────────────────────────
from server.tools.entity import register_entity_tools  # noqa: E402
from server.tools.fact import register_fact_tools  # noqa: E402
from server.tools.semantic import register_semantic_tools  # noqa: E402
from server.tools.write import register_write_tools  # noqa: E402
from server.tools.analysis import register_analysis_tools  # noqa: E402
from server.tools.graph import register_graph_tools  # noqa: E402
from server.tools.inbox import register_inbox_tools  # noqa: E402
from server.tools.siyuan import register_siyuan_tools  # noqa: E402

register_entity_tools(mcp)
register_fact_tools(mcp)
register_semantic_tools(mcp)
register_write_tools(mcp)
register_analysis_tools(mcp)
register_graph_tools(mcp)
register_inbox_tools(mcp)
register_siyuan_tools(mcp)


# ──────────────────────────────────────────────
# 健康检查（非 MCP tool，供 Docker healthcheck）
# ──────────────────────────────────────────────
@mcp.tool()
async def health_check() -> dict:
    """服务健康检查"""
    from server.cache import knowledge_cache
    return {
        "status": "healthy",
        "cache_stats": knowledge_cache.stats,
        "pg_pool_size": pg_storage.pool.get_size() if pg_storage.pool else 0,
    }


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=settings.MCP_HOST,
        port=settings.MCP_PORT,
    )
