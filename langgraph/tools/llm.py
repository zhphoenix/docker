"""LLM Tool - 封装 llama.cpp LLM 服务调用

性能优化：添加指数退避重试，防止单次超时导致整个提取失败。
"""

import asyncio
import logging
from typing import AsyncGenerator

import httpx

from config.settings import settings
from config.policy_loader import get_policy
from monitoring.agent_center import track_tool

logger = logging.getLogger(__name__)


class LLMTool:
    """调用 llama.cpp LLM 服务（OpenAI Compatible API）"""

    def __init__(self):
        self.base_url = settings.OPENAI_BASE_URL
        self.model = settings.MODEL_NAME
        # Sisyphus (Qwythos-9B) 使用 65K context + 推测解码，单次推理可能耗时 60-120s
        self.timeout = 120.0
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """获取复用的 httpx 客户端（连接池）"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
            )
        return self._client

    async def chat(self, messages: list[dict], **kwargs) -> dict:
        """非流式聊天补全（带指数退避重试）

        Args:
            messages: [{"role": "user", "content": "..."}]
            **kwargs: temperature, max_tokens, stop 等

        Returns:
            完整响应 dict（含 choices 和 usage）
        """
        async with track_tool("llm.chat"):
            return await self._chat_with_retry(messages, **kwargs)

    async def _chat_with_retry(self, messages: list[dict], **kwargs) -> dict:
        """非流式聊天补全（带指数退避重试）的内部实现"""
        max_retries = get_policy("retry.max_retries", 3)
        initial_delay = get_policy("retry.initial_delay_seconds", 1)
        max_delay = get_policy("retry.max_delay_seconds", 30)

        last_exc: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                return await self._do_chat(messages, **kwargs)
            except httpx.HTTPStatusError as e:
                # 4xx 客户端错误（除 429 限流外）不可恢复，直接抛出
                if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                    logger.error("LLM client error %d: %s", e.response.status_code, e.response.text[:200])
                    raise
                last_exc = e
            except (httpx.ReadTimeout, httpx.ConnectError) as e:
                last_exc = e

            if attempt == max_retries:
                logger.error(
                    "LLM chat failed after %d attempts: %s",
                    max_retries + 1, last_exc,
                )
                raise last_exc  # type: ignore[misc]

            delay = min(initial_delay * (2 ** attempt), max_delay)
            logger.warning(
                "LLM chat attempt %d/%d failed (%s), retrying in %.1fs",
                attempt + 1, max_retries + 1, type(last_exc).__name__, delay,
            )
            await asyncio.sleep(delay)

        raise last_exc  # type: ignore[misc]

    async def _do_chat(self, messages: list[dict], **kwargs) -> dict:
        """执行单次 LLM 请求"""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            # 默认给足 token 预算：reasoning 模型会先输出长思考过程（实测约 2k tokens），
            # 若 max_tokens 过小会被 reasoning 占满导致 content 为空或被截断。
            # 实测 max_tokens=4096 时 content 能完整输出 JSON（reasoning~1937 + content~668）。
            "max_tokens": kwargs.pop("max_tokens", 4096),
            **kwargs,
        }

        client = self._get_client()
        response = await client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def stream_chat(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        """流式聊天补全

        Yields:
            SSE 原始行（含 "data: " 前缀）
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            **kwargs,
        }

        try:
            client = self._get_client()
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        yield line
        except httpx.ConnectError:
            logger.error("LLM service unavailable at %s", self.base_url)
            raise

    async def close(self):
        """关闭客户端连接池"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# 模块级单例
llm_tool = LLMTool()
