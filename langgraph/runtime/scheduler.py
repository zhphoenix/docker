"""Resource Scheduler - 基于 APScheduler 的定时任务

Jobs:
  - daily_pipeline: 每日处理 pending 文档（触发 Pipeline）
  - weekly_consistency: 每周 Embedding 一致性检查
  - monthly_cleanup: 每月清理 staging + 过期数据
  - task_retry: 每 5 分钟重试失败任务（指数退避）
  - news_collect_high: 每 30 分钟采集高优先级新闻源（RSS）
  - news_collect_normal: 每 2 小时采集普通新闻源（Crawler）
  - news_collect_low: 每 6 小时采集低优先级新闻源
  - watchlist_daily: 每日 Watchlist 监控（时间/开关由 watchlist_settings 配置）
"""

import logging
from datetime import datetime, timezone
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config.policy_loader import get_policy

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _job_daily_pipeline():
    """每日文档处理 Pipeline"""
    from pipelines.document_pipeline import doc_pipeline

    logger.info("[Scheduler] Daily pipeline triggered")
    try:
        limit = get_policy("scheduler.daily_pipeline_limit", 100)
        stats = await doc_pipeline.process_pending_documents(limit=limit)
        logger.info("[Scheduler] Daily pipeline done | %s", stats)
    except Exception as e:
        logger.error("[Scheduler] Daily pipeline failed | %s", e)


async def _job_task_retry():
    """定期重试失败任务（指数退避）"""
    from runtime.queue import task_queue
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
    from collectors.source_registry import source_registry
    from collectors.rss_collector import collect_rss
    from collectors.web_collector import collect_web
    from collectors.health_metrics import record_collect_run
    from graphs.news_analysis_graph import get_news_graph
    from monitoring.agent_center import invoke_tracked

    logger.info("[Scheduler] News collection triggered | priority=%s", priority)
    try:
        sources = source_registry.get_enabled(priority=priority)
        if not sources:
            logger.info("[Scheduler] No %s priority sources", priority)
            return

        graph = get_news_graph()
        total_articles = 0

        for source in sources:
            collect_start = time.monotonic()
            try:
                # 采集
                if source.source_type == "rss":
                    articles = await collect_rss(source)
                elif source.source_type == "crawler":
                    articles = await collect_web(source)
                else:
                    continue

                if not articles:
                    # 采集成功但无文章，仍记录指标
                    await record_collect_run(
                        source.id, source.name, True,
                        latency_ms=int((time.monotonic() - collect_start) * 1000),
                        articles_fetched=0, articles_stored=0,
                    )
                    continue

                # 触发处理管线（统一埋点包装器，写 agent_runs task_kind=pipeline）
                result = await invoke_tracked(
                    graph,
                    {
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
                    },
                    agent_id="news_intelligence",
                    question=f"scheduled collect source={source.id} priority={priority}",
                )

                stored = len(result.get("stored_article_ids", []))
                total_articles += stored
                # 采集健康指标（Latency/Articles/Duplicates）
                await record_collect_run(
                    source.id, source.name, True,
                    latency_ms=int((time.monotonic() - collect_start) * 1000),
                    articles_fetched=len(articles),
                    articles_stored=stored,
                )
                logger.info(
                    "[Scheduler] News processed | source=%s | stored=%d",
                    source.id, stored,
                )

            except Exception as e:
                logger.error("[Scheduler] News source failed | %s | %s", source.id, e)
                # 采集失败指标（Errors）
                await record_collect_run(
                    source.id, source.name, False,
                    latency_ms=int((time.monotonic() - collect_start) * 1000),
                    articles_fetched=0, articles_stored=0,
                    error=str(e)[:500],
                )

        logger.info("[Scheduler] News collection done | priority=%s | total=%d", priority, total_articles)

    except Exception as e:
        logger.error("[Scheduler] News collection failed | %s", e)


async def _job_watchlist_daily():
    """Watchlist 自选股监控任务（按 update_frequency 区分全量/增量）

    读取 watchlist_settings 的 schedule_time / auto_enabled / update_frequency 决定时间、开关与模式：
    - daily    → 全量监控 run_watchlist_monitoring()（触发采集 + 报告 + 告警）
    - hourly   → 增量监控 run_incremental_watchlist_monitoring(hours_back=1.0)
    - realtime → 增量监控 run_incremental_watchlist_monitoring(hours_back=0.25)
    任务内以 asyncio.create_task 异步执行监控主流程，避免阻塞调度循环。
    注：job 是否注册由 start_scheduler/resync_watchlist_job 控制，
    此处仅当 auto_enabled 开启时才会被调度器触发。
    """
    from tools.postgres import postgres_tool

    logger.info("[Scheduler] Watchlist monitoring triggered")
    try:
        rows = await postgres_tool.query(
            "SELECT auto_enabled, update_frequency FROM watchlist.watchlist_settings WHERE id = 1"
        )
        if rows and not rows[0].get("auto_enabled", True):
            logger.info("[Scheduler] Watchlist auto disabled, skip")
            return
        frequency = str((rows[0].get("update_frequency") if rows else "") or "daily")
    except Exception as e:  # noqa: BLE001
        logger.error("[Scheduler] Watchlist settings check failed | %s", e)
        return

    # 异步执行监控主流程（采集/增量/入库/报告/告警）
    async def _wrapped():
        try:
            from monitoring.watchlist_monitor import (
                run_watchlist_monitoring,
                run_incremental_watchlist_monitoring,
            )
            if frequency == "daily":
                result = await run_watchlist_monitoring()
            elif frequency == "hourly":
                result = await run_incremental_watchlist_monitoring(hours_back=1.0)
            else:  # realtime
                result = await run_incremental_watchlist_monitoring(hours_back=0.25)
            logger.info("[Scheduler] Watchlist monitoring done | freq=%s | %s", frequency, result)
        except Exception as e:  # noqa: BLE001
            logger.error("[Scheduler] Watchlist monitoring failed | freq=%s | %s", frequency, e)

    import asyncio
    asyncio.create_task(_wrapped())


async def resync_watchlist_job() -> None:
    """按 watchlist_settings 重新注册 watchlist 监控 job

    在 PUT /api/watchlist/config 修改 schedule_time / auto_enabled / update_frequency 后调用：
    - auto_enabled=false 时移除 job；
    - 否则按 update_frequency 选择触发方式：
        daily    → 每日 schedule_time
        hourly   → 每小时（分钟 = schedule_time 的分钟）
        realtime → 每 15 分钟（IntervalTrigger）
    """
    global _scheduler
    if _scheduler is None:
        logger.info("[Scheduler] Scheduler not started, skip resync")
        return

    try:
        from tools.postgres import postgres_tool

        rows = await postgres_tool.query(
            "SELECT schedule_time, auto_enabled, update_frequency "
            "FROM watchlist.watchlist_settings WHERE id = 1"
        )
        if not rows:
            logger.warning("[Scheduler] Watchlist settings row missing")
            return

        cfg = rows[0]
        auto_enabled = bool(cfg.get("auto_enabled", True))
        schedule_time = str(cfg.get("schedule_time") or "07:00")
        hour, minute = schedule_time.split(":")[:2]
        frequency = str(cfg.get("update_frequency") or "daily")

        job_id = "watchlist_daily"
        if auto_enabled:
            if frequency == "hourly":
                # 每小时：保留分钟对齐，便于观察
                trigger = CronTrigger(minute=int(minute))
                job_name = "Watchlist Hourly Monitoring"
            elif frequency == "realtime":
                # 实时：每 15 分钟增量采集
                trigger = IntervalTrigger(minutes=15)
                job_name = "Watchlist Realtime Monitoring"
            else:
                trigger = CronTrigger(hour=int(hour), minute=int(minute))
                job_name = "Watchlist Daily Monitoring"
            _scheduler.add_job(
                _job_watchlist_daily,
                trigger=trigger,
                id=job_id,
                name=job_name,
                replace_existing=True,
            )
            logger.info(
                "[Scheduler] Watchlist job resynced | freq=%s | schedule=%s | name=%s",
                frequency, schedule_time, job_name,
            )
        else:
            if _scheduler.get_job(job_id):
                _scheduler.remove_job(job_id)
            logger.info("[Scheduler] Watchlist job removed (auto disabled)")
    except Exception as e:  # noqa: BLE001
        logger.error("[Scheduler] Watchlist resync failed | %s", e)


async def _job_agent_center_archive():
    """Agent Center 埋点数据归档（每日）

    - 删除 90 天前的终态 agent_runs（避免无线增长）
    - 删除 180 天前的 agent_tool_stats
    """
    from tools.postgres import postgres_tool

    logger.info("[Scheduler] Agent Center archive triggered")
    try:
        r1 = await postgres_tool.execute(
            "DELETE FROM agent_runs WHERE status IN ('success','failed') "
            "AND created_at < NOW() - INTERVAL '90 days'"
        )
        r2 = await postgres_tool.execute(
            "DELETE FROM agent_tool_stats WHERE created_at < NOW() - INTERVAL '180 days'"
        )
        logger.info("[Scheduler] Agent Center archived | runs=%s | stats=%s", r1, r2)
    except Exception as e:
        logger.error("[Scheduler] Agent Center archive failed | %s", e)


async def _job_package_consume():
    """KOC-A1 Package 消费器：轮询 published Package → consumed/failed

    消费 knowledge_packages 中 status='published' 的包，校验 schema_version 后
    置 consumed（成功）或 failed（失败，可经 retry 重投）。
    每 5 分钟执行一次。
    """
    from services.package_consumer import consume_published

    logger.info("[Scheduler] Package consume triggered")
    try:
        stats = await consume_published()
        logger.info("[Scheduler] Package consume done | %s", stats)
    except Exception as e:
        logger.error("[Scheduler] Package consume failed | %s", e)


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

    # Agent Center 埋点归档（每日 4:30）
    _scheduler.add_job(
        _job_agent_center_archive,
        trigger=CronTrigger(hour=4, minute=30),
        id="agent_center_archive",
        name="Agent Center Archive",
        replace_existing=True,
    )

    # ── KOC-A1 Package 消费（每 5 分钟轮询 published → consumed/failed） ──
    _scheduler.add_job(
        _job_package_consume,
        trigger=IntervalTrigger(minutes=5),
        id="package_consume",
        name="Knowledge Package Consumer",
        replace_existing=True,
    )

    # ── Watchlist 每日监控（按 watchlist_settings 配置） ──
    # start_scheduler 为同步函数，需通过当前事件循环调度异步 resync
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(resync_watchlist_job())
        else:
            loop.run_until_complete(resync_watchlist_job())
    except RuntimeError as e:
        logger.warning("[Scheduler] Watchlist resync skipped | %s", e)

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
