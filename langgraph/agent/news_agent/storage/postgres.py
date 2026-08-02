"""News PostgreSQL Storage - news schema CRUD

复用 tools.postgres.postgres_tool 单例，
所有操作针对 news schema 下的表：
  news.sources / news.articles / news.entities / news.events / news.relations
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)


class NewsPostgresStorage:
    """新闻 PostgreSQL 存储层

    职责：
    - 批量写入 articles / entities / events / relations
    - 文章状态更新
    - 去重查询（content_hash）
    """

    # ──────────────────────────────────────────────
    # Articles
    # ──────────────────────────────────────────────

    async def bulk_insert_articles(self, articles: list[dict]) -> list[str]:
        """批量插入文章

        Args:
            articles: [{"source_id", "title", "content", "url", "language",
                        "category", "importance_score", "published_at", "content_hash", "metadata"}]

        Returns:
            文章 UUID 列表（与输入顺序一一对应，已存在的文章返回其已有 ID）
        """
        if not articles:
            return []

        # C-5 修复：预查询已存在的 URL，避免 ON CONFLICT DO NOTHING 后返回无效 ID
        urls = [art.get("url") for art in articles if art.get("url")]
        existing_map: dict[str, str] = {}  # url → existing article id
        if urls:
            rows = await postgres_tool.query(
                "SELECT id, url FROM news.articles WHERE url = ANY($1)",
                urls,
            )
            existing_map = {r["url"]: str(r["id"]) for r in rows}

        # 分离新/旧文章
        result_ids: list[str] = [""] * len(articles)
        new_args: list[tuple] = []

        for i, art in enumerate(articles):
            url = art.get("url")
            if url and url in existing_map:
                result_ids[i] = existing_map[url]
            else:
                new_id = str(uuid.uuid4())
                result_ids[i] = new_id

                published_at = art.get("published_at")
                if isinstance(published_at, str):
                    try:
                        published_at = datetime.fromisoformat(published_at)
                    except (ValueError, TypeError):
                        published_at = None

                source_id = art.get("source_id")
                metadata = art.get("metadata", {})
                new_args.append((
                    uuid.UUID(new_id),
                    uuid.UUID(source_id) if source_id else None,
                    art.get("title", ""),
                    art.get("content", ""),
                    url,
                    art.get("language", "zh"),
                    art.get("category", "macro"),
                    art.get("importance_score", 0.5),
                    published_at,
                    art.get("content_hash", ""),
                    json.dumps(metadata, ensure_ascii=False),
                    art.get("tier", 3),
                ))

        if new_args:
            sql = """
                INSERT INTO news.articles
                    (id, source_id, title, content, url, language, category,
                     importance_score, published_at, content_hash, metadata, tier, status)
                VALUES
                    ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 'raw')
                ON CONFLICT (url) DO NOTHING
            """
            await postgres_tool.execute_many(sql, new_args)

        inserted = len(new_args)
        skipped = len(articles) - inserted
        logger.debug("Inserted %d articles (%d skipped as duplicates)", inserted, skipped)
        return result_ids

    async def update_articles_status(self, article_ids: list[str], status: str) -> None:
        """批量更新文章状态"""
        if not article_ids:
            return
        uuids = [uuid.UUID(aid) for aid in article_ids]
        sql = "UPDATE news.articles SET status = $2 WHERE id = ANY($1)"
        await postgres_tool.execute(sql, uuids, status)

    async def check_content_hash_exists(self, content_hash: str) -> bool:
        """检查 content_hash 是否已存在（去重）"""
        rows = await postgres_tool.query(
            "SELECT 1 FROM news.articles WHERE content_hash = $1 LIMIT 1",
            content_hash,
        )
        return len(rows) > 0

    # ──────────────────────────────────────────────
    # Entities
    # ──────────────────────────────────────────────

    async def bulk_insert_entities(self, entities: list[dict]) -> list[str]:
        """批量插入实体

        Args:
            entities: [{"article_id", "name", "entity_type", "description", "confidence"}]

        Returns:
            实体 UUID 列表
        """
        if not entities:
            return []

        ids = [str(uuid.uuid4()) for _ in entities]

        sql = """
            INSERT INTO news.entities
                (id, article_id, name, entity_type, description, aliases, confidence)
            VALUES
                ($1, $2, $3, $4, $5, $6, $7)
        """

        args_list = []
        for i, ent in enumerate(entities):
            article_id = ent.get("article_id")
            args_list.append((
                uuid.UUID(ids[i]),
                uuid.UUID(article_id) if article_id else None,
                ent.get("name", ""),
                ent.get("entity_type", "Concept"),
                ent.get("description", ""),
                ent.get("aliases", []),
                ent.get("confidence", 0.8),
            ))

        await postgres_tool.execute_many(sql, args_list)
        logger.debug("Inserted %d entities", len(ids))
        return ids

    # ──────────────────────────────────────────────
    # Events
    # ──────────────────────────────────────────────

    async def bulk_insert_events(self, events: list[dict]) -> list[str]:
        """批量插入事件（含 DLM Event-centric 合并）

        合并策略：同类型 + 标题相似 + 7天窗口内 → 合并为同一事件（source_count + 1）

        Args:
            events: [{"article_id", "event_type", "title", "summary",
                      "event_time", "impact_score", "impact_direction",
                      "market", "sector", "confidence"}]

        Returns:
            事件 UUID 列表
        """
        if not events:
            return []

        ids = [str(uuid.uuid4()) for _ in events]
        merge_window_days = 7  # DLM 事件合并窗口

        for i, evt in enumerate(events):
            article_id = evt.get("article_id")
            event_time = evt.get("event_time")
            if isinstance(event_time, str):
                try:
                    event_time = datetime.fromisoformat(event_time)
                except (ValueError, TypeError):
                    event_time = None

            event_type = evt.get("event_type", "technology")
            title = evt.get("title", "")

            # DLM Event-centric 合并：查询近期同类事件
            merged = False
            if title and len(title) > 5:
                try:
                    # 提取标题关键词（前 20 字符）用于模糊匹配
                    title_keyword = title[:20]
                    existing = await postgres_tool.query(
                        """
                        SELECT id, source_count FROM news.events
                        WHERE event_type = $1
                          AND created_at > NOW() - ($2 || ' days')::interval
                          AND title ILIKE '%' || $3 || '%'
                        LIMIT 1
                        """,
                        event_type, str(merge_window_days), title_keyword,
                    )
                    if existing:
                        # 合并：更新 source_count
                        existing_id = existing[0]["id"]
                        await postgres_tool.execute(
                            "UPDATE news.events SET source_count = COALESCE(source_count, 1) + 1 WHERE id = $1",
                            existing_id,
                        )
                        ids[i] = str(existing_id)
                        merged = True
                        logger.debug("Event merged into existing: '%s'", title[:40])
                except Exception as e:
                    logger.debug("Event merge check failed: %s", e)

            if not merged:
                # 新事件：直接插入
                sql = """
                    INSERT INTO news.events
                        (id, article_id, event_type, title, summary, event_time,
                         impact_score, impact_direction, market, sector, confidence, source_count)
                    VALUES
                        ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 1)
                """
                await postgres_tool.execute(
                    sql,
                    uuid.UUID(ids[i]),
                    uuid.UUID(article_id) if article_id else None,
                    event_type,
                    title,
                    evt.get("summary", ""),
                    event_time,
                    evt.get("impact_score", 0.0),
                    evt.get("impact_direction", "neutral"),
                    evt.get("market", []),
                    evt.get("sector", []),
                    evt.get("confidence", 0.8),
                )

        logger.debug("Processed %d events (merge window=%dd)", len(ids), merge_window_days)
        return ids

    # ──────────────────────────────────────────────
    # Relations
    # ──────────────────────────────────────────────

    async def bulk_insert_relations(self, relations: list[dict]) -> int:
        """批量插入关系

        Args:
            relations: [{"article_id", "source_entity", "target_entity",
                         "relation_type", "confidence"}]

        Returns:
            插入数量
        """
        if not relations:
            return 0

        sql = """
            INSERT INTO news.relations
                (id, article_id, source_entity, target_entity, relation_type, confidence)
            VALUES
                ($1, $2, $3, $4, $5, $6)
        """

        args_list = []
        for rel in relations:
            article_id = rel.get("article_id")
            args_list.append((
                uuid.uuid4(),
                uuid.UUID(article_id) if article_id else None,
                uuid.UUID(rel["source_entity"]),
                uuid.UUID(rel["target_entity"]),
                rel.get("relation_type", "depends_on"),
                rel.get("confidence", 0.7),
            ))

        await postgres_tool.execute_many(sql, args_list)
        logger.debug("Inserted %d relations", len(relations))
        return len(relations)

    # ──────────────────────────────────────────────
    # Sources
    # ──────────────────────────────────────────────

    async def get_or_create_source(self, source_id: str, name: str, source_type: str,
                                   category: list = None, market: list = None) -> str:
        """获取或创建新闻源，返回 source UUID"""
        rows = await postgres_tool.query(
            "SELECT id FROM news.sources WHERE source_id = $1",
            source_id,
        )
        if rows:
            return str(rows[0]["id"])

        new_id = uuid.uuid4()
        await postgres_tool.execute(
            """
            INSERT INTO news.sources (id, source_id, name, source_type, category, market)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            new_id, source_id, name, source_type,
            category or [], market or [],
        )
        return str(new_id)


# 模块级单例
news_storage = NewsPostgresStorage()
