"""Inbox Tools - Knowledge Inbox（HITL 审核流）

Tools:
  13. list_inbox   — 查询 Inbox 记录（按状态过滤）
  14. review_inbox — 人工审核 Inbox 记录（approve / reject）
  15. archive_inbox — 归档 Inbox 记录

对应 core.knowledge_inbox 表（Phase 1 迁移），状态机：
NEW → EXTRACTED → READY_REVIEW → APPROVED / REJECTED → ARCHIVED
"""

from fastmcp import FastMCP

from server.storage.postgres import pg_storage
from server.cache import knowledge_cache
from server.utils import serialize

# Inbox 合法状态
VALID_STATUSES = {"NEW", "EXTRACTED", "READY_REVIEW", "APPROVED", "REJECTED", "ARCHIVED"}


def register_inbox_tools(mcp: FastMCP) -> None:
    """注册 Inbox 相关 MCP Tools"""

    @mcp.tool()
    async def list_inbox(status: str = "", limit: int = 50) -> dict:
        """查询 Knowledge Inbox 待审记录

        Args:
            status: 状态过滤（NEW/EXTRACTED/READY_REVIEW/APPROVED/REJECTED/ARCHIVED），空=全部
            limit: 返回数量上限

        Returns:
            {total, items: [{id, object_type, object_id, status, confidence, source, content, created_at}]}
        """
        if status and status.upper() not in VALID_STATUSES:
            return {"error": f"Invalid status '{status}'. Valid: {sorted(VALID_STATUSES)}"}

        rows = await pg_storage.query(
            """
            SELECT id, object_type, object_id, status, confidence, source, content,
                   reviewer, review_time, created_at, updated_at
            FROM core.knowledge_inbox
            WHERE ($1 = '' OR status = $1)
            ORDER BY created_at ASC
            LIMIT $2
            """,
            status.upper() if status else "",
            limit,
        )
        items = [serialize(r) for r in rows]
        return {"total": len(items), "items": items}

    @mcp.tool()
    async def review_inbox(
        inbox_id: str,
        action: str,
        reason: str = "",
        reviewer: str = "human",
    ) -> dict:
        """人工审核一条 Inbox 记录

        Args:
            inbox_id: Inbox 记录 UUID
            action: approve / reject
            reason: 拒绝原因（reject 时建议填写）
            reviewer: 审核人标识

        Returns:
            {id, status, message}
        """
        action = action.lower()
        if action not in {"approve", "reject"}:
            return {"error": "action must be 'approve' or 'reject'"}

        row = await pg_storage.query_one(
            "SELECT status FROM core.knowledge_inbox WHERE id = $1", inbox_id
        )
        if not row:
            return {"error": f"Inbox record '{inbox_id}' not found"}
        if row["status"] not in {"READY_REVIEW", "EXTRACTED", "NEW"}:
            return {"error": f"Record in state '{row['status']}' cannot be reviewed"}

        new_status = "APPROVED" if action == "approve" else "REJECTED"
        await pg_storage.execute(
            """
            UPDATE core.knowledge_inbox
            SET status = $2, reviewer = $3, review_time = NOW(), updated_at = NOW()
            WHERE id = $1
            """,
            inbox_id, new_status, reviewer,
        )
        # 写审核日志
        await pg_storage.execute(
            """
            INSERT INTO audit.knowledge_review_log (inbox_id, action, reviewer, reason)
            VALUES ($1, $2, $3, $4)
            """,
            inbox_id, action, reviewer, reason or None,
        )

        # 缓存失效
        knowledge_cache.invalidate("inbox:")

        return {"id": inbox_id, "status": new_status, "message": f"Record {action}d"}

    @mcp.tool()
    async def archive_inbox(inbox_id: str, reviewer: str = "human") -> dict:
        """归档一条 Inbox 记录（APPROVED/REJECTED 后归档）

        Args:
            inbox_id: Inbox 记录 UUID
            reviewer: 操作人标识

        Returns:
            {id, status: "ARCHIVED"}
        """
        row = await pg_storage.query_one(
            "SELECT status FROM core.knowledge_inbox WHERE id = $1", inbox_id
        )
        if not row:
            return {"error": f"Inbox record '{inbox_id}' not found"}
        if row["status"] not in {"APPROVED", "REJECTED"}:
            return {"error": f"Only APPROVED/REJECTED records can be archived, got '{row['status']}'"}

        await pg_storage.execute(
            """
            UPDATE core.knowledge_inbox
            SET status = 'ARCHIVED', reviewer = $2, updated_at = NOW()
            WHERE id = $1
            """,
            inbox_id, reviewer,
        )
        knowledge_cache.invalidate("inbox:")
        return {"id": inbox_id, "status": "ARCHIVED"}