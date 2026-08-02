"""Human Approval - 人审机制

应用场景:
  - Agent 生成报告后等待人工确认再写入 Vault
  - 重要操作（删除、批量修改）需人工审批

实现:
  - 基于 tasks 表（task_type='approval', status='awaiting_approval'）
  - 审批通过后执行回调（如写入 Vault）
  - 审批拒绝后标记 rejected
"""

import json
import logging
import uuid
from typing import Any, Callable, Coroutine

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)

# 审批通过后的回调注册表
_approval_callbacks: dict[str, Callable[..., Coroutine[Any, Any, None]]] = {}


def register_approval_callback(action_type: str, callback: Callable[..., Coroutine[Any, Any, None]]):
    """注册审批通过后的回调函数

    Args:
        action_type: 操作类型（如 "vault_write", "report_publish"）
        callback: async 函数，接收 params dict
    """
    _approval_callbacks[action_type] = callback


async def create_approval(
    title: str,
    action_type: str,
    params: dict[str, Any],
    content_preview: str = "",
    created_by: str = "agent",
) -> str:
    """创建审批请求

    Args:
        title: 审批标题
        action_type: 操作类型
        params: 操作参数（审批通过后传给回调）
        content_preview: 内容预览（供审批人查看）
        created_by: 创建者

    Returns:
        approval_id (task_id)
    """
    approval_id = str(uuid.uuid4())
    await postgres_tool.execute(
        """
        INSERT INTO tasks (id, task_type, title, status, params, created_by, stage)
        VALUES ($1, 'approval', $2, 'awaiting_approval', $3::jsonb, $4, $5)
        """,
        approval_id,
        title,
        json.dumps({
            "action_type": action_type,
            "params": params,
            "content_preview": content_preview[:5000],
        }),
        created_by,
        action_type,
    )
    logger.info(
        "Approval created | %s | %s | by=%s",
        approval_id[:8], title, created_by,
    )
    return approval_id


async def approve(approval_id: str, approved_by: str = "human") -> dict[str, Any]:
    """审批通过 → 执行回调

    Returns:
        {"status": "approved", "action_type": str, "result": str}
    """
    rows = await postgres_tool.query(
        "SELECT * FROM tasks WHERE id = $1 AND task_type = 'approval'",
        approval_id,
    )
    if not rows:
        return {"status": "error", "message": "Approval not found"}

    task = rows[0]
    if task["status"] != "awaiting_approval":
        return {"status": "error", "message": f"Invalid state: {task['status']}"}

    params_data = task.get("params", {}) or {}
    if isinstance(params_data, str):
        params_data = json.loads(params_data)

    action_type = params_data.get("action_type", "")
    action_params = params_data.get("params", {})

    # 执行回调
    callback = _approval_callbacks.get(action_type)
    result_msg = "no callback"
    if callback:
        try:
            await callback(action_params)
            result_msg = "executed"
        except Exception as e:
            result_msg = f"callback error: {e}"
            logger.error("Approval callback failed | %s | %s", approval_id[:8], e)

    # 更新状态
    await postgres_tool.execute(
        """
        UPDATE tasks
        SET status = 'done', finished_at = NOW(),
            result = $2::jsonb, updated_at = NOW()
        WHERE id = $1
        """,
        approval_id,
        json.dumps({"approved_by": approved_by, "result": result_msg}),
    )

    logger.info("Approval approved | %s | by=%s", approval_id[:8], approved_by)
    return {"status": "approved", "action_type": action_type, "result": result_msg}


async def reject(approval_id: str, reason: str = "", rejected_by: str = "human") -> dict[str, Any]:
    """审批拒绝"""
    rows = await postgres_tool.query(
        "SELECT id FROM tasks WHERE id = $1 AND task_type = 'approval' AND status = 'awaiting_approval'",
        approval_id,
    )
    if not rows:
        return {"status": "error", "message": "Approval not found or not pending"}

    await postgres_tool.execute(
        """
        UPDATE tasks
        SET status = 'rejected', finished_at = NOW(),
            error_message = $2, result = $3::jsonb, updated_at = NOW()
        WHERE id = $1
        """,
        approval_id,
        reason[:500],
        json.dumps({"rejected_by": rejected_by}),
    )

    logger.info("Approval rejected | %s | by=%s | reason=%s", approval_id[:8], rejected_by, reason[:50])
    return {"status": "rejected", "reason": reason}


async def list_pending_approvals(limit: int = 20) -> list[dict]:
    """列出待审批任务"""
    rows = await postgres_tool.query(
        """
        SELECT id, title, status, params, stage, created_by, created_at
        FROM tasks
        WHERE task_type = 'approval' AND status = 'awaiting_approval'
        ORDER BY created_at ASC
        LIMIT $1
        """,
        limit,
    )
    results = []
    for r in rows:
        params_data = r.get("params", {}) or {}
        if isinstance(params_data, str):
            params_data = json.loads(params_data)
        results.append({
            "id": str(r["id"]),
            "title": r["title"],
            "action_type": params_data.get("action_type", ""),
            "content_preview": params_data.get("content_preview", "")[:500],
            "created_by": r.get("created_by", ""),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        })
    return results

