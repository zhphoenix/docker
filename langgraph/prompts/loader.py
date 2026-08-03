"""Prompt Hub - 统一加载 prompts/ 目录下的 .md 模板文件

目录结构:
  prompts/
  ├── planner.md          # 通用 Planner
  ├── reason.md           # 通用 Reason
  ├── reflect.md          # 通用 Reflect
  ├── writer.md           # 通用 Writer
  ├── chat/system.md      # Chat Agent 专用
  ├── research/system.md  # Research Agent 专用
  └── investment/system.md# Investment Agent 专用

用法:
  load_prompt("planner")                # 加载顶层 planner.md
  load_prompt("chat/system")            # 加载子目录 chat/system.md
  load_prompt("reason", context="...")  # 带变量替换
"""

import logging
from pathlib import Path
from functools import lru_cache

logger = logging.getLogger(__name__)

# prompts 目录路径（相对于 agent/ 目录）
PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=64)
def _read_prompt_file(relative_path: str) -> str:
    """读取并缓存 Prompt 文件原始内容"""
    prompt_file = PROMPTS_DIR / f"{relative_path}.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
    return prompt_file.read_text(encoding="utf-8")


def load_prompt(name: str, **kwargs) -> str:
    """加载 Prompt 模板

    Args:
        name: Prompt 路径（不含 .md 后缀）
              支持子目录: "planner", "chat/system", "research/system"
        **kwargs: 模板变量替换，如 question="...", context="..."

    Returns:
        替换变量后的 Prompt 文本
    """
    content = _read_prompt_file(name)

    # 变量替换（使用安全替换，忽略缺失变量）
    if kwargs:
        for key, value in kwargs.items():
            content = content.replace("{" + key + "}", str(value))

    logger.debug("Loaded prompt '%s' (%d chars)", name, len(content))
    return content


def list_prompts(subdir: str = "") -> list[str]:
    """列出可用的 Prompt 模板

    Args:
        subdir: 子目录名（如 "chat"），空字符串列出顶层

    Returns:
        Prompt 名称列表（不含 .md 后缀）
    """
    target = PROMPTS_DIR / subdir if subdir else PROMPTS_DIR
    if not target.exists():
        return []
    return [f.stem for f in target.glob("*.md")]
