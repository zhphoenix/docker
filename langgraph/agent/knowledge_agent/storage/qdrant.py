"""Knowledge Qdrant Storage - 批量向量索引 + 语义检索

复用 tools.qdrant.qdrant_tool + tools.embedding.embedding_tool 单例。
Collection: knowledge_entities / knowledge_facts
"""

import logging
import uuid

from qdrant_client.models import Filter, FieldCondition, MatchAny

from tools.qdrant import qdrant_tool
from tools.embedding import embedding_tool
from config.policy_loader import get_policy

logger = logging.getLogger(__name__)

# Collection 名称
COLLECTION_ENTITIES = "knowledge_entities"
COLLECTION_FACTS = "knowledge_facts"


class KnowledgeQdrantStorage:
    """知识向量存储层

    职责：
    - 批量 embed + upsert 实体/事实描述到 Qdrant
    - 语义检索（支持 entity_id 过滤）
    """

    # ──────────────────────────────────────────────
    # 索引
    # ──────────────────────────────────────────────

    async def index_entities(self, entities: list[dict]) -> int:
        """批量 embed + upsert 实体描述

        Args:
            entities: [{"id", "name", "entity_type", "description", "canonical_name"}]

        Returns:
            成功索引的数量
        """
        if not entities:
            return 0

        # 构建待 embed 文本
        texts = [
            f"{e['name']}: {e.get('description', '')}"
            for e in entities
        ]

        # 批量 embedding（复用 embedding_tool 内置 semaphore）
        try:
            vectors = await embedding_tool.embed(texts)
        except Exception as e:
            logger.error("Entity embedding failed: %s", e)
            return 0

        # 构建 Qdrant points
        points = [
            {
                "id": str(e.get("id", uuid.uuid4())),
                "vector": vec,
                "payload": {
                    "name": e["name"],
                    "entity_type": e["entity_type"],
                    "canonical_name": e.get("canonical_name", e["name"]),
                    "description": e.get("description", ""),
                },
            }
            for e, vec in zip(entities, vectors)
        ]

        # 分批 upsert
        batch_size = get_policy("knowledge.storage.qdrant_upsert_batch", 200)
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            await qdrant_tool.upsert(COLLECTION_ENTITIES, batch)

        logger.info("Indexed %d entities to Qdrant", len(points))
        return len(points)

    async def index_facts(self, facts: list[dict]) -> int:
        """批量 embed + upsert 事实描述

        Args:
            facts: [{"id", "subject_name", "predicate", "object_value", "entity_id"}]

        Returns:
            成功索引的数量
        """
        if not facts:
            return 0

        # 构建待 embed 文本
        texts = [
            f"{f.get('subject_name', '')} - {f['predicate']}: {f.get('object_value', '')}"
            for f in facts
        ]

        try:
            vectors = await embedding_tool.embed(texts)
        except Exception as e:
            logger.error("Fact embedding failed: %s", e)
            return 0

        points = [
            {
                "id": str(f.get("id", uuid.uuid4())),
                "vector": vec,
                "payload": {
                    "subject_name": f.get("subject_name", ""),
                    "predicate": f["predicate"],
                    "object_value": str(f.get("object_value", "")),
                    "entity_id": f.get("entity_id", ""),
                    "time_start": f.get("time_start", ""),
                },
            }
            for f, vec in zip(facts, vectors)
        ]

        batch_size = get_policy("knowledge.storage.qdrant_upsert_batch", 200)
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            await qdrant_tool.upsert(COLLECTION_FACTS, batch)

        logger.info("Indexed %d facts to Qdrant", len(points))
        return len(points)

    # ──────────────────────────────────────────────
    # 检索
    # ──────────────────────────────────────────────

    async def search_entities(
        self, query: str, limit: int = 10
    ) -> list[dict]:
        """语义搜索实体

        Args:
            query: 自然语言查询
            limit: 返回数量

        Returns:
            [{"id", "score", "payload": {"name", "entity_type", ...}}]
        """
        vectors = await embedding_tool.embed([query])
        if not vectors:
            return []

        return await qdrant_tool.search(
            collection=COLLECTION_ENTITIES,
            vector=vectors[0],
            limit=limit,
        )

    async def search_facts(
        self, query: str, entity_ids: list[str] | None = None, limit: int = 10
    ) -> list[dict]:
        """语义搜索事实（支持 entity_id 过滤）

        Args:
            query: 自然语言查询
            entity_ids: 可选实体 ID 过滤列表
            limit: 返回数量

        Returns:
            [{"id", "score", "payload": {"subject_name", "predicate", ...}}]
        """
        vectors = await embedding_tool.embed([query])
        if not vectors:
            return []

        query_filter = None
        if entity_ids:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="entity_id",
                        match=MatchAny(any=entity_ids),
                    )
                ]
            )

        return await qdrant_tool.search(
            collection=COLLECTION_FACTS,
            vector=vectors[0],
            limit=limit,
            query_filter=query_filter,
        )

    async def hybrid_search(
        self, query: str, entity_ids: list[str] | None = None, limit: int = 10
    ) -> dict:
        """混合检索：同时搜索实体和事实

        Args:
            query: 自然语言查询
            entity_ids: 可选实体过滤
            limit: 每类返回数量

        Returns:
            {"entities": [...], "facts": [...]}
        """
        vectors = await embedding_tool.embed([query])
        if not vectors:
            return {"entities": [], "facts": []}

        vector = vectors[0]

        # 并行搜索实体和事实
        entity_results = await qdrant_tool.search(
            collection=COLLECTION_ENTITIES,
            vector=vector,
            limit=limit,
        )

        fact_filter = None
        if entity_ids:
            fact_filter = Filter(
                must=[
                    FieldCondition(
                        key="entity_id",
                        match=MatchAny(any=entity_ids),
                    )
                ]
            )

        fact_results = await qdrant_tool.search(
            collection=COLLECTION_FACTS,
            vector=vector,
            limit=limit,
            query_filter=fact_filter,
        )

        return {
            "entities": entity_results,
            "facts": fact_results,
        }


# 模块级单例
knowledge_qdrant = KnowledgeQdrantStorage()
