"""Health & Monitoring 路由 - 健康检查 + 系统监控"""

import logging
import time

import httpx
from fastapi import APIRouter

from config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()

_start_time = time.time()


@router.get("/health")
async def health_check():
    """健康检查 - 检查各下游服务连通性"""
    services = {}

    checks = [
        ("qdrant", f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}/healthz"),
        ("embedding", f"{settings.EMBEDDING_URL}/../health"),
        ("reranker", f"{settings.RERANKER_URL}/../health"),
        ("docling", f"{settings.DOCLING_URL}/health"),
        ("llm", f"{settings.OPENAI_BASE_URL}/../health"),
    ]

    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in checks:
            try:
                response = await client.get(url)
                services[name] = "up" if response.status_code < 500 else "down"
            except Exception:
                services[name] = "down"

    # PostgreSQL
    try:
        from tools.postgres import postgres_tool
        services["postgres"] = "up" if postgres_tool.pool else "down"
    except Exception:
        services["postgres"] = "down"

    # MinIO
    try:
        from tools.minio import minio_tool
        services["minio"] = "up" if await minio_tool.health_check() else "down"
    except Exception:
        services["minio"] = "down"

    core_services = ["qdrant", "postgres"]
    core_up = all(services.get(s) == "up" for s in core_services)

    return {
        "status": "healthy" if core_up else "degraded",
        "services": services,
        "uptime_seconds": int(time.time() - _start_time),
    }


@router.get("/metrics")
async def metrics():
    """系统指标 - 数据统计 + 任务队列 + 向量索引"""
    from tools.postgres import postgres_tool

    data = {"timestamp": time.time(), "uptime_seconds": int(time.time() - _start_time)}

    # PostgreSQL 数据统计
    try:
        tables = ["documents", "chunks", "company_basic", "providers", "tasks",
                  "financial_income", "financial_balance", "financial_cashflow", "shareholders"]
        stats = {}
        for t in tables:
            rows = await postgres_tool.query(f"SELECT COUNT(*) as cnt FROM {t}")
            stats[t] = rows[0]["cnt"] if rows else 0
        data["database"] = stats
    except Exception as e:
        data["database"] = {"error": str(e)}

    # Qdrant 向量统计
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            qdrant_stats = {}
            for coll in ["documents_cn", "documents_hk", "documents_us"]:
                resp = await client.get(f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}/collections/{coll}")
                if resp.status_code == 200:
                    r = resp.json().get("result", {})
                    qdrant_stats[coll] = {"points": r.get("points_count", 0), "status": r.get("status", "?")}
            data["qdrant"] = qdrant_stats
    except Exception as e:
        data["qdrant"] = {"error": str(e)}

    # 任务队列状态
    try:
        rows = await postgres_tool.query(
            "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status"
        )
        data["tasks"] = {r["status"]: r["cnt"] for r in rows}
    except Exception:
        data["tasks"] = {}

    # Embedding 进度
    try:
        embed_rows = await postgres_tool.query(
            "SELECT collection_name, "
            "COUNT(*) as total, "
            "COUNT(qdrant_point_id) as embedded "
            "FROM chunks GROUP BY collection_name"
        )
        data["embedding_progress"] = {
            r["collection_name"]: {
                "total": r["total"],
                "embedded": r["embedded"],
                "pending": r["total"] - r["embedded"],
                "pct": round(r["embedded"] / max(r["total"], 1) * 100, 2),
            }
            for r in embed_rows
        }
    except Exception:
        data["embedding_progress"] = {}

    # 文档处理状态
    try:
        doc_rows = await postgres_tool.query(
            "SELECT status, COUNT(*) as cnt FROM documents GROUP BY status"
        )
        data["document_status"] = {r["status"]: r["cnt"] for r in doc_rows}
    except Exception:
        data["document_status"] = {}

    return data


@router.get("/status")
async def status_summary():
    """简洁状态摘要（适合外部监控拉取）"""
    from tools.postgres import postgres_tool

    try:
        docs = await postgres_tool.query("SELECT COUNT(*) as cnt FROM documents")
        chunks = await postgres_tool.query("SELECT COUNT(*) as cnt FROM chunks")
        doc_count = docs[0]["cnt"] if docs else 0
        chunk_count = chunks[0]["cnt"] if chunks else 0
    except Exception:
        doc_count = chunk_count = -1

    return {
        "status": "ok",
        "documents": doc_count,
        "chunks": chunk_count,
        "uptime_h": round((time.time() - _start_time) / 3600, 1),
    }
