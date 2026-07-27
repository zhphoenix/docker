"""Resource Scheduler - 基于 APScheduler 的定时任务

Jobs:
  - daily_pipeline: 每日处理 pending 文档（触发 Pipeline）
  - weekly_consistency: 每周 Embedding 一致性检查
  - monthly_cleanup: 每月清理 staging + 过期数据
  - task_retry: 每 5 分钟重试失败任务（指数退避）
"""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config.policy_loader import get_policy

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _job_daily_pipeline():
    """每日文档处理 Pipeline"""
    from graph.pipeline import doc_pipeline

    logger.info("[Scheduler] Daily pipeline triggered")
    try:
        limit = get_policy("scheduler.daily_pipeline_limit", 100)
        stats = await doc_pipeline.process_pending_documents(limit=limit)
        logger.info("[Scheduler] Daily pipeline done | %s", stats)
    except Exception as e:
        logger.error("[Scheduler] Daily pipeline failed | %s", e)


async def _job_task_retry():
    """定期重试失败任务（指数退避）"""
    from graph.task_queue import task_queue
    from tools.postgres import postgres_tool

    try:
        # 查找可重试的失败任务
        failed_tasks = await postgres_tool.query(
            """
            SELECT id, retry_count, max_retries, finished_at
            FROM tasks
            WHERE status = 'failed'
              AND retry_count < max_retries
            ORDER BY finished_at ASC
            LIMIT 5
            """
        )

        if not failed_tasks:
            return

        now = datetime.now(timezone.utc)
        for task in failed_tasks:
            task_id = str(task["id"])
            delay = await task_queue.get_retry_delay(task_id)

            # 检查是否已过退避时间
            finished_at = task.get("finished_at")
            if finished_at:
                elapsed = (now - finished_at).total_seconds()
                if elapsed < delay:
                    continue

            success = await task_queue.retry_task(task_id)
            if success:
                logger.info(
                    "[Scheduler] Task retried | %s | retry=%d/%d",
                    task_id[:8], task["retry_count"] + 1, task["max_retries"],
                )
    except Exception as e:
        logger.error("[Scheduler] Task retry failed | %s", e)


async def _job_weekly_consistency():
    """每周 Embedding 一致性检查"""
    from tools.postgres import postgres_tool

    logger.info("[Scheduler] Weekly consistency check")
    try:
        # 查找 status=indexed 但 chunk_count=0 的异常文档
        orphans = await postgres_tool.query(
            """
            SELECT COUNT(*) as cnt FROM documents
            WHERE status = 'indexed' AND chunk_count = 0
            """
        )
        orphan_count = orphans[0]["cnt"] if orphans else 0

        # 查找有 chunks 但 status 不是 indexed 的文档
        inconsistent = await postgres_tool.query(
            """
            SELECT COUNT(DISTINCT d.id) as cnt
            FROM documents d
            JOIN chunks c ON c.document_id = d.id
            WHERE d.status NOT IN ('indexed')
            """
        )
        inconsistent_count = inconsistent[0]["cnt"] if inconsistent else 0

        logger.info(
            "[Scheduler] Consistency | orphans=%d | inconsistent=%d",
            orphan_count, inconsistent_count,
        )

        # 自动修复：将 indexed 但无 chunks 的文档重置为 pending
        if orphan_count > 0:
            await postgres_tool.execute(
                """
                UPDATE documents SET status = 'pending'
                WHERE status = 'indexed' AND chunk_count = 0
                """
            )
            logger.info("[Scheduler] Fixed %d orphan documents", orphan_count)

    except Exception as e:
        logger.error("[Scheduler] Consistency check failed | %s", e)


async def _job_monthly_cleanup():
    """每月清理过期数据"""
    from tools.postgres import postgres_tool

    logger.info("[Scheduler] Monthly cleanup")
    try:
        # 清理 90 天前已完成的 tasks
        result = await postgres_tool.execute(
            """
            DELETE FROM tasks
            WHERE status IN ('done', 'failed')
              AND created_at < NOW() - INTERVAL '90 days'
            """
        )
        logger.info("[Scheduler] Cleaned old tasks | %s", result)

        # 清理 90 天前的 research_tasks
        result = await postgres_tool.execute(
            """
            DELETE FROM research_tasks
            WHERE created_at < NOW() - INTERVAL '90 days'
              AND status = 'completed'
            """
        )
        logger.info("[Scheduler] Cleaned old research_tasks | %s", result)

    except Exception as e:
        logger.error("[Scheduler] Cleanup failed | %s", e)


def start_scheduler() -> None:
    """启动调度器（在 FastAPI lifespan 中调用）"""
    global _scheduler

    if _scheduler is not None:
        return

    _scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

    # 每日 Pipeline（凌晨 2:00）
    _scheduler.add_job(
        _job_daily_pipeline,
        trigger=CronTrigger(hour=2, minute=0),
        id="daily_pipeline",
        name="Daily Document Pipeline",
        replace_existing=True,
    )

    # 任务重试（每 5 分钟）
    _scheduler.add_job(
        _job_task_retry,
        trigger=IntervalTrigger(minutes=5),
        id="task_retry",
        name="Task Retry Worker",
        replace_existing=True,
    )

    # 每周一致性检查（周日 3:00）
    _scheduler.add_job(
        _job_weekly_consistency,
        trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),
        id="weekly_consistency",
        name="Weekly Consistency Check",
        replace_existing=True,
    )

    # 每月清理（1 号 4:00）
    _scheduler.add_job(
        _job_monthly_cleanup,
        trigger=CronTrigger(day=1, hour=4, minute=0),
        id="monthly_cleanup",
        name="Monthly Cleanup",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("[Scheduler] Started with %d jobs", len(_scheduler.get_jobs()))


def stop_scheduler() -> None:
    """停止调度器"""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("[Scheduler] Stopped")
