"""Agent Center 埋点 - agent_runs 与 agent_tool_stats 记录

埋点为 fire-and-forget 异步写入，不阻塞主流程；失败仅记录日志。
"""
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)


async def record_tool_call(
    tool_name: str,
    agent_id: str | None,
    duration_ms: int,
    success: bool,
    error_type: str | None = None,
) -> None:
    """记录一次 Tool 调用到 agent_tool_stats"""
    try:
        await postgres_tool.execute(
            "INSERT INTO agent_tool_stats (tool_name, agent_id, duration_ms, success, error_type) "
            "VALUES ($1, $2, $3, $4, $5)",
            tool_name,
            agent_id,
            duration_ms,
            success,
            error_type,
        )
    except Exception as e:
        logger.warning("record_tool_call failed: %s", e)


@asynccontextmanager
async def track_tool(tool_name: str, agent_id: str | None = None):
    """Tool 调用上下文：自动计时并记录统计（fire-and-forget）"""
    start = time.monotonic()
    error_type: str | None = None
    try:
        yield
    except Exception as e:
        error_type = type(e).__name__.lower()
        logger.warning("track_tool '%s' error: %s", tool_name, e)
        raise
    finally:
        duration_ms = int((time.monotonic() - start) * 1000)
        asyncio.create_task(
            record_tool_call(tool_name, agent_id, duration_ms, error_type is None, error_type)
        )


async def record_agent_run(
    agent_id: str,
    task_kind: str,
    status: str,
    question: str | None = None,
    duration_ms: int | None = None,
    error: str | None = None,
    error_category: str | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    trace: list[dict[str, Any]] | None = None,
) -> str | None:
    """记录一次 Agent 运行到 agent_runs，返回 run_id（失败返回 None）"""
    try:
        row = await postgres_tool.query(
            "INSERT INTO agent_runs "
            "(agent_id, task_kind, status, question, duration_ms, error, error_category, tokens_in, tokens_out, trace) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) "
            "RETURNING id",
            agent_id,
            task_kind,
            status,
            question,
            duration_ms,
            error,
            error_category,
            tokens_in,
            tokens_out,
            json.dumps(trace or [], ensure_ascii=False),
        )
        return str(row[0]["id"]) if row else None
    except Exception as e:
        logger.warning("record_agent_run failed: %s", e)
        return None


async def finish_agent_run(
    run_id: str,
    status: str,
    duration_ms: int | None = None,
    error: str | None = None,
    error_category: str | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    trace: list[dict[str, Any]] | None = None,
) -> None:
    """更新 Agent 运行的结束状态"""
    if not run_id:
        return
    try:
        await postgres_tool.execute(
            "UPDATE agent_runs SET status=$2, "
            "duration_ms=COALESCE($3, duration_ms), "
            "error=$4, error_category=$5, tokens_in=$6, tokens_out=$7, trace=$8 "
            "WHERE id=$1",
            run_id,
            status,
            duration_ms,
            error,
            error_category,
            tokens_in,
            tokens_out,
            json.dumps(trace or [], ensure_ascii=False),
        )
    except Exception as e:
        logger.warning("finish_agent_run failed: %s", e)


async def invoke_tracked(
    graph,
    initial_state: dict[str, Any],
    agent_id: str,
    task_kind: str = "pipeline",
    question: str | None = None,
    trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """统一 Graph 调用埋点包装器（AC-B3）

    在 Pipeline Agent（News Intelligence / Knowledge Ingestion）的调用入口处包裹
    graph.ainvoke，自动向 agent_runs 写入一条运行记录（task_kind=pipeline）。
    - 开始：record_agent_run(status='running')，返回 run_id
    - 结束：finish_agent_run(status='completed'/'failed'，含耗时与错误)
    - 埋点为 fire-and-forget，失败仅记录日志，不阻塞主流程
    - 禁止在节点层重复埋点：本包装器是唯一埋点入口

    Args:
        graph: 编译后的 LangGraph 图（有 ainvoke 方法）
        initial_state: 图的初始输入状态
        agent_id: 规范 Agent 名（如 news_intelligence / knowledge_ingestion）
        task_kind: 任务类型，Pipeline 默认 'pipeline'
        question: 人工可读的描述（如 source_id / document_id）
        trace: 可选 trace 列表

    Returns:
        graph.ainvoke 的返回结果（与未包装时一致）
    """
    start = time.monotonic()
    run_id = await record_agent_run(
        agent_id=agent_id,
        task_kind=task_kind,
        status="running",
        question=question,
        trace=trace,
    )
    error: str | None = None
    error_category: str | None = None
    try:
        return await graph.ainvoke(initial_state)
    except Exception as e:
        error = str(e)[:1000]
        error_category = type(e).__name__.lower()
        logger.warning("invoke_tracked '%s' error: %s", agent_id, e)
        await finish_agent_run(
            run_id,
            status="failed",
            duration_ms=int((time.monotonic() - start) * 1000),
            error=error,
            error_category=error_category,
            trace=trace,
        )
        raise
    finally:
        if not (error or error_category):
            try:
                await finish_agent_run(
                    run_id,
                    status="completed",
                    duration_ms=int((time.monotonic() - start) * 1000),
                    trace=trace,
                )
            except Exception as e:
                logger.warning("invoke_tracked finish failed: %s", e)