"""Crawl4AI Provider — Web 抓取提供者

基于 Crawl4AI 集成设计规范:
- 第12节: Provider 规范（Agent 仅调用 Provider）
- 第18.2节: Phase 1 弹性抓取（集成重试 + 限速）

职责:
- 封装 Crawl4AI HTTP API 调用
- 集成 RetryPolicy（指数退避）
- 集成 RateLimiter（域名级限速）
- 返回标准化 CrawlResult

用法:
    provider = Crawl4AIProvider.from_config(config)
    result = await provider.fetch("https://www.cninfo.com.cn/...")

    if result.success:
        markdown = result.markdown
    else:
        print(result.error)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml

from ingestion.web.rate_limiter import RateLimiter
from ingestion.web.retry import RetryPolicy

logger = logging.getLogger(__name__)


@dataclass
class CrawlResult:
    """抓取结果"""

    url: str
    success: bool
    status_code: int | None = None
    title: str | None = None
    markdown: str | None = None
    content_hash: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    error: str | None = None
    attempts: int = 0
    crawl_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc


class Crawl4AIProvider:
    """Crawl4AI 抓取提供者

    封装 Crawl4AI 服务调用，集成重试和限速。
    Agent 和 Pipeline 通过此 Provider 抓取网页，不直接调用 Crawl4AI。
    """

    def __init__(
        self,
        base_url: str = "http://crawl4ai:11235",
        timeout: int = 60,
        api_token: str | None = None,
        retry_policy: RetryPolicy | None = None,
        rate_limiter: RateLimiter | None = None,
        proxy_pool: list[str] | None = None,
    ):
        """
        Args:
            base_url: Crawl4AI 服务地址
            timeout: 请求超时（秒）
            api_token: Crawl4AI API Token（设置后服务需要 Bearer 认证）
            retry_policy: 重试策略
            rate_limiter: 速率限制器
            proxy_pool: 代理池（可选）
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_token = api_token
        self.retry_policy = retry_policy or RetryPolicy()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.proxy_pool = proxy_pool or []
        self._client: httpx.AsyncClient | None = None

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "Crawl4AIProvider":
        """从 crawl4ai.yaml 配置构建"""
        services = config.get("services", {})
        c4ai_cfg = services.get("crawl4ai", {})

        # 构建重试策略
        retry_policy = RetryPolicy.from_config(config)

        # 构建速率限制器
        rate_limiter = RateLimiter.from_config(config)

        # 代理配置
        proxy_cfg = config.get("proxy", {})
        proxy_pool = proxy_cfg.get("pool", []) if proxy_cfg.get("enabled") else []

        return cls(
            base_url=c4ai_cfg.get("url", "http://crawl4ai:11235"),
            timeout=c4ai_cfg.get("timeout", 60),
            api_token=c4ai_cfg.get("api_token"),
            retry_policy=retry_policy,
            rate_limiter=rate_limiter,
            proxy_pool=proxy_pool,
        )

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "Crawl4AIProvider":
        """从 YAML 文件加载配置"""
        with open(yaml_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return cls.from_config(config)

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            headers = {}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers=headers,
            )
        return self._client

    async def fetch(self, url: str, **kwargs) -> CrawlResult:
        """抓取单个 URL（带重试和限速）

        Args:
            url: 目标 URL
            **kwargs: 额外参数传递给 Crawl4AI

        Returns:
            CrawlResult 抓取结果
        """
        domain = urlparse(url).netloc
        attempt = 0
        last_error: str | None = None
        last_status: int | None = None

        while True:
            attempt += 1

            # 速率限制
            await self.rate_limiter.acquire(domain)

            try:
                result = await self._do_crawl(url, **kwargs)

                # 成功
                if result.success:
                    result.attempts = attempt
                    logger.info(f"抓取成功: {url} (尝试 {attempt} 次)")
                    return result

                # 失败但可重试
                last_status = result.status_code
                last_error = result.error

                if not self.retry_policy.should_retry(last_status, attempt, domain):
                    result.attempts = attempt
                    logger.warning(f"抓取失败（不重试）: {url} -> {last_status}")
                    return result

            except httpx.TimeoutException as e:
                last_error = f"Timeout: {e}"
                last_status = None
                logger.warning(f"抓取超时: {url} (尝试 {attempt})")

                if not self.retry_policy.should_retry(None, attempt, domain):
                    return CrawlResult(
                        url=url,
                        success=False,
                        error=last_error,
                        attempts=attempt,
                    )

            except Exception as e:
                last_error = f"Error: {e}"
                last_status = None
                logger.error(f"抓取异常: {url} -> {e}")

                if not self.retry_policy.should_retry(None, attempt, domain):
                    return CrawlResult(
                        url=url,
                        success=False,
                        error=last_error,
                        attempts=attempt,
                    )

            # 等待后重试
            delay = self.retry_policy.get_backoff_delay(attempt, domain)
            logger.info(f"等待 {delay:.1f}s 后重试: {url} (尝试 {attempt})")
            await asyncio.sleep(delay)

    async def _do_crawl(self, url: str, **kwargs) -> CrawlResult:
        """执行实际的 Crawl4AI API 调用"""
        client = await self._get_client()

        # Crawl4AI API 请求体（urls 必须为列表）
        payload = {
            "urls": [url],
            "priority": 8,
            **kwargs,
        }

        response = await client.post("/crawl", json=payload)

        if response.status_code != 200:
            return CrawlResult(
                url=url,
                success=False,
                status_code=response.status_code,
                error=f"HTTP {response.status_code}: {response.text[:200]}",
            )

        data = response.json()

        # Crawl4AI 响应格式: {"success": bool, "results": [...]}
        results = data.get("results", [])
        if not results:
            return CrawlResult(
                url=url,
                success=False,
                error="Empty results from Crawl4AI",
            )

        result = results[0]

        # 解析单个 URL 结果
        if not result.get("success", False):
            return CrawlResult(
                url=url,
                success=False,
                status_code=result.get("status_code"),
                error=result.get("error_message", "Unknown error"),
            )

        # 提取 Markdown 内容（markdown 为 dict，包含 raw_markdown 等）
        md_obj = result.get("markdown", {})
        if isinstance(md_obj, dict):
            markdown = md_obj.get("raw_markdown", "") or md_obj.get("fit_markdown", "")
        else:
            markdown = md_obj or ""

        title = result.get("metadata", {}).get("title", "")

        # 计算内容 Hash
        content_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest() if markdown else None

        # 提取响应头
        resp_headers = result.get("response_headers", {}) or {}

        return CrawlResult(
            url=url,
            success=True,
            status_code=result.get("status_code", 200),
            title=title,
            markdown=markdown,
            content_hash=content_hash,
            etag=resp_headers.get("etag"),
            last_modified=resp_headers.get("last-modified"),
            metadata=result.get("metadata", {}),
        )

    async def fetch_batch(self, urls: list[str], concurrency: int = 3, **kwargs) -> list[CrawlResult]:
        """批量抓取（带并发控制）

        Args:
            urls: URL 列表
            concurrency: 最大并发数
            **kwargs: 额外参数

        Returns:
            CrawlResult 列表
        """
        semaphore = asyncio.Semaphore(concurrency)
        results: list[CrawlResult] = [None] * len(urls)  # type: ignore

        async def _fetch_one(idx: int, url: str):
            async with semaphore:
                results[idx] = await self.fetch(url, **kwargs)

        await asyncio.gather(*[_fetch_one(i, u) for i, u in enumerate(urls)])
        return results

    async def health_check(self) -> bool:
        """检查 Crawl4AI 服务健康状态"""
        try:
            client = await self._get_client()
            response = await client.get("/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Crawl4AI 健康检查失败: {e}")
            return False

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def __repr__(self) -> str:
        return (
            f"Crawl4AIProvider(base_url={self.base_url}, "
            f"retry={self.retry_policy}, "
            f"rate_limiter={self.rate_limiter})"
        )
