"""Node 2b: Embedding Deduplication — 跨批次语义去重

DLM §9 去重机制第二层：Embedding Similarity > 0.92 视为重复。
对所有进入该节点的文章执行（位于 classifier 之前，尚无 tier 信息）。

位置：deduplicator（Hash 去重）之后、classifier 之前。
失败不阻塞：如果 Qdrant/Embedding 服务不可用，直接透传文章。
"""

import logging
import uuid

from config.policy_loader import get_policy

logger = logging.getLogger(__name__)

# 语义去重相似度阈值（DLM §9）
SIMILARITY_THRESHOLD = 0.92

# Qdrant collection 名称
NEWS_EMBEDDINGS_COLLECTION = "news_embeddings"


async def embedding_dedup(state: dict) -> dict:
    """跨批次语义去重节点

    输入: unique_articles（经 Hash 去重后的文章列表）
    输出: unique_articles（去除语义重复后的文章列表）

    逻辑：
    1. 对每篇文章内容生成 Embedding
    2. 在 news_embeddings collection 中搜索相似文章
    3. similarity > 0.92 视为重复，过滤掉
    4. 非重复文章的 Embedding 写入 collection（供后续批次去重）
    """
    articles = state.get("unique_articles", [])
    new_errors: list[str] = []

    if not articles:
        return {"unique_articles": [], "errors": new_errors}

    # 检查是否启用语义去重
    enabled = get_policy("news.dedup.embedding_enabled", True)
    if not enabled:
        return {"unique_articles": articles, "errors": new_errors}

    try:
        from tools.embedding import embedding_tool
        from tools.qdrant import qdrant_tool
    except Exception as e:
        logger.warning("EmbeddingDedup: dependencies unavailable, skipping: %s", e)
        return {"unique_articles": articles, "errors": new_errors}

    # 确保 collection 存在
    await _ensure_collection(qdrant_tool)

    threshold = get_policy("news.dedup.similarity_threshold", SIMILARITY_THRESHOLD)
    unique = []
    new_points = []

    for art in articles:
        content = art.get("content", "")[:2000]
        title = art.get("title", "")

        if not content:
            unique.append(art)
            continue

        try:
            # 生成 Embedding
            vectors = await embedding_tool.embed([f"{title} {content}"])
            vector = vectors[0]

            # 搜索已有相似文章
            hits = await qdrant_tool.search(
                NEWS_EMBEDDINGS_COLLECTION, vector, limit=1
            )

            if hits and hits[0]["score"] > threshold:
                logger.info(
                    "EmbeddingDedup: '%s' similar to existing (score=%.3f), skipping",
                    title[:50], hits[0]["score"],
                )
                continue

            # 非重复，保留并记录待写入
            unique.append(art)
            point_id = str(uuid.uuid4())
            new_points.append({
                "id": point_id,
                "vector": vector,
                "payload": {
                    "title": title,
                    "content_hash": art.get("content_hash", ""),
                    "source": art.get("source_id", ""),
                },
            })

        except Exception as e:
            # 单篇失败不阻塞，保留文章
            logger.debug("EmbeddingDedup: failed for '%s': %s", title[:50], e)
            unique.append(art)

    # 批量写入新 Embedding 点
    if new_points:
        try:
            await qdrant_tool.upsert(NEWS_EMBEDDINGS_COLLECTION, new_points)
            logger.info("EmbeddingDedup: upserted %d new embeddings", len(new_points))
        except Exception as e:
            logger.warning("EmbeddingDedup: upsert failed (non-blocking): %s", e)

    deduped_count = len(articles) - len(unique)
    if deduped_count > 0:
        logger.info("EmbeddingDedup: removed %d semantic duplicates", deduped_count)

    return {"unique_articles": unique, "errors": new_errors}


async def _ensure_collection(qdrant_tool) -> None:
    """确保 news_embeddings collection 存在"""
    import asyncio

    try:
        collections = await asyncio.to_thread(
            qdrant_tool.client.get_collections
        )
        names = [c.name for c in collections.collections]
        if NEWS_EMBEDDINGS_COLLECTION not in names:
            from qdrant_client.models import Distance, VectorParams
            await asyncio.to_thread(
                qdrant_tool.client.create_collection,
                collection_name=NEWS_EMBEDDINGS_COLLECTION,
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
            )
            logger.info("EmbeddingDedup: created collection '%s'", NEWS_EMBEDDINGS_COLLECTION)
    except Exception as e:
        logger.debug("EmbeddingDedup: ensure_collection check failed: %s", e)
