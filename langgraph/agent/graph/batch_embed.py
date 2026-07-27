"""Batch Embed - 批量向量化已有 chunks

将 PostgreSQL chunks 表中缺少 qdrant_point_id 的记录批量向量化并写入 Qdrant。
设计为后台长时任务，支持:
  - 断点续传（通过 qdrant_point_id IS NULL 自动跳过已处理）
  - 分批处理（batch_size 控制内存）
  - 进度追踪（tasks 表）
  - 优雅中断（cancel flag）
"""

import asyncio
import json
import logging
import uuid
from typing import Any

from tools.postgres import postgres_tool
from tools.embedding import embedding_tool
from tools.qdrant import qdrant_tool
from graph.task_queue import task_queue
from config.policy_loader import get_policy

logger = logging.getLogger(__name__)

# 取消标志
_cancelled = False


def cancel_batch_embed():
    """设置取消标志"""
    global _cancelled
    _cancelled = True
    logger.info("[BatchEmbed] Cancel requested")


async def run_batch_embed(
    collection: str = "documents_cn",
    batch_size: int | None = None,
    limit: int = 0,
    task_id: str | None = None,
) -> dict[str, Any]:
    """批量向量化 chunks

    Args:
        collection: 目标 collection（documents_cn / documents_hk）
        batch_size: 每批 embedding 数量（默认从 policy 读取）
        limit: 最大处理数量（0=全部）
        task_id: 外部任务 ID（由 Worker 传入，避免重复创建）

    Returns:
        {"embedded": N, "batches": N, "elapsed_seconds": N}
    """
    global _cancelled
    _cancelled = False

    if batch_size is None:
        batch_size = get_policy("pipeline.embed_batch_size", 16)

    # 统计待处理数量
    count_rows = await postgres_tool.query(
        "SELECT COUNT(*) as cnt FROM chunks "
        "WHERE collection_name = $1 AND qdrant_point_id IS NULL",
        collection,
    )
    total = count_rows[0]["cnt"] if count_rows else 0
    if limit > 0:
        total = min(total, limit)

    if total == 0:
        logger.info("[BatchEmbed] No chunks to embed for %s", collection)
        return {"embedded": 0, "batches": 0, "total": 0}

    logger.info("[BatchEmbed] Starting | collection=%s | total=%d | batch=%d",
                collection, total, batch_size)

    # 创建或使用外部任务
    own_task = task_id is None
    if own_task:
        task_id = await task_queue.create_task(
            task_type="batch_embed",
            title=f"Batch Embed {collection} ({total} chunks)",
            total_items=total,
            params={"collection": collection, "batch_size": batch_size},
        )
        await task_queue.start_task(task_id)

    embedded = 0
    batches = 0
    import time
    start_time = time.time()

    try:
        while True:
            if _cancelled:
                logger.info("[BatchEmbed] Cancelled at %d/%d", embedded, total)
                break

            # 检查 limit
            if limit > 0 and embedded >= limit:
                break

            # 取一批未嵌入的 chunks
            rows = await postgres_tool.query(
                """
                SELECT id, document_id, chunk_index, content, heading
                FROM chunks
                WHERE collection_name = $1 AND qdrant_point_id IS NULL
                ORDER BY document_id, chunk_index
                LIMIT $2
                """,
                collection, batch_size,
            )

            if not rows:
                break

            # Embedding
            texts = [r["content"][:2000] for r in rows]  # 截断保护
            try:
                vectors = await embedding_tool.embed(texts)
            except Exception as e:
                logger.error("[BatchEmbed] Embedding error: %s", e)
                await asyncio.sleep(2)  # 等待后重试
                continue

            # 构建 Qdrant points（批量获取文档元数据避免 N+1）
            doc_ids = list({str(r["document_id"]) for r in rows})
            doc_meta_rows = await postgres_tool.query(
                "SELECT id, symbol, market, year, company, document_type "
                "FROM documents WHERE id = ANY($1)",
                doc_ids,
            )
            meta_map = {str(r["id"]): r for r in doc_meta_rows} if doc_meta_rows else {}

            points = []
            point_ids = []
            for row, vector in zip(rows, vectors):
                point_id = str(uuid.uuid4())
                point_ids.append(point_id)

                meta = meta_map.get(str(row["document_id"]), {})

                points.append({
                    "id": point_id,
                    "vector": vector,
                    "payload": {
                        "content": row["content"],
                        "heading": row.get("heading", ""),
                        "symbol": meta.get("symbol", ""),
                        "market": meta.get("market", ""),
                        "year": meta.get("year"),
                        "company": meta.get("company", ""),
                        "document_type": meta.get("document_type", ""),
                        "document_id": str(row["document_id"]),
                        "chunk_index": row["chunk_index"],
                    },
                })

            # Upsert Qdrant
            await qdrant_tool.upsert(collection, points)

            # 更新 chunks 表（批量 executemany）
            update_args = [(row["id"], pid) for row, pid in zip(rows, point_ids)]
            await postgres_tool.execute_many(
                "UPDATE chunks SET qdrant_point_id = $2, embedded = true WHERE id = $1",
                update_args,
            )

            embedded += len(rows)
            batches += 1

            # 更新进度（每 10 批更新一次）
            if batches % 10 == 0:
                await task_queue.update_progress(
                    task_id, embedded,
                    stage="embedding",
                    current_name=f"batch {batches}",
                )
                elapsed = time.time() - start_time
                rate = embedded / elapsed if elapsed > 0 else 0
                logger.info(
                    "[BatchEmbed] Progress: %d/%d (%.1f%%) | rate=%.0f chunks/s",
                    embedded, total, (embedded / total * 100), rate,
                )

    except Exception as e:
        logger.error("[BatchEmbed] Fatal error: %s", e)
        if own_task:
            await task_queue.fail_task(task_id, str(e))
        raise

    elapsed = time.time() - start_time
    if own_task:
        await task_queue.complete_task(task_id)

    # 更新文档状态：所有 chunks 已嵌入的文档标记为 indexed
    await postgres_tool.execute(
        """
        UPDATE documents SET status = 'indexed'
        WHERE id IN (
            SELECT DISTINCT c.document_id
            FROM chunks c
            WHERE c.collection_name = $1
            AND c.document_id NOT IN (
                SELECT DISTINCT document_id FROM chunks
                WHERE collection_name = $1 AND qdrant_point_id IS NULL
            )
        )
        AND status != 'indexed'
        """,
        collection,
    )

    result = {"embedded": embedded, "batches": batches, "elapsed_seconds": round(elapsed, 1), "total": total}
    logger.info("[BatchEmbed] Complete | %s", result)
    return result
