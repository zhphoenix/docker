"""Search Tools - 语义检索与重排序组合封装

在 qdrant_tool / embedding_tool / reranker_tool 之上提供面向
Agent / Node 的高层检索语义：query → embedding → Qdrant 向量检索 → Rerank。

Node 层无需再关心向量生成、检索与重排的编排细节。
"""

import logging

from tools.embedding import embedding_tool
from tools.qdrant import qdrant_tool
from tools.reranker import reranker_tool

logger = logging.getLogger(__name__)


class SearchTools:
    """语义检索组合工具"""

    async def embed_query(self, query: str) -> list[float]:
        """将查询文本转为向量"""
        vectors = await embedding_tool.embed([query])
        return vectors[0]

    async def search(
        self,
        query: str,
        collection: str,
        limit: int = 10,
        query_filter=None,
    ) -> list[dict]:
        """向量语义检索

        Returns:
            [{"id": str, "score": float, "payload": dict}, ...]
        """
        vector = await self.embed_query(query)
        return await qdrant_tool.search(
            collection=collection,
            vector=vector,
            limit=limit,
            query_filter=query_filter,
        )

    async def search_and_rerank(
        self,
        query: str,
        collection: str,
        retrieve_limit: int = 20,
        query_filter=None,
    ) -> list[dict]:
        """检索 + 重排序

        先做宽召回（retrieve_limit），再用 Reranker 精排，
        返回按相关性降序的原始检索结果（携带 relevance_score）。

        Returns:
            [{"id","score","payload","relevance_score"}, ...] 已按相关性排序
        """
        hits = await self.search(
            query=query,
            collection=collection,
            limit=retrieve_limit,
            query_filter=query_filter,
        )
        if not hits:
            return []

        documents = [self._extract_text(h) for h in hits]
        try:
            ranked = await reranker_tool.rerank(query, documents)
        except Exception as e:
            logger.warning("Rerank failed (%s), falling back to vector score order", e)
            return hits

        # ranked: [{"index": int, "relevance_score": float}, ...]
        result = []
        for item in ranked:
            idx = item.get("index")
            if idx is None or idx >= len(hits):
                continue
            merged = dict(hits[idx])
            merged["relevance_score"] = item.get("relevance_score", 0.0)
            result.append(merged)
        result.sort(key=lambda x: x.get("relevance_score", 0.0), reverse=True)
        return result

    @staticmethod
    def _extract_text(hit: dict) -> str:
        """从检索结果中提取用于重排的文本"""
        payload = hit.get("payload", {}) or {}
        return payload.get("content") or payload.get("text") or ""


search_tools = SearchTools()
