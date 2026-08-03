"""Rendering Engine — 消费 knowledge_render_jobs 并对每个 job 执行渲染+同步

流程：claim job → 读实体 → Diff 变更 Section → 渲染 → SiYuan 幂等写入 → 更新状态。
设计：复用 core.knowledge_render_jobs 表（Phase 1 建立），状态机
pending/running/done/failed，带 retry 指数退避。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from server.adapters.siyuan.client import SiYuanError
from server.rendering.metrics import render_metrics
from server.rendering.renderer import renderer
from server.storage.postgres import pg_storage

logger = logging.getLogger(__name__)

JOB_STATUS_PENDING = "pending"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_DONE = "done"
JOB_STATUS_FAILED = "failed"

MAX_RETRIES = 3


class RenderEngine:
    """渲染引擎主循环"""

    async def claim_next(self, limit: int = 5) -> list[dict]:
        """领取待处理任务（按优先级，加行锁防并发重复领取）"""
        rows = await pg_storage.query(
            """
            SELECT id, entity, type, section, status, retry, priority
            FROM core.knowledge_render_jobs
            WHERE status = $1
            ORDER BY priority ASC, created_at ASC
            LIMIT $2
            FOR UPDATE SKIP LOCKED
            """,
            JOB_STATUS_PENDING, limit,
        )
        if not rows:
            return []
        ids = [r["id"] for r in rows]
        await pg_storage.execute(
            """
            UPDATE core.knowledge_render_jobs
            SET status = $2, updated_at = NOW()
            WHERE id = ANY($1::uuid[])
            """,
            ids, JOB_STATUS_RUNNING,
        )
        render_metrics.record_claim(len(rows))
        return rows

    async def process_job(self, job: dict[str, Any]) -> dict:
        """处理单个渲染任务（幂等）"""
        job_id = job["id"]
        entity_id = job["entity"]
        section = job.get("section")
        start = time.perf_counter()

        entity = await pg_storage.get_entity_by_id(str(entity_id))
        if not entity:
            await self.fail(job_id, "entity not found")
            return {"job_id": job_id, "status": JOB_STATUS_FAILED, "reason": "entity not found"}

        # 若指定 section，则仅同步该 Section；否则全量增量
        from server.adapters.siyuan.sync import siyuan_sync

        if section:
            result = await siyuan_sync.sync_section(entity, section)
        else:
            result = await siyuan_sync.sync_entity(entity)

        await self._complete(job_id)
        render_metrics.record_done(time.perf_counter() - start)
        logger.info("Render job %s done: %s", job_id, result)
        return {"job_id": job_id, "status": JOB_STATUS_DONE, "result": result}

    async def _complete(self, job_id: str) -> None:
        await pg_storage.execute(
            "UPDATE core.knowledge_render_jobs SET status = $2, updated_at = NOW() WHERE id = $1",
            job_id, JOB_STATUS_DONE,
        )

    async def fail(self, job_id: str, error: str) -> None:
        row = await pg_storage.query_one(
            "SELECT retry FROM core.knowledge_render_jobs WHERE id = $1", job_id
        )
        retry = int(row["retry"]) if row else 0
        old_status = row["status"] if row else JOB_STATUS_FAILED
        if old_status == JOB_STATUS_RUNNING and retry < MAX_RETRIES:
            # 指数退避：回退 pending 由下轮重试
            await pg_storage.execute(
                """
                UPDATE core.knowledge_render_jobs
                SET status = 'pending', retry = retry + 1,
                    error_message = $2, updated_at = NOW()
                WHERE id = $1
                """,
                job_id, error[:2000],
            )
            render_metrics.record_fail(retried=True)
        else:
            await pg_storage.execute(
                """
                UPDATE core.knowledge_render_jobs
                SET status = 'failed', error_message = $2, updated_at = NOW()
                WHERE id = $1
                """,
                job_id, error[:2000],
            )
            render_metrics.record_fail(retried=False)

    async def run_once(self, limit: int = 5) -> int:
        """单轮：领取并处理任务，返回处理数。供 Worker 循环调用。"""
        jobs = await self.claim_next(limit)
        for job in jobs:
            try:
                await self.process_job(job)
            except SiYuanError as e:
                await self.fail(job["id"], str(e))
            except Exception as e:  # noqa: BLE001
                logger.exception("render job %s error", job["id"])
                await self.fail(job["id"], str(e))
        return len(jobs)


# 模块级单例
render_engine = RenderEngine()