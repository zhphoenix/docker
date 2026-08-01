"""MCP News PostgreSQL Storage - news schema 查询

独立连接池，针对 news schema 的只读查询。
遵循 MCP-001/002：Tools 不含业务逻辑，通过 storage/ 访问 DB。
"""

import asyncio
import logging
from typing import Optional

import asyncpg

from server.config import settings

logger = logging.getLogger(__name__)


class NewsPostgresStorage:
    """PostgreSQL 连接池 + news schema 查询"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self._lock = asyncio.Lock()

    async def _ensure_pool(self) -> None:
        """双重检查锁定"""
        if not self.pool:
            async with self._lock:
                if not self.pool:
                    await self.connect()

    async def connect(self) -> None:
        """创建连接池"""
        dsn = (
            f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
            f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
        )
        self.pool = await asyncpg.create_pool(
            dsn,
            min_size=settings.PG_POOL_MIN_SIZE,
            max_size=settings.PG_POOL_MAX_SIZE,
            command_timeout=60,
            server_settings={
                "statement_timeout": str(settings.PG_STATEMENT_TIMEOUT_MS),
            },
        )
        logger.info(
            "News MCP PG pool created (min=%d, max=%d)",
            settings.PG_POOL_MIN_SIZE,
            settings.PG_POOL_MAX_SIZE,
        )

    async def close(self) -> None:
        """关闭连接池"""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("News MCP PG pool closed")

    async def query(self, sql: str, *args) -> list[dict]:
        """查询"""
        await self._ensure_pool()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
            return [dict(r) for r in rows]

    async def query_one(self, sql: str, *args) -> Optional[dict]:
        """查询单行"""
        await self._ensure_pool()
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
            return dict(row) if row else None

    # ──────────────────────────────────────────────
    # Article 查询
    # ──────────────────────────────────────────────

    async def search_articles(self, keyword: str = "", category: str = "",
                              days: int = 7, limit: int = 20) -> list[dict]:
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
        params.append(str(limit))

        sql = f"""
            SELECT a.id, a.title, a.summary, a.url, a.category, a.language,
                   a.published_at, a.collected_at, a.status,
                   s.name as source_name,
                   a.metadata->>'importance' as importance
            FROM news.articles a
            LEFT JOIN news.sources s ON a.source_id = s.id
            WHERE {where}
            ORDER BY a.published_at DESC
            LIMIT ${idx}
        """
        return await self.query(sql, *params)

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
        params.append(str(limit))

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


# 模块级单例
news_pg_storage = NewsPostgresStorage()
