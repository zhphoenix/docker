"""Vector API - Qdrant 向量数据库统计（只读）"""

import logging

import httpx
from fastapi import APIRouter

from config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/vector", tags=["vector"])


@router.get("/collections")
async def list_vector_collections():
    """Qdrant 全部 Collection 统计

    直接调用 Qdrant REST API。
    Qdrant 不可达时返回 200 + error 字段（前端据此展示降级 UI）。
    """
    base = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"
    collections = []

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # 获取 collection 列表
            resp = await client.get(f"{base}/collections")
            if resp.status_code != 200:
                return {"collections": [], "error": f"Qdrant returned {resp.status_code}"}

            names = [c["name"] for c in resp.json().get("result", {}).get("collections", [])]

            # 逐个获取详情
            for name in names:
                try:
                    detail = await client.get(f"{base}/collections/{name}")
                    if detail.status_code == 200:
                        r = detail.json().get("result", {})
                        config = r.get("config", {}).get("params", {}).get("vectors", {})
                        collections.append({
                            "name": name,
                            "points_count": r.get("points_count", 0),
                            "vectors_count": r.get("vectors_count", 0),
                            "indexed_vectors_count": r.get("indexed_vectors_count", 0),
                            "status": r.get("status", "unknown"),
                            "vector_size": config.get("size"),
                            "distance": config.get("distance"),
                        })
                    else:
                        collections.append({"name": name, "status": "error"})
                except Exception:
                    collections.append({"name": name, "status": "error"})

        return {"collections": collections, "total": len(collections), "error": None}

    except Exception as e:
        logger.warning("Qdrant unreachable: %s", e)
        return {"collections": [], "total": 0, "error": "Qdrant unreachable"}
