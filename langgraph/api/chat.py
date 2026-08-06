"""Chat 路由 - /v1/chat/completions"""

import logging
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse

from schemas.chat import ChatRequest
from services.router import dispatch_agent
from monitoring.agent_center import record_agent_run, finish_agent_run

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

    question = request.messages[-1].content if request.messages else ""
    start = time.monotonic()

    try:
        # 路由到对应 Agent
        agent = dispatch_agent(request)
        agent_id = getattr(agent, "agent_name", "base")

        if request.stream:
            # 流式响应
            generator = agent.stream_run(request)

            async def traced_stream():
                run_id = await record_agent_run(
                    agent_id, "chat", "running", question=question
                )
                try:
                    async for chunk in generator:
                        yield chunk
                    await finish_agent_run(
                        run_id, "success", duration_ms=int((time.monotonic() - start) * 1000)
                    )
                except Exception as e:
                    await finish_agent_run(
                        run_id, "failed", duration_ms=int((time.monotonic() - start) * 1000),
                        error=str(e), error_category="chat_error",
                    )
                    raise

            return StreamingResponse(
                traced_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
                },
            )
        else:
            # 非流式响应
            run_id = await record_agent_run(agent_id, "chat", "running", question=question)
            try:
                response = await agent.run(request)
                await finish_agent_run(
                    run_id, "success", duration_ms=int((time.monotonic() - start) * 1000)
                )
                return response
            except Exception as e:
                await finish_agent_run(
                    run_id, "failed", duration_ms=int((time.monotonic() - start) * 1000),
                    error=str(e), error_category="chat_error",
                )
                raise

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
