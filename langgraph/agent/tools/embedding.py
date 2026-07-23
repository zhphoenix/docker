"""Embedding Tool - 封装 Embedding 服务调用（Qwen3-Embedding-4B, :8001）"""

import logging

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


class EmbeddingTool:
    """调用 Embedding 服务，将文本转换为向量"""

    def __init__(self):
        self.base_url = settings.EMBEDDING_URL
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """获取复用的 httpx 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=3),
            )
        return self._client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """文本向量化

        Args:
            texts: 待向量化的文本列表

        Returns:
            向量列表，每个向量为 list[float]
        """
        try:
            client = self._get_client()
            response = await client.post(
                f"{self.base_url}/embeddings",
                json={"input": texts, "model": "embedding"},
            )
            response.raise_for_status()
            data = response.json()
            return [item["embedding"] for item in data["data"]]
        except httpx.ConnectError:
            logger.error("Embedding service unavailable at %s", self.base_url)
            raise

    async def close(self):
        """关闭客户端连接池"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# 模块级单例
embedding_tool = EmbeddingTool()
"""Embedding Tool - 封装 Embedding 服务调用（Qwen3-Embedding-4B, :8001）"""

import logging

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


class EmbeddingTool:
    """调用 Embedding 服务，将文本转换为向量"""

    def __init__(self):
        self.base_url = settings.EMBEDDING_URL
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """获取复用的 httpx 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=3),
            )
        return self._client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """文本向量化

        Args:
            texts: 待向量化的文本列表

        Returns:
            向量列表，每个向量为 list[float]
        """
        try:
            client = self._get_client()
            response = await client.post(
                f"{self.base_url}/embeddings",
                json={"input": texts, "model": "embedding"},
            )
            response.raise_for_status()
            data = response.json()
            return [item["embedding"] for item in data["data"]]
        except httpx.ConnectError:
            logger.error("Embedding service unavailable at %s", self.base_url)
            raise

    async def close(self):
        """关闭客户端连接池"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# 模块级单例
embedding_tool = EmbeddingTool()
"""Embedding Tool - 封装 Embedding 服务调用（Qwen3-Embedding-4B, :8001）"""

import logging

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


class EmbeddingTool:
    """调用 Embedding 服务，将文本转换为向量"""

    def __init__(self):
        self.base_url = settings.EMBEDDING_URL
        self.timeout = 30.0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """文本向量化

        Args:
            texts: 待向量化的文本列表

        Returns:
            向量列表，每个向量为 list[float]
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    json={"input": texts, "model": "embedding"},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                return [item["embedding"] for item in data["data"]]
        except httpx.ConnectError:
            logger.error("Embedding service unavailable at %s", self.base_url)
            raise


# 模块级单例
embedding_tool = EmbeddingTool()
