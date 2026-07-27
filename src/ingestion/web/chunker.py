"""Web Markdown 分块器

基于 Crawl4AI 集成设计规范 第10节:
- 按 Markdown 标题层级切分
- 超长段落二次切分（滑动窗口）
- 保留标题上下文（面包屑）

用法:
    chunker = WebChunker(max_chars=800, overlap_chars=100)
    chunks = chunker.chunk(markdown_text)

    for c in chunks:
        print(c.heading, c.content[:50])
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ──────────────────────────────────────────────
# 内容清洗：过滤导航/页脚/链接噪音
# ──────────────────────────────────────────────

# 匹配“纯链接行”（行内 >70% 是 Markdown 链接语法）
_LINK_LINE_RE = re.compile(r"\[([^\]]*)\]\([^)]+\)")

# 导航/页脚标记词
_NAV_MARKERS = [
    "skip to content", "sign in", "sign up", "menu", "search this site",
    "close", "the python network", "font size", "socialize",
    "copyright", "all rights reserved", "privacy policy", "terms of use",
    "powered by", "back to top",
    # 求是网噪音
    "来源：求是网", "责任编辑", "分享到", "相关阅读", "上一篇", "下一篇",
]


def clean_markdown(raw: str) -> str:
    """清洗原始 Markdown，移除导航/页脚/链接噪音

    策略:
        1. 找到第一个 Markdown 标题（# ）作为内容起点
        2. 移除末尾页脚（Copyright / Powered by 等标记后）
        3. 过滤纯导航链接行（链接占比 >70%）
        4. 移除连续空行 > 2
    """
    if not raw:
        return ""

    lines = raw.split("\n")

    # 1. 找内容起点（第一个 # 标题）
    start_idx = 0
    for i, line in enumerate(lines):
        if re.match(r"^#{1,3}\s+\S", line):
            start_idx = i
            break

    # 2. 找页脚起点
    end_idx = len(lines)
    for i in range(len(lines) - 1, start_idx, -1):
        lower = lines[i].lower().strip()
        if any(marker in lower for marker in ["copyright", "all rights reserved", "powered by"]):
            end_idx = i
            break

    # 3. 过滤导航链接行
    cleaned_lines: list[str] = []
    consecutive_nav = 0  # 连续导航行计数

    for line in lines[start_idx:end_idx]:
        stripped = line.strip()

        # 空行保留（但限制连续空行）
        if not stripped:
            if consecutive_nav < 3:
                cleaned_lines.append("")
            continue

        # 检查是否为导航标记
        lower = stripped.lower()
        if any(marker in lower for marker in _NAV_MARKERS):
            consecutive_nav += 1
            continue

        # 检查是否为纯链接行（链接字符占比 > 70%）
        if _is_nav_link_line(stripped):
            consecutive_nav += 1
            # 允许少量链接行（可能是内容中的引用）
            if consecutive_nav <= 2:
                cleaned_lines.append(line)
            continue

        # 正常内容行
        consecutive_nav = 0
        cleaned_lines.append(line)

    # 4. 压缩连续空行
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned_lines))
    return result.strip()


def _is_nav_link_line(line: str) -> bool:
    """判断一行是否为导航链接（链接语法占比 > 60%）"""
    if not line:
        return False

    # 列表项前缀
    content = re.sub(r"^\s*[*\-+]\s*", "", line)

    # 计算链接字符占比
    link_chars = sum(len(m.group(0)) for m in _LINK_LINE_RE.finditer(content))
    total_chars = len(content)

    if total_chars == 0:
        return False

    return (link_chars / total_chars) > 0.6


@dataclass
class Chunk:
    """分块结果"""

    chunk_index: int
    content: str
    heading: str | None = None
    token_count: int | None = None  # 近似估算


@dataclass
class WebChunker:
    """Markdown 按标题分块器

    策略:
        1. 按 ## / ### 标题切分为 section
        2. 每个 section 如果超过 max_chars，用滑动窗口二次切分
        3. 每个 chunk 携带标题面包屑（如 "章节 > 小节"）

    Args:
        max_chars: 单个 chunk 最大字符数
        overlap_chars: 二次切分时的重叠字符数
        min_chars: 过短的 chunk 合并到上一个
    """

    max_chars: int = 800
    overlap_chars: int = 100
    min_chars: int = 50

    # 匹配 Markdown 标题行 (## 或 ###)
    _HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "WebChunker":
        """从 crawl4ai.yaml 配置构建"""
        chunk_cfg = config.get("chunk", {})
        return cls(
            max_chars=chunk_cfg.get("max_chars", 800),
            overlap_chars=chunk_cfg.get("overlap_chars", 100),
            min_chars=chunk_cfg.get("min_chars", 50),
        )

    def chunk(self, markdown: str, auto_clean: bool = True) -> list[Chunk]:
        """将 Markdown 文本分块

        Args:
            markdown: 原始 Markdown 文本
            auto_clean: 是否自动清洗导航/页脚噪音

        Returns:
            Chunk 列表（按顺序）
        """
        if not markdown or not markdown.strip():
            return []

        # 0. 清洗噪音
        if auto_clean:
            markdown = clean_markdown(markdown)
            if not markdown:
                return []

        # 1. 按标题切分为 sections
        sections = self._split_by_headings(markdown)

        # 2. 对每个 section 做大小控制
        chunks: list[Chunk] = []
        idx = 0

        for heading, body in sections:
            body = body.strip()
            if not body:
                continue

            if len(body) <= self.max_chars:
                # 不需要二次切分
                if len(body) < self.min_chars and chunks:
                    # 过短，合并到上一个 chunk
                    prev = chunks[-1]
                    prev.content = prev.content + "\n\n" + body
                    prev.token_count = self._estimate_tokens(prev.content)
                else:
                    chunks.append(Chunk(
                        chunk_index=idx,
                        content=body,
                        heading=heading,
                        token_count=self._estimate_tokens(body),
                    ))
                    idx += 1
            else:
                # 二次切分（滑动窗口）
                sub_chunks = self._sliding_window(body)
                for sc in sub_chunks:
                    chunks.append(Chunk(
                        chunk_index=idx,
                        content=sc,
                        heading=heading,
                        token_count=self._estimate_tokens(sc),
                    ))
                    idx += 1

        return chunks

    def _split_by_headings(self, markdown: str) -> list[tuple[str | None, str]]:
        """按标题切分 Markdown

        Returns:
            [(heading_text, section_body), ...]
            第一个元素 heading 可能为 None（标题前的内容）
        """
        sections: list[tuple[str | None, str]] = []
        last_end = 0
        current_heading: str | None = None

        for match in self._HEADING_RE.finditer(markdown):
            # 标题前的内容
            before = markdown[last_end:match.start()]
            if before.strip():
                sections.append((current_heading, before))

            # 更新当前标题
            level = len(match.group(1))
            title = match.group(2).strip()
            current_heading = title
            last_end = match.end()

        # 最后一段
        remaining = markdown[last_end:]
        if remaining.strip():
            sections.append((current_heading, remaining))

        return sections

    def _sliding_window(self, text: str) -> list[str]:
        """滑动窗口切分超长文本

        优先在段落边界（\\n\\n）切分，退而求其次在句子边界切分。
        """
        if len(text) <= self.max_chars:
            return [text]

        chunks: list[str] = []
        start = 0

        while start < len(text):
            end = start + self.max_chars

            if end >= len(text):
                chunks.append(text[start:])
                break

            # 尝试在段落边界切分
            cut = text.rfind("\n\n", start, end)
            if cut <= start:
                # 尝试在换行处切分
                cut = text.rfind("\n", start, end)
            if cut <= start:
                # 尝试在句号处切分
                for sep in ("。", ". ", "！", "？", "; "):
                    cut = text.rfind(sep, start, end)
                    if cut > start:
                        cut += len(sep)
                        break

            if cut <= start:
                # 硬切
                cut = end

            chunks.append(text[start:cut])
            # 重叠
            start = max(cut - self.overlap_chars, start + 1)

        return chunks

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """近似估算 token 数（中文 ~1.5 tok/char，英文 ~0.25 tok/char）"""
        cn_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        other_chars = len(text) - cn_chars
        return int(cn_chars * 1.5 + other_chars * 0.3)
