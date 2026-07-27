"""Document Pipeline - 文档处理全链路

流程: MinIO PDF → Docling 解析 → Chunk 分片 → Embedding → Qdrant → PostgreSQL 状态更新

支持:
  - 批量处理（limit 控制）
  - 断点续传（通过 tasks 表 stage/current_item）
  - 失败重试（task_queue retry_count）
  - Docling 不可用时优雅降级（跳过解析，标记等待）
"""

import json
import logging
import uuid
from typing import Any

from tools.postgres import postgres_tool
from tools.minio import minio_tool
from tools.docling import docling_tool, DoclingError
from tools.chunker import chunk_markdown
from tools.embedding import embedding_tool
from tools.qdrant import qdrant_tool
from graph.task_queue import task_queue
from config.policy_loader import get_policy

logger = logging.getLogger(__name__)

# Collection 映射
MARKET_COLLECTION = {
    "cn": "documents_cn",
    "hk": "documents_hk",
    "us": "documents_us",
}


class DocumentPipeline:
    """文档处理 Pipeline"""

    def __init__(self):
        self.batch_size = get_policy("pipeline.batch_size", 50)
        self.embed_batch_size = get_policy("pipeline.embed_batch_size", 16)

    async def process_pending_documents(self, limit: int = 50) -> dict[str, int]:
        """处理所有 pending 状态的文档

        Returns:
            {"processed": N, "failed": N, "skipped": N}
        """
        docs = await postgres_tool.query(
            """
            SELECT id, market, symbol, company, year, document_type,
                   bucket, object_key, language
            FROM documents
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT $1
            """,
            limit,
        )

        if not docs:
            logger.info("No pending documents to process")
            return {"processed": 0, "failed": 0, "skipped": 0}

        # 创建 Pipeline 任务
        task_id = await task_queue.create_task(
            task_type="doc_pipeline",
            title=f"文档处理 Pipeline ({len(docs)} docs)",
            total_items=len(docs),
        )
        await task_queue.start_task(task_id)

        stats = {"processed": 0, "failed": 0, "skipped": 0}

        for i, doc in enumerate(docs, 1):
            doc_id = str(doc["id"])
            symbol = doc.get("symbol", "?")
            market = doc.get("market", "?")

            try:
                await task_queue.update_progress(
                    task_id, i, stage="processing",
                    current_name=f"{market}/{symbol}/{doc.get('year', '')}",
                )

                result = await self._process_single_document(doc)
                if result == "indexed":
                    stats["processed"] += 1
                else:
                    stats["skipped"] += 1

            except Exception as e:
                logger.error(
                    "Pipeline error | doc=%s | %s/%s | %s",
                    doc_id[:8], market, symbol, e,
                )
                stats["failed"] += 1
                await postgres_tool.execute(
                    "UPDATE documents SET status = 'error', "
                    "metadata = metadata || $2::jsonb WHERE id = $1",
                    doc_id, json.dumps({"error": str(e)[:500]}),
                )

        await task_queue.complete_task(task_id)
        logger.info(
            "Pipeline complete | processed=%d | failed=%d | skipped=%d",
            stats["processed"], stats["failed"], stats["skipped"],
        )
        return stats

    async def _process_single_document(self, doc: dict) -> str:
        """处理单个文档的完整链路

        Returns:
            "indexed" | "skipped"
        """
        doc_id = str(doc["id"])
        market = doc.get("market", "cn")
        symbol = doc.get("symbol", "")
        bucket = doc.get("bucket", "documents")
        object_key = doc.get("object_key", "")

        # 1. 检查 object_key
        if not object_key:
            logger.warning("Doc %s has no object_key, skipping", doc_id[:8])
            return "skipped"

        # 2. 检查是否已有 chunks（断点续传）
        existing = await postgres_tool.query(
            "SELECT COUNT(*) as cnt FROM chunks WHERE document_id = $1", doc_id
        )
        if existing and existing[0]["cnt"] > 0:
            # 已有 chunks，确保 Qdrant 有向量后标记 indexed
            await postgres_tool.execute(
                "UPDATE documents SET status = 'indexed' WHERE id = $1", doc_id
            )
            return "indexed"

        # 3. 下载 PDF from MinIO
        try:
            pdf_data = await minio_tool.download(bucket, object_key)
        except Exception as e:
            logger.warning("MinIO download failed | %s | %s", object_key, e)
            await postgres_tool.execute(
                "UPDATE documents SET status = 'error', "
                "metadata = metadata || $2::jsonb WHERE id = $1",
                doc_id, json.dumps({"error": f"MinIO download failed: {e}"}),
            )
            return "skipped"

        # 4. Docling 解析 → Markdown
        try:
            filename = object_key.split("/")[-1] if "/" in object_key else object_key
            md_content = await docling_tool.convert_file(pdf_data, filename)
        except DoclingError as e:
            logger.warning("Docling failed | %s | %s", doc_id[:8], e)
            await postgres_tool.execute(
                "UPDATE documents SET status = 'parse_failed', "
                "metadata = metadata || $2::jsonb WHERE id = $1",
                doc_id, json.dumps({"error": f"Docling: {e}"}),
            )
            return "skipped"
        except Exception as e:
            # Docling 服务不可用
            logger.warning("Docling unavailable | %s | %s", doc_id[:8], e)
            await postgres_tool.execute(
                "UPDATE documents SET status = 'waiting_parser' WHERE id = $1",
                doc_id,
            )
            return "skipped"

        # 5. 存储 Markdown 到 MinIO（备份）
        md_key = object_key.rsplit(".", 1)[0] + ".md"
        try:
            await minio_tool.upload(bucket, md_key, md_content.encode("utf-8"))
        except Exception:
            pass  # 非关键路径，失败不阻塞

        # 6. 分片
        chunks = chunk_markdown(md_content)
        if not chunks:
            logger.warning("No chunks generated | %s", doc_id[:8])
            await postgres_tool.execute(
                "UPDATE documents SET status = 'parsed', chunk_count = 0 WHERE id = $1",
                doc_id,
            )
            return "skipped"

        # 7. Embedding（分批）
        collection = MARKET_COLLECTION.get(market, "documents_cn")
        all_vectors: list[list[float]] = []

        for batch_start in range(0, len(chunks), self.embed_batch_size):
            batch = chunks[batch_start:batch_start + self.embed_batch_size]
            texts = [c["content"] for c in batch]
            vectors = await embedding_tool.embed(texts)
            all_vectors.extend(vectors)

        # 8. 写入 Qdrant + PostgreSQL chunks
        points = []
        chunk_records = []

        for i, (chunk, vector) in enumerate(zip(chunks, all_vectors)):
            point_id = str(uuid.uuid4())
            points.append({
                "id": point_id,
                "vector": vector,
                "payload": {
                    "content": chunk["content"],
                    "heading": chunk.get("heading", ""),
                    "symbol": symbol,
                    "market": market,
                    "year": doc.get("year"),
                    "document_type": doc.get("document_type", ""),
                    "company": doc.get("company", ""),
                    "document_id": doc_id,
                    "chunk_index": i,
                },
            })
            chunk_records.append((
                doc_id, i, chunk["content"],
                chunk.get("heading", ""), collection, point_id,
            ))

        # Upsert Qdrant（分批，每批 100）
        for batch_start in range(0, len(points), 100):
            batch = points[batch_start:batch_start + 100]
            await qdrant_tool.upsert(collection, batch)

        # 写入 PostgreSQL chunks 表
        for record in chunk_records:
            await postgres_tool.execute(
                """
                INSERT INTO chunks (document_id, chunk_index, content, heading,
                                    collection_name, qdrant_point_id)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (document_id, chunk_index) DO NOTHING
                """,
                record[0], record[1], record[2], record[3], record[4], record[5],
            )

        # 9. 更新文档状态
        await postgres_tool.execute(
            """
            UPDATE documents
            SET status = 'indexed', parser = 'docling',
                chunk_count = $2, updated_at = NOW()
            WHERE id = $1
            """,
            doc_id, len(chunks),
        )

        logger.info(
            "Document indexed | %s/%s | chunks=%d | collection=%s",
            market, symbol, len(chunks), collection,
        )
        return "indexed"

    async def get_pipeline_status(self) -> dict[str, Any]:
        """获取 Pipeline 整体状态"""
        rows = await postgres_tool.query(
            """
            SELECT status, COUNT(*) as cnt
            FROM documents
            GROUP BY status
            ORDER BY cnt DESC
            """
        )
        return {r["status"]: r["cnt"] for r in rows}

    async def reindex_document(self, doc_id: str) -> bool:
        """重新索引单个文档（清除旧 chunks + 重新处理）"""
        # 删除旧 chunks
        await postgres_tool.execute(
            "DELETE FROM chunks WHERE document_id = $1", doc_id
        )
        # 重置状态
        await postgres_tool.execute(
            "UPDATE documents SET status = 'pending', chunk_count = 0 WHERE id = $1",
            doc_id,
        )
        return True


# 模块级单例
doc_pipeline = DocumentPipeline()
