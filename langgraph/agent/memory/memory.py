"""Memory System - 三层记忆架构

工作记忆 (Working Memory):
    LangGraph Checkpoint → PostgreSQL langgraph 库
    自动管理，无需手动操作。

情景记忆 (Episodic Memory):
    PostgreSQL research_tasks 表
    记录每次研究任务的输入/输出/质量/耗时。

知识记忆 (Knowledge Memory):
    Qdrant 向量索引 + Obsidian Vault
    通过 RAG 检索和 Vault 读写访问。
"""

import json
import logging

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)


class MemoryManager:
    """三层记忆管理器"""

    # ------------------------------------------------------------------
    # 情景记忆：research_tasks
    # ------------------------------------------------------------------

    async def start_episode(
        self,
        question: str,
        agent_type: str = "research",
        market: str | None = None,
        symbol: str | None = None,
        plan: dict | None = None,
    ) -> str:
        """记录研究任务开始，返回 task_id"""
        try:
            rows = await postgres_tool.query(
                """
                INSERT INTO research_tasks (question, agent_type, market, symbol, plan, status)
                VALUES ($1, $2, $3, $4, $5, 'running')
                RETURNING id
                """,
                question,
                agent_type,
                market,
                symbol,
                json.dumps(plan or {}),
            )
            task_id = str(rows[0]["id"])
            logger.debug("Episode started: %s", task_id)
            return task_id
        except Exception as e:
            logger.warning("Failed to start episode: %s", e)
            return ""

    async def complete_episode(
        self,
        task_id: str,
        answer: str,
        quality: str = "good",
        confidence: float = 0.0,
        document_count: int = 0,
        elapsed_seconds: float = 0.0,
    ) -> None:
        """记录研究任务完成"""
        if not task_id:
            return
        try:
            await postgres_tool.execute(
                """
                UPDATE research_tasks
                SET answer=$2, quality=$3, confidence=$4, document_count=$5,
                    elapsed_seconds=$6, status='completed', completed_at=NOW()
                WHERE id=$1
                """,
                task_id,
                answer[:10000],  # 截断避免过大
                quality,
                confidence,
                document_count,
                elapsed_seconds,
            )
            logger.debug("Episode completed: %s (%.1fs)", task_id, elapsed_seconds)
        except Exception as e:
            logger.warning("Failed to complete episode: %s", e)

    async def fail_episode(self, task_id: str, error: str) -> None:
        """记录研究任务失败"""
        if not task_id:
            return
        try:
            await postgres_tool.execute(
                """
                UPDATE research_tasks
                SET error=$2, status='failed', completed_at=NOW()
                WHERE id=$1
                """,
                task_id,
                error[:2000],
            )
        except Exception as e:
            logger.warning("Failed to record episode failure: %s", e)

    async def recall_episodes(
        self,
        symbol: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """回忆历史研究任务

        Args:
            symbol: 按股票代码过滤（可选）
            limit: 返回数量

        Returns:
            历史任务列表（按时间倒序）
        """
        try:
            if symbol:
                rows = await postgres_tool.query(
                    """
                    SELECT id, question, agent_type, market, symbol, quality,
                           confidence, document_count, elapsed_seconds,
                           created_at, completed_at
                    FROM research_tasks
                    WHERE symbol=$1 AND status='completed'
                    ORDER BY created_at DESC
                    LIMIT $2
                    """,
                    symbol,
                    limit,
                )
            else:
                rows = await postgres_tool.query(
                    """
                    SELECT id, question, agent_type, market, symbol, quality,
                           confidence, document_count, elapsed_seconds,
                           created_at, completed_at
                    FROM research_tasks
                    WHERE status='completed'
                    ORDER BY created_at DESC
                    LIMIT $1
                    """,
                    limit,
                )
            for r in rows:
                r["id"] = str(r["id"])
            return rows
        except Exception as e:
            logger.warning("Failed to recall episodes: %s", e)
            return []

    async def get_episode(self, task_id: str) -> dict | None:
        """获取单个研究任务详情（含完整回答）"""
        try:
            rows = await postgres_tool.query(
                "SELECT * FROM research_tasks WHERE id=$1", task_id
            )
            if rows:
                rows[0]["id"] = str(rows[0]["id"])
                return rows[0]
            return None
        except Exception as e:
            logger.warning("Failed to get episode: %s", e)
            return None


# 模块级单例
memory_manager = MemoryManager()
