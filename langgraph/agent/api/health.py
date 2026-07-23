"""Health 路由 - 健康检查"""

import logging

import httpx
from fastapi import APIRouter

from config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查 - 检查各下游服务连通性"""
    services = {}

    # 检查各服务
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

    # PostgreSQL 检查
    try:
        from tools.postgres import postgres_tool
        if postgres_tool.pool:
            services["postgres"] = "up"
        else:
            services["postgres"] = "down"
    except Exception:
        services["postgres"] = "down"

    # Obsidian 检查（可选，不影响整体状态）
    try:
        from tools.obsidian import obsidian_tool
        services["obsidian"] = "up" if await obsidian_tool.health_check() else "down"
    except Exception:
        services["obsidian"] = "down"

    # MinIO 检查（可选）
    try:
        from tools.minio import minio_tool
        services["minio"] = "up" if await minio_tool.health_check() else "down"
    except Exception:
        services["minio"] = "down"

    # 核心服务检查（不含 obsidian）
    core_services = ["qdrant", "embedding", "reranker", "docling", "llm", "postgres"]
    core_up = all(services.get(s) == "up" for s in core_services)

    return {
        "status": "healthy" if core_up else "degraded",
        "services": services,
    }
