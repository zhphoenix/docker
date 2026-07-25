"""Models 路由 - 列出可用模型/Agent"""

import time

from fastapi import APIRouter

from schemas.chat import ModelsResponse, ModelInfo
from graph.router import AGENT_REGISTRY

router = APIRouter()


@router.get("/v1/models")
async def list_models():
    """列出可用模型（每个 Agent 作为一个 model 暴露给 Open WebUI）"""
    models = []
    for agent_name in AGENT_REGISTRY:
        models.append(
            ModelInfo(
                id=agent_name,
                created=int(time.time()),
                owned_by="ai-platform",
            )
        )
    return ModelsResponse(data=models)
