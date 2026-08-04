"""Documents API - 文档列表、统计、详情、分块、实体与生命周期管理"""

import asyncio
import logging
import re
import uuid
from io import BytesIO
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.path_utils import normalize_path
from pipelines.document_pipeline import doc_pipeline
from tools.minio import minio_tool
from tools.postgres import postgres_tool
from tools.qdrant import qdrant_tool

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
    """删除文档（同步清理 Qdrant 向量 + MinIO 对象；chunks 级联删除；关联 facts 一并清理）"""
    doc = await _get_document_or_404(document_id)
    doc_id = str(doc["id"])

    # 先清理外部资源（Qdrant 向量 + MinIO 对象），失败仅 warning 不阻塞 PG 删除
    cleanup = await _purge_document_resources(doc)

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
    return {"status": "ok", "deleted": doc_id, "cleanup": cleanup}


async def _purge_document_resources(doc: dict) -> dict:
    """清理文档的 Qdrant 向量 + MinIO 对象（失败仅 warning，不阻塞 PG 删除）

    Returns:
        {"qdrant_points": N, "minio_keys": [...]}
    """
    doc_id = str(doc["id"])
    cleanup: dict = {"qdrant_points": 0, "minio_keys": []}

    # 1. Qdrant 向量（按 collection 分组删）
    try:
        rows = await postgres_tool.query(
            "SELECT qdrant_point_id, collection_name FROM chunks "
            "WHERE document_id = $1 AND qdrant_point_id IS NOT NULL", doc_id
        )
        by_coll: dict[str, list[str]] = {}
        for r in rows:
            by_coll.setdefault(r["collection_name"], []).append(str(r["qdrant_point_id"]))
        for coll, ids in by_coll.items():
            cleanup["qdrant_points"] += await qdrant_tool.delete_points(coll, ids)
    except Exception as e:
        logger.warning("Qdrant cleanup failed | %s | %s", doc_id[:8], e)

    # 2. MinIO 对象（PDF + 同基名 .md 解析产物）
    bucket = doc.get("bucket") or DEFAULT_BUCKET
    key = doc.get("object_key") or ""
    if key:
        for k in (key, key.rsplit(".", 1)[0] + ".md"):
            try:
                await minio_tool.delete(bucket, k)
                cleanup["minio_keys"].append(k)
            except Exception as e:
                logger.warning("MinIO cleanup failed | %s/%s | %s", bucket, k, e)

    return cleanup


# ─── 管理端点：下载 / 批量清理 / 失败重试 ────────────────


class CleanupRequest(BaseModel):
    status: str | None = None
    orphan: bool = False
    dry_run: bool = True


class RetryFailedRequest(BaseModel):
    statuses: list[str] = ["error", "parse_failed", "waiting_parser"]
    trigger: bool = True


@router.get("/{document_id}/file")
async def download_document_file(document_id: str, format: str = "pdf"):
    """下载文档原始文件（pdf）或解析产物（md）"""
    if format not in ("pdf", "md"):
        raise HTTPException(status_code=400, detail="format 仅支持 pdf 或 md")
    doc = await _get_document_or_404(document_id)
    key = doc.get("object_key") or ""
    if not key:
        raise HTTPException(status_code=404, detail="文档无 object_key")
    if format == "md":
        key = key.rsplit(".", 1)[0] + ".md"
    bucket = doc.get("bucket") or DEFAULT_BUCKET

    if not await minio_tool.exists(bucket, key):
        raise HTTPException(status_code=404, detail=f"MinIO 对象不存在: {key}")
    data = await minio_tool.download(bucket, key)

    media_type = "application/pdf" if format == "pdf" else "text/markdown; charset=utf-8"
    filename = f"{doc.get('symbol')}_{doc.get('year')}.{format}"
    return StreamingResponse(
        BytesIO(data),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/cleanup")
async def cleanup_documents(req: CleanupRequest):
    """按状态或 MinIO 孤儿条件批量清理文档（dry_run=True 默认仅预览）"""
    if not req.status and not req.orphan:
        raise HTTPException(status_code=400, detail="需指定 status 或 orphan=true")

    select_cols = (
        "SELECT id, market, symbol, company, year, document_type, status, "
        "bucket, object_key FROM documents"
    )
    if req.status:
        rows = await postgres_tool.query(
            f"{select_cols} WHERE status = $1 ORDER BY created_at ASC", req.status
        )
    else:
        rows = await postgres_tool.query(f"{select_cols} ORDER BY created_at ASC")
        # 孤儿过滤：MinIO 对象不存在（并发限流 16）
        sem = asyncio.Semaphore(16)

        async def _is_orphan(r: dict) -> bool:
            key = r.get("object_key") or ""
            if not key:
                return True
            async with sem:
                return not await minio_tool.exists(
                    r.get("bucket") or DEFAULT_BUCKET, key
                )

        flags = await asyncio.gather(*[_is_orphan(r) for r in rows])
        rows = [r for r, f in zip(rows, flags) if f]

    matched = [
        {"id": str(r["id"]), "symbol": r["symbol"], "year": r["year"], "status": r["status"]}
        for r in rows
    ]

    if req.dry_run:
        return {"dry_run": True, "matched": len(matched), "documents": matched}

    deleted = 0
    for r in rows:
        await _purge_document_resources(r)
        doc_id = str(r["id"])
        try:
            await postgres_tool.execute(
                "DELETE FROM core.facts WHERE source_document = $1", doc_id
            )
        except Exception as e:
            logger.warning("cleanup: failed to delete facts %s: %s", doc_id[:8], e)
        await postgres_tool.execute("DELETE FROM documents WHERE id = $1", doc_id)
        deleted += 1
    logger.info("Bulk cleanup done | matched=%d deleted=%d", len(matched), deleted)
    return {"dry_run": False, "matched": len(matched), "deleted": deleted}


@router.post("/retry-failed")
async def retry_failed_documents(req: RetryFailedRequest):
    """批量重置失败态文档为 pending，可选入队触发处理"""
    if not req.statuses:
        raise HTTPException(status_code=400, detail="statuses 不能为空")
    rows = await postgres_tool.query(
        "UPDATE documents SET status = 'pending', metadata = metadata - 'error', "
        "updated_at = NOW() WHERE status = ANY($1) RETURNING id",
        req.statuses,
    )
    reset = len(rows)

    task_id = None
    if req.trigger and reset > 0:
        from runtime.queue import task_queue
        task_id = await task_queue.create_task(
            task_type="doc_pipeline",
            title=f"重试失败文档 ({reset} docs)",
            params={"limit": reset},
            total_items=reset,
            created_by="api",
        )
    logger.info("Retry-failed reset | %d docs | task=%s", reset, task_id)
    return {"status": "ok", "reset": reset, "pipeline_task_id": task_id}


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
        from runtime.queue import task_queue
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


# ─── 文件名解析 ───────────────────────────────────────────

# 匹配: 000001_平安银行_2023年年度报告.pdf 或 300313__ST天山_2023年年度报告.pdf
_FILENAME_RE = re.compile(
    r"^(?P<symbol>[A-Za-z0-9]+)"
    r"[_\-]+"
    r"(?P<company>[^_\-]+?)"
    r"[_\-]+"
    r"(?P<year>20\d{2})"
)

# 文件夹名 → 市场代码映射
_DIR_MARKET_MAP = {
    "stock_a": "cn",
    "stock_h": "hk",
    "stock_us": "us",
}


def _infer_market_from_path(folder_path: Path) -> str:
    """从文件夹路径推断市场代码"""
    for part in folder_path.parts:
        if part in _DIR_MARKET_MAP:
            return _DIR_MARKET_MAP[part]
    return "cn"


def _parse_pdf_filename(filename: str) -> dict | None:
    """从 PDF 文件名解析 symbol 和 year

    支持格式:
    - 000001_平安银行_2023年年度报告.pdf
    - 00700_騰訊控股_2025年年度报告.pdf
    - AAPL_大师分析报告_2024.pdf
    """
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    m = _FILENAME_RE.match(stem)
    if not m:
        return None
    return {
        "symbol": m.group("symbol").upper(),
        "year": int(m.group("year")),
    }


@router.post("/upload-folder")
async def upload_folder_pdfs(
    folder_path: str = Form(..., description="服务器上的文件夹路径"),
    market: str = Form("", description="市场代码（空则从路径自动推断）"),
    bucket: str = Form(DEFAULT_BUCKET),
    trigger: bool = Form(False),
):
    """批量上传文件夹内所有 PDF 到 MinIO 并注册文档

    递归扫描文件夹内所有 .pdf 文件，从文件名解析 symbol/year，
    上传到 MinIO 规范路径并注册为 pending 文档。
    返回 found/added/skipped 统计。
    """
    # 路径转换：Windows/WSL → 容器路径
    folder_path = normalize_path(folder_path)
    target = Path(folder_path).resolve()

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"路径不存在: {folder_path}（已转换为容器路径）")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"不是目录: {folder_path}")

    # 推断市场
    market = market.strip().lower() or _infer_market_from_path(target)

    # 递归查找所有 PDF
    pdf_files = sorted(target.rglob("*.pdf"))
    pdf_files = [f for f in pdf_files if not f.name.startswith(".")]

    stats = {"found": len(pdf_files), "added": 0, "skipped": 0, "failed": 0}
    results = []

    if not pdf_files:
        return {
            "status": "ok",
            "folder": str(target),
            "market": market,
            "stats": stats,
            "results": results,
        }

    for pdf_file in pdf_files:
        parsed = _parse_pdf_filename(pdf_file.name)
        if not parsed:
            logger.warning("[UploadFolder] Skip unparseable filename: %s", pdf_file.name)
            stats["skipped"] += 1
            results.append({"file": pdf_file.name, "status": "skipped", "reason": "filename_not_match"})
            continue

        symbol = parsed["symbol"]
        year = parsed["year"]
        object_key = f"{market}/{symbol}/annual_report/{year}/report.pdf"

        # 检查是否已存在
        try:
            existing = await postgres_tool.query(
                "SELECT 1 FROM documents WHERE object_key = $1", object_key
            )
            if existing:
                stats["skipped"] += 1
                results.append({"file": pdf_file.name, "status": "skipped", "reason": "already_exists", "object_key": object_key})
                continue
        except Exception as e:
            logger.warning("[UploadFolder] Dedup check failed for %s: %s", pdf_file.name, e)

        # 上传到 MinIO
        try:
            data = pdf_file.read_bytes()
            await minio_tool.upload(bucket, object_key, data)
        except Exception as e:
            logger.exception("[UploadFolder] MinIO upload failed: %s", pdf_file.name)
            stats["failed"] += 1
            results.append({"file": pdf_file.name, "status": "failed", "reason": str(e)})
            continue

        # 注册为 pending 文档
        try:
            reg_result = await doc_pipeline.register_pending_from_minio(
                bucket=bucket,
                prefix=f"{market}/{symbol}/annual_report/{year}",
                market=market,
            )
            if reg_result.get("added", 0) > 0:
                stats["added"] += 1
            else:
                stats["skipped"] += 1
            results.append({"file": pdf_file.name, "status": "ok", "object_key": object_key, "symbol": symbol, "year": year})
        except Exception as e:
            logger.exception("[UploadFolder] Register failed: %s", pdf_file.name)
            stats["failed"] += 1
            results.append({"file": pdf_file.name, "status": "failed", "reason": str(e)})

    # 可选：触发 Pipeline
    task_id = None
    if trigger and stats["added"] > 0:
        from runtime.queue import task_queue
        task_id = await task_queue.create_task(
            task_type="doc_pipeline",
            title=f"文档处理 Pipeline ({stats['added']} docs from {target.name})",
            params={"limit": stats["added"]},
            total_items=stats["added"],
            created_by="api",
        )

    return {
        "status": "ok",
        "folder": str(target),
        "market": market,
        "stats": stats,
        "results": results,
        "pipeline_task_id": task_id,
    }
