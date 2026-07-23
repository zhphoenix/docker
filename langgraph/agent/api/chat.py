"""Chat 路由 - /v1/chat/completions"""

import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse

from schemas.chat import ChatRequest
from graph.router import dispatch_agent

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    """聊天补全（OpenAI Compatible）

    支持流式和非流式响应。
    """
    logger.info(
        "Chat request: model=%s, stream=%s, messages=%d",
        request.model,
        request.stream,
        len(request.messages),
    )

    try:
        # 路由到对应 Agent
        agent = dispatch_agent(request)

        if request.stream:
            # 流式响应
            return StreamingResponse(
                agent.stream_run(request),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
                },
            )
        else:
            # 非流式响应
            response = await agent.run(request)
            return response

    except Exception as e:
        logger.error("Chat error: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": str(e),
                    "type": "server_error",
                }
            },
        )
