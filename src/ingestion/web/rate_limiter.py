"""弹性抓取 — 域名级速率限制模块

基于 Crawl4AI 集成设计规范 第18.2节 Phase 1:
- 令牌桶算法实现域名级限速
- 支持全局默认 + 按域名覆盖
- 异步安全（asyncio.Lock）

用法:
    limiter = RateLimiter.from_config(config_dict)

    # 在请求前等待
    await limiter.acquire("cninfo.com.cn")

    # 或检查是否可立即请求
    if limiter.can_acquire("sec.gov"):
        ...
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_RPM = 60  # 每分钟请求数


@dataclass
class TokenBucket:
    """令牌桶"""

    capacity: float          # 桶容量（最大令牌数）
    refill_rate: float       # 每秒补充令牌数
    tokens: float = 0.0      # 当前令牌数
    last_refill: float = 0.0  # 上次补充时间

    def __post_init__(self):
        if self.tokens == 0.0:
            self.tokens = self.capacity
        if self.last_refill == 0.0:
            self.last_refill = time.monotonic()

    def refill(self) -> None:
        """补充令牌"""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    def can_acquire(self, tokens: float = 1.0) -> bool:
        """检查是否可以获取令牌"""
        self.refill()
        return self.tokens >= tokens

    def acquire(self, tokens: float = 1.0) -> float:
        """获取令牌，返回需要等待的时间（秒）"""
        self.refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return 0.0
        # 计算需要等待的时间
        deficit = tokens - self.tokens
        wait_time = deficit / self.refill_rate
        return wait_time

    def force_acquire(self, tokens: float = 1.0) -> None:
        """强制获取令牌（等待后扣减）"""
        self.refill()
        self.tokens -= tokens


class RateLimiter:
    """域名级速率限制器"""

    def __init__(
        self,
        default_rpm: int = DEFAULT_RPM,
        per_domain: dict[str, int] | None = None,
    ):
        """
        Args:
            default_rpm: 默认每分钟请求数
            per_domain: 按域名覆盖的 RPM 配置
        """
        self.default_rpm = default_rpm
        self.per_domain = per_domain or {}
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "RateLimiter":
        """从 crawl4ai.yaml 的 rate_limit 段构建"""
        rl_cfg = config.get("rate_limit", {})
        return cls(
            default_rpm=rl_cfg.get("default_rpm", DEFAULT_RPM),
            per_domain=rl_cfg.get("per_domain", {}),
        )

    def get_rpm(self, domain: str) -> int:
        """获取指定域名的 RPM 限制"""
        return self.per_domain.get(domain, self.default_rpm)

    def _get_bucket(self, domain: str) -> TokenBucket:
        """获取或创建域名的令牌桶"""
        if domain not in self._buckets:
            rpm = self.get_rpm(domain)
            # 令牌桶容量 = RPM（允许突发），补充速率 = RPM / 60
            self._buckets[domain] = TokenBucket(
                capacity=float(rpm),
                refill_rate=rpm / 60.0,
            )
            logger.debug(f"创建令牌桶: {domain} -> {rpm} RPM")
        return self._buckets[domain]

    def can_acquire(self, domain: str) -> bool:
        """检查是否可以立即请求（非阻塞）"""
        bucket = self._get_bucket(domain)
        return bucket.can_acquire()

    async def acquire(self, domain: str) -> float:
        """获取请求许可（异步等待）

        Args:
            domain: 目标域名

        Returns:
            实际等待时间（秒）
        """
        async with self._lock:
            bucket = self._get_bucket(domain)
            wait_time = bucket.acquire()

        if wait_time > 0:
            logger.debug(f"限速等待: {domain} -> {wait_time:.2f}s")
            await asyncio.sleep(wait_time)
            # 等待后扣减令牌
            async with self._lock:
                bucket.force_acquire()

        return wait_time

    @staticmethod
    def extract_domain(url: str) -> str:
        """从 URL 提取域名"""
        parsed = urlparse(url)
        return parsed.netloc or parsed.path.split("/")[0]

    def get_stats(self) -> dict[str, dict[str, Any]]:
        """获取所有域名的限速统计"""
        stats = {}
        for domain, bucket in self._buckets.items():
            bucket.refill()
            stats[domain] = {
                "rpm_limit": self.get_rpm(domain),
                "available_tokens": round(bucket.tokens, 2),
                "capacity": bucket.capacity,
            }
        return stats

    def __repr__(self) -> str:
        return (
            f"RateLimiter(default_rpm={self.default_rpm}, "
            f"domains={list(self.per_domain.keys())}, "
            f"active_buckets={len(self._buckets)})"
        )
