"""Chunker - Markdown 文本分片工具

策略:
  - 按标题层级切分（## / ### 作为自然分界）
  - 超长段落按 chunk_size 滑动窗口切分
  - 保留 overlap 确保上下文连贯
  - 每个 chunk 携带 heading 元数据
"""

import re
import logging

from config.policy_loader import get_policy

logger = logging.getLogger(__name__)


def chunk_markdown(
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[dict]:
    """将 Markdown 文本分片

    Args:
        text: Markdown 全文
        chunk_size: 每片最大字符数（默认从 policy 读取）
        chunk_overlap: 重叠字符数

    Returns:
        [{"content": str, "heading": str, "chunk_index": int}, ...]
    """
    if chunk_size is None:
        chunk_size = get_policy("pipeline.chunk_size", 1000)
    if chunk_overlap is None:
        chunk_overlap = get_policy("pipeline.chunk_overlap", 200)

    if not text or not text.strip():
        return []

    # 按标题切分为 sections
    sections = _split_by_headings(text)

    chunks: list[dict] = []
    idx = 0

    for heading, content in sections:
        content = content.strip()
        if not content:
            continue

        # 如果 section 短于 chunk_size，直接作为一个 chunk
        if len(content) <= chunk_size:
            chunks.append({
                "content": content,
                "heading": heading,
                "chunk_index": idx,
            })
            idx += 1
        else:
            # 长文本滑动窗口切分
            sub_chunks = _sliding_window(content, chunk_size, chunk_overlap)
            for sc in sub_chunks:
                chunks.append({
                    "content": sc,
                    "heading": heading,
                    "chunk_index": idx,
                })
                idx += 1

    logger.debug("Chunked: %d chars → %d chunks", len(text), len(chunks))
    return chunks


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    """按 Markdown 标题切分

    Returns:
        [(heading, content), ...]
    """
    # 匹配 ## 或 ### 级别标题
    pattern = re.compile(r"^(#{1,3}\s+.+)$", re.MULTILINE)
    parts = pattern.split(text)

    sections: list[tuple[str, str]] = []
    current_heading = ""

    for part in parts:
        if pattern.match(part):
            current_heading = part.strip().lstrip("#").strip()
        else:
            if part.strip():
                sections.append((current_heading, part))

    # 如果没有任何标题，整体作为一个 section
    if not sections and text.strip():
        sections.append(("", text))

    return sections


def _sliding_window(text: str, size: int, overlap: int) -> list[str]:
    """滑动窗口切分长文本

    优先在段落/句子边界切分。
    """
    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + size

        if end >= text_len:
            chunks.append(text[start:])
            break

        # 尝试在段落边界切分
        cut = _find_cut_point(text, start, end)
        chunks.append(text[start:cut])
        start = cut - overlap

    return chunks


def _find_cut_point(text: str, start: int, end: int) -> int:
    """在 [start, end] 范围内找到最佳切分点

    优先级: 段落(\n\n) > 换行(\n) > 句号 > 空格
    """
    # 从 end 向前搜索
    search_start = max(start + (end - start) // 2, start)

    # 段落边界
    pos = text.rfind("\n\n", search_start, end)
    if pos > search_start:
        return pos + 2

    # 换行
    pos = text.rfind("\n", search_start, end)
    if pos > search_start:
        return pos + 1

    # 中文句号 / 英文句号
    for sep in ("。", ".", "！", "？", "；"):
        pos = text.rfind(sep, search_start, end)
        if pos > search_start:
            return pos + 1

    # 空格
    pos = text.rfind(" ", search_start, end)
    if pos > search_start:
        return pos + 1

    return end
