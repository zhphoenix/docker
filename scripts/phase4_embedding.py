#!/usr/bin/env python3
"""
Phase 4: Embedding 批量处理脚本
================================
从 PostgreSQL 读取未嵌入的 chunks，调用 Embedding 服务向量化，
写入 Qdrant，并更新 PostgreSQL 中的 qdrant_point_id。

用法:
    pip install qdrant-client asyncpg httpx
    python phase4_embedding.py

环境变量（或直接修改下方配置）:
    PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DB
    QDRANT_HOST, QDRANT_PORT
    EMBEDDING_URL
"""

import asyncio
import logging
import os
import sys
import time
import uuid
from typing import Optional

import asyncpg
import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import (
    CollectionStatus,
    Distance,
    PointStruct,
    VectorParams,
    OptimizersConfigDiff,
)

# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5433"))
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "postgres")
PG_DB = os.getenv("PG_DB", "ai")

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

EMBEDDING_URL = os.getenv("EMBEDDING_URL", "http://localhost:8001/v1")

# 批处理参数
EMBED_BATCH_SIZE = 64       # 每次 Embedding 调用的文本数
QDRANT_BATCH_SIZE = 100     # 每次 Qdrant upsert 的点数
FETCH_BATCH_SIZE = 5000     # 每次从 PG 拉取的 chunk 数
MAX_RETRIES = 3             # Embedding 调用最大重试次数

# Collection 定义
COLLECTIONS = {
    "cn": "documents_cn",
    "hk": "documents_hk",
    "us": "documents_us",
}
VECTOR_SIZE = 2560  # Qwen3-Embedding-4B
DISTANCE = Distance.COSINE

# ──────────────────────────────────────────────
# 日志
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Qdrant Collection 管理
# ──────────────────────────────────────────────
def ensure_collections(client: QdrantClient) -> None:
    """确保所有 Collection 存在"""
    existing = {c.name for c in client.get_collections().collections}

    for market, col_name in COLLECTIONS.items():
        if col_name not in existing:
            client.create_collection(
                collection_name=col_name,
                vectors_config=VectorParams(
                    size=VECTOR_SIZE,
                    distance=DISTANCE,
                ),
                optimizers_config=OptimizersConfigDiff(
                    indexing_threshold=10000,
                ),
            )
            logger.info(f"[+] 创建 Collection: {col_name} (dim={VECTOR_SIZE}, dist=Cosine)")
        else:
            info = client.get_collection(col_name)
            logger.info(f"[=] {col_name} 已存在, {info.points_count} points")


# ──────────────────────────────────────────────
# Embedding 服务
# ──────────────────────────────────────────────
class EmbeddingClient:
    """Embedding 服务客户端，带重试和连接池"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0),
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
            )
        return self._client

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """向量化一批文本，带重试"""
        client = self._get_client()
        last_err = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await client.post(
                    f"{self.base_url}/embeddings",
                    json={"input": texts, "model": "embedding"},
                )
                resp.raise_for_status()
                data = resp.json()
                return [item["embedding"] for item in data["data"]]
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                last_err = e
                wait = 2 ** attempt
                logger.warning(
                    f"Embedding 调用失败 (attempt {attempt}/{MAX_RETRIES}): {e}, "
                    f"等待 {wait}s..."
                )
                await asyncio.sleep(wait)
            except httpx.HTTPStatusError as e:
                logger.error(f"Embedding HTTP 错误: {e.response.status_code}")
                raise

        raise RuntimeError(f"Embedding 调用失败，已重试 {MAX_RETRIES} 次: {last_err}")

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# ──────────────────────────────────────────────
# 核心处理逻辑
# ──────────────────────────────────────────────
async def get_remaining_chunks(
    pool: asyncpg.Pool, market: str, limit: int
) -> list[dict]:
    """从 PG 获取指定市场未嵌入的 chunks（含文档元数据）"""
    rows = await pool.fetch(
        """
        SELECT c.id AS chunk_id,
               c.document_id,
               c.chunk_index,
               c.content,
               c.page_start,
               c.page_end,
               c.heading,
               d.market,
               d.symbol,
               d.year,
               d.language,
               d.document_type
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE d.market = $1
          AND c.qdrant_point_id IS NULL
        ORDER BY d.id, c.chunk_index
        LIMIT $2
        """,
        market,
        limit,
    )
    return [dict(r) for r in rows]


async def update_qdrant_point_id(
    pool: asyncpg.Pool, chunk_ids: list[str], point_ids: list[str]
) -> None:
    """批量更新 PG 中的 qdrant_point_id"""
    # 使用 unnest 批量更新
    await pool.execute(
        """
        UPDATE chunks c
        SET qdrant_point_id = u.point_id::uuid
        FROM unnest($1::uuid[], $2::uuid[]) AS u(chunk_id, point_id)
        WHERE c.id = u.chunk_id
        """,
        chunk_ids,
        point_ids,
    )


async def process_market(
    market: str,
    pool: asyncpg.Pool,
    emb_client: EmbeddingClient,
    qdrant_client: QdrantClient,
) -> dict:
    """处理指定市场的所有剩余 chunks"""
    col_name = COLLECTIONS[market]
    stats = {"embedded": 0, "upserted": 0, "errors": 0}

    # 查询总数
    total_row = await pool.fetchval(
        """
        SELECT count(*) FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE d.market = $1 AND c.qdrant_point_id IS NULL
        """,
        market,
    )
    total_remaining = int(total_row)
    logger.info(f"[{market}] 剩余未嵌入 chunks: {total_remaining}")

    if total_remaining == 0:
        logger.info(f"[{market}] 无剩余 chunks，跳过")
        return stats

    processed = 0
    start_time = time.time()

    while True:
        # 拉取一批
        chunks = await get_remaining_chunks(pool, market, FETCH_BATCH_SIZE)
        if not chunks:
            break

        logger.info(
            f"[{market}] 拉取 {len(chunks)} chunks "
            f"(已处理 {processed}/{total_remaining})"
        )

        # 分批 Embedding + Upsert
        for i in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[i : i + EMBED_BATCH_SIZE]
            texts = [c["content"] for c in batch]

            try:
                # 调用 Embedding
                vectors = await emb_client.embed_batch(texts)
                stats["embedded"] += len(batch)

                # 构造 Qdrant points
                points = []
                chunk_ids = []
                point_ids = []

                for chunk, vector in zip(batch, vectors):
                    point_id = str(uuid.uuid4())
                    chunk_ids.append(str(chunk["chunk_id"]))
                    point_ids.append(point_id)

                    payload = {
                        "document_id": str(chunk["document_id"]),
                        "chunk_id": str(chunk["chunk_id"]),
                        "market": chunk["market"],
                        "symbol": chunk["symbol"],
                        "year": chunk["year"],
                        "page": chunk["page_start"],
                        "heading": chunk["heading"] or "",
                        "language": chunk["language"] or "zh",
                        "content": chunk["content"],
                    }

                    points.append(
                        PointStruct(
                            id=point_id,
                            vector=vector,
                            payload=payload,
                        )
                    )

                # 分批 upsert 到 Qdrant
                for j in range(0, len(points), QDRANT_BATCH_SIZE):
                    qdrant_batch = points[j : j + QDRANT_BATCH_SIZE]
                    await asyncio.to_thread(
                        qdrant_client.upsert,
                        collection_name=col_name,
                        points=qdrant_batch,
                        wait=False,
                    )
                    stats["upserted"] += len(qdrant_batch)

                # 更新 PG qdrant_point_id
                await update_qdrant_point_id(pool, chunk_ids, point_ids)

                processed += len(batch)
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                eta = (total_remaining - processed) / rate if rate > 0 else 0

                logger.info(
                    f"[{market}] 进度: {processed}/{total_remaining} "
                    f"({processed*100//total_remaining}%) | "
                    f"速率: {rate:.1f} chunks/s | "
                    f"ETA: {eta/60:.1f}min"
                )

            except Exception as e:
                stats["errors"] += len(batch)
                logger.error(
                    f"[{market}] 批次处理失败 ({len(batch)} chunks): {e}"
                )
                # 继续下一批，不中断
                processed += len(batch)
                continue

    elapsed = time.time() - start_time
    logger.info(
        f"[{market}] 完成! 耗时: {elapsed/60:.1f}min, "
        f"嵌入: {stats['embedded']}, "
        f"上传: {stats['upserted']}, "
        f"错误: {stats['errors']}"
    )
    return stats


# ──────────────────────────────────────────────
# 验证
# ──────────────────────────────────────────────
async def verify(pool: asyncpg.Pool, qdrant_client: QdrantClient) -> None:
    """验证最终状态"""
    logger.info("=" * 50)
    logger.info("  验证最终状态")
    logger.info("=" * 50)

    for market, col_name in COLLECTIONS.items():
        # PG 统计
        pg_stats = await pool.fetchrow(
            """
            SELECT count(*) AS total,
                   count(c.qdrant_point_id) AS embedded
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE d.market = $1
            """,
            market,
        )

        # Qdrant 统计
        try:
            info = qdrant_client.get_collection(col_name)
            qdrant_count = info.points_count
        except Exception:
            qdrant_count = "N/A"

        logger.info(
            f"[{market}] {col_name}: "
            f"PG total={pg_stats['total']}, "
            f"PG embedded={pg_stats['embedded']}, "
            f"Qdrant points={qdrant_count}"
        )


# ──────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────
async def main():
    logger.info("=" * 50)
    logger.info("  Phase 4: Embedding 批量处理")
    logger.info("  Qwen3-Embedding-4B → Qdrant")
    logger.info("=" * 50)

    # 连接 PostgreSQL
    pool = await asyncpg.create_pool(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASSWORD,
        database=PG_DB,
        min_size=2,
        max_size=5,
    )
    logger.info(f"[OK] PostgreSQL 连接: {PG_HOST}:{PG_PORT}/{PG_DB}")

    # 连接 Qdrant
    qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    logger.info(f"[OK] Qdrant 连接: {QDRANT_HOST}:{QDRANT_PORT}")

    # 确保 Collections 存在
    ensure_collections(qdrant_client)

    # Embedding 客户端
    emb_client = EmbeddingClient(EMBEDDING_URL)
    logger.info(f"[OK] Embedding 服务: {EMBEDDING_URL}")

    # 测试 Embedding 服务
    try:
        test_vec = await emb_client.embed_batch(["test"])
        logger.info(f"[OK] Embedding 测试成功, 向量维度: {len(test_vec[0])}")
    except Exception as e:
        logger.error(f"[FAIL] Embedding 服务不可用: {e}")
        await emb_client.close()
        await pool.close()
        sys.exit(1)

    # 处理各市场
    total_stats = {"embedded": 0, "upserted": 0, "errors": 0}
    markets_to_process = ["cn", "hk", "us"]

    for market in markets_to_process:
        # 检查该市场是否有文档
        doc_count = await pool.fetchval(
            "SELECT count(*) FROM documents WHERE market = $1", market
        )
        if int(doc_count) == 0:
            logger.info(f"[{market}] 无文档，跳过")
            continue

        logger.info(f"\n{'='*40}")
        logger.info(f"  开始处理: {market.upper()} 市场")
        logger.info(f"  文档数: {doc_count}")
        logger.info(f"{'='*40}")

        stats = await process_market(market, pool, emb_client, qdrant_client)
        for k in total_stats:
            total_stats[k] += stats[k]

    # 验证
    await verify(pool, qdrant_client)

    # 总结
    logger.info("\n" + "=" * 50)
    logger.info("  Phase 4 完成!")
    logger.info(f"  总嵌入: {total_stats['embedded']}")
    logger.info(f"  总上传: {total_stats['upserted']}")
    logger.info(f"  总错误: {total_stats['errors']}")
    logger.info("=" * 50)

    # 清理
    await emb_client.close()
    await pool.close()
    qdrant_client.close()


if __name__ == "__main__":
    asyncio.run(main())
