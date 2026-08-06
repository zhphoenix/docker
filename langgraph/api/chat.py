"""Chat 路由 - /v1/chat/completions"""

import logging
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse

from schemas.chat import ChatRequest
from services.router import dispatch_agent
from monitoring.agent_center import record_agent_run, finish_agent_run
from prompts.loader import reset_variant_context, variant_label
from api.agents import is_agent_api_enabled

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

        # AC-P4-6：Agent API 权限校验，停用后返回 403
        if not await is_agent_api_enabled(agent_id):
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "message": f"Agent '{agent_id}' API access is disabled by administrator",
                        "type": "permission_denied",
                    }
                },
            )

        if request.stream:
            # 流式响应
            generator = agent.stream_run(request)

            async def traced_stream():
                reset_variant_context()
                run_id = await record_agent_run(
                    agent_id, "chat", "running", question=question
                )
                try:
                    async for chunk in generator:
                        yield chunk
                    await finish_agent_run(
                        run_id, "success", duration_ms=int((time.monotonic() - start) * 1000),
                        variant=variant_label() or getattr(agent, "last_variant", None),
                    )
                except Exception as e:
                    await finish_agent_run(
                        run_id, "failed", duration_ms=int((time.monotonic() - start) * 1000),
                        error=str(e), error_category="chat_error",
                        variant=variant_label() or getattr(agent, "last_variant", None),
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
            reset_variant_context()
            run_id = await record_agent_run(agent_id, "chat", "running", question=question)
            try:
                response = await agent.run(request)
                await finish_agent_run(
                    run_id, "success", duration_ms=int((time.monotonic() - start) * 1000),
                    tokens_in=getattr(response.usage, "prompt_tokens", 0),
                    tokens_out=getattr(response.usage, "completion_tokens", 0),
                    variant=variant_label() or getattr(agent, "last_variant", None),
                )
                return response
            except Exception as e:
                await finish_agent_run(
                    run_id, "failed", duration_ms=int((time.monotonic() - start) * 1000),
                    error=str(e), error_category="chat_error",
                    variant=variant_label() or getattr(agent, "last_variant", None),
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
