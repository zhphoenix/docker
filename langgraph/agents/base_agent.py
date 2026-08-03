"""Base Agent - Agent 基类"""

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage

from schemas.chat import ChatRequest, ChatResponse, ChatChoice, ChatMessage, UsageInfo, StreamChunk, StreamChoice, StreamDelta
from memory import memory_manager

logger = logging.getLogger(__name__)


class BaseAgent:
    """Agent 基类

    所有 Agent 继承此类，提供统一的 run/stream_run 接口。
    """

    def __init__(self, graph, agent_name: str = "base"):
        self.graph = graph
        self.agent_name = agent_name

    def _build_initial_state(self, request: ChatRequest) -> dict:
        """从 ChatRequest 构建初始 State"""
        question = request.messages[-1].content if request.messages else ""

        return {
            "messages": [HumanMessage(content=question)],
            "question": question,
            "plan": {},
            "documents": [],
            "tool_results": {},
            "answer": "",
            "reflect": {},
            "metadata": {
                "agent": self.agent_name,
                "model": request.model,
                "start_time": time.time(),
            },
        }

    async def run(self, request: ChatRequest) -> ChatResponse:
        """非流式执行

        Args:
            request: Chat 请求

        Returns:
            ChatResponse
        """
        initial_state = self._build_initial_state(request)
        question = initial_state["question"]

        logger.info("[%s] Starting run", self.agent_name)
        start_time = time.time()

        # 情景记忆：记录任务开始
        task_id = await memory_manager.start_episode(
            question=question,
            agent_type=self.agent_name,
        )

        try:
            result = await self.graph.ainvoke(initial_state)
        except Exception as e:
            await memory_manager.fail_episode(task_id, str(e))
            raise

        elapsed = time.time() - start_time
        answer = result.get("answer", "")
        reflect = result.get("reflect", {})
        documents = result.get("documents", [])

        # 情景记忆：记录任务完成
        await memory_manager.complete_episode(
            task_id=task_id,
            answer=answer,
            quality=reflect.get("quality", "unknown"),
            confidence=reflect.get("confidence", 0.0),
            document_count=len(documents),
            elapsed_seconds=elapsed,
        )

        logger.info("[%s] Run completed in %.2fs, answer=%d chars", self.agent_name, elapsed, len(answer))

        # 从 metadata 提取 token 用量
        metadata = result.get("metadata", {})
        usage = UsageInfo(
            prompt_tokens=metadata.get("prompt_tokens", 0),
            completion_tokens=metadata.get("completion_tokens", 0),
            total_tokens=metadata.get("total_tokens", 0),
        )

        return ChatResponse(
            id=f"chatcmpl-{int(time.time() * 1000)}",
            created=int(time.time()),
            model=request.model,
            choices=[
                ChatChoice(
                    message=ChatMessage(role="assistant", content=answer),
                    finish_reason="stop",
                )
            ],
            usage=usage,
        )

    async def stream_run(self, request: ChatRequest) -> AsyncGenerator[str, None]:
        """真实流式执行

        手动执行 Workflow 节点到 Reason 之前，然后直接流式调用 LLM。
        首字等待时间 = Planner + Retrieve + Rerank 时间（不等待完整推理）。

        Yields:
            SSE 格式的 JSON chunk
        """
        from tools.llm import llm_tool
        from nodes.research.planner import planner
        from nodes.research.retrieve import retrieve
        from nodes.research.rerank import rerank
        from prompts.loader import load_prompt

        initial_state = self._build_initial_state(request)
        chat_id = f"chatcmpl-{int(time.time() * 1000)}"
        created = int(time.time())

        logger.info("[%s] Starting stream_run", self.agent_name)
        start_time = time.time()

        # 发送 role
        first_chunk = StreamChunk(
            id=chat_id,
            created=created,
            model=request.model,
            choices=[StreamChoice(delta=StreamDelta(role="assistant"))],
        )
        yield f"data: {first_chunk.model_dump_json()}\n\n"

        try:
            # 手动执行前置节点
            if self.agent_name == "research":
                # Research: Planner → Retrieve → Rerank
                try:
                    plan_result = await asyncio.wait_for(planner(initial_state), timeout=60.0)
                    initial_state.update(plan_result)
                except asyncio.TimeoutError:
                    logger.warning("[%s] Planner timed out (60s), skipping", self.agent_name)
                    # Planner 失败时不阻断流程，Retrieve 会自动推断 market
                except Exception as e:
                    logger.warning("[%s] Planner failed: %s, skipping", self.agent_name, e)

            # Retrieve → Rerank（所有 Agent 都需要）
            retrieve_result = await retrieve(initial_state)
            initial_state.update(retrieve_result)

            rerank_result = await rerank(initial_state)
            initial_state.update(rerank_result)

            # 构建 Reason 的上下文
            question = initial_state["question"]
            documents = initial_state.get("documents", [])
            context = _build_context(documents)
            system_prompt = load_prompt("reason", question=question, context=context)

            # 直接流式调用 LLM（跳过 Reason Node 的非流式调用）
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ]

            full_answer = ""
            async for line in llm_tool.stream_chat(messages, temperature=0.7, max_tokens=4096):
                if line == "data: [DONE]":
                    yield "data: [DONE]\n\n"
                    break
                # 直接透传 LLM 的 SSE 数据
                try:
                    chunk_data = json.loads(line[6:])  # 去掉 "data: " 前缀
                    delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_answer += content
                        chunk = StreamChunk(
                            id=chat_id,
                            created=created,
                            model=request.model,
                            choices=[StreamChoice(delta=StreamDelta(content=content))],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"
                except (json.JSONDecodeError, IndexError, KeyError):
                    continue

            elapsed = time.time() - start_time
            logger.info("[%s] Stream completed in %.2fs, answer=%d chars", self.agent_name, elapsed, len(full_answer))

        except Exception as e:
            logger.error("[%s] Stream error: %s", self.agent_name, e, exc_info=True)
            error_chunk = StreamChunk(
                id=chat_id,
                created=created,
                model=request.model,
                choices=[StreamChoice(delta=StreamDelta(content=f"Error: {e}"), finish_reason="stop")],
            )
            yield f"data: {error_chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"


def _build_context(documents: list[dict]) -> str:
    """将文档列表构建为上下文字符串"""
    if not documents:
        return "（无检索结果）"
    parts = []
    for i, doc in enumerate(documents, 1):
        symbol = doc.get("symbol", "")
        year = doc.get("year", "")
        market = doc.get("market", "")
        source = f"{symbol}/{year}" if symbol else (market or "unknown")
        content = doc.get("content", "")
        parts.append(f"[文档 {i}] 来源: {source}\n{content}")
    return "\n\n---\n\n".join(parts)
