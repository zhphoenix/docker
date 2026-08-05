"""Qdrant + Embedding 存储层 - 语义向量检索

Collection: knowledge_entities / knowledge_facts / knowledge_chunks / knowledge_reports
"""

import asyncio
import logging
from typing import Optional

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchAny

from server.config import settings

logger = logging.getLogger(__name__)

# Collection 名称
COLLECTION_ENTITIES = "knowledge_entities"
COLLECTION_FACTS = "knowledge_facts"
COLLECTION_CHUNKS = "knowledge_chunks"
COLLECTION_REPORTS = "knowledge_reports"


class QdrantStorage:
    """Qdrant 向量检索 + Embedding 调用"""

    def __init__(self):
        self._client: Optional[QdrantClient] = None
        self._embed_client: Optional[httpx.AsyncClient] = None
        self._embed_semaphore = asyncio.Semaphore(settings.EMBEDDING_MAX_CONCURRENCY)
        self._client_lock = asyncio.Lock()

    def _get_qdrant_client(self) -> QdrantClient:
        """获取 Qdrant 客户端（lazy init，避免模块导入时阻塞）"""
        if self._client is None:
            self._client = QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                timeout=120,
            )
        return self._client

    async def _get_embed_client(self) -> httpx.AsyncClient:
        """获取复用的 httpx 客户端（Lock 保护，防止并发创建）"""
        if self._embed_client is None or self._embed_client.is_closed:
            async with self._client_lock:
                if self._embed_client is None or self._embed_client.is_closed:
                    self._embed_client = httpx.AsyncClient(
                        timeout=httpx.Timeout(connect=5.0, read=settings.EMBEDDING_TIMEOUT, write=30.0, pool=5.0),
                        limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
                    )
        return self._embed_client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """文本向量化"""
        if not texts:
            return []

        async with self._embed_semaphore:
            client = await self._get_embed_client()
            response = await client.post(
                f"{settings.EMBEDDING_URL.rstrip('/')}/embeddings",
                json={"model": settings.EMBEDDING_MODEL, "input": texts},
            )
            response.raise_for_status()
            data = response.json()
            if "data" not in data:
                raise ValueError(f"Embedding response missing 'data' field: {list(data.keys())}")
            return [item["embedding"] for item in data["data"]]

    async def search(
        self,
        collection: str,
        vector: list[float],
        limit: int = 10,
        query_filter: Optional[Filter] = None,
        score_threshold: Optional[float] = None,
    ) -> list[dict]:
        """语义检索

        Args:
            score_threshold: 相似度下限（低于该分数的结果直接丢弃，
                防止无关概念如"光模块"混入"茅台"类查询的证据集）。
                None 表示不过滤（向后兼容）。
        """
        client = self._get_qdrant_client()
        response = await asyncio.to_thread(
            client.query_points,
            collection_name=collection,
            query=vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
        )
        return [
            {"id": str(p.id), "score": p.score, "payload": p.payload}
            for p in response.points
        ]

    async def semantic_search(
        self,
        query: str,
        collection: str = COLLECTION_CHUNKS,
        top_k: int = 10,
        score_threshold: Optional[float] = None,
    ) -> list[dict]:
        """语义搜索（embed + search 一步完成）"""
        vectors = await self.embed([query])
        if not vectors:
            return []
        return await self.search(
            collection=collection,
            vector=vectors[0],
            limit=top_k,
            score_threshold=score_threshold,
        )

    async def parallel_search(
        self,
        query: str,
        collections: list[str],
        top_k: int = 10,
        score_threshold: Optional[float] = None,
    ) -> dict[str, list[dict]]:
        """并行多 Collection 搜索（asyncio.gather 优化）"""
        vectors = await self.embed([query])
        if not vectors:
            return {c: [] for c in collections}

        vector = vectors[0]
        tasks = [
            self.search(
                collection=c,
                vector=vector,
                limit=top_k,
                score_threshold=score_threshold,
            )
            for c in collections
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = {}
        for c, r in zip(collections, results):
            if isinstance(r, Exception):
                logger.warning("Search %s failed: %s", c, r)
                output[c] = []
            else:
                output[c] = r
        return output

    async def search_facts_by_entity(
        self, query: str, entity_ids: list[str], limit: int = 10
    ) -> list[dict]:
        """语义搜索事实（entity_id 过滤）"""
        vectors = await self.embed([query])
        if not vectors:
            return []

        query_filter = Filter(
            must=[FieldCondition(key="entity_id", match=MatchAny(any=entity_ids))]
        ) if entity_ids else None

        return await self.search(
            collection=COLLECTION_FACTS,
            vector=vectors[0],
            limit=limit,
            query_filter=query_filter,
        )

    async def close(self) -> None:
        """关闭资源"""
        if self._embed_client and not self._embed_client.is_closed:
            await self._embed_client.aclose()
            self._embed_client = None
        if self._client:
            self._client.close()
            self._client = None


# 模块级单例
qdrant_storage = QdrantStorage()
