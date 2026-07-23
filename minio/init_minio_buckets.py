"""
MinIO Bucket 初始化脚本
=======================
基于 24_数据底座规范.md 第二章，创建 5 个 Bucket 并设置目录结构、版本控制、生命周期策略。

用法:
    pip install minio
    python init_minio_buckets.py

环境变量:
    MINIO_ENDPOINT   (默认: localhost:9000)
    MINIO_ACCESS_KEY  (默认: minioadmin)
    MINIO_SECRET_KEY  (默认: minioadmin)
    MINIO_SECURE      (默认: false)
"""

import os
import json
import io
from datetime import datetime, timezone
from minio import Minio
from minio.commonconfig import ENABLED
from minio.lifecycleconfig import LifecycleConfig, Expiration, Rule
from minio.versioningconfig import VersioningConfig

# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────
ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# Bucket 定义（规范 2.1）
BUCKETS = ["documents", "knowledge", "datasets", "artifacts", "staging"]

# 需要启用版本控制的 Bucket（规范 9.1）
VERSIONED_BUCKETS = ["documents", "knowledge", "artifacts"]

# 目录结构定义（规范 2.2）
DIRECTORY_STRUCTURE = {
    # ── documents: 原始文档 ──
    # 路径规范: {market}/{symbol}/{doc_type}/{year}/
    "documents": [
        # 市场目录
        "cn/", "hk/", "us/",
        # 示例：A股
        "cn/600519/annual_report/2025/",
        "cn/600519/annual_report/2024/",
        "cn/600519/announcement/2025/",
        "cn/600519/news/",
        "cn/600519/research/",
        "cn/600519/prospectus/",
        # 示例：港股
        "hk/00700/annual_report/2025/",
        # 示例：美股
        "us/aapl/annual_report/2025/",
    ],

    # ── knowledge: Agent 提取的结构化知识 ──
    # 路径规范: {market}/{symbol}/{doc_type}/{year}/
    "knowledge": [
        "cn/", "hk/", "us/",
        "cn/600519/annual_report/2025/",
        "hk/00700/annual_report/2025/",
        "us/aapl/annual_report/2025/",
    ],

    # ── datasets: 外部数据集 ──
    # 路径规范: {source}/
    "datasets": [
        "tushare/",
        "akshare/",
        "wind/",
        "macro/",
        "industry/",
    ],

    # ── artifacts: Agent 生成产物 ──
    # 路径规范: {type}/
    "artifacts": [
        "research/",
        "markdown/",
        "pdf/",
        "ppt/",
        "obsidian/",
    ],

    # ── staging: 临时处理 ──
    # 路径规范: {status}/
    "staging": [
        "download/",
        "ocr/",
        "chunk/",
        "tmp/",
        "retry/",
    ],
}

# metadata.json 模板（对齐规范 2.4 + schemas/metadata.schema.json）
METADATA_TEMPLATE = {
    "id": "",
    "market": "",
    "symbol": "",
    "document_type": "",
    "year": None,
    "language": "zh",
    "source": "",
    "publish_date": "",
    "parser": "docling",
    "parser_version": "",
    "status": "pending",
    "hash": "",
    "created_time": "",
    "updated_time": "",
    "version": 1,
    "embedding_model": "Qwen3-Embedding-4B",
    "embedding_version": "v1",
    "chunk_strategy": "heading",
    "domain_fields": {}
}


def create_client() -> Minio:
    """创建 MinIO 客户端"""
    client = Minio(
        ENDPOINT,
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        secure=SECURE,
    )
    print(f"[OK] 连接 MinIO @ {ENDPOINT} (secure={SECURE})")
    return client


def create_buckets(client: Minio) -> None:
    """创建所有 Bucket"""
    print("\n===== 创建 Buckets =====")
    for bucket in BUCKETS:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            print(f"  [+] {bucket}/  (已创建)")
        else:
            print(f"  [=] {bucket}/  (已存在，跳过)")


def enable_versioning(client: Minio) -> None:
    """对指定 Bucket 启用版本控制"""
    print("\n===== 启用版本控制 =====")
    for bucket in VERSIONED_BUCKETS:
        client.set_bucket_versioning(bucket, VersioningConfig(ENABLED))
        print(f"  [V] {bucket}/  版本控制已启用")


def set_lifecycle(client: Minio) -> None:
    """设置 staging Bucket 的 30 天自动清理策略"""
    print("\n===== 设置生命周期策略 =====")
    config = LifecycleConfig(
        rules=[
            Rule(
                rule_id="auto-cleanup-30d",
                status=ENABLED,
                expiration=Expiration(days=30),
            )
        ]
    )
    client.set_bucket_lifecycle("staging", config)
    print("  [T] staging/  30 天自动清理已设置")


def create_directories(client: Minio) -> None:
    """
    在 MinIO 中创建目录占位对象。
    MinIO 没有真正的目录，通过上传 key 以 '/' 结尾的 0 字节对象来标识目录。
    """
    print("\n===== 创建目录结构 =====")
    empty = io.BytesIO(b"")

    for bucket, prefixes in DIRECTORY_STRUCTURE.items():
        for prefix in prefixes:
            client.put_object(
                bucket,
                prefix,
                empty,
                length=0,
                content_type="application/x-directory",
            )
            print(f"  [{bucket}] {prefix}")
        empty.seek(0)


def create_metadata_template(client: Minio) -> None:
    """
    在 documents Bucket 中放置 metadata.json 模板，
    供后续文档上传时参考填写。
    """
    print("\n===== 创建 metadata 模板 =====")
    data = json.dumps(METADATA_TEMPLATE, ensure_ascii=False, indent=2).encode("utf-8")
    client.put_object(
        "documents",
        "_templates/metadata.json",
        io.BytesIO(data),
        length=len(data),
        content_type="application/json",
    )
    print("  [M] documents/_templates/metadata.json")


def verify(client: Minio) -> None:
    """验证最终状态"""
    print("\n===== 验证结果 =====")
    for bucket in BUCKETS:
        objects = list(client.list_objects(bucket, recursive=True))
        dir_count = sum(1 for o in objects if o.object_name.endswith("/"))
        file_count = len(objects) - dir_count
        print(f"  {bucket}/  →  {dir_count} 个目录, {file_count} 个文件")


def main():
    print("=" * 50)
    print("  MinIO Bucket 初始化工具")
    print("  基于 24_数据底座规范.md")
    print("=" * 50)

    client = create_client()
    create_buckets(client)
    enable_versioning(client)
    set_lifecycle(client)
    create_directories(client)
    create_metadata_template(client)
    verify(client)

    print("\n" + "=" * 50)
    print("  初始化完成!")
    print("=" * 50)
    print("""
目录规范:
  documents/{market}/{symbol}/{doc_type}/{year}/
  knowledge/{market}/{symbol}/{doc_type}/{year}/
  datasets/{source}/
  artifacts/{type}/
  staging/{status}/

市场代码: cn / hk / us
文档类型: annual_report / quarterly_report / announcement /
          news / research / prospectus
""")


if __name__ == "__main__":
    main()
