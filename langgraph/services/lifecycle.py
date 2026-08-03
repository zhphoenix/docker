"""News Lifecycle Service — DLM §14 Knowledge Maintenance Agent

每日定时运行（凌晨 3:30），负责：
- Duplicate Detection: 跨批次 Hash + Embedding 重复检测
- Importance Rescoring: 重新评估未分级文章
- Archive: 归档过期 Tier 3 文章（>90天）
- Graph Cleanup: AGE 清理低置信度孤立节点
- Embedding Cleanup: Qdrant 删除已归档文章的 embedding points

遵循 DLM 核心原则：把短期信息不断压缩成长期知识。
"""

import logging

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)


class NewsLifecycleService:
    """新闻生命周期维护服务"""

    # ──────────────────────────────────────────────
    # Duplicate Detection
    # ──────────────────────────────────────────────

    async def run_duplicate_detection(self) -> dict:
        """检测跨批次重复（Hash 精确匹配）

        查找不同 ID 但 content_hash 相同的文章，标记后者为 duplicate。
        """
        try:
            rows = await postgres_tool.query("""
                SELECT a.id, a.title
                FROM news.articles a
                INNER JOIN news.articles b
                    ON a.content_hash = b.content_hash
                    AND a.id > b.id
                WHERE a.status != 'duplicate'
                  AND a.content_hash IS NOT NULL
                  AND a.content_hash != ''
                LIMIT 100
            """)

            if rows:
                ids = [r["id"] for r in rows]
                await postgres_tool.execute(
                    "UPDATE news.articles SET status = 'duplicate' WHERE id = ANY($1)",
                    ids,
                )
                logger.info("Lifecycle: marked %d duplicate articles", len(ids))

            return {"duplicates_found": len(rows)}
        except Exception as e:
            logger.error("Lifecycle duplicate_detection failed: %s", e)
            return {"error": str(e)}

    # ──────────────────────────────────────────────
    # Importance Rescoring
    # ──────────────────────────────────────────────

    async def run_importance_rescoring(self) -> dict:
        """重新评估未分级文章的重要性

        对 tier 为默认值 3 但 importance_score >= 0.5 的文章重新分级。
        """
        try:
            result = await postgres_tool.execute("""
                UPDATE news.articles
                SET tier = CASE
                    WHEN importance_score >= 0.8 THEN 1
                    WHEN importance_score >= 0.5 THEN 2
                    ELSE 3
                END
                WHERE tier = 3
                  AND importance_score >= 0.5
                  AND status = 'indexed'
            """)
            logger.info("Lifecycle: importance rescoring completed")
            return {"rescored": True}
        except Exception as e:
            logger.error("Lifecycle importance_rescoring failed: %s", e)
            return {"error": str(e)}

    # ──────────────────────────────────────────────
    # Archive
    # ──────────────────────────────────────────────

    async def run_archive(self) -> dict:
        """归档过期 Tier 3 文章（>90天）

        DLM §13: Tier 3 短期保存 30-90 天。
        """
        try:
            result = await postgres_tool.execute("""
                UPDATE news.articles
                SET status = 'archived'
                WHERE tier = 3
                  AND status = 'indexed'
                  AND collected_at < NOW() - INTERVAL '90 days'
            """)
            logger.info("Lifecycle: archive completed")
            return {"archived": True}
        except Exception as e:
            logger.error("Lifecycle archive failed: %s", e)
            return {"error": str(e)}

    # ──────────────────────────────────────────────
    # Graph Cleanup (AGE)
    # ──────────────────────────────────────────────

    async def run_graph_cleanup(self) -> dict:
        """AGE: 清理低置信度孤立节点

        删除 confidence < 0.3 且无任何边连接的节点。
        """
        try:
            from storage.knowledge.age import knowledge_age

            if not knowledge_age.available:
                return {"skipped": "AGE unavailable"}

            async with knowledge_age.pool.acquire() as conn:
                await conn.execute("LOAD 'age';")
                cypher = """
                    MATCH (n)
                    WHERE n.confidence < 0.3 AND NOT (n)--()
                    WITH collect(n) AS nodes
                    FOREACH (x IN nodes | DELETE x)
                    RETURN size(nodes) AS deleted
                """
                sql = f"SELECT * FROM cypher('investment_knowledge_graph', $${cypher}$$) AS (deleted agtype);"
                try:
                    row = await conn.fetchrow(sql)
                    deleted = row["deleted"] if row else 0
                    logger.info("Lifecycle: AGE graph cleanup deleted %s nodes", deleted)
                    return {"deleted_nodes": str(deleted)}
                except Exception as e:
                    logger.debug("Lifecycle: AGE cleanup cypher failed: %s", e)
                    return {"error": str(e)}
        except Exception as e:
            logger.error("Lifecycle graph_cleanup failed: %s", e)
            return {"error": str(e)}

    # ──────────────────────────────────────────────
    # Embedding Cleanup (Qdrant)
    # ──────────────────────────────────────────────

    async def run_embedding_cleanup(self) -> dict:
        """Qdrant: 删除已归档文章的 embedding points

        查询 status='archived' 且有 embedding_id 的文章，
        从 news_embeddings collection 中删除对应 points。
        """
        try:
            rows = await postgres_tool.query("""
                SELECT embedding_id FROM news.articles
                WHERE status = 'archived'
                  AND embedding_id IS NOT NULL
                  AND embedding_id != ''
                LIMIT 500
            """)

            if not rows:
                return {"cleaned": 0}

            from tools.qdrant import qdrant_tool
            import asyncio

            point_ids = [r["embedding_id"] for r in rows]
            try:
                await asyncio.to_thread(
                    qdrant_tool.client.delete,
                    collection_name="news_embeddings",
                    points_selector=point_ids,
                )
                # 清除 PG 中的 embedding_id 引用
                await postgres_tool.execute(
                    "UPDATE news.articles SET embedding_id = NULL WHERE embedding_id = ANY($1)",
                    point_ids,
                )
                logger.info("Lifecycle: cleaned %d embeddings", len(point_ids))
            except Exception as e:
                logger.debug("Lifecycle: Qdrant cleanup failed: %s", e)

            return {"cleaned": len(point_ids)}
        except Exception as e:
            logger.error("Lifecycle embedding_cleanup failed: %s", e)
            return {"error": str(e)}

    # ──────────────────────────────────────────────
    # Full Run
    # ──────────────────────────────────────────────

    async def run_all(self) -> dict:
        """执行全部生命周期维护任务"""
        logger.info("Lifecycle: starting full maintenance run")
        results = {}
        results["duplicate_detection"] = await self.run_duplicate_detection()
        results["importance_rescoring"] = await self.run_importance_rescoring()
        results["archive"] = await self.run_archive()
        results["graph_cleanup"] = await self.run_graph_cleanup()
        results["embedding_cleanup"] = await self.run_embedding_cleanup()
        logger.info("Lifecycle: maintenance complete: %s", results)
        return results


# 模块级单例
news_lifecycle = NewsLifecycleService()
