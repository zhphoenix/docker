"""Prompt Loader - 统一加载 prompts/ 目录下的 .md 模板文件"""

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# prompts 目录路径（相对于 agent/ 目录）
PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str, **kwargs) -> str:
    """加载 Prompt 模板

    Args:
        name: Prompt 名称（不含 .md 后缀），如 "planner", "reason"
        **kwargs: 模板变量替换，如 question="...", context="..."

    Returns:
        替换变量后的 Prompt 文本
    """
    prompt_file = PROMPTS_DIR / f"{name}.md"

    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

    content = prompt_file.read_text(encoding="utf-8")

    # 变量替换
    if kwargs:
        content = content.format(**kwargs)

    logger.debug("Loaded prompt '%s' (%d chars)", name, len(content))
    return content
