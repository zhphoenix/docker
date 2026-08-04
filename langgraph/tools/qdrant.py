"""Qdrant Tool - 封装 Qdrant 向量检索（:6333）"""

import asyncio
import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue, Range, PointIdsList  # noqa: F401 (re-export for nodes)

from config.settings import settings

logger = logging.getLogger(__name__)


class QdrantTool:
    """Qdrant 向量检索"""

    def __init__(self):
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            timeout=120,  # 2.5M points HNSW 搜索可能耗时较长
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

    async def delete_points(self, collection: str, point_ids: list[str]) -> int:
        """按 point id 批量删除向量；collection 不存在视为成功

        Returns:
            实际请求删除的 point 数量
        """
        if not point_ids:
            return 0
        try:
            await asyncio.to_thread(
                self.client.delete,
                collection_name=collection,
                points_selector=PointIdsList(points=point_ids),
            )
            return len(point_ids)
        except Exception as e:
            # collection 不存在等场景不阻塞调用方
            logger.warning("Qdrant delete_points failed | %s | %d ids | %s", collection, len(point_ids), e)
            return 0

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
