#!/usr/bin/env python3
"""下游 Pipeline 集成测试: Chunk → Embedding → Qdrant

验证完整向量化流程:
1. 从 MinIO 读取已抓取的 Markdown
2. 分块 → 写入 web_chunks
3. Embedding → Qdrant 向量化
4. 相似性搜索验证可检索

用法:
    python3 scripts/test_downstream_pipeline.py
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
PG_DSN = "postgresql://postgres:postgres@localhost:5433/ai"
EMBED_URL = "http://localhost:8001/v1/embeddings"
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333

# 用 python.org/about 做测试（内容丰富，有标题结构）
TEST_URL = "https://www.python.org/about/"


async def main():
    print("\n" + "=" * 60)
    print("  下游 Pipeline 集成测试")
    print("  Chunk → Embedding → Qdrant → 相似性搜索")
    print("=" * 60)

    # ── 初始化 ──
    print("\n[1/6] 初始化组件...")

    provider = Crawl4AIProvider(
        base_url=CRAWL4AI_URL, timeout=60, api_token=CRAWL4AI_TOKEN
    )
    minio_client = Minio(
        MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY, secure=False,
    )
    pg_pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=5)

    pipeline = WebPipeline(
        provider=provider,
        minio_client=minio_client,
        pg_pool=pg_pool,
        bucket="documents",
        prefix="website/",
        embed_url=EMBED_URL,
        embed_model="qwen3-embedding",
        embed_batch_size=8,
        qdrant_host=QDRANT_HOST,
        qdrant_port=QDRANT_PORT,
        qdrant_collection="web_pages",
    )
    print("  ✅ Pipeline 就绪")

    # ── 确认测试页面存在 ──
    print(f"\n[2/6] 确认测试页面: {TEST_URL}")
    page = await pg_pool.fetchrow(
        "SELECT id, page_status, minio_path FROM web_pages WHERE url = $1",
        TEST_URL,
    )

    if not page:
        print("  页面不存在，先抓取...")
        result = await pipeline.process_url(TEST_URL)
        print(f"  抓取结果: {result}")
        page = await pg_pool.fetchrow(
            "SELECT id, page_status, minio_path FROM web_pages WHERE url = $1",
            TEST_URL,
        )

    if not page or page["page_status"] != "success":
        print("  ❌ 测试页面不可用")
        await cleanup(provider, pg_pool)
        return

    print(f"  ✅ 页面存在 (minio: {page['minio_path']})")

    # ── 执行 Chunk + Embed ──
    print(f"\n[3/6] 执行 Chunk → Embedding → Qdrant...")
    result = await pipeline.chunk_and_embed_page(TEST_URL)
    print(f"  结果: {result}")

    if result.get("status") != "synced":
        print(f"  ❌ 向量化失败: {result}")
        await cleanup(provider, pg_pool)
        return

    print(f"  ✅ 向量化成功: {result['chunks']} chunks, {result['points']} points")

    # ── 验证 web_chunks ──
    print(f"\n[4/6] 验证 web_chunks 表...")
    chunks = await pg_pool.fetch(
        """
        SELECT chunk_index, heading, token_count, embedded,
               LENGTH(content) as content_len
        FROM web_chunks
        WHERE page_id = $1
        ORDER BY chunk_index
        """,
        page["id"],
    )
    print(f"  共 {len(chunks)} 个 chunks:")
    for c in chunks[:8]:
        heading = c["heading"] or "(无标题)"
        print(f"    [{c['chunk_index']}] {heading[:30]:<30} "
              f"({c['content_len']} chars, ~{c['token_count']} tok, "
              f"embedded={c['embedded']})")
    if len(chunks) > 8:
        print(f"    ... 还有 {len(chunks) - 8} 个")

    # ── 验证 Qdrant ──
    print(f"\n[5/6] 验证 Qdrant collection...")
    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/web_pages")
        info = resp.json()["result"]
        print(f"  points_count: {info['points_count']}")
        print(f"  vectors_count: {info.get('vectors_count', 'N/A')}")

    # ── 相似性搜索测试 ──
    print(f"\n[6/6] 相似性搜索测试...")
    # 先生成查询向量
    query_text = "What is Python used for?"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            EMBED_URL,
            json={"input": [query_text], "model": "qwen3-embedding"},
        )
        query_vec = resp.json()["data"][0]["embedding"]

    # Qdrant 搜索
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/web_pages/points/search",
            json={
                "vector": query_vec,
                "limit": 3,
                "with_payload": True,
            },
        )
        search_results = resp.json()["result"]

    print(f"  查询: \"{query_text}\"")
    print(f"  Top-3 结果:")
    for i, hit in enumerate(search_results):
        payload = hit["payload"]
        score = hit["score"]
        content_preview = payload.get("content", "")[:80].replace("\n", " ")
        print(f"    [{i+1}] score={score:.4f} | {payload.get('heading', 'N/A')[:25]}")
        print(f"        \"{content_preview}...\"")

    # ── 清理 ──
    await cleanup(provider, pg_pool)

    print("\n" + "=" * 60)
    print("  ✅ 下游 Pipeline 集成测试通过!")
    print("  完整链路: URL → Crawl → MinIO → Chunk → Embed → Qdrant → Search")
    print("=" * 60 + "\n")


async def cleanup(provider, pg_pool):
    await provider.close()
    await pg_pool.close()


if __name__ == "__main__":
    asyncio.run(main())
