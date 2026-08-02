"""弹性抓取 — 重试策略模块

基于 Crawl4AI 集成设计规范 第18.2节 Phase 1:
- 指数退避重试
- 可重试状态码判定
- 死信检测
- 域名级配置覆盖

用法:
    policy = RetryPolicy.from_config(config_dict)
    policy = policy.with_domain_override("cninfo.com.cn", {"max_attempts": 5})

    if policy.should_retry(status_code=429, attempt=2):
        wait = policy.get_backoff_delay(attempt=2)
        await asyncio.sleep(wait)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_BASE = 2
DEFAULT_BACKOFF_MAX = 60
DEFAULT_RETRY_ON_STATUS = [429, 500, 502, 503, 504]
DEFAULT_DEAD_LETTER_AFTER = 5


@dataclass
class RetryPolicy:
    """重试策略配置与计算"""

    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    backoff_base: int = DEFAULT_BACKOFF_BASE
    backoff_max: int = DEFAULT_BACKOFF_MAX
    retry_on_status: list[int] = field(default_factory=lambda: DEFAULT_RETRY_ON_STATUS.copy())
    dead_letter_after: int = DEFAULT_DEAD_LETTER_AFTER

    # 域名级覆盖（domain -> override dict）
    domain_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "RetryPolicy":
        """从 crawl4ai.yaml 的 retry 段构建"""
        retry_cfg = config.get("retry", {})
        return cls(
            max_attempts=retry_cfg.get("max_attempts", DEFAULT_MAX_ATTEMPTS),
            backoff_base=retry_cfg.get("backoff_base", DEFAULT_BACKOFF_BASE),
            backoff_max=retry_cfg.get("backoff_max", DEFAULT_BACKOFF_MAX),
            retry_on_status=retry_cfg.get("retry_on_status", DEFAULT_RETRY_ON_STATUS.copy()),
            dead_letter_after=retry_cfg.get("dead_letter_after", DEFAULT_DEAD_LETTER_AFTER),
        )

    def with_domain_override(self, domain: str, override: dict[str, Any]) -> "RetryPolicy":
        """注册域名级配置覆盖"""
        self.domain_overrides[domain] = override
        return self

    def get_effective_config(self, domain: str | None = None) -> dict[str, Any]:
        """获取指定域名的有效配置（全局 + 覆盖）"""
        effective = {
            "max_attempts": self.max_attempts,
            "backoff_base": self.backoff_base,
            "backoff_max": self.backoff_max,
            "retry_on_status": self.retry_on_status,
            "dead_letter_after": self.dead_letter_after,
        }
        if domain and domain in self.domain_overrides:
            override = self.domain_overrides[domain]
            effective.update(override)
            logger.debug(f"域名 {domain} 使用覆盖配置: {override}")
        return effective

    def should_retry(self, status_code: int | None, attempt: int, domain: str | None = None) -> bool:
        """判断是否应该重试

        Args:
            status_code: HTTP 状态码（None 表示网络错误）
            attempt: 当前尝试次数（从 1 开始）
            domain: 目标域名（用于获取覆盖配置）

        Returns:
            是否应该重试
        """
        cfg = self.get_effective_config(domain)

        # 超过最大尝试次数
        if attempt >= cfg["max_attempts"]:
            logger.info(f"已达最大重试次数 {cfg['max_attempts']}，停止重试")
            return False

        # 网络错误（无状态码）始终重试
        if status_code is None:
            return True

        # 检查状态码是否在可重试列表
        return status_code in cfg["retry_on_status"]

    def get_backoff_delay(self, attempt: int, domain: str | None = None) -> float:
        """计算指数退避延迟（秒）

        公式: min(backoff_base ^ attempt, backoff_max)

        Args:
            attempt: 当前尝试次数（从 1 开始）
            domain: 目标域名

        Returns:
            延迟秒数
        """
        cfg = self.get_effective_config(domain)
        delay = min(cfg["backoff_base"] ** attempt, cfg["backoff_max"])
        return float(delay)

    def get_next_retry_time(self, attempt: int, domain: str | None = None) -> datetime:
        """计算下次重试时间（UTC）"""
        delay = self.get_backoff_delay(attempt, domain)
        return datetime.now(timezone.utc) + timedelta(seconds=delay)

    def is_dead_letter(self, total_failures: int, domain: str | None = None) -> bool:
        """判断是否应标记为死信

        Args:
            total_failures: 累计失败次数
            domain: 目标域名

        Returns:
            是否应标记为 dead
        """
        cfg = self.get_effective_config(domain)
        return total_failures >= cfg["dead_letter_after"]

    def __repr__(self) -> str:
        return (
            f"RetryPolicy(max_attempts={self.max_attempts}, "
            f"backoff_base={self.backoff_base}, "
            f"backoff_max={self.backoff_max}, "
            f"dead_letter_after={self.dead_letter_after}, "
            f"domain_overrides={list(self.domain_overrides.keys())})"
        )
