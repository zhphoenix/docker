"""Semantic Tools - 语义向量检索

Tools:
  7. semantic_search   — 语义搜索（Qdrant）
  8. similar_documents — 混合检索（并行多 Collection）
"""

from fastmcp import FastMCP

from server.storage.qdrant import (
    qdrant_storage,
    COLLECTION_CHUNKS,
    COLLECTION_ENTITIES,
    COLLECTION_FACTS,
    COLLECTION_REPORTS,
)

# 合法 Collection 映射
_VALID_COLLECTIONS = {
    "chunks": COLLECTION_CHUNKS,
    "entities": COLLECTION_ENTITIES,
    "facts": COLLECTION_FACTS,
    "reports": COLLECTION_REPORTS,
}


def register_semantic_tools(mcp: FastMCP) -> None:
    """注册 Semantic 相关 MCP Tools"""

    @mcp.tool()
    async def semantic_search(query: str, collection: str = "chunks", top_k: int = 10) -> dict:
        """语义向量检索

        基于 Qwen3-Embedding-4B (2560维) 对 Qdrant 进行语义搜索。

        Args:
            query: 自然语言查询（如 "AI semiconductor supply chain risk"）
            collection: 目标 Collection（chunks/entities/facts/reports）
            top_k: 返回结果数量

        Returns:
            {collection, results: [{id, score, payload}], count}
        """
        col_name = _VALID_COLLECTIONS.get(collection, COLLECTION_CHUNKS)

        results = await qdrant_storage.semantic_search(
            query=query, collection=col_name, top_k=top_k
        )

        return {
            "collection": collection,
            "results": results,
            "count": len(results),
        }

    @mcp.tool()
    async def similar_documents(query: str, top_k: int = 10) -> dict:
        """混合语义检索（并行多 Collection）

        同时在 entities + facts + chunks 三个 Collection 并行搜索，
        使用 asyncio.gather 优化延迟。

        Args:
            query: 自然语言查询
            top_k: 每个 Collection 返回数量

        Returns:
            {entities: [...], facts: [...], chunks: [...]}
        """
        results = await qdrant_storage.parallel_search(
            query=query,
            collections=[COLLECTION_ENTITIES, COLLECTION_FACTS, COLLECTION_CHUNKS],
            top_k=top_k,
        )

        return {
            "entities": results.get(COLLECTION_ENTITIES, []),
            "facts": results.get(COLLECTION_FACTS, []),
            "chunks": results.get(COLLECTION_CHUNKS, []),
        }
