"""Documents API - 文档列表、统计、详情、分块、实体与生命周期管理"""

import logging
import uuid
from pathlib import PurePosixPath

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from services.pipeline import doc_pipeline
from tools.minio import minio_tool
from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])

DEFAULT_BUCKET = "documents"


def _doc_row_to_dict(r: dict) -> dict:
    """将 documents 表行转换为 API 响应结构"""
    return {
        "id": str(r["id"]),
        "market": r["market"],
        "symbol": r["symbol"],
        "company": r.get("company"),
        "year": r["year"],
        "document_type": r["document_type"],
        "language": r.get("language"),
        "bucket": r.get("bucket"),
        "object_key": r.get("object_key"),
        "status": r["status"],
        "parser": r.get("parser"),
        "parser_version": r.get("parser_version"),
        "chunk_count": r.get("chunk_count") or 0,
        "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
    }


@router.get("/stats")
async def document_stats():
    """文档状态统计（按 status 分组）"""
    try:
        rows = await postgres_tool.query(
            "SELECT status, COUNT(*) as cnt FROM documents GROUP BY status"
        )
        by_status = {r["status"]: r["cnt"] for r in rows}
        total = sum(by_status.values())
        return {"by_status": by_status, "total": total}
    except Exception as e:
        logger.exception("Failed to get document stats")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_documents(
    status: str | None = None,
    market: str | None = None,
    symbol: str | None = None,
    page: int = 1,
    page_size: int = 50,
):
    """文档分页列表，支持 status/market/symbol 筛选"""
    query = (
        "SELECT id, market, symbol, company, year, document_type, "
        "status, chunk_count, created_at, updated_at "
        "FROM documents WHERE 1=1"
    )
    count_query = "SELECT COUNT(*) as cnt FROM documents WHERE 1=1"
    params: list = []
    idx = 1

    if status:
        cond = f" AND status = ${idx}"
        query += cond
        count_query += cond
        params.append(status)
        idx += 1
    if market:
        cond = f" AND market = ${idx}"
        query += cond
        count_query += cond
        params.append(market)
        idx += 1
    if symbol:
        cond = f" AND symbol ILIKE ${idx}"
        query += cond
        count_query += cond
        params.append(f"%{symbol}%")
        idx += 1

    # 总数
    try:
        total_rows = await postgres_tool.query(count_query, *params)
        total = total_rows[0]["cnt"] if total_rows else 0
    except Exception as e:
        logger.exception("Failed to count documents")
        raise HTTPException(status_code=500, detail=str(e))

    # 分页数据
    offset = (max(page, 1) - 1) * page_size
    query += f" ORDER BY updated_at DESC LIMIT ${idx} OFFSET ${idx + 1}"
    params.extend([page_size, offset])

    try:
        rows = await postgres_tool.query(query, *params)
        documents = []
        for r in rows:
            documents.append({
                "id": str(r["id"]),
                "market": r["market"],
                "symbol": r["symbol"],
                "company": r.get("company"),
                "year": r["year"],
                "document_type": r["document_type"],
                "status": r["status"],
                "chunk_count": r.get("chunk_count") or 0,
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
            })
        return {"documents": documents, "total": total, "page": page, "page_size": page_size}
    except Exception as e:
        logger.exception("Failed to list documents")
        raise HTTPException(status_code=500, detail=str(e))


async def _get_document_or_404(document_id: str) -> dict:
    """按 ID 查询文档，不存在则抛 404"""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID format")
    rows = await postgres_tool.query(
        "SELECT * FROM documents WHERE id = $1", doc_uuid
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Document not found")
    return rows[0]


@router.get("/{document_id}")
async def get_document(document_id: str):
    """文档详情（含分块/实体/事实统计）"""
    doc = await _get_document_or_404(document_id)
    doc_id = str(doc["id"])

    # 分块统计
    chunks = 0
    embedded = 0
    try:
        rows = await postgres_tool.query(
            "SELECT COUNT(*) AS total, "
            "COUNT(qdrant_point_id) AS embedded FROM chunks WHERE document_id = $1",
            doc_id,
        )
        chunks = rows[0]["total"] if rows else 0
        embedded = rows[0]["embedded"] if rows else 0
    except Exception:
        pass

    # 知识图谱统计（通过 core.facts.source_document 关联）
    entities = 0
    facts = 0
    try:
        erows = await postgres_tool.query(
            "SELECT COUNT(DISTINCT subject_entity) AS entities, COUNT(*) AS facts "
            "FROM core.facts WHERE source_document = $1",
            doc_id,
        )
        entities = erows[0]["entities"] if erows else 0
        facts = erows[0]["facts"] if erows else 0
    except Exception:
        pass

    return {
        "document": _doc_row_to_dict(doc),
        "stats": {
            "chunks": chunks,
            "embedded": embedded,
            "entities": entities,
            "facts": facts,
        },
    }


@router.get("/{document_id}/chunks")
async def get_document_chunks(
    document_id: str,
    page: int = 1,
    page_size: int = 50,
    keyword: str | None = None,
):
    """文档分块列表（分页 + 关键字过滤）"""
    doc = await _get_document_or_404(document_id)
    doc_id = str(doc["id"])

    where = "WHERE document_id = $1"
    params: list = [doc_id]
    idx = 2
    if keyword:
        where += f" AND content ILIKE ${idx}"
        params.append(f"%{keyword}%")
        idx += 1

    try:
        total_rows = await postgres_tool.query(
            f"SELECT COUNT(*) AS cnt FROM chunks {where}", *params
        )
        total = total_rows[0]["cnt"] if total_rows else 0
    except Exception as e:
        logger.exception("Failed to count chunks")
        raise HTTPException(status_code=500, detail=str(e))

    offset = (max(page, 1) - 1) * page_size
    query = (
        f"SELECT id, chunk_index, content, heading, page_start, page_end, "
        f"token_count, collection_name, qdrant_point_id "
        f"FROM chunks {where} ORDER BY chunk_index ASC "
        f"LIMIT ${idx} OFFSET ${idx + 1}"
    )
    params.extend([page_size, offset])

    try:
        rows = await postgres_tool.query(query, *params)
        chunks = []
        for r in rows:
            chunks.append({
                "id": str(r["id"]),
                "chunk_index": r["chunk_index"],
                "content": r["content"],
                "heading": r.get("heading"),
                "page_start": r.get("page_start"),
                "page_end": r.get("page_end"),
                "token_count": r.get("token_count"),
                "collection_name": r.get("collection_name"),
                "qdrant_point_id": str(r["qdrant_point_id"]) if r.get("qdrant_point_id") else None,
            })
        return {"chunks": chunks, "total": total, "page": page, "page_size": page_size}
    except Exception as e:
        logger.exception("Failed to list chunks")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_id}/entities")
async def get_document_entities(document_id: str):
    """文档关联实体（通过 core.facts.source_document 关联）"""
    doc = await _get_document_or_404(document_id)
    doc_id = str(doc["id"])
    try:
        rows = await postgres_tool.query(
            """
            SELECT DISTINCT e.id, e.name, e.entity_type, e.description,
                   e.confidence, e.source_count
            FROM core.facts f
            JOIN core.entities e ON e.id = f.subject_entity
            WHERE f.source_document = $1
            ORDER BY e.name
            """,
            doc_id,
        )
        entities = [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "entity_type": r["entity_type"],
                "description": r.get("description"),
                "confidence": r.get("confidence"),
                "source_count": r.get("source_count", 0),
            }
            for r in rows
        ]
        return {"entities": entities, "total": len(entities)}
    except Exception as e:
        logger.exception("Failed to list document entities")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    """删除文档（chunks 级联删除；关联 facts 一并清理）"""
    doc = await _get_document_or_404(document_id)
    doc_id = str(doc["id"])

    # 删除关联的知识图谱 facts（evidence 级联删除）
    try:
        await postgres_tool.execute(
            "DELETE FROM core.facts WHERE source_document = $1", doc_id
        )
    except Exception as e:
        logger.warning("Failed to delete facts for doc %s: %s", doc_id[:8], e)

    # 删除文档（chunks 通过 ON DELETE CASCADE 自动删除）
    await postgres_tool.execute("DELETE FROM documents WHERE id = $1", doc_id)
    logger.info("Document deleted | %s | %s/%s/%s", doc_id[:8], doc.get("market"), doc.get("symbol"), doc.get("year"))
    return {"status": "ok", "deleted": doc_id}


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    market: str = Form(...),
    symbol: str = Form(...),
    year: int = Form(...),
    bucket: str = Form(DEFAULT_BUCKET),
    trigger: bool = Form(False),
):
    """上传 PDF 年报到 MinIO，并注册为 pending 文档

    规范路径: {market}/{symbol}/annual_report/{year}/report.pdf
    trigger=True 时立即入队 doc_pipeline 处理。
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

    # 校验参数
    market = market.strip().lower()
    symbol = symbol.strip().upper()
    if not market or not symbol:
        raise HTTPException(status_code=400, detail="market 和 symbol 不能为空")
    if not (2000 <= year <= 2100):
        raise HTTPException(status_code=400, detail="year 参数无效")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件内容为空")

    # 构造 MinIO 规范对象路径
    object_key = f"{market}/{symbol}/annual_report/{year}/report.pdf"

    try:
        await minio_tool.upload(bucket, object_key, data)
    except Exception as e:
        logger.exception("Upload to MinIO failed: %s", e)
        raise HTTPException(status_code=500, detail=f"MinIO 上传失败: {e}")

    # 注册为 pending 文档（幂等，按 object_key 判重）
    try:
        result = await doc_pipeline.register_pending_from_minio(
            bucket=bucket,
            prefix=f"{market}/{symbol}/annual_report/{year}",
            market=market,
        )
    except Exception as e:
        logger.exception("Register pending failed: %s", e)
        raise HTTPException(status_code=500, detail=f"文档注册失败: {e}")

    task_id = None
    if trigger and result.get("added", 0) > 0:
        from services.task_queue import task_queue
        task_id = await task_queue.create_task(
            task_type="doc_pipeline",
            title=f"文档处理 Pipeline (1 doc, {market}/{symbol}/{year})",
            params={"limit": 1},
            total_items=1,
            created_by="api",
        )

    return {
        "status": "ok",
        "object_key": object_key,
        "registered": result,
        "pipeline_task_id": task_id,
    }
