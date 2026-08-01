"""Web Collector — Crawl4AI 网页新闻采集

复用 src/providers/web/crawl4ai_provider.py（Crawl4AI HTTP API）。
支持列表页 → 文章链接提取 → 逐篇抓取。
"""

import logging
import os
import sys
from datetime import datetime, timezone

# 添加 src 到路径（复用 Crawl4AI Provider）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
_SRC_PATH = os.path.join(_PROJECT_ROOT, "src")
if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

logger = logging.getLogger(__name__)

# 延迟导入（避免无 Crawl4AI 环境时 import 失败）
_provider = None


async def _get_provider():
    """延迟初始化 Crawl4AI Provider"""
    global _provider
    if _provider is None:
        from providers.web.crawl4ai_provider import Crawl4AIProvider
        crawl4ai_url = os.getenv("CRAWL4AI_URL", "http://crawl4ai:11235")
        crawl4ai_token = os.getenv("CRAWL4AI_API_TOKEN", "crawl4ai-dev-token")
        _provider = Crawl4AIProvider(
            base_url=crawl4ai_url,
            timeout=60,
            api_token=crawl4ai_token,
        )
    return _provider


async def collect_web(source) -> list[dict]:
    """从网页采集新闻（列表页 → 文章链接 → 正文）

    Args:
        source: NewsSource 对象（config 中需有 list_url）

    Returns:
        [{title, content, url, published_at, source_name}]
    """
    list_url = source.config.get("list_url")
    if not list_url:
        logger.warning("Web source '%s' missing list_url", source.id)
        return []

    max_articles = source.config.get("max_articles", 20)

    try:
        provider = await _get_provider()

        # 健康检查
        healthy = await provider.health_check()
        if not healthy:
            logger.warning("Crawl4AI unavailable, skipping '%s'", source.id)
            return []

        # Step 1: 抓取列表页
        list_result = await provider.fetch(list_url)
        if not list_result.success:
            logger.warning("List page fetch failed for '%s': %s", source.id, list_result.error)
            return []

        # Step 2: 提取文章链接
        from ingestion.web.link_extractor import LinkExtractor

        include_patterns = source.config.get("include_patterns", [])
        exclude_patterns = source.config.get("exclude_patterns", [r"javascript:", r"#"])

        extractor = LinkExtractor(
            include_patterns=include_patterns or None,
            exclude_patterns=exclude_patterns,
            max_articles=max_articles,
            sort_by="date_desc",
        )

        article_links = extractor.extract_from_links(list_result.links, list_url)

        if not article_links:
            logger.info("Web '%s': no article links found", source.id)
            return []

        # Step 3: 逐篇抓取正文
        from ingestion.web.chunker import clean_markdown

        articles = []
        for link in article_links[:max_articles]:
            try:
                page_result = await provider.fetch(link.url)
                if not page_result.success:
                    continue

                content = clean_markdown(page_result.markdown or "")
                if len(content) < 100:
                    continue  # 正文过短，跳过

                articles.append({
                    "title": page_result.title or link.title or "",
                    "content": content,
                    "url": link.url,
                    "published_at": link.date_str or datetime.now(timezone.utc).isoformat(),
                    "source_name": source.name,
                })
            except Exception as e:
                logger.debug("Article fetch failed (%s): %s", link.url, e)
                continue

        logger.info("Web '%s': collected %d articles", source.id, len(articles))
        return articles

    except Exception as e:
        logger.error("Web collection failed for '%s': %s", source.id, e)
        return []


async def close():
    """关闭 Provider"""
    global _provider
    if _provider:
        await _provider.close()
        _provider = None
