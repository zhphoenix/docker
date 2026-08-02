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
