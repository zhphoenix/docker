"""Reranker Tool - 封装 Reranker 服务调用（Qwen3-Reranker-0.6B, :8002）"""

import logging

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


class RerankerTool:
    """调用 Reranker 服务，对检索结果重排序"""

    def __init__(self):
        self.base_url = settings.RERANKER_URL
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """获取复用的 httpx 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=3),
            )
        return self._client

    async def rerank(self, query: str, documents: list[str]) -> list[dict]:
        """重排序

        Args:
            query: 查询文本
            documents: 待排序的文档内容列表

        Returns:
            重排序后的结果列表 [{"index": int, "relevance_score": float}, ...]
        """
        try:
            client = self._get_client()
            response = await client.post(
                f"{self.base_url}/rerank",
                json={"query": query, "documents": documents},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
        except httpx.ConnectError:
            logger.error("Reranker service unavailable at %s", self.base_url)
            raise

    async def close(self):
        """关闭客户端连接池"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# 模块级单例
reranker_tool = RerankerTool()
"""Reranker Tool - 封装 Reranker 服务调用（Qwen3-Reranker-0.6B, :8002）"""

import logging

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


class RerankerTool:
    """调用 Reranker 服务，对检索结果重排序"""

    def __init__(self):
        self.base_url = settings.RERANKER_URL
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """获取复用的 httpx 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=3),
            )
        return self._client

    async def rerank(self, query: str, documents: list[str]) -> list[dict]:
        """重排序

        Args:
            query: 查询文本
            documents: 待排序的文档内容列表

        Returns:
            重排序后的结果列表 [{"index": int, "relevance_score": float}, ...]
        """
        try:
            client = self._get_client()
            response = await client.post(
                f"{self.base_url}/rerank",
                json={"query": query, "documents": documents},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
        except httpx.ConnectError:
            logger.error("Reranker service unavailable at %s", self.base_url)
            raise

    async def close(self):
        """关闭客户端连接池"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# 模块级单例
reranker_tool = RerankerTool()
"""Reranker Tool - 封装 Reranker 服务调用（Qwen3-Reranker-0.6B, :8002）"""

import logging

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


class RerankerTool:
    """调用 Reranker 服务，对检索结果重排序"""

    def __init__(self):
        self.base_url = settings.RERANKER_URL
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """获取复用的 httpx 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=3),
            )
        return self._client

    async def rerank(self, query: str, documents: list[str]) -> list[dict]:
        """重排序

        Args:
            query: 查询文本
            documents: 待排序的文档内容列表

        Returns:
            重排序后的结果列表 [{"index": int, "relevance_score": float}, ...]
        """
        try:
            client = self._get_client()
            response = await client.post(
                f"{self.base_url}/rerank",
                json={"query": query, "documents": documents},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
        except httpx.ConnectError:
            logger.error("Reranker service unavailable at %s", self.base_url)
            raise

    async def close(self):
        """关闭客户端连接池"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# 模块级单例
reranker_tool = RerankerTool()
"""Reranker Tool - 封装 Reranker 服务调用（Qwen3-Reranker-0.6B, :8002）"""

import logging

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


class RerankerTool:
    """调用 Reranker 服务，对检索结果重排序"""

    def __init__(self):
        self.base_url = settings.RERANKER_URL
        self.timeout = 30.0

    async def rerank(self, query: str, documents: list[str]) -> list[dict]:
        """重排序

        Args:
            query: 查询文本
            documents: 待排序的文档内容列表

        Returns:
            重排序后的结果列表 [{"index": int, "relevance_score": float}, ...]
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/rerank",
                    json={"query": query, "documents": documents},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("results", [])
        except httpx.ConnectError:
            logger.error("Reranker service unavailable at %s", self.base_url)
            raise


# 模块级单例
reranker_tool = RerankerTool()
