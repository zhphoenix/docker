"""News Storage Service - news schema 查询

复用 tools/postgres.py 连接池，提供 news schema 只读查询。
SQL 迁移自 mcp-news/server/storage/postgres.py。
"""

import logging
from typing import Optional

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)


class NewsStorageService:
    """News schema 查询服务（复用平台 PG 连接池）"""

    @property
    def _pool(self):
        return postgres_tool

    async def query(self, sql: str, *args) -> list[dict]:
        return await self._pool.query(sql, *args)

    async def query_one(self, sql: str, *args) -> Optional[dict]:
        await self._pool._ensure_pool()
        async with self._pool.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
            return dict(row) if row else None

    # ──────────────────────────────────────────────
    # Article 查询
    # ──────────────────────────────────────────────

    async def search_articles(self, keyword: str = "", category: str = "",
                              days: int = 7, limit: int = 20,
                              offset: int = 0) -> list[dict]:
        """搜索新闻文章"""
        conditions = ["a.collected_at > NOW() - ($1 || ' days')::interval"]
        params: list = [str(days)]
        idx = 2

        if keyword:
            conditions.append(f"(a.title ILIKE ${idx} OR a.content ILIKE ${idx})")
            params.append(f"%{keyword}%")
            idx += 1

        if category:
            conditions.append(f"a.category = ${idx}")
            params.append(category)
            idx += 1

        where = " AND ".join(conditions)
        params.append(limit)
        params.append(offset)

        sql = f"""
            SELECT a.id, a.title, a.summary, a.url, a.category, a.language,
                   a.published_at, a.collected_at, a.status,
                   s.name as source_name,
                   a.metadata->>'importance' as importance
            FROM news.articles a
            LEFT JOIN news.sources s ON a.source_id = s.id
            WHERE {where}
            ORDER BY a.published_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
        """
        return await self.query(sql, *params)

    async def count_articles(self, keyword: str = "", category: str = "",
                             days: int = 7) -> int:
        """统计文章总数（用于分页）"""
        conditions = ["a.collected_at > NOW() - ($1 || ' days')::interval"]
        params: list = [str(days)]
        idx = 2

        if keyword:
            conditions.append(f"(a.title ILIKE ${idx} OR a.content ILIKE ${idx})")
            params.append(f"%{keyword}%")
            idx += 1

        if category:
            conditions.append(f"a.category = ${idx}")
            params.append(category)
            idx += 1

        where = " AND ".join(conditions)
        sql = f"""
            SELECT COUNT(*) as total
            FROM news.articles a
            WHERE {where}
        """
        result = await self.query_one(sql, *params)
        return result["total"] if result else 0

    async def get_article_by_id(self, article_id: str) -> Optional[dict]:
        """获取文章详情（含实体和事件）"""
        article = await self.query_one(
            """
            SELECT a.*, s.name as source_name, s.source_type
            FROM news.articles a
            LEFT JOIN news.sources s ON a.source_id = s.id
            WHERE a.id = $1
            """,
            article_id,
        )
        if not article:
            return None

        # 获取关联实体
        entities = await self.query(
            "SELECT id, name, entity_type, description, confidence FROM news.entities WHERE article_id = $1",
            article_id,
        )
        article["entities"] = entities

        # 获取关联事件
        events = await self.query(
            "SELECT id, event_type, title, summary, impact_score, impact_direction FROM news.events WHERE article_id = $1",
            article_id,
        )
        article["events"] = events

        return article

    # ──────────────────────────────────────────────
    # Event 查询
    # ──────────────────────────────────────────────

    async def search_events(self, event_type: str = "", entity_name: str = "",
                            days: int = 30, limit: int = 20) -> list[dict]:
        """搜索新闻事件"""
        conditions = ["e.created_at > NOW() - ($1 || ' days')::interval"]
        params: list = [str(days)]
        idx = 2

        if event_type:
            conditions.append(f"e.event_type = ${idx}")
            params.append(event_type)
            idx += 1

        if entity_name:
            conditions.append(f"""
                EXISTS (
                    SELECT 1 FROM news.entities ent
                    WHERE ent.article_id = e.article_id
                    AND ent.name ILIKE ${idx}
                )
            """)
            params.append(f"%{entity_name}%")
            idx += 1

        where = " AND ".join(conditions)
        params.append(limit)

        sql = f"""
            SELECT e.id, e.event_type, e.title, e.summary, e.event_time,
                   e.impact_score, e.impact_direction, e.market, e.sector,
                   e.confidence, e.created_at,
                   a.title as article_title
            FROM news.events e
            LEFT JOIN news.articles a ON e.article_id = a.id
            WHERE {where}
            ORDER BY e.event_time DESC NULLS LAST
            LIMIT ${idx}
        """
        return await self.query(sql, *params)

    async def get_event_impact(self, event_id: str) -> Optional[dict]:
        """获取事件影响评估"""
        return await self.query_one(
            """
            SELECT e.id, e.event_type, e.title, e.summary, e.event_time,
                   e.impact_score, e.impact_direction, e.market, e.sector,
                   e.confidence,
                   a.title as article_title, a.category as article_category
            FROM news.events e
            LEFT JOIN news.articles a ON e.article_id = a.id
            WHERE e.id = $1
            """,
            event_id,
        )

    # ──────────────────────────────────────────────
    # Analysis 查询
    # ──────────────────────────────────────────────

    async def get_entity_news_impact(self, entity_name: str, days: int = 30) -> list[dict]:
        """聚合分析实体近期新闻影响"""
        return await self.query(
            """
            SELECT e.name as entity_name, e.entity_type,
                   ev.event_type, ev.title as event_title,
                   ev.impact_score, ev.impact_direction, ev.event_time,
                   a.title as article_title, a.published_at
            FROM news.entities e
            JOIN news.articles a ON e.article_id = a.id
            LEFT JOIN news.events ev ON ev.article_id = a.id
            WHERE e.name ILIKE $1
              AND a.collected_at > NOW() - ($2 || ' days')::interval
            ORDER BY a.published_at DESC
            LIMIT 50
            """,
            f"%{entity_name}%", str(days),
        )

    async def get_entity_news_timeline(self, entity_name: str, days: int = 90,
                                       limit: int = 50) -> list[dict]:
        """获取实体新闻时间线"""
        return await self.query(
            """
            SELECT a.title, a.category, a.published_at, a.url,
                   a.metadata->>'importance' as importance,
                   s.name as source_name
            FROM news.entities e
            JOIN news.articles a ON e.article_id = a.id
            LEFT JOIN news.sources s ON a.source_id = s.id
            WHERE e.name ILIKE $1
              AND a.collected_at > NOW() - ($2 || ' days')::interval
            ORDER BY a.published_at DESC
            LIMIT $3
            """,
            f"%{entity_name}%", str(days), limit,
        )

    # ──────────────────────────────────────────────
    # Source 查询
    # ──────────────────────────────────────────────

    async def list_sources(self, enabled_only: bool = True) -> list[dict]:
        """列出新闻源"""
        where = "WHERE enabled = true" if enabled_only else ""
        return await self.query(
            f"""
            SELECT id, source_id, name, source_type, category, market,
                   priority, enabled, created_at
            FROM news.sources
            {where}
            ORDER BY priority DESC, name
            """
        )

    # ──────────────────────────────────────────────
    # Source Health（NIC-C2）
    # ──────────────────────────────────────────────

    @staticmethod
    def _health_status(r: dict) -> str:
        """根据采集指标判定健康状态

        - disabled : 已停用
        - no_data  : 已启用但从未采集
        - healthy  : 最近成功且无连续失败
        - degraded : 有 1 次近期失败但非连续
        - error    : 最近一次失败或连续失败 >= 2（异常源，红色标记）
        """
        if not r["enabled"]:
            return "disabled"
        total = r["total_runs"] or 0
        failed = r["failed_count"] or 0
        if total == 0 or r["last_collected_at"] is None:
            return "no_data"
        if r["last_success"] is False:
            return "error"
        if failed >= 2:
            return "error"
        if failed == 1:
            return "degraded"
        return "healthy"

    async def get_source_health(self, days: int = 30) -> dict:
        """Source Health 聚合（news.sources 扩列 + news.collect_runs 统计）

        对每个源返回 Latency/Errors/Articles/Duplicates 四项指标 + 覆盖率。
        """
        rows = await self.query(
            """
            SELECT
                s.source_id, s.name, s.source_type, s.category, s.market,
                s.priority, s.enabled,
                s.last_latency_ms, s.last_success, s.last_error,
                s.error_count, s.last_collected_at,
                COUNT(c.id)                                    AS total_runs,
                COUNT(c.id) FILTER (WHERE c.success)           AS success_count,
                COUNT(c.id) FILTER (WHERE NOT c.success)       AS failed_count,
                COALESCE(AVG(c.latency_ms)::float, 0)          AS avg_latency_ms,
                COALESCE(SUM(c.articles_fetched), 0)           AS total_articles,
                COALESCE(SUM(c.articles_stored), 0)            AS total_stored,
                COALESCE(SUM(c.duplicates), 0)                 AS total_duplicates
            FROM news.sources s
            LEFT JOIN news.collect_runs c
                ON c.source_id = s.source_id
                AND c.created_at > NOW() - ($1 || ' days')::interval
            GROUP BY s.source_id, s.name, s.source_type, s.category, s.market,
                     s.priority, s.enabled, s.last_latency_ms, s.last_success,
                     s.last_error, s.error_count, s.last_collected_at
            ORDER BY s.enabled DESC, s.priority DESC, s.name
            """,
            str(days),
        )

        # 覆盖率：enabled 源中健康（无连续失败且最近成功）的比例
        enabled_sources = [r for r in rows if r["enabled"]]
        total_enabled = len(enabled_sources)
        healthy_enabled = sum(1 for r in enabled_sources if self._health_status(r) == "healthy")
        coverage = healthy_enabled / total_enabled if total_enabled else 0.0

        for r in rows:
            r["status"] = self._health_status(r)

        return {
            "sources": rows,
            "coverage": round(coverage, 3),
            "total_sources": len(rows),
            "enabled_sources": total_enabled,
            "healthy_sources": healthy_enabled,
            "days": days,
        }

    # ──────────────────────────────────────────────
    # Article 更新
    # ──────────────────────────────────────────────

    async def update_minio_key(self, article_id: str, minio_key: str) -> None:
        """更新文章的 MinIO raw 存储路径"""
        await postgres_tool.execute(
            "UPDATE news.articles SET minio_key = $2 WHERE id = $1",
            article_id, minio_key,
        )


# 模块级单例
news_storage = NewsStorageService()
