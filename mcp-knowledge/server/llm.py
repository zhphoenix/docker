"""轻量 LLM client（OpenAI 兼容，GraphRAG 融合推理用）

复用 langgraph/agent/tools/llm.py 的调用模式（httpx + 指数退避重试），
但与 langgraph 服务解耦独立初始化，供 MCP Knowledge Server 内部调用。
"""

import asyncio
import logging

import httpx

from server.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """调用本地 LLM 推理服务（OpenAI Compatible API）"""

    def __init__(self):
        self.base_url = settings.OPENAI_BASE_URL
        self.model = settings.MODEL_NAME
        self.api_key = settings.OPENAI_API_KEY
        self.timeout = settings.LLM_TIMEOUT
        self.max_retries = settings.LLM_MAX_RETRIES
        self._client: httpx.AsyncClient | None = None
        self._resolved_base_url: str | None = None

    async def _resolve_base_url(self) -> str:
        """解析可达的 LLM 服务地址（lazy + 缓存）

        容器内 localhost 指向自身，宿主 LLM 需经 host.docker.internal 访问。
        首次调用时探测候选地址，优先原配置，失败则回退到宿主别名。
        """
        if self._resolved_base_url:
            return self._resolved_base_url

        base = self.base_url.rstrip("/")
        candidates: list[str] = [base]
        if "localhost" in base or "127.0.0.1" in base:
            for repl in ("host.docker.internal", "172.17.0.1"):
                c = base.replace("localhost", repl).replace("127.0.0.1", repl)
                if c not in candidates:
                    candidates.append(c)

        client = self._get_client()
        for cand in candidates:
            try:
                # 连接成功即视为可达（404/307 等也说明服务监听中），连接异常才算不可达
                await client.get(cand)
                if cand != base:
                    logger.warning("LLM base_url fallback %s -> %s", base, cand)
                self._resolved_base_url = cand
                return cand
            except httpx.HTTPStatusError:
                pass  # 有响应即可达
            except Exception as e:
                logger.info("LLM candidate %s unreachable: %s", cand, str(e)[:80])

        # 全部不可达，退回原配置（由调用方做降级处理）
        self._resolved_base_url = base
        return base

    def _get_client(self) -> httpx.AsyncClient:
        """获取复用的 httpx 客户端（连接池）"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
                headers={"Authorization": f"Bearer {self.api_key}"}
                if self.api_key and self.api_key != "EMPTY" else {},
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
        initial_delay = 1.0
        max_delay = 30.0
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await self._do_chat(messages, **kwargs)
            except httpx.HTTPStatusError as e:
                # 4xx（除 429）不可恢复，直接抛出
                if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                    logger.error(
                        "LLM client error %d: %s",
                        e.response.status_code, e.response.text[:200],
                    )
                    raise
                last_exc = e
            except (httpx.ReadTimeout, httpx.ConnectError) as e:
                last_exc = e

            if attempt == self.max_retries:
                logger.error(
                    "LLM chat failed after %d attempts: %s",
                    self.max_retries + 1, last_exc,
                )
                raise last_exc  # type: ignore[misc]

            delay = min(initial_delay * (2 ** attempt), max_delay)
            logger.warning(
                "LLM chat attempt %d/%d failed (%s), retrying in %.1fs",
                attempt + 1, self.max_retries + 1,
                type(last_exc).__name__, delay,
            )
            await asyncio.sleep(delay)

        raise last_exc  # type: ignore[misc]

    async def _do_chat(self, messages: list[dict], **kwargs) -> dict:
        """执行单次 LLM 请求"""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            **kwargs,
        }
        client = self._get_client()
        base = await self._resolve_base_url()
        response = await client.post(
            f"{base}/chat/completions",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        """关闭客户端连接池"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


# 模块级单例
llm_client = LLMClient()