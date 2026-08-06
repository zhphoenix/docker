"""Acquire 统一入口元数据单元测试（DP-B2）

覆盖：
  - build_acquire_metadata 产出统一的 acquire block 结构
  - 三种采集入口（ManIO 扫描 / 上传 / 手动导入）metadata 结构一致
  - checksum 判重依据正确生成（sha256_hex）
  - merge_acquire_into_metadata 幂等合并、处理 str/json 输入

全部 mock，不触真实 DB。
"""

import json
import pytest
from unittest.mock import AsyncMock, patch

from pipelines.acquire import (
    AcquireOrigin,
    AcquirePriority,
    AcquireTrigger,
    build_acquire_metadata,
    merge_acquire_into_metadata,
    sha256_hex,
)
from pipelines.document_pipeline import DocumentPipeline
from tools.postgres import postgres_tool


def test_sha256_hex_deterministic():
    """同一内容应产出相同 SHA-256，str 与 bytes 等价"""
    assert sha256_hex("hello") == sha256_hex(b"hello")
    assert len(sha256_hex("hello")) == 64


def test_build_acquire_metadata_structure():
    """acquire block 应含 source_type/trigger/priority/origin/acquired_at"""
    meta = build_acquire_metadata(
        source_type="annual_report",
        trigger=AcquireTrigger.MINIO_SCAN,
        priority=AcquirePriority.LOW,
        checksum="obj-key",
        origin=AcquireOrigin.MINIO,
        object_key="obj-key",
    )
    assert "acquire" in meta
    block = meta["acquire"]
    assert block["source_type"] == "annual_report"
    assert block["trigger"] == "minio_scan"
    assert block["priority"] == "low"
    assert block["origin"] == "minio"
    assert block["checksum"] == "obj-key"
    assert block["object_key"] == "obj-key"
    assert "acquired_at" in block


def test_build_acquire_metadata_origin_defaults_to_trigger():
    """origin 缺省时取 trigger 值"""
    meta = build_acquire_metadata(
        source_type="markdown",
        trigger=AcquireTrigger.MANUAL_INGEST,
    )
    assert meta["acquire"]["origin"] == "manual_ingest"


def test_merge_acquire_into_metadata_preserves_base():
    """合并应保留既有字段并写入 acquire"""
    merged = merge_acquire_into_metadata(
        {"source_path": "/a/b.md", "ingest": "manual"},
        build_acquire_metadata(source_type="markdown", trigger="manual_ingest"),
    )
    assert merged["source_path"] == "/a/b.md"
    assert merged["ingest"] == "manual"
    assert merged["acquire"]["source_type"] == "markdown"


def test_merge_accepts_json_string_base():
    """base_metadata 为 JSON 字符串时可解析合并"""
    base = json.dumps({"source": "minio", "object_key": "k"})
    merged = merge_acquire_into_metadata(
        base,
        build_acquire_metadata(source_type="markdown", trigger="manual_ingest"),
    )
    assert merged["source"] == "minio"
    assert merged["acquire"]["trigger"] == "manual_ingest"


@patch("tools.postgres.postgres_tool")
def test_minio_scan_entry_metadata_uniform(mock_pg_raw):
    """MinIO 扫描入口：metadata.acquire 结构统一 + acquire.checksum 判重"""
    desc = DocumentPipeline()
    mock_pg = mock_pg_raw
    mock_pg.query = AsyncMock(return_value=[])  # 首个对象不存在 → 判重通过
    mock_pg.execute = AsyncMock()
    with patch("tools.minio.minio_tool.list_objects", new=AsyncMock(
        return_value=["cn/000001/annual_report/2024/report.pdf"]
    )), patch("runtime.queue.task_queue"), patch(
        "pipelines.document_pipeline.postgres_tool", mock_pg
    ):
        import asyncio
        result = asyncio.run(
            desc.register_pending_from_minio(bucket="documents", prefix="")
        )
    assert result["added"] == 1
    # 校验 INSERT 的 metadata JSON 结构
    insert_args = mock_pg.execute.call_args[0]
    metadata_json = insert_args[6]  # 0=sql,1=doc_id,2=mkt,3=symbol,4=year,5=doc_type,6=metadata
    meta = json.loads(metadata_json)
    assert meta["acquire"]["source_type"] == "annual_report"
    assert meta["acquire"]["trigger"] == "minio_scan"
    assert meta["acquire"]["priority"] == "low"
    assert meta["acquire"]["origin"] == "minio"
    assert meta["acquire"]["checksum"] == "cn/000001/annual_report/2024/report.pdf"
    # 保留既有字段
    assert meta["source"] == "minio"
    assert meta["acquire"]["object_key"] == "cn/000001/annual_report/2024/report.pdf"


@patch("tools.chunker.chunk_markdown")
@patch("tools.embedding.embedding_tool")
@patch("tools.qdrant.qdrant_tool")
@patch("api.knowledge.postgres_tool")
def test_manual_ingest_entry_metadata_uniform(mock_pg, mock_qd, mock_emb, mock_chunk):
    """手动导入入口：metadata.acquire 结构统一 + sha256 checksum 判重"""
    import asyncio
    import tempfile
    from pathlib import Path
    from api.knowledge import _run_ingest

    content = "# 测试文档\n\n这是第一章内容。"
    mock_pg.query = AsyncMock(return_value=[])  # 判重通过
    mock_pg.execute = AsyncMock()
    mock_chunk.return_value = [
        {"content": "这是第一章内容。", "heading": "第一章"}
    ]
    mock_emb.embed = AsyncMock(return_value=[[0.1, 0.2]])
    mock_qd.upsert = AsyncMock()

    with tempfile.TemporaryDirectory() as tmp:
        md_file = Path(tmp) / "doc.md"
        md_file.write_text(content, encoding="utf-8")
        stats = asyncio.run(_run_ingest(str(md_file), "documents_cn"))

    assert stats["added"] == 1
    # 找到 documents INSERT 调用并校验 metadata
    doc_insert = [c for c in mock_pg.execute.call_args_list if "INSERT INTO documents" in c[0][0]]
    assert doc_insert, "应存在 documents INSERT 调用"
    metadata_json = doc_insert[0][0][4]  # 0=sql,1=doc_id,2=file_name,3=chunk_count,4=metadata
    meta = json.loads(metadata_json)
    assert meta["acquire"]["source_type"] == "markdown"
    assert meta["acquire"]["trigger"] == "manual_ingest"
    assert meta["acquire"]["priority"] == "normal"
    assert meta["acquire"]["origin"] == "manual"
    assert meta["acquire"]["checksum"] == sha256_hex(content)
    # 保留既有字段
    assert meta["source_path"] == str(md_file)
    assert meta["ingest"] == "manual"


@patch("tools.chunker.chunk_markdown")
@patch("tools.embedding.embedding_tool")
@patch("tools.qdrant.qdrant_tool")
@patch("api.knowledge.postgres_tool")
def test_manual_ingest_dedup_by_checksum(mock_pg, mock_qd, mock_emb, mock_chunk):
    """手动导入：相同内容（checksum）重复导入应被跳过"""
    import asyncio
    import tempfile
    from pathlib import Path
    from api.knowledge import _run_ingest

    content = "# 重复文档\n\n内容相同。"
    mock_pg.query = AsyncMock(return_value=[{"1": 1}])  # 判重命中
    mock_pg.execute = AsyncMock()
    mock_chunk.return_value = [{"content": "内容相同。", "heading": ""}]
    mock_emb.embed = AsyncMock(return_value=[[0.1]])
    mock_qd.upsert = AsyncMock()

    with tempfile.TemporaryDirectory() as tmp:
        md_file = Path(tmp) / "dup.md"
        md_file.write_text(content, encoding="utf-8")
        stats = asyncio.run(_run_ingest(str(md_file), "documents_cn"))

    assert stats["added"] == 0
    assert stats["skipped"] == 1
    # 不应触发 documents INSERT
    doc_insert = [c for c in mock_pg.execute.call_args_list if "INSERT INTO documents" in c[0][0]]
    assert not doc_insert