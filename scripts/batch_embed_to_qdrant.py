#!/usr/bin/env python3
"""高性能批量 Embedding → Qdrant v3 (async 合并版)

合并 phase4_embedding.py 的异步架构 + batch_embed_to_qdrant.py 的 CLI 接口。

核心优化：
  - asyncpg 异步连接池（消除 GIL + OFFSET 退化）
  - httpx AsyncClient + asyncio.gather 并发 embedding
  - `qdrant_point_id IS NULL` 增量查询（真断点续传）
  - 回写 qdrant_point_id（中断后自动跳过已完成）

用法：
  python3 scripts/batch_embed_to_qdrant.py --market cn
  python3 scripts/batch_embed_to_qdrant.py --market cn --batch-size 16 --concurrency 4
  python3 scripts/batch_embed_to_qdrant.py --market hk --limit 1000
"""

import asyncio
import os
import sys
import time
import argparse
import uuid

import asyncpg
import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

# ── 配置 ──────────────────────────────────────────────────────────────────────

PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = int(os.environ.get("PG_PORT", "5433"))
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASS = os.environ.get("PG_PASS", "postgres")
PG_DB = os.environ.get("PG_DB", "ai")

EMBEDDING_URL = os.environ.get("EMBEDDING_URL", "http://localhost:8001/v1/embeddings")
QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6333"))

COLLECTION_MAP = {"cn": "documents_cn", "hk": "documents_hk", "us": "documents_us"}

# 文本截断（llama.cpp ctx=16384, slots=8 → 2048 tokens/slot，中文 ~1.5 tok/char）
MAX_CHARS = 800
# 每次从 PG 拉取的 chunk 数
FETCH_SIZE = 500
# Qdrant 每批 upsert 大小
QDRANT_UPSERT_SIZE = 200


async def embed_batch(client: httpx.AsyncClient, texts: list[str]) -> list[list[float]]:
    """调用 Embedding 服务（单次请求）"""
    resp = await client.post(
        EMBEDDING_URL,
        json={"input": texts, "model": "qwen3-embedding"},
        timeout=120.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return [item["embedding"] for item in data["data"]]


async def embed_concurrent(
    client: httpx.AsyncClient, texts: list[str], batch_size: int, concurrency: int
) -> list[list[float]]:
    """将 texts 分成 batch_size 大小的子批，concurrency 个并发执行"""
    batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]
    results: list[list[float]] = [None] * len(batches)  # type: ignore

    sem = asyncio.Semaphore(concurrency)

    async def _do(idx: int, batch: list[str]):
        async with sem:
            vecs = await embed_batch(client, batch)
            results[idx] = vecs

    await asyncio.gather(*[_do(i, b) for i, b in enumerate(batches)])

    # 展平
    flat = []
    for r in results:
        flat.extend(r)
    return flat


async def main():
    parser = argparse.ArgumentParser(description="高性能批量 Embedding → Qdrant v3")
    parser.add_argument("--market", type=str, default="cn")
    parser.add_argument("--batch-size", type=int, default=16, help="每次 Embedding 请求的文本数")
    parser.add_argument("--concurrency", type=int, default=4, help="并发 Embedding 请求数")
    parser.add_argument("--limit", type=int, default=0, help="限制处理数量（0=全部）")
    args = parser.parse_args()

    market = args.market
    batch_size = args.batch_size
    concurrency = args.concurrency
    collection = COLLECTION_MAP.get(market, "documents_cn")

    print("=" * 70)
    print(f"  批量 Embedding → Qdrant v3 (async)")
    print(f"  市场: {market} → {collection}")
    print(f"  batch_size: {batch_size} | concurrency: {concurrency}")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # 连接 PostgreSQL (asyncpg 连接池)
    pool = await asyncpg.create_pool(
        host=PG_HOST, port=PG_PORT, user=PG_USER,
        password=PG_PASS, database=PG_DB,
        min_size=2, max_size=5,
    )

    # Qdrant 客户端
    qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=120)

    # 统计
    total_remaining = await pool.fetchval("""
        SELECT COUNT(*) FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE d.market = $1 AND c.qdrant_point_id IS NULL
    """, market)

    try:
        info = qdrant.get_collection(collection)
        existing = info.points_count or 0
    except Exception:
        existing = 0

    if args.limit > 0:
        total_remaining = min(total_remaining, args.limit)

    print(f"\n  待处理: {total_remaining:,} | Qdrant 已有: {existing:,}")
    print()
    sys.stdout.flush()

    if total_remaining == 0:
        print("  无剩余 chunks，已完成！")
        await pool.close()
        return

    # HTTP 客户端（异步，连接池）
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(120.0),
        limits=httpx.Limits(max_connections=concurrency + 2, max_keepalive_connections=concurrency),
    )

    processed = 0
    failed = 0
    skipped = 0
    t_start = time.time()
    last_report = t_start

    while processed < total_remaining:
        # 拉取一批未嵌入的 chunks
        fetch_limit = min(FETCH_SIZE, total_remaining - processed)
        rows = await pool.fetch("""
            SELECT c.id AS chunk_id, c.content, c.chunk_index,
                   d.symbol, d.year, d.market,
                   d.document_type,
                   COALESCE(d.metadata->>'source', '') AS source_provider,
                   d.created_at::date AS published_date
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE d.market = $1 AND c.qdrant_point_id IS NULL
            ORDER BY d.symbol, d.year, c.chunk_index
            LIMIT $2
        """, market, fetch_limit)

        if not rows:
            break

        # 预处理：截断 + 过滤
        prepared = []
        skip_ids = []
        for r in rows:
            content = r["content"] or ""
            if len(content.strip()) < 10:
                skipped += 1
                skip_ids.append(r["chunk_id"])
                continue
            if len(content) > MAX_CHARS:
                content = content[:MAX_CHARS]
            prepared.append({
                "chunk_id": r["chunk_id"],
                "content": content,
                "chunk_index": r["chunk_index"],
                "symbol": r["symbol"],
                "year": r["year"],
                "market": r["market"],
                "document_type": r["document_type"],
                "source_provider": r["source_provider"],
                "published_date": str(r["published_date"]) if r["published_date"] else "",
            })

        # 标记跳过的 chunks（避免反复拉取）
        if skip_ids:
            await pool.execute("""
                UPDATE chunks SET qdrant_point_id = id
                WHERE id = ANY($1)
            """, skip_ids)

        if not prepared:
            continue

        # 逐批 Embedding → Qdrant → PG（流水线，concurrency 路并发）
        sub_batches = [prepared[i:i + batch_size] for i in range(0, len(prepared), batch_size)]

        # 每次并发 concurrency 个 sub_batch
        for wave_start in range(0, len(sub_batches), concurrency):
            wave = sub_batches[wave_start:wave_start + concurrency]

            # 并发 Embedding
            embed_tasks = [
                embed_batch(http_client, [p["content"] for p in batch])
                for batch in wave
            ]
            embed_results = await asyncio.gather(*embed_tasks, return_exceptions=True)

            # 处理结果
            all_points = []
            all_chunk_ids = []
            all_point_ids = []

            for batch, result in zip(wave, embed_results):
                if isinstance(result, Exception):
                    failed += len(batch)
                    if failed <= 50:
                        print(f"  [EMBED ERROR] {result}")
                    continue

                for item, vec in zip(batch, result):
                    pid = str(uuid.uuid4())
                    all_chunk_ids.append(item["chunk_id"])
                    all_point_ids.append(pid)
                    all_points.append(PointStruct(
                        id=pid,
                        vector=vec,
                        payload={
                            "symbol": item["symbol"],
                            "year": item["year"],
                            "market": item["market"],
                            "chunk_index": item["chunk_index"],
                            "content": item["content"][:2000],
                            "document_type": item["document_type"],
                            "source_provider": item["source_provider"],
                            "published_date": item["published_date"],
                        },
                    ))

            # Upsert Qdrant
            if all_points:
                try:
                    await asyncio.to_thread(
                        qdrant.upsert,
                        collection_name=collection,
                        points=all_points,
                        wait=False,
                    )
                except Exception as e:
                    print(f"  [QDRANT ERROR] {e}")
                    await asyncio.sleep(2)
                    continue

                # 回写 qdrant_point_id
                await pool.execute("""
                    UPDATE chunks c
                    SET qdrant_point_id = u.point_id::uuid
                    FROM unnest($1::uuid[], $2::uuid[]) AS u(chunk_id, point_id)
                    WHERE c.id = u.chunk_id
                """, all_chunk_ids, all_point_ids)

                processed += len(all_points)

        # 进度报告（每 30s）
        now = time.time()
        if now - last_report >= 30:
            elapsed = now - t_start
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = total_remaining - processed
            eta_min = (remaining / rate / 60) if rate > 0 else 0
            print(
                f"  [{processed:,}/{total_remaining:,}] "
                f"{rate:.1f} chunks/s | "
                f"fail={failed} | "
                f"ETA={eta_min:.0f}min ({eta_min/60:.1f}h)"
            )
            sys.stdout.flush()
            last_report = now

    # 完成
    elapsed = time.time() - t_start
    rate = processed / elapsed if elapsed > 0 else 0
    print()
    print("=" * 70)
    print(f"  完成！处理: {processed:,} | 跳过: {skipped:,} | 失败: {failed:,}")
    print(f"  耗时: {elapsed/60:.1f}min | 平均: {rate:.1f} chunks/s")

    info = qdrant.get_collection(collection)
    print(f"  Qdrant {collection}: {info.points_count:,} points")
    print("=" * 70)

    await http_client.aclose()
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
