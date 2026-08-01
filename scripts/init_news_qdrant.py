#!/usr/bin/env python3
"""News Intelligence Pipeline — Qdrant Collections 初始化

创建新闻管线所需的向量集合：
  - news_embeddings: 文章 embedding（去重 + 语义搜索）
  - news_events: 事件 embedding（事件语义检索）

用法:
  python3 scripts/init_news_qdrant.py
  python3 scripts/init_news_qdrant.py --qdrant-host localhost --qdrant-port 6333

环境变量:
  QDRANT_HOST (default: localhost)
  QDRANT_PORT (default: 6333)
  EMBEDDING_DIM (default: 2560)
"""

import argparse
import os
import sys

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, HnswConfigDiff

# ── 配置 ──────────────────────────────────────────────────────────────────────

QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6333"))
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "2560"))

# ── Collections 定义 ──────────────────────────────────────────────────────────

COLLECTIONS = {
    "news_embeddings": {
        "description": "新闻文章 embedding（去重 + 语义搜索）",
        "vectors": VectorParams(
            size=EMBEDDING_DIM,
            distance=Distance.COSINE,
        ),
        "hnsw_config": HnswConfigDiff(m=16, ef_construct=100),
    },
    "news_events": {
        "description": "新闻事件 embedding（事件语义检索）",
        "vectors": VectorParams(
            size=EMBEDDING_DIM,
            distance=Distance.COSINE,
        ),
        "hnsw_config": HnswConfigDiff(m=16, ef_construct=100),
    },
}


def main():
    parser = argparse.ArgumentParser(description="Initialize News Qdrant Collections")
    parser.add_argument("--qdrant-host", default=QDRANT_HOST, help="Qdrant host")
    parser.add_argument("--qdrant-port", type=int, default=QDRANT_PORT, help="Qdrant port")
    parser.add_argument("--embedding-dim", type=int, default=EMBEDDING_DIM, help="Embedding dimension")
    args = parser.parse_args()

    print(f"Connecting to Qdrant at {args.qdrant_host}:{args.qdrant_port}...")

    try:
        client = QdrantClient(host=args.qdrant_host, port=args.qdrant_port, timeout=10)
        # 验证连接
        client.get_collections()
        print("✓ Qdrant connected")
    except Exception as e:
        print(f"✗ Cannot connect to Qdrant: {e}")
        sys.exit(1)

    for name, config in COLLECTIONS.items():
        # 更新维度（如果命令行指定了不同值）
        vectors = VectorParams(size=args.embedding_dim, distance=Distance.COSINE)

        exists = client.collection_exists(name)
        if exists:
            info = client.get_collection(name)
            print(f"  ✓ {name} already exists (points: {info.points_count})")
            continue

        client.create_collection(
            collection_name=name,
            vectors_config=vectors,
            hnsw_config=config["hnsw_config"],
        )
        print(f"  ✓ Created {name} (dim={args.embedding_dim})")

    # 汇总
    collections = client.get_collections().collections
    news_collections = [c.name for c in collections if c.name.startswith("news_")]
    print(f"\n✓ News Collections ready: {news_collections}")

    client.close()


if __name__ == "__main__":
    main()
