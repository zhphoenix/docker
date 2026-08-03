"""Rendering Metrics — 轻量进程内指标采集

不引入 prometheus_client 依赖，用结构化日志输出，便于未来对接 Prometheus / SLA。
每个指标以 `[RenderMetric]` 前缀输出，字段为 key=value 形式。

指标：
  - jobs_claimed        累计领取任务数
  - jobs_done           累计完成数
  - jobs_failed         累计失败数
  - jobs_retried        累计重试回退数
  - jobs_running        当前处理中任务数
  - queue_depth         当前队列深度（worker 待处理）
  - avg_duration_ms     最近任务平均耗时
  - throughput_per_sec  窗口内每秒完成数（60s 自动滚动）

进程内度量的意义：渲染 worker 是长驻后台进程，指标可随时通过
`render_metrics.snapshot()` 输出，或由外部采集器读取日志中的
`[RenderMetric]` 行做聚合。
"""

from __future__ import annotations

import logging
import time
from collections import deque

logger = logging.getLogger(__name__)

_PREFIX = "[RenderMetric]"
_WINDOW_SECONDS = 60.0


class RenderMetrics:
    """渲染指标采集器（进程内 + 结构化日志）"""

    def __init__(self) -> None:
        self.claimed = 0
        self.done = 0
        self.failed = 0
        self.retried = 0
        self.running = 0
        self.queue_depth = 0
        self._recent_durations: deque[float] = deque(maxlen=100)
        self._window_start = time.monotonic()
        self._window_done = 0
        self._last_throughput = 0.0

    # ── 记录 ──────────────────────────────
    def record_claim(self, n: int) -> None:
        """领取 n 个任务入队"""
        self.claimed += n
        self.running += n

    def record_done(self, duration_s: float) -> None:
        """任务成功完成"""
        self.done += 1
        self.running = max(0, self.running - 1)
        self._window_done += 1
        self._recent_durations.append(duration_s * 1000)

    def record_fail(self, retried: bool) -> None:
        """任务失败；retried=True 表示已回退 pending 待重试"""
        self.failed += 1
        self.running = max(0, self.running - 1)
        if retried:
            self.retried += 1

    def record_queue_depth(self, depth: int) -> None:
        """记录队列深度（背压水位）"""
        self.queue_depth = depth

    # 每 60s 自动滚动一次吞吐量窗口
    def _throughput(self) -> float:
        now = time.monotonic()
        elapsed = now - self._window_start
        if elapsed >= _WINDOW_SECONDS:
            self._last_throughput = self._window_done / elapsed if elapsed > 0 else 0.0
            self._window_start = now
            self._window_done = 0
        return self._last_throughput

    @property
    def avg_duration_ms(self) -> float:
        if not self._recent_durations:
            return 0.0
        return sum(self._recent_durations) / len(self._recent_durations)

    # ── 输出 ──────────────────────────────
    def snapshot(self) -> dict:
        return {
            "jobs_claimed": self.claimed,
            "jobs_done": self.done,
            "jobs_failed": self.failed,
            "jobs_retried": self.retried,
            "jobs_running": self.running,
            "queue_depth": self.queue_depth,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "throughput_per_sec": round(self._throughput(), 3),
        }

    def log_snapshot(self) -> None:
        """输出一条结构化 metric 日志，供日志采集器聚合"""
        fields = " ".join(f"{k}={v}" for k, v in self.snapshot().items())
        logger.info("%s %s", _PREFIX, fields)


# 模块级单例
render_metrics = RenderMetrics()