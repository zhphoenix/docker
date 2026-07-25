"""Task Queue - 基于 PostgreSQL tasks 表的简单任务队列

支持：
  - 任务创建、状态更新、进度追踪
  - 断点续传（通过 stage/current_item）
  - 重试（retry_count + 指数退避）
  - 优先级排序
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)


class TaskQueue:
    """PostgreSQL 任务队列"""

    async def create_task(
        self,
        task_type: str,
        title: str,
        params: dict[str, Any] | None = None,
        total_items: int = 0,
        created_by: str = "system",
    ) -> str:
        """创建任务，返回 task_id"""
        task_id = str(uuid.uuid4())
        await postgres_tool.execute(
            """
            INSERT INTO tasks (id, task_type, title, status, params, total_items, created_by)
            VALUES ($1, $2, $3, 'pending', $4, $5, $6)
            """,
            task_id, task_type, title,
            params or {}, total_items, created_by,
        )
        logger.info("Task created: %s [%s] %s", task_id[:8], task_type, title)
        return task_id

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
        await postgres_tool.execute(
            """
            UPDATE tasks
            SET current_item = $2, stage = $3, current_name = $4,
                progress = CASE WHEN total_items > 0
                    THEN ROUND(($2::numeric / total_items) * 100, 2)
                    ELSE 0 END
            WHERE id = $1
            """,
            task_id, current_item, stage, current_name,
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
        """标记任务失败"""
        await postgres_tool.execute(
            """
            UPDATE tasks
            SET status = 'failed', error_message = $2, finished_at = NOW()
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

        query += f" ORDER BY created_at ASC LIMIT ${idx}"
        params.append(limit)

        return await postgres_tool.query(query, *params)

    async def get_task(self, task_id: str) -> dict | None:
        """获取任务详情"""
        rows = await postgres_tool.query("SELECT * FROM tasks WHERE id = $1", task_id)
        return rows[0] if rows else None

    async def retry_task(self, task_id: str) -> bool:
        """重试失败的任务（指数退避由调用方控制）"""
        result = await postgres_tool.execute(
            """
            UPDATE tasks
            SET status = 'pending', error_message = NULL, started_at = NULL, finished_at = NULL
            WHERE id = $1 AND status = 'failed'
            """,
            task_id,
        )
        return "UPDATE 1" in result


# 模块级单例
task_queue = TaskQueue()
