"""Reranker Tool - 统一 Reranker 调用层（Qwen3-Reranker-0.6B, :8002）

所有需要文档重排序的模块必须通过 RerankerTool 调用，
禁止业务代码直接使用 httpx / requests 调用 Reranker 服务。
"""

import asyncio
import logging

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

# Retry 退避间隔（秒）
_RETRY_DELAYS = [1.0, 2.0]


class RerankerTool:
    """统一 Reranker 调用层

    职责：
    - 管理 HTTP 连接池（长生命周期 AsyncClient）
    - 请求 Reranker Server
    - 响应校验
    - 自动 Retry（指数退避）
    - Semaphore 并发限制
    - 分类异常处理 + 完整日志
    - 生命周期管理
    """

    def __init__(self) -> None:
        self._base_url = settings.RERANKER_URL.rstrip("/")
        self._model = settings.RERANKER_MODEL
        self._max_retries = settings.RERANKER_MAX_RETRIES
        self._top_k = settings.RERANK_TOP_K
        self._max_chars = settings.RERANK_MAX_CHARS
        self._semaphore = asyncio.Semaphore(settings.RERANKER_MAX_CONCURRENCY)
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # HTTP Client（连接池，长生命周期）
    # ------------------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        """获取复用的 httpx 客户端（连接池 + Keep-Alive）"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=settings.RERANKER_CONNECT_TIMEOUT,
                    read=settings.RERANKER_READ_TIMEOUT,
                    write=settings.RERANKER_WRITE_TIMEOUT,
                    pool=settings.RERANKER_POOL_TIMEOUT,
                ),
                limits=httpx.Limits(
                    max_connections=settings.RERANKER_MAX_CONNECTIONS,
                    max_keepalive_connections=settings.RERANKER_KEEPALIVE_CONNECTIONS,
                ),
            )
        return self._client

    # ------------------------------------------------------------------
    # 核心方法
    # ------------------------------------------------------------------

    async def rerank(self, query: str, documents: list[str]) -> list[dict]:
        """文档重排序

        内部自动处理：
        - Top-K 截取（settings.RERANK_TOP_K）
        - 文档截断（settings.RERANK_MAX_CHARS）

        Args:
            query: 查询文本
            documents: 待排序的文档内容列表

        Returns:
            重排序结果 [{"index": int, "relevance_score": float}, ...]
            index 对应原始 documents 下标

        Raises:
            httpx.ConnectError: Reranker 服务不可达（重试耗尽）
            httpx.ReadTimeout: GPU 推理超时（重试耗尽）
            ValueError: 响应格式校验失败
        """
        if not documents:
            return []

        # Top-K 截取 + 截断（Node 无需关心）
        top_docs = documents[: self._top_k]
        truncated = [doc[: self._max_chars] for doc in top_docs]

        logger.debug(
            "Reranking %d/%d documents (max_chars=%d)",
            len(truncated),
            len(documents),
            self._max_chars,
        )

        async with self._semaphore:
            return await self._rerank_with_retry(query, truncated)

    async def _rerank_with_retry(
        self, query: str, documents: list[str]
    ) -> list[dict]:
        """带自动重试的 Rerank 调用"""
        last_exc: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                return await self._do_request(query, documents)

            except httpx.ConnectError as exc:
                last_exc = exc
                logger.warning(
                    "Reranker service unreachable at %s (attempt %d/%d)",
                    self._base_url,
                    attempt + 1,
                    self._max_retries + 1,
                )

            except httpx.ReadTimeout as exc:
                last_exc = exc
                logger.warning(
                    "Reranker read timeout at %s (attempt %d/%d)",
                    self._base_url,
                    attempt + 1,
                    self._max_retries + 1,
                )

            except httpx.HTTPStatusError as exc:
                last_exc = exc
                logger.warning(
                    "Reranker HTTP %d at %s | body: %s (attempt %d/%d)",
                    exc.response.status_code,
                    self._base_url,
                    exc.response.text[:500],
                    attempt + 1,
                    self._max_retries + 1,
                )

            except Exception:
                logger.exception(
                    "Reranker unexpected error at %s (attempt %d/%d)",
                    self._base_url,
                    attempt + 1,
                    self._max_retries + 1,
                )
                raise  # 未知异常不重试

            # 退避等待
            if attempt < self._max_retries:
                delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
                await asyncio.sleep(delay)

        # 重试耗尽
        logger.error(
            "Reranker failed after %d attempts at %s",
            self._max_retries + 1,
            self._base_url,
        )
        raise last_exc  # type: ignore[misc]

    async def _do_request(self, query: str, documents: list[str]) -> list[dict]:
        """执行单次 HTTP 请求 + 响应校验"""
        client = self._get_client()
        response = await client.post(
            f"{self._base_url}/rerank",
            json={"query": query, "documents": documents},
        )
        response.raise_for_status()

        data = response.json()

        # ---- 响应校验 ----
        if "results" not in data:
            raise ValueError(
                f"Reranker response missing 'results' field: {list(data.keys())}"
            )

        results = data["results"]

        if not isinstance(results, list):
            raise ValueError(
                f"Reranker 'results' is not a list: {type(results)}"
            )

        # 校验每个结果包含必要字段
        for i, item in enumerate(results):
            if "index" not in item or "relevance_score" not in item:
                raise ValueError(
                    f"Reranker result[{i}] missing 'index' or 'relevance_score'"
                )

        return results

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """关闭客户端连接池，释放 Keep-Alive / Socket 资源"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.debug("RerankerTool client closed")


# 模块级单例（整个进程唯一实例）
reranker_tool = RerankerTool()
