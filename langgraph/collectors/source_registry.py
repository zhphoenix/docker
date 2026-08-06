"""Source Registry — 新闻源配置加载器

从 registry/news_sources.yaml 加载新闻源配置。
支持按 priority 过滤和排序。
"""

import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# 项目根目录（.../langgraph/collectors/source_registry.py → 上溯 3 层到项目根）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY_PATH = _PROJECT_ROOT / "registry" / "news_sources.yaml"


class NewsSource:
    """单个新闻源配置"""

    def __init__(self, data: dict, defaults: dict):
        self.id: str = data["id"]
        self.name: str = data.get("name", self.id)
        self.source_type: str = data["source_type"]  # rss / crawler / api
        self.category: list[str] = data.get("category", [])
        self.market: list[str] = data.get("market", [])
        self.priority: str = data.get("priority", "normal")
        self.config: dict = data.get("config", {})
        self.enabled: bool = data.get("enabled", defaults.get("enabled", True))

    def __repr__(self):
        return f"NewsSource(id={self.id!r}, type={self.source_type!r}, priority={self.priority!r})"


class SourceRegistry:
    """新闻源注册表"""

    def __init__(self, registry_path: Optional[Path] = None):
        self._path = registry_path or _REGISTRY_PATH
        self._sources: list[NewsSource] = []
        self._defaults: dict = {}
        self._schedule: dict = {}
        self._loaded = False

    def load(self) -> None:
        """加载 YAML 配置"""
        if not self._path.exists():
            logger.warning("News sources registry not found: %s", self._path)
            self._loaded = True
            return

        with open(self._path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self._defaults = data.get("defaults", {})
        self._schedule = data.get("schedule", {})

        for item in data.get("sources", []):
            self._sources.append(NewsSource(item, self._defaults))

        self._loaded = True
        logger.info(
            "Loaded %d news sources (%d enabled)",
            len(self._sources),
            sum(1 for s in self._sources if s.enabled),
        )

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def get_enabled(self, priority: Optional[str] = None, source_type: Optional[str] = None) -> list[NewsSource]:
        """获取已启用的新闻源（可按 priority/type 过滤）"""
        self._ensure_loaded()
        results = [s for s in self._sources if s.enabled]

        if priority:
            results = [s for s in results if s.priority == priority]
        if source_type:
            results = [s for s in results if s.source_type == source_type]

        # 按优先级排序: high > normal > low
        priority_order = {"high": 0, "normal": 1, "low": 2}
        results.sort(key=lambda s: priority_order.get(s.priority, 1))
        return results

    def get_by_id(self, source_id: str) -> Optional[NewsSource]:
        """按 ID 获取新闻源"""
        self._ensure_loaded()
        for s in self._sources:
            if s.id == source_id:
                return s
        return None

    def set_enabled(self, source_id: str, enabled: bool) -> bool:
        """启停一个新闻源（更新内存 + 持久化到 YAML）

        返回 True 表示找到并更新成功；False 表示源不存在。
        """
        self._ensure_loaded()
        target = None
        for s in self._sources:
            if s.id == source_id:
                target = s
                break
        if target is None:
            return False
        target.enabled = enabled
        return self._persist_enabled(source_id, enabled)

    def _persist_enabled(self, source_id: str, enabled: bool) -> bool:
        """逐行改写 YAML 中对应源的 enabled 字段，保留注释与格式"""
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines(keepends=True)
        except OSError:
            logger.error("Cannot read registry: %s", self._path)
            return False

        in_block = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("- id:"):
                sid = stripped.split(":", 1)[1].strip().strip("'\"")
                in_block = sid == source_id
                continue
            if in_block:
                # 当前 source 块结束：遇到另一个列表项或顶层键
                if stripped.startswith("- ") or (line and not line[0].isspace()):
                    break
                if stripped.startswith("enabled:"):
                    indent = line[: len(line) - len(line.lstrip())]
                    value = "true" if enabled else "false"
                    lines[i] = f"{indent}enabled: {value}\n"
                    try:
                        self._path.write_text("".join(lines), encoding="utf-8")
                    except OSError:
                        logger.error("Cannot write registry: %s", self._path)
                        return False
                    logger.info("Source %r enabled=%s persisted", source_id, enabled)
                    return True

        logger.warning("enabled field not found for source %r", source_id)
        return False

    @property
    def schedule(self) -> dict:
        """调度配置"""
        self._ensure_loaded()
        return self._schedule


# 模块级单例
source_registry = SourceRegistry()
