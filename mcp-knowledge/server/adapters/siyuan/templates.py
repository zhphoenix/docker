"""Jinja2 模板渲染 — 知识对象 → Markdown 文档

遵循设计红线：页面由模板渲染，非 LLM 拼接。模板定义在
server/adapters/siyuan/templates/ 目录（company.md / industry.md / event.md）。

渲染输入为 mapper 产出的统一上下文，输出为 SiYuan Markdown 文档。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

logger = logging.getLogger(__name__)

# 默认模板目录（本文件同目录下 templates/）
_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

# 对象类型 → 模板文件名
_TEMPLATE_MAP: dict[str, str] = {
    "Company": "company.md",
    "Industry": "industry.md",
    "Event": "event.md",
    "default": "default.md",
}


class TemplateRenderer:
    """Jinja2 模板渲染器"""

    def __init__(self, template_dir: str | Path | None = None):
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir or _TEMPLATE_DIR)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
        # 注册通用过滤器
        self._env.filters["pct"] = lambda v: f"{v * 100:.0f}%" if isinstance(v, (int, float)) else str(v)
        self._env.filters["conf"] = lambda v: f"{v * 100:.0f}%" if isinstance(v, (int, float)) else str(v)

    def template_name(self, object_type: str) -> str:
        """对象类型 → 模板文件名（带兜底）"""
        return _TEMPLATE_MAP.get(object_type, _TEMPLATE_MAP["default"])

    def render(self, object_type: str, context: dict[str, Any]) -> str:
        """渲染完整文档 Markdown"""
        name = self.template_name(object_type)
        try:
            tmpl = self._env.get_template(name)
        except TemplateNotFound:
            logger.warning("template %s not found, fallback to default", name)
            tmpl = self._env.get_template(_TEMPLATE_MAP["default"])
        return tmpl.render(**context)

    def render_section(self, section: str, context: dict[str, Any]) -> str:
        """渲染单个 Section 的 Markdown（增量更新用）"""
        # 约定：section 模板文件名为 <section>.md（如 financial.md）
        try:
            tmpl = self._env.get_template(f"{section.lower()}.md")
        except TemplateNotFound:
            # 兜底：用通用 section 模板
            tmpl = self._env.get_template("section.md")
        return tmpl.render(section=section, **context)


# 模块级单例
renderer = TemplateRenderer()

# 供 __init__.py 暴露的便捷入口
render_templates = renderer.render