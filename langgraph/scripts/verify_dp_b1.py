"""DP-B1 端到端验收：真实 DB 验证阶段记录写入 task_logs 与 documents.metadata.processing

临时创建一条测试 documents + tasks，驱动 StageTracker 走 enter/complete，
查询确认：
  1. task_logs 出现阶段记录（stage 字段 = 阶段名，level = info/error）
  2. documents.metadata->'processing'->'stages' 反映各阶段状态
最后清理测试数据。
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path

_LANGGRAPH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_LANGGRAPH))

from dotenv import load_dotenv

load_dotenv(Path(_LANGGRAPH).parent / ".env", override=False)

from pipelines.stages import Stage, StageTracker, StageStatus  # noqa: E402
from tools.postgres import postgres_tool  # noqa: E402


async def main() -> int:
    doc_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    symbol = "DPB1" + uuid.uuid4().hex[:6].upper()

    # 准备测试数据
    await postgres_tool.execute(
        "INSERT INTO tasks (id, task_type, title, status) VALUES ($1, 'dp_b1_verify', $2, 'running')",
        task_id, f"DP-B1 verify {task_id[:8]}",
    )
    await postgres_tool.execute(
        "INSERT INTO documents (id, market, symbol, company, year, document_type, status, parser, chunk_count, metadata, bucket, object_key) "
        "VALUES ($1, 'cn', $2, '', 2025, 'annual_report', 'pending', 'docling', 0, $3::jsonb, 'documents', $4)",
        doc_id, symbol, json.dumps({"source": "dp_b1_verify"}),
        f"cn/{symbol}/annual_report/2025/report.pdf",
    )

    tracker = StageTracker(doc_id, task_id=task_id)
    await tracker.load(postgres_tool)
    tracker.set_metadata(parser="docling", routing_strategy="annual_report", embedding_model="test-model")

    # 驱动若干阶段
    await tracker.enter(postgres_tool, Stage.ACQUIRE, "acquire doc")
    await tracker.complete(postgres_tool, Stage.ACQUIRE, "acquired")
    await tracker.enter(postgres_tool, Stage.PARSE, "parse")
    await tracker.complete(postgres_tool, Stage.PARSE, "parsed")
    await tracker.enter(postgres_tool, Stage.CHUNK, "chunk")
    await tracker.fail(postgres_tool, Stage.CHUNK, "chunk failed (simulated)")

    # 断言 1: documents.metadata.processing.stages
    rows = await postgres_tool.query(
        "SELECT metadata->'processing' AS processing FROM documents WHERE id = $1", doc_id
    )
    proc = rows[0]["processing"]
    if isinstance(proc, str):
        proc = json.loads(proc)  # asyncpg 把 jsonb 返回为 str
    stages = {s["stage"]: s for s in proc["stages"]}
    assert proc["parser"] == "docling", proc
    assert proc["routing_strategy"] == "annual_report", proc
    assert stages["acquire"]["status"] == StageStatus.SUCCESS.value, stages
    assert stages["parse"]["status"] == StageStatus.SUCCESS.value, stages
    assert stages["chunk"]["status"] == StageStatus.FAILED.value, stages
    assert stages["chunk"]["error"] == "chunk failed (simulated)", stages
    assert stages["acquire"]["duration_ms"] is not None, stages
    print("[PASS] documents.metadata.processing.stages 完整反映各阶段")
    print("       ->", json.dumps(proc, ensure_ascii=False))

    # 断言 2: task_logs 记录（stage 字段）
    logs = await postgres_tool.query(
        "SELECT level, message, stage FROM task_logs WHERE task_id = $1 ORDER BY created_at ASC", task_id
    )
    stage_set = {row["stage"] for row in logs}
    assert "acquire" in stage_set and "parse" in stage_set and "chunk" in stage_set, logs
    err_logs = [row for row in logs if row["stage"] == "chunk"]
    assert err_logs and err_logs[-1]["level"] == "error", logs
    print("[PASS] task_logs 含 acquire/parse/chunk 阶段记录，chunk 失败为 error 级")
    for row in logs:
        print("       [%s/%s] %s" % (row["stage"], row["level"], row["message"]))

    # 清理
    await postgres_tool.execute("DELETE FROM task_logs WHERE task_id = $1", task_id)
    await postgres_tool.execute("DELETE FROM tasks WHERE id = $1", task_id)
    await postgres_tool.execute("DELETE FROM documents WHERE id = $1", doc_id)
    print("[CLEAN] 测试数据已清理")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))