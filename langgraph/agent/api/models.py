"""Models 路由 - 列出可用模型"""

import time

from fastapi import APIRouter

from schemas.chat import ModelsResponse, ModelInfo

router = APIRouter()


@router.get("/v1/models")
async def list_models():
    """列出可用模型"""
    return ModelsResponse(
        data=[
            ModelInfo(
                id="qwen3",
                created=int(time.time()),
                owned_by="local",
            )
        ]
    )
