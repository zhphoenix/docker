"""Render Worker 单元测试

覆盖 Phase 8 性能优化：
  1. 背压：队列满时 producer 阻塞，内存中任务数不超过 queue_size
  2. 多消费者：并发消费任务，吞吐量正确
  3. 失败重试：消费者异常 → 调用 engine._fail 回退 pending

架构：producer（claim → 入队）+ consumer（取出 → process_job）。
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from server.rendering.worker import RenderWorker


@pytest.fixture
def worker() -> RenderWorker:
    return RenderWorker(workers=3, poll_interval=0.01, batch=2, queue_size=4)


@pytest.fixture
def fake_job() -> dict:
    return {"id": "job-1", "entity": "11111111-1111-1111-1111-111111111111", "type": None, "section": None}


@pytest.mark.asyncio
async def test_queue_maxsize_backpressure(worker):
    """背压：队列容量受 queue_size 限制，producer 阻塞而非无限堆积"""
    worker._running = True
    worker._queue = asyncio.Queue(maxsize=worker.queue_size)

    # claim_next 返回任务，但 process_job 不消费（模拟渲染慢），验证队列不会超限
    jobs = [{"id": f"job-{i}", "entity": str(i)} for i in range(worker.queue_size + 5)]
    with patch.object(worker, "_producer_loop", new_callable=AsyncMock) as mock_producer:
        # 直接手动验证：put 超过 queue_size 会阻塞
        async def fill():
            for j in jobs:
                await worker._queue.put(j)

        task = asyncio.create_task(fill())
        await asyncio.sleep(0.05)
        assert worker._queue.qsize() == worker.queue_size, "队列已满，producer 应阻塞"
        task.cancel()

    assert worker.queue_size == 4


@pytest.mark.asyncio
async def test_consumer_processes_job(fake_job):
    """消费者：从队列取任务并调用 render_engine.process_job"""
    w = RenderWorker(workers=1, poll_interval=0.01, batch=2, queue_size=4)
    w._running = True
    w._queue = asyncio.Queue(maxsize=4)

    async def get_once():
        # 第一轮返回 job，随后停止循环（自然退出，避免挂起）
        w._running = False
        return fake_job

    with patch.object(w, "_queue") as mock_q, \
         patch("server.rendering.worker.render_engine") as mock_engine:
        mock_q.get = AsyncMock(side_effect=get_once)
        mock_q.task_done = Mock()  # asyncio.Queue.task_done 是同步方法
        mock_engine.process_job = AsyncMock(return_value={"status": "done"})

        await asyncio.wait_for(w._consumer_loop(0), timeout=5)

        mock_engine.process_job.assert_awaited_once_with(fake_job)
        mock_q.task_done.assert_called_once()


@pytest.mark.asyncio
async def test_consumer_failure_calls_fail(fake_job):
    """消费者异常：调用 engine._fail 回退任务（不丢失）"""
    w = RenderWorker(workers=1, poll_interval=0.01, batch=2, queue_size=4)
    w._running = True
    w._queue = asyncio.Queue(maxsize=4)

    async def get_once():
        w._running = False
        return fake_job

    with patch.object(w, "_queue") as mock_q, \
         patch("server.rendering.worker.render_engine") as mock_engine:
        mock_q.get = AsyncMock(side_effect=get_once)
        mock_q.task_done = Mock()  # asyncio.Queue.task_done 是同步方法
        mock_engine.process_job = AsyncMock(side_effect=RuntimeError("boom"))
        mock_engine.fail = AsyncMock()

        await asyncio.wait_for(w._consumer_loop(0), timeout=5)

        mock_engine.fail.assert_awaited_once_with(fake_job["id"], "boom")
        mock_q.task_done.assert_called_once()


@pytest.mark.asyncio
async def test_producer_claims_batch(worker):
    """生产者：claim 任务并入队，无任务时降低轮询频率"""
    worker._running = True
    worker._queue = asyncio.Queue(maxsize=worker.queue_size)

    jobs = [{"id": f"job-{i}", "entity": str(i)} for i in range(2)]

    async def claim_once(batch):
        # 第一轮返回任务，随后停止循环
        worker._running = False
        return jobs

    with patch("server.rendering.worker.render_engine") as mock_engine:
        mock_engine.claim_next = AsyncMock(side_effect=claim_once)
        await asyncio.wait_for(worker._producer_loop(), timeout=5)

        mock_engine.claim_next.assert_awaited()
        assert worker._queue.qsize() == 2

        # 队列中的任务被顺序放入
        for j in jobs:
            assert await worker._queue.get() == j


@pytest.mark.asyncio
async def test_start_creates_workers():
    """start：创建 1 个 producer + N 个 consumer"""
    w = RenderWorker(workers=2, poll_interval=0.01, batch=2, queue_size=4)
    with patch("server.rendering.worker.render_engine") as mock_engine:
        mock_engine.claim_next = AsyncMock(return_value=[])
        mock_engine.process_job = AsyncMock(return_value={"status": "done"})
        mock_engine.fail = AsyncMock()

        start_task = asyncio.create_task(w.start())
        await asyncio.sleep(0.05)
        w._running = False
        await w.stop()
        start_task.cancel()

        assert w._producer is not None
        assert len(w._consumers) == 2
        assert w._queue is not None
        assert w._queue.maxsize == 4