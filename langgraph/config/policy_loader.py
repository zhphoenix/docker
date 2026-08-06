"""Policy Center - 策略配置加载与热更新"""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

POLICIES_FILE = Path(__file__).parent / "policies.yaml"
AGENTS_FILE = Path(__file__).parent / "agents.yaml"
WORKFLOWS_FILE = Path(__file__).parent / "workflows.yaml"
PRICING_FILE = Path(__file__).parent / "pricing.yaml"

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


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """加载一个 YAML 配置文件（文件缺失时返回空 dict）"""
    if not path.exists():
        logger.warning("%s not found, returning empty config", path.name)
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_agents_registry() -> dict[str, dict]:
    """获取 Agent 注册表（来自 agents.yaml）

    Returns:
        {agent_name: {"module": str, "class": str, "description": str}, ...}
    """
    return _load_yaml_file(AGENTS_FILE).get("agents", {})


def get_workflows_registry() -> dict[str, dict]:
    """获取 Workflows 注册表（来自 workflows.yaml）

    Returns:
        {workflow_name: {"module": str, "builder": str, "description": str}, ...}
    """
    return _load_yaml_file(WORKFLOWS_FILE).get("workflows", {})


def get_agent_price(agent_id: str) -> dict:
    """获取 Agent 的 LLM 计价配置（来自 pricing.yaml，AC-P3-3）

    未配置的 agent 回退到 default（单价 0 → 成本估算置 0）。

    Returns:
        {"input_per_mtok": float, "output_per_mtok": float}
    """
    pricing = _load_yaml_file(PRICING_FILE).get("pricing", {})
    agents = pricing.get("agents", {})
    price = agents.get(agent_id) if isinstance(agents, dict) else None
    if not isinstance(price, dict):
        price = pricing.get("default", {})
    return {
        "input_per_mtok": float(price.get("input_per_mtok", 0.0) or 0.0),
        "output_per_mtok": float(price.get("output_per_mtok", 0.0) or 0.0),
    }
