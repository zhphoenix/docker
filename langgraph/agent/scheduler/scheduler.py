"""Resource Scheduler - 基于 APScheduler 的定时任务

Jobs:
  - daily_pipeline: 每日处理 pending 文档（触发 Pipeline）
  - weekly_consistency: 每周 Embedding 一致性检查
  - monthly_cleanup: 每月清理 staging + 过期数据
  - task_retry: 每 5 分钟重试失败任务（指数退避）
  - news_collect_high: 每 30 分钟采集高优先级新闻源（RSS）
  - news_collect_normal: 每 2 小时采集普通新闻源（Crawler）
  - news_collect_low: 每 6 小时采集低优先级新闻源
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
    from services.pipeline import doc_pipeline

    logger.info("[Scheduler] Daily pipeline triggered")
    try:
        limit = get_policy("scheduler.daily_pipeline_limit", 100)
        stats = await doc_pipeline.process_pending_documents(limit=limit)
        logger.info("[Scheduler] Daily pipeline done | %s", stats)
    except Exception as e:
        logger.error("[Scheduler] Daily pipeline failed | %s", e)


async def _job_task_retry():
    """定期重试失败任务（指数退避）"""
    from services.task_queue import task_queue
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


async def _job_news_collect(priority: str = "high"):
    """新闻采集任务

    按优先级采集新闻源，触发 News Intelligence Agent 处理管线。
    """
    from news_agent.collector.source_registry import source_registry
    from news_agent.collector.rss_collector import collect_rss
    from news_agent.collector.web_collector import collect_web
    from news_agent.graph import get_news_graph

    logger.info("[Scheduler] News collection triggered | priority=%s", priority)
    try:
        sources = source_registry.get_enabled(priority=priority)
        if not sources:
            logger.info("[Scheduler] No %s priority sources", priority)
            return

        graph = get_news_graph()
        total_articles = 0

        for source in sources:
            try:
                # 采集
                if source.source_type == "rss":
                    articles = await collect_rss(source)
                elif source.source_type == "crawler":
                    articles = await collect_web(source)
                else:
                    continue

                if not articles:
                    continue

                # 触发处理管线
                result = await graph.ainvoke({
                    "source_id": source.id,
                    "raw_articles": articles,
                    "cleaned_articles": [],
                    "unique_articles": [],
                    "classified_articles": [],
                    "entities": [],
                    "events": [],
                    "relations": [],
                    "impact_assessments": [],
                    "stored_article_ids": [],
                    "stored_event_ids": [],
                    "knowledge_agent_triggered": False,
                    "errors": [],
                })

                stored = len(result.get("stored_article_ids", []))
                total_articles += stored
                logger.info(
                    "[Scheduler] News processed | source=%s | stored=%d",
                    source.id, stored,
                )

            except Exception as e:
                logger.error("[Scheduler] News source failed | %s | %s", source.id, e)

        logger.info("[Scheduler] News collection done | priority=%s | total=%d", priority, total_articles)

    except Exception as e:
        logger.error("[Scheduler] News collection failed | %s", e)


async def _job_news_lifecycle():
    """DLM 新闻生命周期维护任务

    每日凌晨 3:30 执行：去重检测、重要性重评分、归档、AGE 图清理、Embedding 清理。
    """
    from services.lifecycle import news_lifecycle

    logger.info("[Scheduler] News lifecycle maintenance triggered")
    try:
        results = await news_lifecycle.run_all()
        logger.info("[Scheduler] News lifecycle done | %s", results)
    except Exception as e:
        logger.error("[Scheduler] News lifecycle failed | %s", e)


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

    # ── 新闻采集任务 ──
    # 高优先级源（RSS）：每 30 分钟
    _scheduler.add_job(
        _job_news_collect,
        trigger=IntervalTrigger(minutes=30),
        args=["high"],
        id="news_collect_high",
        name="News Collection (High Priority)",
        replace_existing=True,
    )

    # 普通源（Crawler）：每 2 小时
    _scheduler.add_job(
        _job_news_collect,
        trigger=IntervalTrigger(hours=2),
        args=["normal"],
        id="news_collect_normal",
        name="News Collection (Normal Priority)",
        replace_existing=True,
    )

    # 低优先级源：每 6 小时
    _scheduler.add_job(
        _job_news_collect,
        trigger=IntervalTrigger(hours=6),
        args=["low"],
        id="news_collect_low",
        name="News Collection (Low Priority)",
        replace_existing=True,
    )

    # ── DLM 新闻生命周期维护（每日 3:30） ──
    _scheduler.add_job(
        _job_news_lifecycle,
        trigger=CronTrigger(hour=3, minute=30),
        id="news_lifecycle",
        name="News Lifecycle Maintenance",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("[Scheduler] Started with %d jobs", len(_scheduler.get_jobs()))


def get_scheduler_jobs() -> list[dict]:
    """返回已注册的调度任务列表（只读，供 API 展示）

    Returns:
        [{"id": str, "name": str, "next_run_time": str | None, "trigger": str}]
    """
    if _scheduler is None:
        return []
    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        })
    return jobs


def stop_scheduler() -> None:
    """停止调度器"""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("[Scheduler] Stopped")
