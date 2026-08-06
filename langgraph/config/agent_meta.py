"""Agent 元数据加载 - 读取 config/agent_meta.yaml（展示与依赖信息）"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

META_FILE = Path(__file__).resolve().parent / "agent_meta.yaml"

_cache: dict | None = None


def get_agent_meta(name: str | None = None) -> dict:
    """获取全部 Agent 元数据；name 省略时返回整个 meta 字典"""
    global _cache
    if _cache is None:
        meta = {}
        if META_FILE.exists():
            try:
                import yaml
                with open(META_FILE, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                meta = data.get("meta", {})
            except Exception as e:
                logger.warning("Failed to load agent_meta.yaml: %s", e)
        _cache = meta
    if name is None:
        return _cache
    return _cache.get(name, {})


def reload() -> None:
    """清空缓存，下次调用重新读文件（热更新用）"""
    global _cache
    _cache = None