"""Health & Monitoring 路由 - 健康检查 + 系统监控"""

import asyncio
import logging
import time

import httpx
from fastapi import APIRouter

from config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()

_start_time = time.time()

# 单次探测超时（秒）。多个服务不可达时，并行检查可避免串行超时累加。
CHECK_TIMEOUT = 2.0

# 需要检查的 HTTP 服务（name, url）
HTTP_CHECKS = [
    ("qdrant", f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}/healthz"),
    ("embedding", f"{settings.EMBEDDING_URL}/../health"),
    ("reranker", f"{settings.RERANKER_URL}/../health"),
    ("docling", f"{settings.DOCLING_URL}/health"),
    ("llm", f"{settings.OPENAI_BASE_URL}/../health"),
    ("paddleocr", f"{settings.PADDLEOCR_URL}/health"),
    ("siyuan", f"{settings.SIYUAN_URL}/"),
    ("crawl4ai", f"{settings.CRAWL4AI_URL}/health"),
    ("open-webui", f"{settings.OPENWEBUI_URL}/"),
]

# MCP 服务（FastMCP 暴露 JSON-RPC over HTTP POST /mcp）
MCP_CHECKS = [
    ("mcp-knowledge", settings.MCP_KNOWLEDGE_URL),
    ("mcp-news", settings.MCP_NEWS_URL),
]


async def _check_http(name: str, url: str) -> tuple[str, str]:
    """探测单个 HTTP 服务连通性"""
    try:
        async with httpx.AsyncClient(timeout=CHECK_TIMEOUT) as client:
            response = await client.get(url)
            return name, "up" if response.status_code < 500 else "down"
    except Exception:
        return name, "down"


async def _check_mcp(name: str, url: str) -> tuple[str, str]:
    """探测单个 MCP 服务（JSON-RPC initialize）"""
    try:
        async with httpx.AsyncClient(timeout=CHECK_TIMEOUT) as client:
            response = await client.post(
                f"{url}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "health-check", "version": "0.1"},
                    },
                },
                headers={"Accept": "application/json, text/event-stream"},
            )
            return name, "up" if response.status_code < 500 else "down"
    except Exception:
        return name, "down"


@router.get("/health")
async def health_check():
    """健康检查 - 检查各下游服务连通性（并行探测，总耗时受最慢单次限制）"""
    # 并行检查 HTTP 与 MCP 服务，避免串行超时累加
    results = await asyncio.gather(
        *[_check_http(name, url) for name, url in HTTP_CHECKS],
        *[_check_mcp(name, url) for name, url in MCP_CHECKS],
    )
    services = dict(results)

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
