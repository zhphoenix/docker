"""Task Worker - 后台任务处理器

职责:
  - 轮询 tasks 表中 pending 状态的任务
  - 根据 task_type 分发到对应处理器
  - 控制并发（同时只运行 1 个 Pipeline 任务）
  - 失败自动标记（由 Scheduler 负责重试）
"""

import asyncio
import json
import logging
from typing import Callable, Coroutine, Any

from runtime.queue import task_queue
from config.policy_loader import get_policy

logger = logging.getLogger(__name__)

# 任务处理器注册表
_handlers: dict[str, Callable[..., Coroutine[Any, Any, None]]] = {}

# 自管理任务状态的任务类型：handler 内部自行调用 complete/fail，
# Worker 循环不再重复标记完成/失败（避免覆盖 handler 内的状态）。
SELF_MANAGED_TYPES = {"upload_folder", "ingest_minio"}

_worker_task: asyncio.Task | None = None
_running = False
_current_task: str | None = None


def get_worker_status() -> dict:
    """返回 Worker 运行状态（供 API 展示，in-process 内存态）

    Returns:
        {
            "running": bool,
            "active_tasks": int,
            "current_task_id": str | None,
            "registered_handlers": [str],
        }
    """
    return {
        "running": _running,
        "active_tasks": 1 if _current_task else 0,
        "current_task_id": _current_task,
        "registered_handlers": list(_handlers.keys()),
    }


def register_handler(task_type: str, handler: Callable[..., Coroutine[Any, Any, None]]):
    """注册任务处理器

    Args:
        task_type: 任务类型（对应 tasks.task_type）
        handler: async 处理函数，接收 task dict 参数
    """
    _handlers[task_type] = handler
    logger.info("Task handler registered: %s", task_type)


async def _handle_doc_pipeline(task: dict) -> None:
    """处理 doc_pipeline 类型任务"""
    from pipelines.document_pipeline import doc_pipeline

    params = task.get("params", {}) or {}
    if isinstance(params, str):
        params = json.loads(params)
    limit = params.get("limit", 50)
    await doc_pipeline.process_pending_documents(limit=limit)


async def _handle_reembed(task: dict) -> None:
    """处理 re-embed 类型任务（重新向量化单个文档）"""
    from pipelines.document_pipeline import doc_pipeline

    params = task.get("params", {}) or {}
    if isinstance(params, str):
        params = json.loads(params)
    doc_id = params.get("document_id", "")
    if doc_id:
        await doc_pipeline.reembed_document(doc_id)


async def _handle_batch_embed(task: dict) -> None:
    """处理 batch_embed 类型任务（批量向量化）"""
    from services.batch_embed import run_batch_embed

    params = task.get("params", {}) or {}
    if isinstance(params, str):
        params = json.loads(params)
    collection = params.get("collection", "documents_cn")
    batch_size = params.get("batch_size", 16)
    limit = params.get("limit", 0)
    task_id = str(task.get("id", ""))
    await run_batch_embed(
        collection=collection, batch_size=batch_size,
        limit=limit, task_id=task_id,
    )


async def _handle_knowledge_extraction(task: dict) -> None:
    """处理 knowledge_extraction 类型任务（知识提取流水线）"""
    from graphs.knowledge_graph import build_knowledge_ingestion_graph
    from tools.postgres import postgres_tool

    params = task.get("params", {}) or {}
    if isinstance(params, str):
        params = json.loads(params)

    document_ids = params.get("document_ids", [])
    raw_texts = params.get("raw_texts", {})  # {doc_id: text}

    if not document_ids:
        logger.warning("[Worker] knowledge_extraction: no document_ids")
        return

    graph = build_knowledge_ingestion_graph()

    for doc_id in document_ids:
        # 获取文档内容
        raw_text = raw_texts.get(doc_id, "")
        if not raw_text:
            # 尝试从 chunks 表获取
            rows = await postgres_tool.query(
                "SELECT content FROM chunks WHERE document_id = $1 ORDER BY chunk_index",
                doc_id,
            )
            raw_text = "\n\n".join(r["content"] for r in rows)

        if not raw_text:
            logger.warning("[Worker] knowledge_extraction: no content for doc=%s", doc_id[:8])
            continue

        # 获取文档元数据
        doc_meta = await postgres_tool.query(
            "SELECT document_type, market, symbol, company FROM documents WHERE id = $1",
            doc_id,
        )
        doc_type = doc_meta[0].get("document_type", "") if doc_meta else ""

        # 执行知识提取 Graph
        initial_state = {
            "document_id": doc_id,
            "document_type": doc_type,
            "raw_text": raw_text,
            "source_metadata": doc_meta[0] if doc_meta else {},
            "chunks": [],
            "entities": [],
            "relations": [],
            "facts": [],
            "evidence": [],
            "conflicts": [],
            "confidence_score": 0.0,
            "stored_entity_ids": [],
            "stored_fact_ids": [],
            "errors": [],
        }

        try:
            result = await graph.ainvoke(initial_state)
            logger.info(
                "[Worker] knowledge_extraction done | doc=%s | entities=%d | facts=%d | errors=%d",
                doc_id[:8],
                len(result.get("stored_entity_ids", [])),
                len(result.get("stored_fact_ids", [])),
                len(result.get("errors", [])),
            )
        except Exception as e:
            logger.error("[Worker] knowledge_extraction failed | doc=%s | %s", doc_id[:8], e)
            raise


async def _handle_upload_folder(task: dict) -> None:
    """处理 upload_folder 类型任务（批量上传文件夹到 MinIO 并注册文档）"""
    from pathlib import Path
    from api.documents import _run_upload_folder_async, DEFAULT_BUCKET

    params = task.get("params", {}) or {}
    if isinstance(params, str):
        params = json.loads(params)

    target = Path(params.get("folder", ""))
    pdf_files = sorted(target.rglob("*.pdf")) if target.is_dir() else []
    pdf_files = [f for f in pdf_files if not f.name.startswith(".")]

    await _run_upload_folder_async(
        str(task["id"]),
        target,
        params.get("market", ""),
        params.get("bucket", DEFAULT_BUCKET),
        params.get("trigger", False),
        pdf_files,
    )


async def _handle_ingest_minio(task: dict) -> None:
    """处理 ingest_minio 类型任务（从 MinIO 扫描并注册 pending 文档）"""
    from api.knowledge import _run_ingest_minio_async, MinioIngestRequest

    params = task.get("params", {}) or {}
    if isinstance(params, str):
        params = json.loads(params)

    req = MinioIngestRequest(
        bucket=params.get("bucket", "documents"),
        prefix=params.get("prefix", ""),
        market=params.get("market", ""),
        trigger=params.get("trigger", False),
    )
    await _run_ingest_minio_async(str(task["id"]), req)


# 注册默认处理器
register_handler("doc_pipeline", _handle_doc_pipeline)
register_handler("re-embed", _handle_reembed)
register_handler("batch_embed", _handle_batch_embed)
register_handler("knowledge_extraction", _handle_knowledge_extraction)
register_handler("upload_folder", _handle_upload_folder)
register_handler("ingest_minio", _handle_ingest_minio)


async def _worker_loop():
    """Worker 主循环"""
    global _running
    _running = True

    poll_interval = get_policy("worker.poll_interval_seconds", 30)
    stale_after = get_policy("worker.stale_after_seconds", 300)
    logger.info("[Worker] Started | poll_interval=%ds | stale_after=%ds", poll_interval, stale_after)

    # 启动时回收僵尸 running 任务（上一进程崩溃遗留，避免永久卡住）
    try:
        recovered = await task_queue.recover_stale_tasks(stale_after)
        if recovered:
            logger.warning("[Worker] Recovered %d stale running task(s)", recovered)
    except Exception as e:
        logger.warning("[Worker] Recover stale tasks failed | %s", e)

    while _running:
        try:
            # 获取 pending 任务（按优先级 + 创建时间排序）
            pending = await task_queue.get_pending_tasks(limit=1)

            if not pending:
                await asyncio.sleep(poll_interval)
                continue

            task = pending[0]
            task_id = str(task["id"])
            task_type = task["task_type"]

            handler = _handlers.get(task_type)
            if not handler:
                logger.warning("[Worker] No handler for task_type=%s", task_type)
                await task_queue.fail_task(task_id, f"No handler for {task_type}")
                continue

            # 执行任务
            global _current_task
            _current_task = task_id
            logger.info(
                "[Worker] Processing | %s | type=%s | %s",
                task_id[:8], task_type, task.get("title", ""),
            )
            await task_queue.start_task(task_id)

            try:
                await handler(task)
                # 自管理任务由 handler 内部处理状态，Worker 不重复标记
                if task_type not in SELF_MANAGED_TYPES:
                    await task_queue.complete_task(task_id)
            except Exception as e:
                logger.error("[Worker] Task failed | %s | %s", task_id[:8], e)
                await task_queue.fail_task(task_id, str(e))
            finally:
                _current_task = None

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("[Worker] Loop error | %s", e)
            await asyncio.sleep(10)

    logger.info("[Worker] Stopped")


def start_worker() -> None:
    """启动后台 Worker（在 FastAPI lifespan 中调用）"""
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_worker_loop())
        logger.info("[Worker] Background task created")


def stop_worker() -> None:
    """停止 Worker"""
    global _running, _worker_task
    _running = False
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        _worker_task = None
        logger.info("[Worker] Background task cancelled")
