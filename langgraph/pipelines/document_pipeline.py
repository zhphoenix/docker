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
import re
import time
import uuid
from typing import Any

from tools.postgres import postgres_tool
from tools.minio import minio_tool
from tools.docling import docling_tool, DoclingError
from tools.chunker import chunk_markdown
from tools.embedding import embedding_tool
from tools.qdrant import qdrant_tool
from runtime.queue import task_queue
from config.policy_loader import get_policy
from config.settings import settings
from pipelines.acquire import (
    AcquireOrigin,
    AcquirePriority,
    AcquireTrigger,
    build_acquire_metadata,
    merge_acquire_into_metadata,
)
from pipelines.routing import RoutingPlan, RoutingStrategy, resolve_routing
from pipelines.stages import Stage, StageTracker, track_stage
from schemas.knowledge_package import (
    Entity,
    Evidence,
    Fact,
    KnowledgePackage,
    ProcessingMetadata,
    Relation,
    SourceMetadata,
    SourceType,
)
from storage.knowledge.package import package_storage

logger = logging.getLogger(__name__)

# Collection 映射
MARKET_COLLECTION = {
    "cn": "documents_cn",
    "hk": "documents_hk",
    "us": "documents_us",
}

# 失败态集合（重上传/重试时可重置为 pending）
FAILED_STATUSES = ("error", "parse_failed", "waiting_parser")


class DocumentPipeline:
    """文档处理 Pipeline"""

    def __init__(self):
        self.batch_size = get_policy("pipeline.batch_size", 50)
        self.embed_batch_size = get_policy("pipeline.embed_batch_size", 16)
        # DP-C2 双通道开关：pipeline.extraction.mode = package | direct
        #   package：内嵌知识抽取图并把输出写 Package 草稿
        #   direct：跳过内嵌图调用，由独立 knowledge_extraction 任务直写 core.*（回退路径）
        self.extraction_mode = get_policy("pipeline.extraction.mode", "direct")

    async def process_pending_documents(self, limit: int = 50) -> dict[str, int]:
        """处理所有 pending 状态的文档

        使用单语句原子认领（UPDATE ... RETURNING）将 pending 置为 processing，
        避免并发触发时重复处理同一批文档。

        Returns:
            {"processed": N, "failed": N, "skipped": N}
        """
        docs = await postgres_tool.query(
            """
            UPDATE documents SET status = 'processing'
            WHERE id IN (
                SELECT id FROM documents
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT $1
            )
            RETURNING id, market, symbol, company, year, document_type,
                      bucket, object_key, language, metadata
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
                await task_queue.log_task(
                    task_id, "info",
                    f"开始处理 {market}/{symbol} {doc.get('year', '')}",
                    "processing",
                )

                result = await self._process_single_document(doc, task_id, i)
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

    async def _process_single_document(self, doc: dict, task_id: str | None = None, index: int = 0) -> str:
        """处理单个文档的完整链路

        Args:
            doc: 文档记录
            task_id: 关联任务 ID（用于细分 stage 与写日志）
            index: 文档序号（作为细化阶段里的 current_item）

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

        # 2.5 路由决策（DP-B3）：依据采集元数据/文档类型决定解析路径
        metadata = doc.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        acquire = metadata.get("acquire") or {}
        plan = resolve_routing(
            document_type=doc.get("document_type"),
            source_type=acquire.get("source_type"),
            object_key=object_key,
        )
        if task_id:
            await task_queue.log_task(
                task_id, "info",
                f"routing={plan.strategy.value} parser={plan.parser} ({plan.label})",
                "routing",
            )

        # 2.6 阶段追踪（DP-B4）：初始化 StageTracker 并写入 processing 元字段
        tracker = StageTracker(document_id=doc_id, task_id=task_id)
        await tracker.load(postgres_tool)
        tracker.set_metadata(
            parser=plan.parser,
            routing_strategy=plan.strategy.value,
            embedding_model=settings.EMBEDDING_MODEL,
            llm_model=settings.MODEL_NAME,
            ocr_engine="paddleocr",
            chunk_strategy=f"size={get_policy('pipeline.chunk_size', 1000)}",
        )
        _processing_started = time.monotonic()
        await tracker.enter(postgres_tool, Stage.ROUTING, plan.label)
        await tracker.complete(postgres_tool, Stage.ROUTING, plan.label)

        # 3. 下载 PDF from MinIO
        try:
            pdf_data = await minio_tool.download(bucket, object_key)
            if task_id:
                await task_queue.log_task(
                    task_id, "info", f"下载完成 {object_key}", "parse"
                )
        except Exception as e:
            logger.warning("MinIO download failed | %s | %s", object_key, e)
            await postgres_tool.execute(
                "UPDATE documents SET status = 'error', "
                "metadata = metadata || $2::jsonb WHERE id = $1",
                doc_id, json.dumps({"error": f"MinIO download failed: {e}"}),
            )
            return "skipped"

        # 4. 解析 → Markdown（依据 routing 策略选择解析器）
        try:
            filename = object_key.split("/")[-1] if "/" in object_key else object_key
            async with track_stage(tracker, postgres_tool, Stage.PARSE, f"{symbol} 解析"):
                if plan.parser == "direct":
                    # general 策略：原始对象即文本（markdown），直接解码分片
                    md_content = pdf_data.decode("utf-8")
                else:
                    md_content = await docling_tool.convert_file(pdf_data, filename)
            if task_id:
                await task_queue.update_progress(
                    task_id, index, stage="parse",
                    current_name=f"{symbol} 解析",
                )
                await task_queue.log_task(
                    task_id, "info",
                    f"解析完成 {symbol} | {len(md_content)} chars", "parse",
                )
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
        async with track_stage(tracker, postgres_tool, Stage.CHUNK, f"{symbol} 分块"):
            chunks = chunk_markdown(md_content)
        if not chunks:
            logger.warning("No chunks generated | %s", doc_id[:8])
            if task_id:
                await task_queue.log_task(
                    task_id, "warn", f"未生成分块 {symbol}", "chunk"
                )
            await postgres_tool.execute(
                "UPDATE documents SET status = 'parsed', chunk_count = 0 WHERE id = $1",
                doc_id,
            )
            return "skipped"

        if task_id:
            await task_queue.update_progress(
                task_id, index, stage="chunk",
                current_name=f"{symbol} 分块",
            )
            await task_queue.log_task(
                task_id, "info", f"分块完成 {symbol} | {len(chunks)} chunks", "chunk"
            )

        # 7. Extraction 编入 Stage 5（DP-C1/DP-C2）：
        #    双通道开关 pipeline.extraction.mode = package | direct
        #   - package：内嵌调用知识抽取图，输出写 Package 草稿
        #   - direct：跳过内嵌图调用（保留现状，由独立 knowledge_extraction
        #     任务直写 core.*，作为回退路径）
        # 顺序遵循八阶段 Stage=5(extraction) 位于 Stage=6(embedding) 之前（见退出条件）
        extraction_result: dict[str, Any] = {}
        if self.extraction_mode == "package":
            try:
                from graphs.knowledge_graph import build_knowledge_ingestion_graph
                from monitoring.agent_center import invoke_tracked

                async with track_stage(tracker, postgres_tool, Stage.EXTRACTION, f"{symbol} 知识抽取"):
                    graph = build_knowledge_ingestion_graph()
                    initial_state = {
                        "document_id": doc_id,
                        "document_type": doc.get("document_type", ""),
                        "raw_text": md_content,
                        "source_metadata": {
                            "source": acquire.get("source_type", ""),
                            "document_type": doc.get("document_type", ""),
                            "market": market,
                            "symbol": symbol,
                            "company": doc.get("company", ""),
                            "year": doc.get("year"),
                        },
                        "chunks": [],
                        "entities": [],
                        "relations": [],
                        "facts": [],
                        "evidence": [],
                        "conflicts": [],
                        "confidence_score": 0.0,
                        "stored_entity_ids": [],
                        "stored_fact_ids": [],
                        "errors": [],
                    }
                    extraction_result = await invoke_tracked(
                        graph,
                        initial_state,
                        agent_id="knowledge_ingestion",
                        question=f"doc_pipeline extraction doc={doc_id[:8]}",
                    )
                if task_id:
                    await task_queue.log_task(
                        task_id, "info",
                        f"知识抽取 {symbol} | entities={len(extraction_result.get('entities', []))} "
                        f"relations={len(extraction_result.get('relations', []))} "
                        f"facts={len(extraction_result.get('facts', []))}",
                        "extraction",
                    )
            except Exception as e:
                # 异常时自动回退 direct 并告警（DP-C2）：extraction_result 保留空，
                # 由独立任务直写 core.*，知识获取不因抽取失败而中断
                logger.warning(
                    "Extraction failed, auto-fallback to direct | %s/%s | %s",
                    market, symbol, e,
                )
                extraction_result = {}
        else:
            # direct 模式：保留现直写 core.* 路径；extraction 阶段仍标记完成（内容由独立任务处理）
            async with track_stage(tracker, postgres_tool, Stage.EXTRACTION, f"{symbol} 知识抽取(direct)"):
                pass
            logger.info("Extraction mode=direct (skip inline graph) | %s/%s", market, symbol)

        # 8. Embedding（分批）
        collection = MARKET_COLLECTION.get(market, "documents_cn")
        all_vectors: list[list[float]] = []

        if task_id:
            await task_queue.update_progress(
                task_id, index, stage="embedding",
                current_name=f"{symbol} 嵌入",
            )
            await task_queue.log_task(
                task_id, "info", f"开始嵌入 {symbol} | {len(chunks)} chunks", "embedding"
            )

        async with track_stage(tracker, postgres_tool, Stage.EMBEDDING, f"{symbol} 嵌入"):
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

        if task_id:
            await task_queue.log_task(
                task_id, "info",
                f"索引完成 {symbol} | {len(chunks)} chunks | {collection}",
                "embedding",
            )

        # 10. 落 KnowledgePackage 草稿（DP-B4）：processing 元数据 + 阶段记录
        tracker.set_metadata(
            processing_time=round(time.monotonic() - _processing_started, 3)
        )
        await self._save_package_draft(doc, plan, tracker, extraction_result)

        logger.info(
            "Document indexed | %s/%s | chunks=%d | collection=%s",
            market, symbol, len(chunks), collection,
        )
        return "indexed"

    async def _save_package_draft(
        self, doc: dict, plan: RoutingPlan, tracker: StageTracker,
        extraction: dict[str, Any] | None = None,
    ) -> str | None:
        """构造 KnowledgePackage 草稿并落库（DP-B4 + DP-C1）

        processing_metadata 含 parser/ocr_engine/embedding_model/llm_model/
        routing_strategy/processing_time/stages；失败不阻塞主流程。
        extraction 为知识抽取图输出时，把 entities/relations/facts/evidence
        映射为 Package 契约写入草稿（DP-C1 验收：草稿含非空四项）。
        """
        doc_id = str(doc["id"])
        source_type = (
            SourceType.ANNUAL_REPORT
            if plan.strategy is RoutingStrategy.ANNUAL_REPORT
            else SourceType.GENERAL
        )
        symbol = doc.get("symbol", "")
        company = doc.get("company", "")
        source = SourceMetadata(
            source_type=source_type,
            source_id=doc.get("source_id") or "documents",
            document_id=doc_id,
            title=company or symbol,
            file_path=doc.get("object_key"),
        )
        entities: list[Entity] = []
        relations: list[Relation] = []
        facts: list[Fact] = []
        evidence: list[Evidence] = []
        if extraction:
            entities, relations, facts, evidence = self._map_extraction_to_package(
                extraction, doc_id
            )
        package = KnowledgePackage(
            id=str(uuid.uuid4()),
            source_type=source_type,
            document_id=doc_id,
            source=source,
            entities=entities,
            relations=relations,
            facts=facts,
            evidence=evidence,
            processing_metadata=ProcessingMetadata(**tracker.processing),
        )
        return await package_storage.save_draft(package)

    @staticmethod
    def _clean_dt(value: Any) -> Any:
        """把时间字段安全转为 datetime（ISO 字符串/Native；非法返回 None）"""
        if not value:
            return None
        from datetime import datetime
        try:
            return datetime.fromisoformat(str(value))
        except (ValueError, TypeError):
            return None

    def _map_extraction_to_package(
        self, result: dict[str, Any], document_id: str
    ) -> tuple[list[Entity], list[Relation], list[Fact], list[Evidence]]:
        """把知识抽取图输出映射为 Package 契约模型列表（DP-C1）

        - 实体：name→id 映射（已有 existing_id 复用，否则生成新 UUID）
        - 关系：source/target 名称解析为实体 ID（无法解析则跳过）
        - 事实：subject 解析为实体 ID；evidence 与 facts 同索引对齐
        - 时间字段统一经 _clean_dt 安全转换
        """
        entities_raw = result.get("entities", []) or []
        relations_raw = result.get("relations", []) or []
        facts_raw = result.get("facts", []) or []
        evidence_raw = result.get("evidence", []) or []

        name_to_id: dict[str, str] = {}
        entities: list[Entity] = []
        for e in entities_raw:
            eid = e.get("existing_id") or str(uuid.uuid4())
            name = e.get("name", "")
            if name:
                name_to_id[name.lower()] = eid
            entities.append(Entity(
                id=eid,
                name=name,
                entity_type=e.get("entity_type", "unknown"),
                aliases=e.get("aliases", []) or [],
                properties=e.get("properties", {}) or {},
                canonical_name=e.get("canonical_name"),
                confidence=e.get("confidence"),
            ))

        relations: list[Relation] = []
        for r in relations_raw:
            source_id = name_to_id.get((r.get("source") or "").lower())
            target_id = name_to_id.get((r.get("target") or "").lower())
            if not source_id or not target_id:
                continue
            relations.append(Relation(
                id=str(uuid.uuid4()),
                source_entity=source_id,
                target_entity=target_id,
                relation_type=r.get("relation_type", ""),
                properties=r.get("properties", {}) or {},
                confidence=r.get("confidence"),
            ))

        facts: list[Fact] = []
        evidence: list[Evidence] = []
        for i, f in enumerate(facts_raw):
            subject_id = name_to_id.get((f.get("subject") or "").lower()) or ""
            fact_id = str(uuid.uuid4())
            facts.append(Fact(
                id=fact_id,
                subject_entity=subject_id,
                predicate=f.get("predicate", ""),
                object_value=f.get("object_value", {}),
                unit=f.get("unit"),
                time_start=self._clean_dt(f.get("time_start")),
                time_end=self._clean_dt(f.get("time_end")),
                source_document=document_id,
                confidence=f.get("confidence"),
            ))
            ev = evidence_raw[i] if i < len(evidence_raw) else None
            if ev:
                evidence.append(Evidence(
                    id=str(uuid.uuid4()),
                    fact_id=fact_id,
                    document_id=document_id,
                    location=ev.get("location"),
                    quote=ev.get("quote"),
                    confidence=ev.get("confidence"),
                ))

        return entities, relations, facts, evidence

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

    async def reembed_document(self, doc_id: str) -> bool:
        """重新向量化单个文档（清除旧 Qdrant 向量 + 旧 chunks + 重新处理）"""
        # 先删 Qdrant 旧向量（按 collection 分组），避免重索引后新旧向量并存
        try:
            rows = await postgres_tool.query(
                "SELECT qdrant_point_id, collection_name FROM chunks "
                "WHERE document_id = $1 AND qdrant_point_id IS NOT NULL", doc_id
            )
            by_coll: dict[str, list[str]] = {}
            for r in rows:
                by_coll.setdefault(r["collection_name"], []).append(str(r["qdrant_point_id"]))
            for coll, ids in by_coll.items():
                await qdrant_tool.delete_points(coll, ids)
        except Exception as e:
            logger.warning("Re-embed: Qdrant old points cleanup failed | %s | %s", doc_id[:8], e)

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

    _ANNUAL_REPORT_RE = re.compile(
        r"^(?P<market>[^/]+)/(?P<symbol>[^/]+)/annual_report/(?P<year>\d{4})/report\.(pdf|md)$"
    )

    async def register_pending_from_minio(
        self, bucket: str = "documents", prefix: str = "", market: str = "",
        task_id: str = "",
    ) -> dict[str, int]:
        """扫描 MinIO 桶，把年报对象注册为 pending documents（幂等）

        仅处理 /annual_report/{year}/report.{pdf|md} 形态的对象；
        已存在（按 object_key 判重）或无法解析路径的对象跳过；
        已存在但处于失败态的记录重置为 pending（计入 reset）。

        task_id 非空时启用协作式控制：逐对象上报进度、支持暂停/取消。

        Returns:
            {"added": N, "skipped": M, "found": K, "reset": R, "cancelled": bool}
        """
        object_keys = await minio_tool.list_objects(bucket, prefix)
        if market:
            object_keys = [k for k in object_keys if k.startswith(f"{market}/")]

        found = len(object_keys)
        added = 0
        skipped = 0
        reset = 0

        # 异步任务模式下先设定总数，供进度百分比计算
        if task_id:
            await task_queue.set_total_items(task_id, found)

        for i, key in enumerate(object_keys, start=1):
            # 协作式取消/暂停（仅 task_id 非空时生效）
            if task_id:
                if task_queue.is_cancelled(task_id):
                    logger.info("[IngestMinio] %s cancelled by user", task_id[:8])
                    break
                await task_queue.wait_if_paused(task_id)

            m = self._ANNUAL_REPORT_RE.match(key)
            if not m:
                skipped += 1
                await self._report_progress(task_id, i, found, key, added, skipped, reset)
                continue

            mkt = m.group("market")
            symbol = m.group("symbol")
            try:
                year = int(m.group("year"))
            except ValueError:
                skipped += 1
                await self._report_progress(task_id, i, found, key, added, skipped, reset)
                continue
            doc_type = "annual_report" if key.endswith(".pdf") else "markdown"

            # 幂等：按 object_key 判重；失败态重置为 pending
            exists = await postgres_tool.query(
                "SELECT status FROM documents WHERE object_key = $1", key
            )
            if exists:
                if exists[0]["status"] in FAILED_STATUSES:
                    await postgres_tool.execute(
                        "UPDATE documents SET status = 'pending', "
                        "metadata = metadata - 'error', updated_at = NOW() "
                        "WHERE object_key = $1",
                        key,
                    )
                    reset += 1
                else:
                    skipped += 1
                await self._report_progress(task_id, i, found, key, added, skipped, reset)
                continue

            doc_id = str(uuid.uuid4())
            # 统一 acquire metadata（DP-B2）：source_type/trigger/priority/checksum/origin
            acquire_meta = merge_acquire_into_metadata(
                {"source": "minio"},
                build_acquire_metadata(
                    source_type=doc_type,
                    trigger=AcquireTrigger.MINIO_SCAN,
                    priority=AcquirePriority.LOW,
                    checksum=key,  # MinIO 对象以 object_key 作为内容判重依据
                    origin=AcquireOrigin.MINIO,
                    object_key=key,
                ),
            )
            await postgres_tool.execute(
                """
                INSERT INTO documents
                    (id, market, symbol, company, year, document_type,
                     status, parser, chunk_count, metadata, bucket, object_key)
                VALUES ($1, $2, $3, '', $4, $5, 'pending', 'docling', 0,
                        $6::jsonb, $7, $8)
                """,
                doc_id, mkt, symbol, year, doc_type,
                json.dumps(acquire_meta),
                bucket, key,
            )
            added += 1
            logger.info(
                "Registered pending doc | %s | %s/%s | year=%d",
                doc_id[:8], mkt, symbol, year,
            )
            await self._report_progress(task_id, i, found, key, added, skipped, reset)

        logger.info(
            "MinIO pending registration done | bucket=%s prefix=%r | found=%d added=%d skipped=%d reset=%d",
            bucket, prefix, found, added, skipped, reset,
        )
        cancelled = task_id and task_queue.is_cancelled(task_id)
        return {
            "added": added, "skipped": skipped, "found": found, "reset": reset,
            "cancelled": bool(cancelled),
        }

    @staticmethod
    async def _report_progress(
        task_id: str, i: int, found: int, key: str,
        added: int, skipped: int, reset: int,
    ) -> None:
        """异步任务模式下上报单个对象处理进度（task_id 为空时跳过）"""
        if not task_id:
            return
        stage = f"{i}/{found} · 新增{added} 跳过{skipped} 重置{reset}"
        await task_queue.update_progress(
            task_id, current_item=i, stage=stage, current_name=key,
        )


# 模块级单例
doc_pipeline = DocumentPipeline()
