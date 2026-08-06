"""Task Queue - 基于 PostgreSQL tasks 表的简单任务队列

支持：
  - 任务创建、状态更新、进度追踪
  - 断点续传（通过 stage/current_item）
  - 重试（retry_count + 指数退避）
  - 优先级排序
"""

import asyncio
import json
import logging
import uuid
from typing import Any

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)

# DP-D4 三级优先级 → tasks.priority 整数（数字越大越优先，与 idx_tasks_priority 索引一致）
#   HIGH=10   Breaking News/实时任务优先被 Worker 认领
#   NORMAL=0  默认（普通文档/批量任务）
#   LOW=-10   Annual Report 等批量重活，避免挤占实时任务
PRIORITY_LEVELS = {"high": 10, "normal": 0, "low": -10}


# 进程内任务控制标志（task_id -> {paused, cancelled}），供协作式取消/暂停使用
_controls: dict[str, dict] = {}


class TaskQueue:
    """PostgreSQL 任务队列"""

    async def create_task(
        self,
        task_type: str,
        title: str,
        params: dict[str, Any] | None = None,
        total_items: int = 0,
        created_by: str = "system",
        priority: int | str = 0,
    ) -> str:
        """创建任务，返回 task_id

        Args:
            priority: 优先级，支持整数（越大越优先）或 high/normal/low 字符串
                （DP-D4 三级队列，与 AcquirePriority 枚举对应）
        """
        task_id = str(uuid.uuid4())
        prio = self._normalize_priority(priority)
        await postgres_tool.execute(
            """
            INSERT INTO tasks (id, task_type, title, status, params, total_items, created_by, priority)
            VALUES ($1, $2, $3, 'pending', $4::jsonb, $5, $6, $7)
            """,
            task_id, task_type, title,
            json.dumps(params or {}), total_items, created_by, prio,
        )
        logger.info("Task created: %s [%s] %s | priority=%d", task_id[:8], task_type, title, prio)
        return task_id

    @staticmethod
    def _normalize_priority(priority: int | str) -> int:
        """归一化优先级：int 直接用；字符串按 high/normal/low 映射（未知回退 0=normal）"""
        if isinstance(priority, int):
            return priority
        if isinstance(priority, str):
            return PRIORITY_LEVELS.get(priority.lower(), 0)
        return 0

    async def start_task(self, task_id: str) -> None:
        """标记任务开始"""
        await postgres_tool.execute(
            """
            UPDATE tasks SET status = 'running', started_at = NOW()
            WHERE id = $1
            """,
            task_id,
        )

    async def update_progress(
        self,
        task_id: str,
        current_item: int,
        stage: str = "",
        current_name: str = "",
    ) -> None:
        """更新任务进度"""
        # 先获取 total_items 计算进度
        task = await self.get_task(task_id)
        total = task.get("total_items", 0) if task else 0
        progress = round((current_item / total) * 100, 2) if total > 0 else 0

        await postgres_tool.execute(
            """
            UPDATE tasks
            SET current_item = $2, stage = $3, current_name = $4,
                progress = $5, updated_at = NOW()
            WHERE id = $1
            """,
            task_id, current_item, stage, current_name, progress,
        )

    async def set_total_items(self, task_id: str, total: int) -> None:
        """更新任务总项数（用于扫描型任务在运行时获知总数）"""
        await postgres_tool.execute(
            "UPDATE tasks SET total_items = $2 WHERE id = $1", task_id, total
        )

    async def complete_task(self, task_id: str) -> None:
        """标记任务完成"""
        await postgres_tool.execute(
            """
            UPDATE tasks
            SET status = 'done', progress = 100, finished_at = NOW(),
                duration_ms = EXTRACT(EPOCH FROM (NOW() - started_at)) * 1000
            WHERE id = $1
            """,
            task_id,
        )
        logger.info("Task completed: %s", task_id[:8])

    async def fail_task(self, task_id: str, error: str) -> None:
        """标记任务失败（自动递增 retry_count）"""
        await postgres_tool.execute(
            """
            UPDATE tasks
            SET status = 'failed', error_message = $2, finished_at = NOW(),
                retry_count = retry_count + 1, updated_at = NOW()
            WHERE id = $1
            """,
            task_id, error[:2000],
        )
        logger.error("Task failed: %s - %s", task_id[:8], error[:100])

    async def get_pending_tasks(self, task_type: str | None = None, limit: int = 10) -> list[dict]:
        """获取待处理任务"""
        query = "SELECT * FROM tasks WHERE status = 'pending'"
        params = []
        idx = 1

        if task_type:
            query += f" AND task_type = ${idx}"
            params.append(task_type)
            idx += 1

        # DP-D4: 按优先级降序 + 创建时间升序认领（复用 idx_tasks_priority 索引），
        # HIGH 任务优先被 Worker 认领
        query += f" ORDER BY priority DESC, created_at ASC LIMIT ${idx}"
        params.append(limit)

        return await postgres_tool.query(query, *params)

    async def recover_stale_tasks(self, stale_after_seconds: int = 300) -> int:
        """回收僵尸 running 任务（worker 崩溃/重启遗留），重置为 pending 以便重新认领

        Worker 单实例启动时，数据库中任何 status='running' 的任务都必然是上一进程
        崩溃前遗留的僵尸任务（worker 崩溃时既没有 complete_task 也没有 fail_task，
        任务会永久卡在 running）。本方法将这些任务重置为 pending，并清空运行期字段，
        使新 Worker 能重新认领处理。

        Args:
            stale_after_seconds: 仅回收 started_at 距今超过该秒数的 running 任务，
                避免误回收仍在运行中的任务（未来若支持多 worker 实例时安全）。

        Returns:
            被回收的任务数
        """
        result = await postgres_tool.execute(
            """
            UPDATE tasks
            SET status = 'pending',
                started_at = NULL,
                finished_at = NULL,
                current_item = 0,
                progress = 0,
                stage = '',
                current_name = '',
                error_message = NULL,
                updated_at = NOW()
            WHERE status = 'running'
              AND started_at < NOW() - make_interval(secs => $1)
            """,
            stale_after_seconds,
        )
        # result 形如 "UPDATE 3"，解析受影响行数
        try:
            recovered = int(result.split()[-1])
        except (ValueError, IndexError):
            recovered = 0
        if recovered:
            logger.warning(
                "Recovered %d stale running task(s) -> pending", recovered
            )
        return recovered

    async def get_task(self, task_id: str) -> dict | None:
        """获取任务详情"""
        rows = await postgres_tool.query("SELECT * FROM tasks WHERE id = $1", task_id)
        return rows[0] if rows else None

    async def log_task(self, task_id: str, level: str, message: str, stage: str = "") -> None:
        """写入任务日志（非关键路径，失败不阻塞主流程）"""
        try:
            await postgres_tool.execute(
                """
                INSERT INTO task_logs (task_id, level, message, stage)
                VALUES ($1, $2, $3, $4)
                """,
                task_id, level, message[:2000], stage,
            )
        except Exception as e:
            logger.warning("log_task failed | task=%s | %s", task_id[:8], e)

    async def get_task_logs(self, task_id: str, limit: int = 200) -> list[dict]:
        """查询任务日志（按创建时间升序）"""
        rows = await postgres_tool.query(
            """
            SELECT id, level, message, stage, created_at
            FROM task_logs
            WHERE task_id = $1
            ORDER BY created_at ASC
            LIMIT $2
            """,
            task_id, limit,
        )
        for r in rows:
            r["id"] = str(r["id"])
            if r.get("created_at"):
                r["created_at"] = r["created_at"].isoformat()
        return rows

    async def delete_task(self, task_id: str) -> bool:
        """删除任务记录（仅 done/failed 可删，日志级联删除）"""
        task = await self.get_task(task_id)
        if not task:
            return False
        if task["status"] not in ("done", "failed"):
            return False
        result = await postgres_tool.execute(
            "DELETE FROM tasks WHERE id = $1 AND status IN ('done', 'failed')",
            task_id,
        )
        return "DELETE 1" in result

    async def clone_task(self, task_id: str) -> str | None:
        """复制任务参数创建新任务（返回新 task_id）"""
        task = await self.get_task(task_id)
        if not task:
            return None
        new_id = str(uuid.uuid4())
        await postgres_tool.execute(
            """
            INSERT INTO tasks (id, task_type, title, status, params, total_items, created_by)
            VALUES ($1, $2, $3, 'pending', $4::jsonb, $5, $6)
            """,
            new_id, task["task_type"], f"{task['title']} (clone)",
            json.dumps(task.get("params") or {}), task.get("total_items", 0),
            "api",
        )
        logger.info("Task cloned: %s -> %s", task_id[:8], new_id[:8])
        return new_id

    async def retry_task(self, task_id: str) -> bool:
        """重试失败的任务（检查 retry_count < max_retries）"""
        task = await self.get_task(task_id)
        if not task:
            return False
        if task["status"] != "failed":
            return False
        if task["retry_count"] >= task["max_retries"]:
            logger.warning(
                "Task %s exceeded max retries (%d/%d)",
                task_id[:8], task["retry_count"], task["max_retries"],
            )
            return False

        result = await postgres_tool.execute(
            """
            UPDATE tasks
            SET status = 'pending', error_message = NULL,
                started_at = NULL, finished_at = NULL, updated_at = NOW()
            WHERE id = $1 AND status = 'failed'
            """,
            task_id,
        )
        return "UPDATE 1" in result

    async def get_retry_delay(self, task_id: str) -> float:
        """计算指数退避延迟（秒）: 1, 2, 4, 8..."""
        task = await self.get_task(task_id)
        if not task:
            return 1.0
        from config.policy_loader import get_retry_config
        cfg = get_retry_config()
        initial = cfg.get("initial_delay_seconds", 1)
        multiplier = cfg.get("backoff_multiplier", 2)
        return initial * (multiplier ** task["retry_count"])

    # ─── 任务控制（暂停 / 取消，进程内标志）───────────────
    # 供支持协作式取消的任务（如 upload_folder）在工作循环中检查。

    def request_control(self, task_id: str) -> dict:
        """获取（或创建）任务控制标志：{paused, cancelled}"""
        c = _controls.get(task_id)
        if c is None:
            c = {"paused": False, "cancelled": False}
            _controls[task_id] = c
        return c

    def set_paused(self, task_id: str, paused: bool) -> None:
        """设置任务暂停状态"""
        self.request_control(task_id)["paused"] = paused

    def set_cancelled(self, task_id: str) -> None:
        """标记任务取消"""
        self.request_control(task_id)["cancelled"] = True

    def is_cancelled(self, task_id: str) -> bool:
        """任务是否已被请求取消"""
        return self.request_control(task_id)["cancelled"]

    def purge_control(self, task_id: str) -> None:
        """清理任务控制标志（任务结束后调用）"""
        _controls.pop(task_id, None)

    async def wait_if_paused(self, task_id: str) -> None:
        """若任务被暂停则挂起；暂停期间被取消则抛 CancelledError"""
        c = self.request_control(task_id)
        while c["paused"]:
            if c["cancelled"]:
                raise asyncio.CancelledError()
            await asyncio.sleep(0.5)


# 模块级单例
task_queue = TaskQueue()
