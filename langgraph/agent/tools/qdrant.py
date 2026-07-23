"""Qdrant Tool - 封装 Qdrant 向量检索（:6333）"""

import asyncio
import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Filter

from config.settings import settings

logger = logging.getLogger(__name__)


class QdrantTool:
    """Qdrant 向量检索"""

    def __init__(self):
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
        )

    async def search(
        self,
        collection: str,
        vector: list[float],
        limit: int = 10,
        query_filter: Optional[Filter] = None,
    ) -> list[dict]:
        """语义检索

        Args:
            collection: Collection 名称（如 documents_cn）
            vector: 查询向量
            limit: 返回数量
            query_filter: Qdrant 过滤条件

        Returns:
            [{"id": str, "score": float, "payload": dict}, ...]
        """
        # 使用 to_thread 避免阻塞事件循环
        response = await asyncio.to_thread(
            self.client.query_points,
            collection_name=collection,
            query=vector,
            query_filter=query_filter,
            limit=limit,
        )
        return [
            {"id": str(p.id), "score": p.score, "payload": p.payload}
            for p in response.points
        ]

    async def upsert(self, collection: str, points: list[dict]) -> None:
        """插入/更新向量

        Args:
            collection: Collection 名称
            points: [{"id": int, "vector": list[float], "payload": dict}, ...]
        """
        await asyncio.to_thread(
            self.client.upsert,
            collection_name=collection,
            points=[PointStruct(**p) for p in points],
        )


# 模块级单例
qdrant_tool = QdrantTool()
