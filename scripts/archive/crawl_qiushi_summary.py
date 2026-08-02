#!/usr/bin/env python3
"""求是网文章自动摘要 Pipeline（独立脚本）

流程:
  1. 抓取列表页 → 提取文章链接（按日期降序）
  2. 逐篇抓取正文 → Markdown 清洗
  3. 调用 LLM 生成结构化摘要
  4. 存储: PostgreSQL (web_pages.metadata.summary) + 本地 Markdown 文件

用法:
  # 默认：抓取求是网首页最新 20 篇文章
  python3 scripts/crawl_qiushi_summary.py

  # 指定栏目
  python3 scripts/crawl_qiushi_summary.py --column /qslgxd/

  # 限制数量
  python3 scripts/crawl_qiushi_summary.py --max-articles 5

  # 跳过摘要（仅抓取+存储）
  python3 scripts/crawl_qiushi_summary.py --skip-summary

  # 指定 LLM 地址
  python3 scripts/crawl_qiushi_summary.py --llm-url http://localhost:8080/v1/chat/completions

前置条件:
  - Crawl4AI 服务运行中: docker compose up -d crawl4ai
  - LLM 服务运行中（摘要功能需要）
  - PostgreSQL 运行中（存储功能需要，可选）
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from providers.web.crawl4ai_provider import Crawl4AIProvider
from ingestion.web.link_extractor import LinkExtractor
from ingestion.web.chunker import clean_markdown
from ingestion.web.summarizer import ArticleSummarizer

# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("crawl_qiushi")

CRAWL4AI_URL = os.getenv("CRAWL4AI_URL", "http://localhost:11235")
CRAWL4AI_TOKEN = os.getenv("CRAWL4AI_API_TOKEN", "crawl4ai-dev-token")
LLM_URL = os.getenv("LLM_BASE_URL", "http://localhost:8080/v1/chat/completions")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "reports" / "qiushi"


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────

async def run_pipeline(args):
    """执行完整流水线"""
    entry_url = f"https://www.qstheory.cn{args.column}" if args.column else "https://www.qstheory.cn/"

    print("\n" + "=" * 60)
    print("  求是网文章自动摘要 Pipeline")
    print(f"  入口: {entry_url}")
    print(f"  最大文章数: {args.max_articles}")
    print(f"  LLM: {args.llm_url}")
    print(f"  输出目录: {OUTPUT_DIR}")
    print("=" * 60 + "\n")

    # 初始化组件
    provider = Crawl4AIProvider(
        base_url=CRAWL4AI_URL,
        timeout=60,
        api_token=CRAWL4AI_TOKEN,
    )

    extractor = LinkExtractor(
        include_patterns=[r"/2026\d{4}/", r"/2025\d{4}/"],
        exclude_patterns=[r"javascript:", r"#", r"/index", r"node_"],
        max_articles=args.max_articles,
        sort_by="date_desc",
    )

    summarizer = ArticleSummarizer(
        llm_url=args.llm_url,
        model="qwen3",
        max_input_chars=6000,
        max_summary_chars=500,
    ) if not args.skip_summary else None

    # 确保输出目录
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    stats = {"total": 0, "crawled": 0, "summarized": 0, "failed": 0}

    try:
        # ━━ Step 1: 健康检查 ━━
        print("[1/4] 检查 Crawl4AI 服务...")
        healthy = await provider.health_check()
        if not healthy:
            print("  ❌ Crawl4AI 服务不可用！请先启动: docker compose up -d crawl4ai")
            return
        print("  ✅ Crawl4AI 服务正常")

        # ━━ Step 2: 抓取列表页 ━━
        print(f"\n[2/4] 抓取列表页: {entry_url}")
        list_result = await provider.fetch(entry_url)

        if not list_result.success:
            print(f"  ❌ 列表页抓取失败: {list_result.error}")
            return

        print(f"  ✅ 列表页抓取成功 (标题: {list_result.title})")
        print(f"  📎 页面内链接数: {len(list_result.links)}")

        # ━━ Step 3: 提取文章链接 ━━
        print(f"\n[3/4] 提取文章链接 (最新 {args.max_articles} 篇)...")
        articles = extractor.extract_from_links(list_result.links, entry_url)
        stats["total"] = len(articles)

        if not articles:
            print("  ⚠️ 未提取到文章链接，请检查选择器配置")
            return

        print(f"  ✅ 提取到 {len(articles)} 篇文章:")
        for i, a in enumerate(articles[:5], 1):
            print(f"    {i}. [{a.date_str or 'N/A'}] {a.title or a.url}")
        if len(articles) > 5:
            print(f"    ... 共 {len(articles)} 篇")

        # ━━ Step 4: 逐篇抓取 + 摘要 ━━
        print(f"\n[4/4] 逐篇抓取正文 + 生成摘要...")
        all_results = []

        for i, article in enumerate(articles, 1):
            url = article.url
            title = article.title or ""

            print(f"\n  [{i}/{len(articles)}] {url}")

            # 抓取正文
            page_result = await provider.fetch(url)
            if not page_result.success:
                print(f"    ❌ 抓取失败: {page_result.error}")
                stats["failed"] += 1
                continue

            stats["crawled"] += 1
            page_title = page_result.title or title
            print(f"    📄 标题: {page_title}")
            print(f"    📝 正文: {len(page_result.markdown or '')} 字符")

            # 清洗
            cleaned = clean_markdown(page_result.markdown or "")
            if len(cleaned) < 100:
                print(f"    ⚠️ 正文过短，跳过")
                stats["failed"] += 1
                continue

            # 摘要
            summary = None
            if summarizer:
                summary = await summarizer.summarize(page_title, cleaned)
                if summary:
                    stats["summarized"] += 1
                    print(f"    ✅ 摘要: {len(summary)} 字")
                else:
                    print(f"    ⚠️ 摘要生成失败")

            # 保存到本地文件
            safe_title = "".join(c for c in page_title if c.isalnum() or c in " _-").strip()[:50]
            filename = f"{article.date_str or 'unknown'}_{safe_title}.md"
            filepath = OUTPUT_DIR / filename

            content_parts = [
                f"# {page_title}\n",
                f"> 来源: {url}",
                f"> 日期: {article.date_str or '未知'}",
                f"> 抓取时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
            ]
            if summary:
                content_parts.append(f"## 摘要\n\n{summary}\n")
            content_parts.append(f"## 正文\n\n{cleaned[:3000]}\n")

            filepath.write_text("\n".join(content_parts), encoding="utf-8")
            print(f"    💾 保存: {filepath.name}")

            all_results.append({
                "url": url,
                "title": page_title,
                "date": article.date_str,
                "summary": summary,
                "file": str(filepath),
            })

        # ━━ 汇总 ━━
        elapsed = time.time() - t0
        print("\n" + "=" * 60)
        print("  Pipeline 完成!")
        print(f"  文章总数: {stats['total']}")
        print(f"  成功抓取: {stats['crawled']}")
        print(f"  生成摘要: {stats['summarized']}")
        print(f"  失败: {stats['failed']}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  输出: {OUTPUT_DIR}")
        print("=" * 60 + "\n")

        # 保存结果索引
        index_path = OUTPUT_DIR / "_index.json"
        index_data = {
            "run_time": datetime.now().isoformat(),
            "entry_url": entry_url,
            "stats": stats,
            "articles": all_results,
        }
        index_path.write_text(json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  📋 结果索引: {index_path}")

    finally:
        await provider.close()
        if summarizer:
            await summarizer.close()


# ──────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="求是网文章自动摘要 Pipeline")
    parser.add_argument(
        "--column", type=str, default="",
        help="栏目路径（如 /qslgxd/），默认为首页",
    )
    parser.add_argument(
        "--max-articles", type=int, default=5,
        help="最大文章数（默认 5）",
    )
    parser.add_argument(
        "--llm-url", type=str, default=LLM_URL,
        help="LLM API 地址",
    )
    parser.add_argument(
        "--skip-summary", action="store_true",
        help="跳过摘要生成（仅抓取+清洗+保存）",
    )
    args = parser.parse_args()
    asyncio.run(run_pipeline(args))


if __name__ == "__main__":
    main()
