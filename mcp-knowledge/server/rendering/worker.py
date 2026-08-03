"""Render Worker — 后台消费渲染队列

架构：生产者/消费者 + 背压（Asyncio Queue maxsize）
  - producer：从 core.knowledge_render_jobs claim 任务入队（队列满则阻塞 → 背压）
  - consumer：N 个并发 worker 从队列取任务并渲染（由 SiYuanClient 的 Semaphore 控制器限流）

与单 worker 轮询相比，本实现：
  - 严格限制内存中待处理任务数（queue_size），避免突发任务涌入
  - 多 worker 并发消费，吞吐量随 workers 线性提升
  - claim 与消费解耦，DB 压力可控

启动方式：python -m server.rendering.worker
"""

from __future__ import annotations

import asyncio
import logging

from server.adapters.siyuan.client import SiYuanError
from server.adapters.siyuan.config import get_siyuan_config
from server.rendering.engine import render_engine
from server.rendering.metrics import render_metrics

logger = logging.getLogger(__name__)


# 定期输出 metric 快照的间隔（秒）
METRIC_LOG_INTERVAL = 60.0


class RenderWorker:
    """后台渲染 Worker（背压队列 + 多消费者）"""

    def __init__(
        self,
        workers: int | None = None,
        poll_interval: float = 2.0,
        batch: int = 5,
        queue_size: int | None = None,
    ):
        self.workers = workers or get_siyuan_config().concurrency
        self.poll_interval = poll_interval
        self.batch = batch
        # 背压上限：默认取 SiYuan 队列大小，避免内存中缓存海量任务
        self.queue_size = queue_size or get_siyuan_config().queue_size
        self._queue: asyncio.Queue | None = None
        self._running = False
        self._producer: asyncio.Task | None = None
        self._consumers: list[asyncio.Task] = []

    # ──────────────────────────────
    # 生产者：claim → 入队（背压）
    # ──────────────────────────────
    async def _producer_loop(self) -> None:
        """从 DB 领取任务并放入队列；队列满则阻塞（背压），避免 DB 高频轮询。"""
        last_metric = 0.0
        while self._running:
            try:
                jobs = await render_engine.claim_next(self.batch)
                if not jobs:
                    # 无任务，降低轮询频率
                    await asyncio.sleep(self.poll_interval)
                    continue
                for job in jobs:
                    # 队列满时 put 阻塞，天然形成背压，防止任务无限堆积
                    await self._queue.put(job)
                # 记录队列水位（背压监控）
                render_metrics.record_queue_depth(self._queue.qsize())

                now = asyncio.get_event_loop().time()
                if now - last_metric >= METRIC_LOG_INTERVAL:
                    render_metrics.log_snapshot()
                    last_metric = now
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                logger.exception("render producer loop error: %s", e)
                await asyncio.sleep(self.poll_interval)

    # ──────────────────────────────
    # 消费者：取任务 → 渲染
    # ──────────────────────────────
    async def _consumer_loop(self, idx: int) -> None:
        """单个消费者：从队列取任务并渲染（幂等 + 失败重试）。"""
        while self._running:
            try:
                job = await self._queue.get()
                job_id = job.get("id")
                try:
                    await render_engine.process_job(job)
                except SiYuanError as e:
                    await render_engine.fail(job_id, str(e))
                except Exception as e:  # noqa: BLE001
                    logger.exception("render consumer %s job %s error", idx, job_id)
                    await render_engine.fail(job_id, str(e))
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                logger.exception("render consumer %s error: %s", idx, e)
                await asyncio.sleep(self.poll_interval)

    # ──────────────────────────────
    # 生命周期
    # ──────────────────────────────
    async def start(self) -> None:
        self._running = True
        self._queue = asyncio.Queue(maxsize=self.queue_size)
        self._producer = asyncio.create_task(self._producer_loop(), name="render-producer")
        self._consumers = [
            asyncio.create_task(self._consumer_loop(i), name=f"render-consumer-{i}")
            for i in range(self.workers)
        ]
        logger.info(
            "Render worker started (%d consumers, queue_size=%d, batch=%d)",
            self.workers, self.queue_size, self.batch,
        )
        await asyncio.gather(self._producer, *self._consumers)

    async def stop(self) -> None:
        self._running = False
        tasks: list[asyncio.Task] = []
        if self._producer:
            self._producer.cancel()
            tasks.append(self._producer)
        for c in self._consumers:
            c.cancel()
            tasks.append(c)
        # 等待任务真正结束，避免 pending task 警告与资源泄漏
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    worker = RenderWorker()
    logger.info("Rendering worker starting...")
    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())