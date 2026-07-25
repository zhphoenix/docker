"""Provider Registry API - 数据源管理"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/providers", tags=["providers"])


class ProviderOut(BaseModel):
    id: str
    name: str
    category: str
    base_url: str | None = None
    priority: int = 0
    status: str = "active"


@router.get("")
async def list_providers(category: str | None = None, status: str | None = None):
    """列出所有数据源 Provider"""
    query = "SELECT id, name, category, base_url, priority, status FROM providers WHERE 1=1"
    params = []
    idx = 1

    if category:
        query += f" AND category = ${idx}"
        params.append(category)
        idx += 1
    if status:
        query += f" AND status = ${idx}"
        params.append(status)
        idx += 1

    query += " ORDER BY priority DESC, name"

    try:
        rows = await postgres_tool.query(query, *params)
        # UUID 转字符串
        for r in rows:
            r["id"] = str(r["id"])
        return {"providers": rows, "total": len(rows)}
    except Exception as e:
        logger.exception("Failed to list providers")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{provider_id}")
async def get_provider(provider_id: str):
    """获取单个 Provider 详情"""
    try:
        rows = await postgres_tool.query(
            "SELECT * FROM providers WHERE id = $1", provider_id
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Provider not found")
        row = rows[0]
        row["id"] = str(row["id"])
        return row
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{provider_id}/test")
async def test_provider(provider_id: str):
    """测试 Provider 连通性（预留）"""
    return {
        "provider_id": provider_id,
        "status": "not_implemented",
        "message": "Provider connectivity test is planned for future implementation",
    }
