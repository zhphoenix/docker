"""Documents API - 文档只读列表与统计"""

import logging

from fastapi import APIRouter, HTTPException

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


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
