"""
Qdrant Collection 初始化脚本
============================
基于 24_数据底座规范.md 第五章，创建 documents_{market} Collection。

用法:
    pip install qdrant-client
    python init_qdrant.py

环境变量:
    QDRANT_HOST (默认: localhost)
    QDRANT_PORT (默认: 6333)
    QDRANT_API_KEY (可选)
"""

import os
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams,
    Distance,
    CollectionConfig,
    OptimizersConfigDiff,
)

# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

# Collection 定义（规范 5.1）
# 向量维度 2560 = Qwen3-Embedding-4B 默认输出维度
COLLECTIONS = [
    {
        "name": "documents_cn",
        "description": "A股文档（年报、公告、研报等）",
        "vector_size": 2560,
        "distance": Distance.COSINE,
        "domain": "finance",
    },
    {
        "name": "documents_hk",
        "description": "港股文档",
        "vector_size": 2560,
        "distance": Distance.COSINE,
        "domain": "finance",
    },
    {
        "name": "documents_us",
        "description": "美股文档",
        "vector_size": 2560,
        "distance": Distance.COSINE,
        "domain": "finance",
    },
]


def create_client() -> QdrantClient:
    """创建 Qdrant 客户端"""
    client = QdrantClient(
        host=QDRANT_HOST,
        port=QDRANT_PORT,
        api_key=QDRANT_API_KEY,
    )
    print(f"[OK] 连接 Qdrant @ {QDRANT_HOST}:{QDRANT_PORT}")
    return client


def create_collections(client: QdrantClient) -> None:
    """创建所有 Collection"""
    print("\n===== 创建 Collections =====")
    for col in COLLECTIONS:
        existing = client.get_collections().collections
        exists = any(c.name == col["name"] for c in existing)

        if not exists:
            client.create_collection(
                collection_name=col["name"],
                vectors_config=VectorParams(
                    size=col["vector_size"],
                    distance=col["distance"],
                ),
                optimizers_config=OptimizersConfigDiff(
                    indexing_threshold=20000,
                ),
            )
            print(f"  [+] {col['name']}  (已创建, dim={col['vector_size']}, dist={col['distance'].value})")
        else:
            print(f"  [=] {col['name']}  (已存在，跳过)")


def verify(client: QdrantClient) -> None:
    """验证最终状态"""
    print("\n===== 验证结果 =====")
    collections = client.get_collections().collections
    for col in COLLECTIONS:
        match = next((c for c in collections if c.name == col["name"]), None)
        if match:
            info = client.get_collection(col["name"])
            points = info.points_count
            print(f"  {col['name']}  →  {points} points, vector_size={col['vector_size']}")
        else:
            print(f"  {col['name']}  →  NOT FOUND!")


def main():
    print("=" * 50)
    print("  Qdrant Collection 初始化工具")
    print("  基于 24_数据底座规范.md 第五章")
    print("=" * 50)

    client = create_client()
    create_collections(client)
    verify(client)

    print("\n" + "=" * 50)
    print("  初始化完成!")
    print("=" * 50)
    print("""
Collection 规范:
  documents_cn  - A股文档（年报、公告、研报等）
  documents_hk  - 港股文档
  documents_us  - 美股文档

向量配置:
  维度: 2560 (Qwen3-Embedding-4B)
  距离: Cosine

Payload 标准（8字段）:
  document_id, chunk_id, content, page,
  section, title, tags, language
""")


if __name__ == "__main__":
    main()
