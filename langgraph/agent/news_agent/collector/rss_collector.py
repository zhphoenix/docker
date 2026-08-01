"""RSS Collector — RSS/Atom Feed 新闻采集

使用 feedparser 解析 RSS/Atom feeds，返回标准化文章列表。
"""

import asyncio
import logging
from datetime import datetime, timezone
from time import mktime

import feedparser

logger = logging.getLogger(__name__)


async def collect_rss(source) -> list[dict]:
    """从 RSS Feed 采集新闻

    Args:
        source: NewsSource 对象（config 中需有 feed_url）

    Returns:
        [{title, content, url, published_at, source_name}]
    """
    feed_url = source.config.get("feed_url")
    if not feed_url:
        logger.warning("RSS source '%s' missing feed_url", source.id)
        return []

    max_articles = source.config.get("max_articles", 20)

    try:
        # W-4 修复：feedparser.parse 内含网络 I/O，放入线程池避免阻塞事件循环
        loop = asyncio.get_running_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, feed_url)

        if feed.bozo and not feed.entries:
            logger.warning("RSS parse error for '%s': %s", source.id, feed.bozo_exception)
            return []

        articles = []
        for entry in feed.entries[:max_articles]:
            # 解析发布时间
            published_at = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published_at = datetime.fromtimestamp(
                    mktime(entry.published_parsed), tz=timezone.utc
                ).isoformat()
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published_at = datetime.fromtimestamp(
                    mktime(entry.updated_parsed), tz=timezone.utc
                ).isoformat()

            # 提取正文（优先 content，其次 summary）
            content = ""
            if hasattr(entry, "content") and entry.content:
                content = entry.content[0].get("value", "")
            elif hasattr(entry, "summary"):
                content = entry.summary or ""

            articles.append({
                "title": entry.get("title", "").strip(),
                "content": content.strip(),
                "url": entry.get("link", ""),
                "published_at": published_at,
                "source_name": source.name,
            })

        logger.info("RSS '%s': collected %d articles", source.id, len(articles))
        return articles

    except Exception as e:
        logger.error("RSS collection failed for '%s': %s", source.id, e)
        return []
