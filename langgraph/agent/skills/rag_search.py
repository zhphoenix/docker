"""RAG Search Skill - 向量检索 + 重排序

使用模块级单例 Tool，避免重复创建连接。
"""

import logging
from typing import Any

from skills.base_skill import BaseSkill
from tools.qdrant import QdrantTool
from tools.embedding import EmbeddingTool
from tools.reranker import RerankerTool
from schemas.authority import get_authority_level, filter_by_authority
from qdrant_client.models import Filter, FieldCondition, MatchValue

logger = logging.getLogger(__name__)


class RAGSearchSkill(BaseSkill):
    """RAG 检索 Skill：Embedding → Qdrant 向量检索 → Reranker 重排序"""

    @property
    def name(self) -> str:
        return "rag_search"

    @property
    def description(self) -> str:
        return "基于语义向量检索相关文档片段，并通过 Reranker 精排"

    @property
    def tags(self) -> list[str]:
        return ["search", "rag", "retrieval"]

    def __init__(self):
        self._qdrant = QdrantTool()
        self._embedding = EmbeddingTool()
        self._reranker = RerankerTool()

    async def execute(self, **kwargs) -> dict[str, Any]:
        """执行 RAG 检索

        Args:
            query: 查询文本（必填）
            market: 市场过滤（cn/hk/us，可选）
            symbol: 股票代码过滤（可选）
            top_k: 返回数量（默认 5）
            use_rerank: 是否重排序（默认 True）
            min_authority: 最低权威度级别（可选，如 "very_high"）
            time_range: 时效过滤（可选，如 {"start_date": "2025-01-01"}）
        """
        query = kwargs.get("query")
        if not query:
            return {"success": False, "error": "query is required"}

        market = kwargs.get("market")
        symbol = kwargs.get("symbol")
        top_k = kwargs.get("top_k", 5)
        use_rerank = kwargs.get("use_rerank", True)
        min_authority = kwargs.get("min_authority")
        time_range = kwargs.get("time_range")

        try:
            # 1. Embedding
            vectors = await self._embedding.embed([query])
            query_vector = vectors[0]

            # 2. 确定 Collection
            collection_map = {"cn": "documents_cn", "hk": "documents_hk", "us": "documents_us"}
            collection = collection_map.get(market, "documents_cn")

            # 3. 构建过滤条件
            query_filter = self._build_filter(symbol, kwargs.get("year"))

            # 4. 向量检索
            results = await self._qdrant.search(
                collection=collection,
                vector=query_vector,
                top_k=top_k * 2 if use_rerank else top_k,
                query_filter=query_filter,
            )

            if not results:
                return {"success": True, "data": [], "total": 0}

            # 5. Rerank
            if use_rerank and len(results) > 1:
                documents = [r.get("payload", {}).get("content", "") for r in results]
                reranked = await self._reranker.rerank(query, documents)
                # 按 rerank 分数排序取 top_k
                indexed = list(enumerate(reranked))
                indexed.sort(key=lambda x: x[1].get("score", 0), reverse=True)
                top_indices = [idx for idx, _ in indexed[:top_k]]
                results = [results[i] for i in top_indices if i < len(results)]

            # 6. 格式化输出 + 权威度标注
            output = []
            for r in results[:top_k]:
                payload = r.get("payload", {})
                output.append({
                    "content": payload.get("content", ""),
                    "symbol": payload.get("symbol", ""),
                    "year": payload.get("year"),
                    "score": r.get("score", 0),
                    "authority": get_authority_level(
                        payload.get("source_provider", "_default")
                    ),
                    "metadata": {k: v for k, v in payload.items() if k != "content"},
                })

            # 7. 权威度过滤
            if min_authority:
                output = filter_by_authority(output, min_authority)

            return {"success": True, "data": output, "total": len(output)}

        except Exception as e:
            logger.exception("RAG search failed")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _build_filter(symbol: str | None, year: int | None) -> Filter | None:
        """构建 Qdrant 过滤条件"""
        conditions = []
        if symbol:
            conditions.append(FieldCondition(key="symbol", match=MatchValue(value=symbol)))
        if year:
            conditions.append(FieldCondition(key="year", match=MatchValue(value=year)))
        return Filter(must=conditions) if conditions else None
