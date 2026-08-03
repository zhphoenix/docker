"""Render Metrics 单元测试

覆盖 Phase 9 监控埋点：
  1. 计数：claim/done/fail 累计正确
  2. 平均耗时：record_done 后 avg_duration_ms 正确
  3. 重试统计：record_fail(retried=True) 计入 retried
  4. 快照输出：snapshot() 结构完整、字段为非负
  5. 队列深度：record_queue_depth 记录背压水位
"""

from server.rendering.metrics import RenderMetrics


def test_claim_done_count():
    m = RenderMetrics()
    m.record_claim(3)
    assert m.claimed == 3
    assert m.running == 3

    m.record_done(0.5)
    assert m.done == 1
    assert m.running == 2


def test_avg_duration():
    m = RenderMetrics()
    m.record_done(0.2)  # 200ms
    m.record_done(0.4)  # 400ms
    assert m.avg_duration_ms == 300.0


def test_fail_retry_counting():
    m = RenderMetrics()
    m.record_claim(2)
    m.record_fail(retried=True)
    m.record_fail(retried=False)
    assert m.failed == 2
    assert m.retried == 1
    assert m.running == 0


def test_snapshot_structure():
    m = RenderMetrics()
    m.record_claim(1)
    m.record_done(0.1)
    m.record_queue_depth(5)
    snap = m.snapshot()

    assert snap["jobs_claimed"] == 1
    assert snap["jobs_done"] == 1
    assert snap["jobs_failed"] == 0
    assert snap["queue_depth"] == 5
    assert snap["avg_duration_ms"] == 100.0
    assert 0 <= snap["throughput_per_sec"] < 1
    # 快照字段全集
    assert set(snap) == {
        "jobs_claimed", "jobs_done", "jobs_failed", "jobs_retried",
        "jobs_running", "queue_depth", "avg_duration_ms", "throughput_per_sec",
    }


def test_running_never_negative():
    m = RenderMetrics()
    m.record_done(0.1)  # 未 claim 直接 done，running 不应为负
    assert m.running == 0