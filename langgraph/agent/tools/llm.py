"""LLM Tool - 封装 llama.cpp LLM 服务调用"""

import json
import logging
from typing import AsyncGenerator

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


class LLMTool:
    """调用 llama.cpp LLM 服务（OpenAI Compatible API）"""

    def __init__(self):
        self.base_url = settings.OPENAI_BASE_URL
        self.model = settings.MODEL_NAME
        self.timeout = 20.0
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
        """非流式聊天补全

        Args:
            messages: [{"role": "user", "content": "..."}]
            **kwargs: temperature, max_tokens, stop 等

        Returns:
            完整响应 dict（含 choices 和 usage）
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            **kwargs,
        }

        try:
            client = self._get_client()
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError:
            logger.error("LLM service unavailable at %s", self.base_url)
            raise
        except httpx.HTTPStatusError as e:
            logger.error("LLM service error: %s", e.response.text)
            raise

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
