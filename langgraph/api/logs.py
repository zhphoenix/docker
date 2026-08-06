"""Agent Logs API — agent_runs + task_logs 联合视图（AC-P3-5）

- GET /api/logs?agent_id=&status=&keyword=&page=     联合日志列表（分页）
- GET /api/logs/{run_id}/trace                       单次运行的 Trace 详情（节点级 + 错误分类）
- GET /api/logs/export?agent_id=&status=&keyword=    CSV 下载

数据源：agent_runs（Pipeline Agent 运行记录，含 status/duration/error_category/trace）
      + task_logs（Workflow 任务级日志，经 tasks 关联 task_type）。
"""

import csv
import io
import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/logs", tags=["logs"])

# task_type ↔ agent 映射：联合视图中 task_logs 段按此过滤（agent 详情页只看相关任务日志）
TASK_TYPE_TO_AGENT = {
    "knowledge_ingestion": ("doc_pipeline", "doc_pipeline_verify", "ingest_minio", "upload_folder"),
    "news_intelligence": ("news", "news_pipeline"),
}


def _fmt_ts(ts) -> str | None:
    """datetime → ISO 字符串（asyncpg 返回 datetime 对象）"""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    return str(ts)


def _norm_trace(trace) -> list:
    """trace JSONB → list（asyncpg 可能返回 str 或 list）"""
    if isinstance(trace, str):
        try:
            return json.loads(trace)
        except (json.JSONDecodeError, TypeError):
            return []
    return trace or []


def _build_filters(agent_id: str, status: str, keyword: str) -> tuple[str, str, list]:
    """构造 agent_runs 段与 task_logs 段的 WHERE 子句与公共参数

    Returns:
        (runs_where, task_where, params) — 两段均引用同一参数序号
    """
    runs_clauses = []
    task_clauses = []
    params: list = []
    if agent_id:
        params.append(agent_id)
        runs_clauses.append(f"r.agent_id = ${len(params)}")
        task_types = TASK_TYPE_TO_AGENT.get(agent_id)
        if task_types:
            params.append(list(task_types))
            task_clauses.append(f"t.task_type = ANY(${len(params)})")
        else:
            task_clauses.append("FALSE")  # 未知 agent → task_logs 段不返回
    if status:
        params.append(status)
        runs_clauses.append(f"r.status = ${len(params)}")
        task_clauses.append(f"tl.level = ${len(params)}")
    if keyword:
        params.append(f"%{keyword}%")
        runs_clauses.append(
            f"(r.question ILIKE ${len(params)} OR r.error ILIKE ${len(params)})"
        )
        task_clauses.append(f"tl.message ILIKE ${len(params)}")
    runs_where = " AND ".join(runs_clauses) if runs_clauses else "TRUE"
    task_where = " AND ".join(task_clauses) if task_clauses else "TRUE"
    return runs_where, task_where, params


def _build_runs_filters(agent_id: str, status: str, keyword: str) -> tuple[str, list]:
    """仅 agent_runs 段的 WHERE 与参数（CSV 导出等单表场景）"""
    clauses = []
    params: list = []
    if agent_id:
        params.append(agent_id)
        clauses.append(f"r.agent_id = ${len(params)}")
    if status:
        params.append(status)
        clauses.append(f"r.status = ${len(params)}")
    if keyword:
        params.append(f"%{keyword}%")
        clauses.append(
            f"(r.question ILIKE ${len(params)} OR r.error ILIKE ${len(params)})"
        )
    where = " AND ".join(clauses) if clauses else "TRUE"
    return where, params


@router.get("")
async def list_logs(
    agent_id: str = Query(""),
    status: str = Query("", pattern="^(|running|completed|failed|success)$"),
    keyword: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Agent 运行日志 + 任务日志的联合视图（按时间倒序）"""
    where, task_where, params = _build_filters(agent_id, status, keyword)

    # 联合视图：agent_runs 为主，task_logs（经 tasks 关联）为辅
    base = f"""
        SELECT source, ts, entity, level, message, duration_ms, error_category, run_id, task_id
        FROM (
            SELECT
                'agent_run'::text AS source,
                r.created_at AS ts,
                r.agent_id AS entity,
                r.status AS level,
                COALESCE(r.question, '') AS message,
                r.duration_ms AS duration_ms,
                r.error_category AS error_category,
                r.id::text AS run_id,
                NULL::uuid AS task_id
            FROM agent_runs r
            WHERE {where}
            UNION ALL
            SELECT
                'task_log'::text AS source,
                tl.created_at AS ts,
                t.task_type AS entity,
                tl.level AS level,
                tl.message AS message,
                t.duration_ms AS duration_ms,
                NULL::text AS error_category,
                NULL::text AS run_id,
                tl.task_id AS task_id
            FROM task_logs tl
            JOIN tasks t ON t.id = tl.task_id
            WHERE {task_where}
        ) u
        ORDER BY ts DESC
    """

    total_rows = await postgres_tool.query(
        f"SELECT COUNT(*) AS total FROM ({base}) u",
        *params,
    )
    total = int(total_rows[0]["total"]) if total_rows else 0

    rows = await postgres_tool.query(
        f"{base} LIMIT $%d OFFSET $%d" % (len(params) + 1, len(params) + 2),
        *params,
        page_size,
        (page - 1) * page_size,
    )

    items = [
        {
            "source": r["source"],
            "time": _fmt_ts(r["ts"]),
            "entity": r["entity"],
            "level": r["level"],
            "message": r["message"],
            "duration_ms": r["duration_ms"],
            "error_category": r["error_category"],
            "run_id": r["run_id"],
            "task_id": str(r["task_id"]) if r["task_id"] else None,
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{run_id}/trace")
async def get_run_trace(run_id: str):
    """单次 Agent 运行的 Trace 详情（节点级轨迹 + 错误分类）"""
    try:
        uuid.UUID(run_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    rows = await postgres_tool.query(
        "SELECT id, agent_id, task_kind, status, question, duration_ms, "
        "error, error_category, tokens_in, tokens_out, trace, created_at "
        "FROM agent_runs WHERE id = $1",
        run_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    r = rows[0]
    trace = _norm_trace(r.get("trace"))

    # 节点级轨迹时间线：trace 元素支持 {node, status, duration_ms, ...}
    timeline = []
    for t in trace:
        if isinstance(t, dict):
            timeline.append(
                {
                    "node": t.get("node") or t.get("name") or t.get("step") or "step",
                    "status": t.get("status", "completed"),
                    "duration_ms": t.get("duration_ms"),
                    "detail": t.get("detail") or t.get("message"),
                }
            )

    return {
        "run_id": str(r["id"]),
        "agent_id": r["agent_id"],
        "task_kind": r["task_kind"],
        "status": r["status"],
        "question": r["question"],
        "duration_ms": r["duration_ms"],
        "error": r["error"],
        "error_category": r["error_category"],
        "tokens_in": r["tokens_in"],
        "tokens_out": r["tokens_out"],
        "created_at": _fmt_ts(r["created_at"]),
        "trace": trace,
        "timeline": timeline,
    }


@router.get("/export")
async def export_logs(
    agent_id: str = Query(""),
    status: str = Query("", pattern="^(|running|completed|failed|success)$"),
    keyword: str = Query(""),
):
    """导出过滤后的日志为 CSV（下载）"""
    where, params = _build_runs_filters(agent_id, status, keyword)
    rows = await postgres_tool.query(
        f"""
        SELECT r.created_at, r.agent_id, r.status, r.duration_ms,
               r.error_category, r.question, r.error
        FROM agent_runs r
        WHERE {where}
        ORDER BY r.created_at DESC
        """,
        *params,
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["time", "agent_id", "status", "duration_ms", "error_category", "question", "error"])
    for r in rows:
        writer.writerow(
            [
                _fmt_ts(r["created_at"]),
                r["agent_id"],
                r["status"],
                r["duration_ms"],
                r["error_category"] or "",
                (r["question"] or "").replace("\n", " "),
                (r["error"] or "").replace("\n", " "),
            ]
        )
    csv_data = buf.getvalue()

    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="agent_logs_{now}.csv"'
        },
    )