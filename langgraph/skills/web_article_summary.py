"""Web Article Summary Skill - 网页文章自动摘要

从指定网站首页/栏目列表页提取文章链接，逐篇抓取正文，
调用 LLM 生成结构化摘要，写入 PostgreSQL + Obsidian Vault。

执行流程:
  1. 调用 Crawl4AI 抓取列表页 → 获取页面内链接
  2. LinkExtractor 过滤 + 按日期排序 → 文章 URL 列表
  3. 逐篇调用 Crawl4AI 抓取正文 → Markdown
  4. 清洗 Markdown（去导航/页脚噪音）
  5. 调用 LLM 生成摘要
  6. 写入 PostgreSQL (web_pages.metadata.summary) + Obsidian Vault

Agent 调用方式:
    from skills.registry import get_registry
    result = await get_registry().execute(
        "web_article_summary",
        domain="www.qstheory.cn",
        max_articles=10,
    )
"""

import logging
import os
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from skills.base_skill import BaseSkill
from tools.llm import llm_tool
from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)

# Crawl4AI 服务地址（Docker 内部）
CRAWL4AI_URL = os.getenv("CRAWL4AI_URL", "http://crawl4ai:11235")
CRAWL4AI_TOKEN = os.getenv("CRAWL4AI_API_TOKEN", "crawl4ai-dev-token")

# 默认站点配置
DEFAULT_DOMAIN = "www.qstheory.cn"
DEFAULT_ENTRY_URL = "https://www.qstheory.cn/"
DEFAULT_MAX_ARTICLES = 20

# 摘要 Prompt
_SUMMARY_SYSTEM = "你是一位专业的政策研究分析师，擅长提炼文章核心观点并生成结构化摘要。"
_SUMMARY_TEMPLATE = """请为以下文章生成结构化摘要。

要求：
1. 用中文输出
2. 格式：
   - **核心观点**：1-2 句话概括文章主旨
   - **主要论述**：3-5 个要点（用编号列表）
   - **政策信号**：如有明确政策导向或信号，简要指出（如无则省略此项）
3. 总长度不超过 {max_chars} 字
4. 客观准确，不添加原文没有的信息

文章标题：{title}

文章正文：
{content}
"""

# URL 日期提取正则
_DATE_RE = re.compile(r"/(\d{4})(\d{2})(\d{2})/|/(\d{4})(\d{2})/")

# 导航噪音标记
_NAV_MARKERS = [
    "copyright", "all rights reserved", "powered by",
    "来源：求是网", "责任编辑", "分享到", "相关阅读", "上一篇", "下一篇",
]


# ──────────────────────────────────────────────
# 内部工具函数
# ──────────────────────────────────────────────

def _extract_date(url: str) -> str:
    """从 URL 提取日期字符串用于排序"""
    m = _DATE_RE.search(url)
    if m:
        groups = [g for g in m.groups() if g]
        if len(groups) >= 3:
            return "".join(groups[:3])
        elif len(groups) == 2:
            return groups[0] + groups[1] + "01"
    return "00000000"


def _clean_markdown(raw: str) -> str:
    """简易 Markdown 清洗（去导航/页脚）"""
    if not raw:
        return ""
    lines = raw.split("\n")

    # 找内容起点
    start = 0
    for i, line in enumerate(lines):
        if re.match(r"^#{1,3}\s+\S", line):
            start = i
            break

    # 找页脚
    end = len(lines)
    for i in range(len(lines) - 1, start, -1):
        lower = lines[i].lower().strip()
        if any(m in lower for m in _NAV_MARKERS):
            end = i
            break

    # 过滤导航行
    cleaned = []
    for line in lines[start:end]:
        lower = line.strip().lower()
        if any(m in lower for m in _NAV_MARKERS):
            continue
        cleaned.append(line)

    result = re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned))
    return result.strip()


def _filter_article_links(
    links: list[dict], base_url: str, max_articles: int
) -> list[dict[str, str]]:
    """从链接列表中过滤文章链接并按日期排序"""
    base_domain = urlparse(base_url).netloc
    articles: list[dict[str, str]] = []
    seen: set[str] = set()

    # 排除模式
    exclude = re.compile(
        r"javascript:|#|/index|node_|\.pdf$|\.jpg$|\.png$|\.css$|\.js$"
    )
    # 包含模式（求是网文章 URL 含 YYYYMMDD 日期路径）
    include = re.compile(r"/20\d{6}/")

    for link in links:
        href = link.get("href", "")
        text = link.get("text", "").strip()
        if not href:
            continue

        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)

        # 同域
        if parsed.netloc != base_domain:
            continue
        # 排除
        if exclude.search(full_url):
            continue
        # 必须含年份路径
        if not include.search(full_url):
            continue
        # 去重
        clean = full_url.split("#")[0].rstrip("/")
        if clean in seen:
            continue
        seen.add(clean)

        articles.append({"url": clean, "title": text})

    # 按日期降序
    articles.sort(key=lambda a: _extract_date(a["url"]), reverse=True)
    return articles[:max_articles]


# ──────────────────────────────────────────────
# Skill 类
# ──────────────────────────────────────────────

class WebArticleSummarySkill(BaseSkill):
    """网页文章自动摘要 Skill

    从指定站点列表页提取文章 → 抓取正文 → LLM 摘要 → 存储
    """

    @property
    def name(self) -> str:
        return "web_article_summary"

    @property
    def description(self) -> str:
        return "从网站首页/栏目列表页提取最新文章，逐篇抓取正文并生成结构化摘要"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def tags(self) -> list[str]:
        return ["web", "crawl", "summary", "policy"]

    def validate_params(self, **kwargs) -> list[str]:
        errors = []
        max_articles = kwargs.get("max_articles", DEFAULT_MAX_ARTICLES)
        if not isinstance(max_articles, int) or max_articles < 1 or max_articles > 100:
            errors.append("max_articles must be an integer between 1 and 100")
        return errors

    async def execute(self, **kwargs) -> dict[str, Any]:
        """执行文章摘要流水线

        Args:
            domain: 目标站点域名（默认 www.qstheory.cn）
            entry_url: 列表页 URL（默认 https://www.qstheory.cn/）
            column_path: 栏目路径（可选，如 /qslgxd/）
            max_articles: 最大文章数（默认 20）
            max_summary_chars: 摘要长度上限（默认 500）
            skip_existing: 跳过已有摘要的 URL（默认 True）

        Returns:
            {"success": bool, "data": {"articles": [...], "stats": {...}}}
        """
        domain = kwargs.get("domain", DEFAULT_DOMAIN)
        entry_url = kwargs.get("entry_url", DEFAULT_ENTRY_URL)
        column_path = kwargs.get("column_path", "")
        max_articles = kwargs.get("max_articles", DEFAULT_MAX_ARTICLES)
        max_summary_chars = kwargs.get("max_summary_chars", 500)
        skip_existing = kwargs.get("skip_existing", True)

        # 如果指定了栏目路径，拼接 URL
        if column_path:
            entry_url = f"https://{domain}{column_path}"

        logger.info(
            "WebArticleSummary: domain=%s, entry=%s, max=%d",
            domain, entry_url, max_articles,
        )

        try:
            # ━━ Step 1: 抓取列表页 ━━
            list_result = await self._crawl_page(entry_url)
            if not list_result.get("success"):
                return {
                    "success": False,
                    "error": f"列表页抓取失败: {list_result.get('error')}",
                }

            # ━━ Step 2: 提取文章链接 ━━
            links = list_result.get("links", [])
            articles = _filter_article_links(links, entry_url, max_articles)

            if not articles:
                return {
                    "success": True,
                    "data": {"articles": [], "stats": {"total": 0, "summarized": 0}},
                    "message": "未从列表页提取到文章链接",
                }

            logger.info("提取到 %d 篇文章链接", len(articles))

            # ━━ Step 3: 逐篇抓取 + 摘要 ━━
            results = []
            stats = {"total": len(articles), "summarized": 0, "failed": 0, "skipped": 0}

            for i, article in enumerate(articles):
                url = article["url"]
                title = article["title"] or ""

                # 跳过已有摘要
                if skip_existing and await self._has_summary(url):
                    stats["skipped"] += 1
                    continue

                # 抓取正文
                page_result = await self._crawl_page(url)
                if not page_result.get("success"):
                    stats["failed"] += 1
                    results.append({"url": url, "status": "crawl_failed"})
                    continue

                markdown = page_result.get("markdown", "")
                page_title = page_result.get("title") or title

                # 清洗
                cleaned = _clean_markdown(markdown)
                if not cleaned or len(cleaned) < 100:
                    stats["failed"] += 1
                    results.append({"url": url, "status": "empty_content"})
                    continue

                # 生成摘要
                summary = await self._generate_summary(page_title, cleaned, max_summary_chars)
                if not summary:
                    stats["failed"] += 1
                    results.append({"url": url, "status": "summary_failed"})
                    continue

                # 存储
                await self._store_result(url, page_title, domain, summary)

                stats["summarized"] += 1
                results.append({
                    "url": url,
                    "title": page_title,
                    "summary": summary[:200] + "..." if len(summary) > 200 else summary,
                    "status": "success",
                })

                logger.info(
                    "  [%d/%d] ✅ %s", i + 1, len(articles), page_title[:40]
                )

            return {
                "success": True,
                "data": {
                    "domain": domain,
                    "entry_url": entry_url,
                    "articles": results,
                    "stats": stats,
                },
            }

        except Exception as e:
            logger.exception("WebArticleSummary failed")
            return {"success": False, "error": str(e)}

    # ──────────────────────────────────────────────
    # 内部方法
    # ──────────────────────────────────────────────

    async def _crawl_page(self, url: str) -> dict[str, Any]:
        """调用 Crawl4AI 抓取单个页面"""
        headers = {}
        if CRAWL4AI_TOKEN:
            headers["Authorization"] = f"Bearer {CRAWL4AI_TOKEN}"

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60.0),
                headers=headers,
            ) as client:
                resp = await client.post(
                    f"{CRAWL4AI_URL}/crawl",
                    json={"urls": [url], "priority": 8},
                )
                resp.raise_for_status()
                data = resp.json()

                results = data.get("results", [])
                if not results:
                    return {"success": False, "error": "Empty results"}

                result = results[0]
                if not result.get("success", False):
                    return {
                        "success": False,
                        "error": result.get("error_message", "Unknown"),
                    }

                # 提取 Markdown
                md_obj = result.get("markdown", {})
                if isinstance(md_obj, dict):
                    markdown = md_obj.get("raw_markdown", "") or md_obj.get("fit_markdown", "")
                else:
                    markdown = md_obj or ""

                # 提取链接
                links_data = result.get("links", {})
                internal_links = links_data.get("internal", []) if isinstance(links_data, dict) else []

                title = result.get("metadata", {}).get("title", "")

                return {
                    "success": True,
                    "markdown": markdown,
                    "title": title,
                    "links": internal_links,
                }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _generate_summary(
        self, title: str, markdown: str, max_chars: int
    ) -> str | None:
        """调用 LLM 生成摘要"""
        content = markdown[:6000]
        prompt = _SUMMARY_TEMPLATE.format(
            title=title, content=content, max_chars=max_chars
        )

        try:
            messages = [
                {"role": "system", "content": _SUMMARY_SYSTEM},
                {"role": "user", "content": prompt},
            ]
            result = await llm_tool.chat(messages, temperature=0.3, max_tokens=1024)
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error("摘要 LLM 调用失败: %s", e)
            return None

    async def _has_summary(self, url: str) -> bool:
        """检查 URL 是否已有摘要"""
        try:
            row = await postgres_tool.pool.fetchrow(
                "SELECT metadata->>'summary' as s FROM web_pages WHERE url = $1",
                url,
            )
            return bool(row and row["s"])
        except Exception:
            return False

    async def _store_result(
        self, url: str, title: str, domain: str, summary: str
    ) -> None:
        """存储摘要到 PostgreSQL + Obsidian Vault"""
        # 1. PostgreSQL: upsert web_pages + 写入 metadata.summary
        try:
            await postgres_tool.pool.execute(
                """
                INSERT INTO web_pages (url, title, domain, page_status, metadata)
                VALUES ($1, $2, $3, 'success', jsonb_build_object('summary', $4))
                ON CONFLICT (url) DO UPDATE SET
                    title = EXCLUDED.title,
                    metadata = web_pages.metadata || jsonb_build_object('summary', $4),
                    crawl_time = NOW()
                """,
                url, title, domain, summary,
            )
        except Exception as e:
            logger.warning("PG 写入失败: %s -> %s", url, e)

        # 2. 摘要已写入 PG，Vault 写入已移除
        logger.debug("Summary generated for: %s", title[:50])
