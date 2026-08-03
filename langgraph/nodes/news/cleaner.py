"""Node 1: News Cleaner — 语言检测 + 清洗 + 标准化

职责：
- 检测文章语言（zh/en）
- 清洗 HTML 标签、多余空白
- 计算 content_hash（SHA-256，供去重使用）
- 过滤过短/无效文章
"""

import hashlib
import logging
import re

logger = logging.getLogger(__name__)

# 简单语言检测：中文字符占比 > 30% → zh
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_HTML_PATTERN = re.compile(r"<[^>]+>")
_WHITESPACE_PATTERN = re.compile(r"\s+")

MIN_CONTENT_LENGTH = 50


def _detect_language(text: str) -> str:
    """简单语言检测"""
    if not text:
        return "unknown"
    cjk_chars = len(_CJK_PATTERN.findall(text[:500]))
    total_chars = min(len(text), 500)
    if total_chars > 0 and cjk_chars / total_chars > 0.3:
        return "zh"
    return "en"


def _clean_content(text: str) -> str:
    """清洗内容：去 HTML、规范化空白"""
    if not text:
        return ""
    text = _HTML_PATTERN.sub("", text)
    text = _WHITESPACE_PATTERN.sub(" ", text)
    return text.strip()


def _content_hash(title: str, content: str) -> str:
    """计算内容指纹（SHA-256）"""
    raw = f"{title.strip().lower()}|{content[:500].strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def news_cleaner(state: dict) -> dict:
    """新闻清洗节点

    输入: raw_articles
    输出: cleaned_articles（含 language, content_hash）
    """
    raw_articles = state.get("raw_articles", [])
    new_errors: list[str] = []

    if not raw_articles:
        new_errors.append("Cleaner: no raw articles to process")
        return {"cleaned_articles": [], "errors": new_errors}

    cleaned = []
    for i, article in enumerate(raw_articles):
        title = (article.get("title") or "").strip()
        content = _clean_content(article.get("content", ""))

        # 过滤无效文章
        if not title:
            continue
        if len(content) < MIN_CONTENT_LENGTH and len(title) < 10:
            continue

        language = _detect_language(title + " " + content[:200])
        content_hash = _content_hash(title, content)

        cleaned.append({
            **article,
            "title": title,
            "content": content,
            "language": language,
            "content_hash": content_hash,
            "article_idx": i,
        })

    logger.info("Cleaner: %d/%d articles passed cleaning", len(cleaned), len(raw_articles))

    return {"cleaned_articles": cleaned, "errors": new_errors}
