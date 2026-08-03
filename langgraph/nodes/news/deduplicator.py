"""Node 2: News Deduplicator — 两级去重

策略：
- 第一层：content_hash 精确去重（同批次内）
- 第二层：标题相似度去重（简单 Jaccard 相似）

注：Embedding 语义去重（Qdrant）在 Publisher 阶段执行（需要存储后才能比对历史）。
"""

import logging
import re

logger = logging.getLogger(__name__)

# 标题相似度阈值
TITLE_SIMILARITY_THRESHOLD = 0.7

_WORD_PATTERN = re.compile(r"\w+")


def _title_similarity(a: str, b: str) -> float:
    """简单 Jaccard 相似度（词级别）"""
    words_a = set(_WORD_PATTERN.findall(a.lower()))
    words_b = set(_WORD_PATTERN.findall(b.lower()))
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


async def news_deduplicator(state: dict) -> dict:
    """新闻去重节点

    输入: cleaned_articles
    输出: unique_articles
    """
    articles = state.get("cleaned_articles", [])
    new_errors: list[str] = []

    if not articles:
        return {"unique_articles": [], "errors": new_errors}

    # 第一层：content_hash 去重
    seen_hashes: set[str] = set()
    hash_unique = []
    for article in articles:
        h = article.get("content_hash", "")
        if h and h in seen_hashes:
            continue
        if h:
            seen_hashes.add(h)
        hash_unique.append(article)

    # 第二层：标题相似度去重
    unique = []
    for article in hash_unique:
        title = article.get("title", "")
        is_dup = False
        for existing in unique:
            if _title_similarity(title, existing.get("title", "")) > TITLE_SIMILARITY_THRESHOLD:
                is_dup = True
                break
        if not is_dup:
            unique.append(article)

    removed = len(articles) - len(unique)
    if removed > 0:
        logger.info("Deduplicator: removed %d duplicates (%d → %d)", removed, len(articles), len(unique))

    return {"unique_articles": unique, "errors": new_errors}
