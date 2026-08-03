"""Embedding Tool - 统一 Embedding 调用层（Qwen3-Embedding-4B, :8001）

所有需要生成向量的模块必须通过 EmbeddingTool 调用，
禁止业务代码直接使用 httpx / requests / OpenAI SDK。
"""

import asyncio
import logging

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

# Retry 退避间隔（秒）
_RETRY_DELAYS = [0.5, 1.0, 2.0]


class EmbeddingTool:
    """统一 Embedding 调用层

    职责：
    - 管理 HTTP 连接池（长生命周期 AsyncClient）
    - 请求 Embedding Server
    - 响应校验
    - 自动 Retry（指数退避）
    - Semaphore 并发限制
    - 分类异常处理 + 完整日志
    - 生命周期管理
    """

    def __init__(self) -> None:
        self._base_url = settings.EMBEDDING_URL.rstrip("/")
        self._model = settings.EMBEDDING_MODEL
        self._max_retries = settings.EMBEDDING_MAX_RETRIES
        self._semaphore = asyncio.Semaphore(settings.EMBEDDING_MAX_CONCURRENCY)
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # HTTP Client（连接池，长生命周期）
    # ------------------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        """获取复用的 httpx 客户端（连接池 + Keep-Alive）"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=settings.EMBEDDING_CONNECT_TIMEOUT,
                    read=settings.EMBEDDING_READ_TIMEOUT,
                    write=settings.EMBEDDING_WRITE_TIMEOUT,
                    pool=settings.EMBEDDING_POOL_TIMEOUT,
                ),
                limits=httpx.Limits(
                    max_connections=settings.EMBEDDING_MAX_CONNECTIONS,
                    max_keepalive_connections=settings.EMBEDDING_KEEPALIVE_CONNECTIONS,
                ),
            )
        return self._client

    # ------------------------------------------------------------------
    # 核心方法
    # ------------------------------------------------------------------

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """文本向量化

        Args:
            texts: 待向量化的文本列表

        Returns:
            向量列表 list[list[float]]，与输入一一对应

        Raises:
            httpx.ConnectError: Embedding 服务不可达（重试耗尽）
            httpx.ReadTimeout: GPU 推理超时（重试耗尽）
            ValueError: 响应格式校验失败
        """
        if not texts:
            return []

        logger.debug("Embedding %d texts", len(texts))

        async with self._semaphore:
            return await self._embed_with_retry(texts)

    async def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        """带自动重试的 Embedding 调用"""
        last_exc: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                return await self._do_request(texts)

            except httpx.ConnectError as exc:
                last_exc = exc
                logger.warning(
                    "Embedding service unreachable at %s (attempt %d/%d)",
                    self._base_url,
                    attempt + 1,
                    self._max_retries + 1,
                )

            except httpx.ReadTimeout as exc:
                last_exc = exc
                logger.warning(
                    "Embedding read timeout at %s (attempt %d/%d)",
                    self._base_url,
                    attempt + 1,
                    self._max_retries + 1,
                )

            except httpx.HTTPStatusError as exc:
                last_exc = exc
                logger.warning(
                    "Embedding HTTP %d at %s | body: %s (attempt %d/%d)",
                    exc.response.status_code,
                    self._base_url,
                    exc.response.text[:500],
                    attempt + 1,
                    self._max_retries + 1,
                )

            except Exception:
                logger.exception(
                    "Embedding unexpected error at %s (attempt %d/%d)",
                    self._base_url,
                    attempt + 1,
                    self._max_retries + 1,
                )
                raise  # 未知异常不重试，直接抛出

            # 退避等待（最后一次失败不再等待）
            if attempt < self._max_retries:
                delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
                await asyncio.sleep(delay)

        # 重试耗尽
        logger.error(
            "Embedding failed after %d attempts at %s",
            self._max_retries + 1,
            self._base_url,
        )
        raise last_exc  # type: ignore[misc]

    async def _do_request(self, texts: list[str]) -> list[list[float]]:
        """执行单次 HTTP 请求 + 响应校验"""
        client = self._get_client()
        response = await client.post(
            f"{self._base_url}/embeddings",
            json={"model": self._model, "input": texts},
        )
        response.raise_for_status()

        data = response.json()

        # ---- 响应校验 ----
        if "data" not in data:
            raise ValueError(
                f"Embedding response missing 'data' field: {list(data.keys())}"
            )

        items = data["data"]

        if len(items) != len(texts):
            raise ValueError(
                f"Embedding response count mismatch: "
                f"expected {len(texts)}, got {len(items)}"
            )

        result: list[list[float]] = []
        for i, item in enumerate(items):
            if "embedding" not in item:
                raise ValueError(
                    f"Embedding response item[{i}] missing 'embedding' field"
                )
            result.append(item["embedding"])

        return result

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """关闭客户端连接池，释放 Keep-Alive / Socket 资源"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.debug("EmbeddingTool client closed")


# 模块级单例（整个进程唯一实例）
embedding_tool = EmbeddingTool()
