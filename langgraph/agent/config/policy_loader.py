"""Policy Center - 策略配置加载与热更新"""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

POLICIES_FILE = Path(__file__).parent / "policies.yaml"

_policies: dict[str, Any] = {}
_last_mtime: float = 0


def _load_policies() -> dict[str, Any]:
    """加载策略配置文件"""
    global _policies, _last_mtime

    if not POLICIES_FILE.exists():
        logger.warning("policies.yaml not found, using defaults")
        return {}

    mtime = POLICIES_FILE.stat().st_mtime
    if mtime != _last_mtime or not _policies:
        with open(POLICIES_FILE, "r", encoding="utf-8") as f:
            _policies = yaml.safe_load(f) or {}
        _last_mtime = mtime
        logger.info("Policies reloaded (mtime=%.0f)", mtime)

    return _policies


def get_policy(path: str, default: Any = None) -> Any:
    """获取策略值（支持点号路径）

    Args:
        path: 策略路径，如 "rate_limit.llm.requests_per_minute"
        default: 默认值

    Examples:
        get_policy("routing.default_agent")  # → "chat"
        get_policy("retry.max_retries", 3)   # → 3
    """
    policies = _load_policies()
    keys = path.split(".")
    current = policies
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


def get_routing_rules() -> list[dict]:
    """获取 Agent 路由规则"""
    return get_policy("routing.rules", [])


def get_rate_limit(service: str) -> dict:
    """获取服务限流配置"""
    return get_policy(f"rate_limit.{service}", {})


def get_retry_config() -> dict:
    """获取重试配置"""
    return get_policy("retry", {
        "max_retries": 3,
        "backoff_multiplier": 2,
        "initial_delay_seconds": 1,
    })
