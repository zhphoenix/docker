"""列表页链接提取器

从 Crawl4AI 返回的页面链接中提取文章 URL。
支持：
- URL 模式过滤（include/exclude 正则）
- 按日期降序排序（从 URL 路径提取 YYYYMM/YYYYMMDD）
- 同域过滤
- 去重
- 最大数量限制

用法:
    extractor = LinkExtractor(
        include_patterns=[r"/2026/", r"/2025/"],
        exclude_patterns=[r"javascript:", r"/index", r"node_"],
        max_articles=20,
    )
    articles = extractor.extract_from_links(links, base_url="https://www.qstheory.cn/")
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse


@dataclass
class ExtractedArticle:
    """提取到的文章"""

    url: str
    title: str | None = None
    date_str: str | None = None  # 从 URL 提取的日期字符串


# 从 URL 路径中提取日期的正则（匹配 YYYYMMDD 或 YYYYMM 或 YYYY/MM）
_DATE_PATTERNS = [
    re.compile(r"/(\d{4})(\d{2})(\d{2})/"),   # /20260725/
    re.compile(r"/(\d{4})(\d{2})/"),           # /202607/
    re.compile(r"/(\d{4})/(\d{2})/"),          # /2026/07/
    re.compile(r"[/_](\d{4})(\d{2})(\d{2})"),  # _20260725
]


def _extract_date_from_url(url: str) -> str | None:
    """从 URL 中提取日期字符串（用于排序）

    Returns:
        日期字符串如 "20260725"，无法提取返回 None
    """
    for pattern in _DATE_PATTERNS:
        m = pattern.search(url)
        if m:
            groups = m.groups()
            if len(groups) == 3:
                return "".join(groups)  # YYYYMMDD
            elif len(groups) == 2:
                return groups[0] + groups[1] + "01"  # YYYYMM → YYYYMM01
    return None


class LinkExtractor:
    """从 Crawl4AI 响应中提取文章链接

    Args:
        include_patterns: URL 白名单正则列表（匹配任一即保留）
        exclude_patterns: URL 黑名单正则列表（匹配任一即排除）
        max_articles: 最大文章数
        same_domain: 是否仅保留同域链接
        sort_by: 排序方式（date_desc / none）
    """

    def __init__(
        self,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        max_articles: int = 20,
        same_domain: bool = True,
        sort_by: str = "date_desc",
    ):
        self.include_patterns = [re.compile(p) for p in (include_patterns or [])]
        self.exclude_patterns = [re.compile(p) for p in (exclude_patterns or [
            r"javascript:", r"#", r"/index", r"\.pdf$", r"\.jpg$", r"\.png$",
            r"\.css$", r"\.js$", r"node_",
        ])]
        self.max_articles = max_articles
        self.same_domain = same_domain
        self.sort_by = sort_by

    def extract_from_links(
        self, links: list[dict[str, Any]], base_url: str
    ) -> list[ExtractedArticle]:
        """从 Crawl4AI 返回的 links 列表中提取文章

        Crawl4AI 响应格式:
            result["links"]["internal"] = [{"href": ..., "text": ...}, ...]

        Args:
            links: Crawl4AI 返回的内部链接列表
            base_url: 列表页 URL（用于绝对化和同域判断）

        Returns:
            按日期降序排列的文章列表
        """
        base_domain = urlparse(base_url).netloc
        articles: list[ExtractedArticle] = []
        seen_urls: set[str] = set()

        for link in links:
            href = link.get("href", "")
            text = link.get("text", "").strip()

            if not href:
                continue

            # 绝对化
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)

            # 同域过滤
            if self.same_domain and parsed.netloc != base_domain:
                continue

            # 黑名单
            if any(p.search(full_url) for p in self.exclude_patterns):
                continue

            # 白名单（如果配置了，必须匹配至少一个）
            if self.include_patterns:
                if not any(p.search(full_url) for p in self.include_patterns):
                    continue

            # 去重（去掉 fragment 和尾部斜杠）
            clean_url = full_url.split("#")[0].rstrip("/")
            if clean_url in seen_urls:
                continue
            seen_urls.add(clean_url)

            # 提取日期
            date_str = _extract_date_from_url(clean_url)

            articles.append(ExtractedArticle(
                url=clean_url,
                title=text or None,
                date_str=date_str,
            ))

        # 排序
        if self.sort_by == "date_desc":
            # 有日期的排前面，按日期降序；无日期的排后面
            articles.sort(
                key=lambda a: a.date_str or "00000000",
                reverse=True,
            )

        # 截取
        return articles[:self.max_articles]

    @classmethod
    def from_crawl_rules(cls, crawl_rules: dict[str, Any]) -> "LinkExtractor":
        """从 websites.yaml 的 crawl_rules 配置构建

        Args:
            crawl_rules: 站点配置中的 crawl_rules 字典
        """
        # 从 article_selector 提取 include patterns
        # 格式: "a[href*='/2026/'], a[href*='/2025/']"
        selector = crawl_rules.get("article_selector", "")
        include_patterns = []
        if selector:
            # 提取 href*= 后的模式
            for m in re.finditer(r"href\*='([^']+)'", selector):
                pattern = re.escape(m.group(1)).replace(r"\*", ".*")
                include_patterns.append(pattern)

        return cls(
            include_patterns=include_patterns or None,
            exclude_patterns=crawl_rules.get("exclude_patterns"),
            max_articles=crawl_rules.get("max_articles", 20),
            same_domain=True,
            sort_by=crawl_rules.get("sort_by", "date_desc"),
        )
