"""DP-B2 端到端验收：真实 DB 验证三种入口统一 acquire metadata + checksum 判重

验收点：
  1. MinIO 扫描入口 register_pending_from_minio 落库 metadata.acquire 结构完整
     （source_type/trigger/priority/checksum/origin/acquired_at）
  2. 手动导入入口 _run_ingest 落库 metadata.acquire 结构完整 + sha256 checksum
  3. checksum 判重生效：重复扫描/重复导入均跳过（added=0）
最后清理测试数据。

说明：MinIO list_objects 与手动导入的 chunk/embed/qdrant 均 mock（避免依赖外部服务），
      documents 记录真实写入 PostgreSQL 以验证 metadata 落库。
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path

_LANGGRAPH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_LANGGRAPH))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(_LANGGRAPH).parent / ".env", override=False)

from unittest.mock import AsyncMock, patch  # noqa: E402

from pipelines.document_pipeline import doc_pipeline  # noqa: E402
from tools.postgres import postgres_tool  # noqa: E402


MARKET = "d"
SYMBOL = "DPB2" + uuid.uuid4().hex[:6].upper()
YEAR = 2025
OBJ_KEY = f"{MARKET}/{SYMBOL}/annual_report/{YEAR}/report.pdf"


async def verify_minio_scan() -> tuple[str, str]:
    """MinIO 扫描入口：落库 acquire 结构 + 判重"""
    doc_id = str(uuid.uuid4())
    with patch("tools.minio.minio_tool.list_objects", new=AsyncMock(
        return_value=[OBJ_KEY]
    )), patch("runtime.queue.task_queue"):
        result = await doc_pipeline.register_pending_from_minio(
            bucket="documents", prefix=""
        )
    assert result["added"] == 1, result

    rows = await postgres_tool.query(
        "SELECT object_key, metadata->'acquire' AS acquire FROM documents "
        "WHERE object_key = $1",
        OBJ_KEY,
    )
    assert rows, "MinIO 扫描后应存在 documents 记录"
    acq = rows[0]["acquire"]
    if isinstance(acq, str):
        acq = json.loads(acq)
    _assert_acquire(acq, source_type="annual_report", trigger="minio_scan",
                    priority="low", checksum=OBJ_KEY, origin="minio")
    print("[PASS] MinIO 扫描入口落库统一 acquire metadata")
    print("       ->", json.dumps(acq, ensure_ascii=False))

    # checksum 判重：重复扫描应跳过
    with patch("tools.minio.minio_tool.list_objects", new=AsyncMock(
        return_value=[OBJ_KEY]
    )), patch("runtime.queue.task_queue"):
        result2 = await doc_pipeline.register_pending_from_minio(
            bucket="documents", prefix=""
        )
    assert result2["added"] == 0, result2
    print("[PASS] MinIO 扫描 checksum/object_key 判重生效（重复扫描 added=0）")
    return doc_id, OBJ_KEY


async def verify_manual_ingest() -> tuple[str, str]:
    """手动导入入口：落库 acquire 结构 + sha256 checksum 判重"""
    from api.knowledge import _run_ingest

    doc_id = str(uuid.uuid4())
    content = f"# DP-B2 手动导入测试\n\n唯一内容 {uuid.uuid4().hex}。"
    tmp_md = Path("/tmp") / f"dpb2_{uuid.uuid4().hex[:6]}.md"
    tmp_md.write_text(content, encoding="utf-8")

    with patch("tools.chunker.chunk_markdown", return_value=[
        {"content": "唯一内容。", "heading": ""}
    ]), patch("tools.embedding.embedding_tool.embed", new=AsyncMock(
        return_value=[[0.1, 0.2]]
    )), patch("tools.qdrant.qdrant_tool.upsert", new=AsyncMock()):
        stats = await _run_ingest(str(tmp_md), "documents_cn")
    assert stats["added"] == 1, stats

    rows = await postgres_tool.query(
        "SELECT metadata->'acquire' AS acquire, metadata->>'source_path' AS sp "
        "FROM documents WHERE metadata->'acquire'->>'source_path' = $1",
        str(tmp_md),
    )
    assert rows, "手动导入后应存在 documents 记录"
    acq = rows[0]["acquire"]
    if isinstance(acq, str):
        acq = json.loads(acq)
    _assert_acquire(acq, source_type="markdown", trigger="manual_ingest",
                    priority="normal", checksum=None, origin="manual")
    assert acq["checksum"] and len(acq["checksum"]) == 64, acq
    print("[PASS] 手动导入入口落库统一 acquire metadata + sha256 checksum")
    print("       ->", json.dumps(acq, ensure_ascii=False))

    # checksum 判重：相同内容重复导入应跳过
    with patch("tools.chunker.chunk_markdown", return_value=[
        {"content": "唯一内容。", "heading": ""}
    ]), patch("tools.embedding.embedding_tool.embed", new=AsyncMock(
        return_value=[[0.1, 0.2]]
    )), patch("tools.qdrant.qdrant_tool.upsert", new=AsyncMock()):
        stats2 = await _run_ingest(str(tmp_md), "documents_cn")
    assert stats2["added"] == 0 and stats2["skipped"] == 1, stats2
    print("[PASS] 手动导入 sha256 checksum 判重生效（重复导入 added=0）")
    return doc_id, str(tmp_md)


def _assert_acquire(acq: dict, **expect) -> None:
    for k, v in expect.items():
        if v is None:
            continue
        assert acq.get(k) == v, f"acquire.{k} 期望 {v!r} 实际 {acq.get(k)!r}"
    for required in ("source_type", "trigger", "priority", "origin", "acquired_at"):
        assert required in acq, f"acquire 缺字段 {required}: {acq}"


async def main() -> int:
    obj_key = ""
    sp = ""
    try:
        doc_id, obj_key = await verify_minio_scan()

        doc_id2, sp = await verify_manual_ingest()
    finally:
        # 清理：按 object_key/source_path 删除
        await postgres_tool.execute(
            "DELETE FROM documents WHERE object_key = $1", obj_key
        )
        await postgres_tool.execute(
            "DELETE FROM documents WHERE metadata->'acquire'->>'source_path' = $1",
            sp,
        )
        print("[CLEAN] 测试数据已清理")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))