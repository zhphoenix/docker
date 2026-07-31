"""Models 路由 - 列出可用模型/Agent"""

import time

from fastapi import APIRouter

from schemas.chat import ModelsResponse, ModelInfo
from graph.router import AGENT_REGISTRY

router = APIRouter()


@router.get("/v1/models")
async def list_models():
    """列出可用模型（Sisyphus LLM + 本地 Agent）"""
    models = [
        # Sisyphus LLM 模型
        ModelInfo(
            id="sisyphus",
            created=int(time.time()),
            owned_by="sisyphus",
        ),
    ]
    # 本地 Agent 作为模型
    for agent_name in AGENT_REGISTRY:
        models.append(
            ModelInfo(
                id=agent_name,
                created=int(time.time()),
                owned_by="ai-platform",
            )
        )
    return ModelsResponse(data=models)
