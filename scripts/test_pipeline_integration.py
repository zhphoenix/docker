#!/usr/bin/env python3
"""Web Pipeline 完整集成测试

测试完整数据流: URL → Crawl4AI → Markdown → MinIO → PostgreSQL

用法:
    python3 scripts/test_pipeline_integration.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import asyncpg
from minio import Minio

from providers.web.crawl4ai_provider import Crawl4AIProvider
from pipelines.web_pipeline import WebPipeline


# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────

CRAWL4AI_URL = "http://localhost:11235"
CRAWL4AI_TOKEN = "crawl4ai-dev-token"

MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
MINIO_BUCKET = "documents"

PG_DSN = "postgresql://postgres:postgres@localhost:5433/ai"

# 测试 URL（选择稳定可访问的页面）
TEST_URLS = [
    "https://example.com",
    "https://www.python.org/about/",
    "https://httpbin.org/html",
]


async def main():
    print("\n" + "=" * 60)
    print("  Web Pipeline 完整集成测试")
    print("  数据流: URL → Crawl4AI → MinIO → PostgreSQL")
    print("=" * 60)

    # ── 1. 初始化组件 ──
    print("\n[1/5] 初始化组件...")

    # Provider
    provider = Crawl4AIProvider(
        base_url=CRAWL4AI_URL,
        timeout=60,
        api_token=CRAWL4AI_TOKEN,
    )
    print(f"  Provider: {CRAWL4AI_URL}")

    # MinIO
    minio_client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )
    # 确认 bucket 存在
    if not minio_client.bucket_exists(MINIO_BUCKET):
        print(f"  ❌ Bucket '{MINIO_BUCKET}' 不存在!")
        return
    print(f"  MinIO: {MINIO_ENDPOINT} / {MINIO_BUCKET}")

    # PostgreSQL
    pg_pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=5)
    print(f"  PostgreSQL: {PG_DSN.split('@')[1]}")

    # Pipeline
    pipeline = WebPipeline(
        provider=provider,
        minio_client=minio_client,
        pg_pool=pg_pool,
        bucket=MINIO_BUCKET,
        prefix="website/",
    )
    print("  Pipeline: 就绪")

    # ── 2. 健康检查 ──
    print("\n[2/5] Crawl4AI 健康检查...")
    healthy = await provider.health_check()
    if not healthy:
        print("  ❌ Crawl4AI 不可用，终止测试")
        await cleanup(provider, pg_pool)
        return
    print("  ✅ 服务正常")

    # ── 3. 执行批量抓取 ──
    print(f"\n[3/5] 批量抓取 {len(TEST_URLS)} 个 URL...")
    print("  " + "-" * 50)

    stats = await pipeline.process_batch(TEST_URLS, concurrency=2)

    print(f"\n  结果统计:")
    print(f"    总计: {stats.total}")
    print(f"    成功: {stats.success}")
    print(f"    失败: {stats.failed}")
    print(f"    死信: {stats.dead}")
    print(f"    耗时: {stats.duration_seconds:.1f}s")

    # ── 4. 验证 MinIO ──
    print(f"\n[4/5] 验证 MinIO 存储...")
    objects = list(minio_client.list_objects(MINIO_BUCKET, prefix="website/", recursive=True))
    md_files = [o for o in objects if o.object_name.endswith(".md")]
    print(f"  website/ 下共 {len(md_files)} 个 Markdown 文件:")
    for obj in md_files[:10]:
        print(f"    - {obj.object_name} ({obj.size} bytes)")

    # ── 5. 验证 PostgreSQL ──
    print(f"\n[5/5] 验证 PostgreSQL web_pages...")
    rows = await pg_pool.fetch(
        """
        SELECT url, title, domain, page_status, content_hash, minio_path, retry_count
        FROM web_pages
        ORDER BY crawl_time DESC
        LIMIT 10
        """
    )
    print(f"  共 {len(rows)} 条记录:")
    for r in rows:
        status_icon = "✅" if r["page_status"] == "success" else "❌"
        title = (r["title"] or "")[:30]
        print(f"    {status_icon} [{r['page_status']:>7}] {r['domain']:<25} {title}")
        if r["minio_path"]:
            print(f"             → {r['minio_path']}")

    # 检查失败记录
    failed = await pg_pool.fetchval(
        "SELECT COUNT(*) FROM web_pages WHERE page_status != 'success'"
    )
    if failed:
        print(f"\n  ⚠️ {failed} 条失败记录:")
        fail_rows = await pg_pool.fetch(
            "SELECT url, last_error, error_code FROM web_pages WHERE page_status != 'success'"
        )
        for r in fail_rows:
            print(f"    - {r['url'][:50]} -> [{r['error_code']}] {r['last_error'][:60]}")

    # ── 清理 ──
    await cleanup(provider, pg_pool)

    # ── 总结 ──
    print("\n" + "=" * 60)
    if stats.success > 0:
        print(f"  ✅ 集成测试通过! ({stats.success}/{stats.total} 成功)")
    else:
        print(f"  ⚠️ 无成功抓取，请检查网络/服务状态")
    print("=" * 60 + "\n")


async def cleanup(provider, pg_pool):
    """清理资源"""
    await provider.close()
    await pg_pool.close()


if __name__ == "__main__":
    asyncio.run(main())
