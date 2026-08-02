"""Knowledge API - 知识库管理（Collection 统计 + 知识图谱查询 + Hybrid 检索）"""

import asyncio
import logging
import os
import uuid as uuid_mod
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from config.settings import settings
from tools.postgres import postgres_tool
from knowledge_agent.storage.postgres import knowledge_storage
from knowledge_agent.storage.qdrant import knowledge_qdrant
from services.task_queue import task_queue

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/collections")
async def list_collections():
    """知识库 Collection 列表

    合并 collections 表元数据 + chunks 实际计数 + Qdrant points 统计。
    Qdrant 不可达时 qdrant_points 字段为 null（降级）。
    """
    try:
        rows = await postgres_tool.query(
            """
            SELECT c.id, c.name, c.description, c.vector_size, c.distance, c.domain,
                   COUNT(ch.id) AS chunk_count,
                   COUNT(ch.qdrant_point_id) AS embedded_count
            FROM collections c
            LEFT JOIN chunks ch ON ch.collection_name = c.name
            GROUP BY c.id, c.name, c.description, c.vector_size, c.distance, c.domain
            ORDER BY c.name
            """
        )
    except Exception as e:
        logger.exception("Failed to query collections")
        raise HTTPException(status_code=500, detail=str(e))

    # Qdrant points 统计（独立降级，不影响主数据）
    qdrant_stats: dict[str, int] = {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            for r in rows:
                name = r["name"]
                try:
                    resp = await client.get(
                        f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}/collections/{name}"
                    )
                    if resp.status_code == 200:
                        qdrant_stats[name] = resp.json().get("result", {}).get("points_count", 0)
                except Exception:
                    pass  # 单个 collection 查询失败不影响其他
    except Exception:
        logger.warning("Qdrant unreachable, qdrant_points will be null")

    collections = []
    for r in rows:
        collections.append({
            "id": str(r["id"]),
            "name": r["name"],
            "description": r.get("description"),
            "vector_size": r["vector_size"],
            "distance": r.get("distance"),
            "domain": r.get("domain"),
            "chunk_count": r["chunk_count"],
            "embedded_count": r["embedded_count"],
            "qdrant_points": qdrant_stats.get(r["name"]),  # None 表示不可用
        })

    return {"collections": collections, "total": len(collections)}


# ============================================================
# 知识图谱查询 API
# ============================================================


@router.get("/entities")
async def list_entities(
    name: str = Query("", description="实体名称搜索"),
    entity_type: str = Query("", description="实体类型过滤"),
    limit: int = Query(20, ge=1, le=100),
):
    """查询实体（by name/type）"""
    try:
        entities = await knowledge_storage.search_entities(
            name=name, entity_type=entity_type, limit=limit
        )
        return {
            "entities": [
                {
                    "id": str(e["id"]),
                    "name": e["name"],
                    "entity_type": e["entity_type"],
                    "description": e.get("description"),
                    "canonical_name": e.get("canonical_name"),
                    "confidence": e.get("confidence"),
                    "source_count": e.get("source_count", 0),
                }
                for e in entities
            ],
            "total": len(entities),
        }
    except Exception as e:
        logger.exception("Failed to query entities")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entities/{entity_id}")
async def get_entity_detail(entity_id: str):
    """实体详情（含 aliases、properties）"""
    try:
        import uuid as _uuid
        rows = await postgres_tool.query(
            """
            SELECT id, name, entity_type, description, canonical_name,
                   confidence, source_count, aliases, properties,
                   status, created_at, updated_at
            FROM core.entities
            WHERE id = $1 AND status = 'active'
            """,
            _uuid.UUID(entity_id),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Entity not found")
        e = rows[0]
        return {
            "id": str(e["id"]),
            "name": e["name"],
            "entity_type": e["entity_type"],
            "description": e.get("description"),
            "canonical_name": e.get("canonical_name"),
            "confidence": e.get("confidence"),
            "source_count": e.get("source_count", 0),
            "aliases": e.get("aliases") or [],
            "properties": e.get("properties") or {},
            "created_at": str(e["created_at"]) if e.get("created_at") else None,
            "updated_at": str(e["updated_at"]) if e.get("updated_at") else None,
        }
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entity ID format")
    except Exception as e:
        logger.exception("Failed to get entity detail")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entities/{entity_id}/neighbors")
async def get_entity_neighbors(
    entity_id: str,
    depth: int = Query(1, ge=1, le=2, description="遍历深度（最大 2）"),
):
    """图遍历：获取实体的关联实体"""
    try:
        neighbors = await knowledge_storage.get_entity_neighbors(entity_id, depth=depth)
        return {
            "entity_id": entity_id,
            "depth": depth,
            "neighbors": [
                {
                    "source_entity": str(n["source_entity"]),
                    "target_entity": str(n["target_entity"]),
                    "relation_type": n["relation_type"],
                    "depth": n["depth"],
                }
                for n in neighbors
            ],
            "total": len(neighbors),
        }
    except Exception as e:
        logger.exception("Failed to get neighbors")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/facts")
async def list_facts(
    subject: str = Query("", description="主体实体 ID"),
    predicate: str = Query("", description="谓词过滤"),
    limit: int = Query(50, ge=1, le=200),
):
    """查询事实（by subject/predicate）"""
    if not subject:
        raise HTTPException(status_code=400, detail="subject parameter required")

    try:
        facts = await knowledge_storage.get_facts_by_subject(
            subject_entity=subject,
            predicate=predicate or None,
            limit=limit,
        )
        return {
            "facts": [
                {
                    "id": str(f["id"]),
                    "predicate": f["predicate"],
                    "object_value": f["object_value"],
                    "unit": f.get("unit"),
                    "time_start": str(f["time_start"]) if f.get("time_start") else None,
                    "time_end": str(f["time_end"]) if f.get("time_end") else None,
                    "confidence": f.get("confidence"),
                    "verification_status": f.get("verification_status"),
                }
                for f in facts
            ],
            "total": len(facts),
        }
    except Exception as e:
        logger.exception("Failed to query facts")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Hybrid 检索 API
# ============================================================


class HybridSearchRequest(BaseModel):
    query: str
    entity_name: str = ""
    limit: int = 10


@router.post("/search")
async def hybrid_search(request: HybridSearchRequest):
    """混合检索：图查询 + 向量检索 + RRF 合并"""
    try:
        # 1. 图查询（结构化）
        graph_results = []
        entity_ids = []

        if request.entity_name:
            entities = await knowledge_storage.find_entity_by_name(
                request.entity_name, limit=1
            )
            if entities:
                entity_id = str(entities[0]["id"])
                entity_ids = [entity_id]
                graph_results = await knowledge_storage.get_entity_neighbors(
                    entity_id, depth=2
                )

        # 2. 向量检索（语义）
        vector_results = await knowledge_qdrant.hybrid_search(
            query=request.query,
            entity_ids=entity_ids if entity_ids else None,
            limit=request.limit,
        )

        # 3. 合并结果
        return {
            "query": request.query,
            "graph_results": [
                {
                    "source_entity": str(r["source_entity"]),
                    "target_entity": str(r["target_entity"]),
                    "relation_type": r["relation_type"],
                    "depth": r["depth"],
                }
                for r in graph_results
            ],
            "vector_results": vector_results,
            "entity_ids_used": entity_ids,
        }
    except Exception as e:
        logger.exception("Hybrid search failed")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 知识提取任务 API
# ============================================================


class ExtractRequest(BaseModel):
    document_ids: list[str]
    raw_texts: dict[str, str] = {}  # 可选：直接传入文本


@router.post("/extract")
async def trigger_extraction(request: ExtractRequest):
    """触发知识提取任务（创建 task → worker 处理）"""
    if not request.document_ids:
        raise HTTPException(status_code=400, detail="document_ids required")

    try:
        task_id = await task_queue.create_task(
            task_type="knowledge_extraction",
            title=f"知识提取 ({len(request.document_ids)} docs)",
            total_items=len(request.document_ids),
            params={
                "document_ids": request.document_ids,
                "raw_texts": request.raw_texts,
            },
        )
        return {
            "task_id": task_id,
            "status": "pending",
            "document_count": len(request.document_ids),
        }
    except Exception as e:
        logger.exception("Failed to create extraction task")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 目录浏览 API
# ============================================================


# 允许浏览的根路径白名单（安全限制）
ALLOWED_BROWSE_ROOTS = ["/data", "/app"]


@router.get("/browse-dirs")
async def browse_dirs(path: str = Query("/data/minio/documents", description="要浏览的目录路径")):
    """浏览服务器目录结构（仅返回目录，用于目录选择器）"""
    target = Path(path).resolve()

    # 安全检查：路径必须在允许的根目录下
    if not any(str(target).startswith(root) for root in ALLOWED_BROWSE_ROOTS):
        raise HTTPException(
            status_code=403,
            detail=f"路径不在允许范围内，允许的根路径: {', '.join(ALLOWED_BROWSE_ROOTS)}"
        )

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"路径不存在: {path}")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"不是目录: {path}")

    # 获取子目录列表
    subdirs = []
    try:
        for item in sorted(target.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                subdirs.append({
                    "name": item.name,
                    "path": str(item),
                })
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"无权限访问: {path}")

    # 计算父级路径
    parent = target.parent
    can_go_up = any(str(parent).startswith(root) for root in ALLOWED_BROWSE_ROOTS) and parent != target

    return {
        "current_path": str(target),
        "parent_path": str(parent) if can_go_up else None,
        "can_go_up": can_go_up,
        "directories": subdirs,
        "total": len(subdirs),
    }


# ============================================================
# MD 文件手动导入 API
# ============================================================


class IngestRequest(BaseModel):
    path: str = Field(..., min_length=1, description="文件或目录路径")
    collection: str = Field("documents_cn", description="目标 Qdrant collection")


async def _run_ingest(path: str, collection: str) -> None:
    """后台执行 MD 文件导入处理管线"""
    from tools.chunker import chunk_markdown
    from tools.embedding import embedding_tool
    from tools.qdrant import qdrant_tool

    logger.info("[Ingest] Start | path=%s | collection=%s", path, collection)
    try:
        target = Path(path)
        md_files: list[Path] = []

        if target.is_file() and target.suffix == ".md":
            md_files = [target]
        elif target.is_dir():
            md_files = sorted(target.rglob("*.md"))
        else:
            logger.warning("[Ingest] Invalid path: %s", path)
            return

        if not md_files:
            logger.info("[Ingest] No .md files found at %s", path)
            return

        total_files = 0
        total_chunks = 0
        embed_batch_size = 16

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding="utf-8")
                if not content.strip():
                    continue

                # Chunking
                chunks = chunk_markdown(content)
                if not chunks:
                    continue

                # 创建 document 记录
                doc_id = str(uuid_mod.uuid4())
                file_name = md_file.stem
                await postgres_tool.execute(
                    """
                    INSERT INTO documents (id, market, symbol, company, year,
                                           document_type, status, parser,
                                           chunk_count, metadata)
                    VALUES ($1, 'cn', $2, '', 0, 'markdown', 'indexing',
                            'direct', $3, $4::jsonb)
                    """,
                    doc_id, file_name, len(chunks),
                    f'{{"source_path": "{md_file}", "ingest": "manual"}}',
                )

                # Embedding（分批）
                all_vectors: list[list[float]] = []
                for batch_start in range(0, len(chunks), embed_batch_size):
                    batch = chunks[batch_start:batch_start + embed_batch_size]
                    texts = [c["content"][:2000] for c in batch]
                    vectors = await embedding_tool.embed(texts)
                    all_vectors.extend(vectors)

                # 写入 Qdrant + PostgreSQL chunks
                points = []
                for i, (chunk, vector) in enumerate(zip(chunks, all_vectors)):
                    point_id = str(uuid_mod.uuid4())
                    points.append({
                        "id": point_id,
                        "vector": vector,
                        "payload": {
                            "content": chunk["content"],
                            "heading": chunk.get("heading", ""),
                            "symbol": file_name,
                            "market": "cn",
                            "document_type": "markdown",
                            "document_id": doc_id,
                            "chunk_index": i,
                            "source_path": str(md_file),
                        },
                    })
                    await postgres_tool.execute(
                        """
                        INSERT INTO chunks (document_id, chunk_index, content,
                                            heading, collection_name, qdrant_point_id)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (document_id, chunk_index) DO NOTHING
                        """,
                        doc_id, i, chunk["content"],
                        chunk.get("heading", ""), collection, point_id,
                    )

                # Upsert Qdrant
                for batch_start in range(0, len(points), 100):
                    batch = points[batch_start:batch_start + 100]
                    await qdrant_tool.upsert(collection, batch)

                # 更新文档状态
                await postgres_tool.execute(
                    "UPDATE documents SET status = 'indexed' WHERE id = $1",
                    doc_id,
                )

                total_files += 1
                total_chunks += len(chunks)
                logger.info(
                    "[Ingest] Processed | %s | chunks=%d", md_file.name, len(chunks)
                )

            except Exception as e:
                logger.error("[Ingest] File failed | %s | %s", md_file, e)

        logger.info(
            "[Ingest] Complete | files=%d | chunks=%d | collection=%s",
            total_files, total_chunks, collection,
        )

    except Exception as e:
        logger.error("[Ingest] Fatal error: %s", e)


@router.post("/ingest")
async def trigger_ingest(req: IngestRequest):
    """手动导入 MD 文件并执行处理管线（异步执行，立即返回）"""
    # 基本路径验证
    target = Path(req.path)
    if not target.exists():
        raise HTTPException(status_code=400, detail=f"路径不存在: {req.path}")

    # 只接受目录路径
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="请选择目录，而不是单个文件")

    # 快速检测是否存在 .md 文件（避免大目录全量递归扫描）
    file_count = 0
    for _ in target.rglob("*.md"):
        file_count += 1
        if file_count >= 9999:
            break

    if file_count == 0:
        raise HTTPException(status_code=400, detail=f"目录下无 .md 文件: {req.path}")

    asyncio.create_task(_run_ingest(req.path, req.collection))
    count_label = f"{file_count}+" if file_count >= 9999 else str(file_count)
    return {
        "status": "accepted",
        "message": f"导入任务已启动（{count_label} 个文件 → {req.collection}）",
        "file_count": file_count,
        "collection": req.collection,
    }
