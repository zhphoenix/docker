"""Node 6: News Publisher — 存储 + 触发 Knowledge Agent

职责：
- 批量存储文章、实体、事件、关系到 PostgreSQL（news schema）
- 高置信度实体/关系触发 Knowledge Agent 合并到 core schema
- 更新文章状态（raw → indexed）

遵循 ARCH-003：不直接 import asyncpg/httpx，通过 storage/ 层访问。
"""

import logging

from news_agent.storage.postgres import news_storage
from config.policy_loader import get_policy

logger = logging.getLogger(__name__)

# 触发 Knowledge Agent 合并的置信度阈值
KNOWLEDGE_MERGE_CONFIDENCE = 0.8


async def news_publisher(state: dict) -> dict:
    """新闻发布/存储节点

    输入: classified_articles, entities, events, relations, impact_assessments
    输出: stored_article_ids, stored_event_ids, knowledge_agent_triggered
    """
    articles = state.get("classified_articles", [])
    entities = state.get("entities", [])
    events = state.get("events", [])
    relations = state.get("relations", [])
    source_id = state.get("source_id", "")
    new_errors: list[str] = []

    if not articles:
        return {
            "stored_article_ids": [],
            "stored_event_ids": [],
            "knowledge_agent_triggered": False,
            "errors": new_errors,
        }

    # ── 0. 解析 source_id 字符串 → UUID (C-2 修复) ──
    source_uuid = None
    if source_id:
        try:
            source_uuid = await news_storage.get_or_create_source(
                source_id=source_id,
                name=source_id,
                source_type="rss",  # 默认，后续可由 registry 覆盖
            )
        except Exception as e:
            logger.warning("Publisher: source resolution failed: %s", e)

    # ── 1. 存储文章 ──
    article_records = []
    for art in articles:
        article_records.append({
            "source_id": source_uuid,  # UUID 或 None
            "title": art.get("title", ""),
            "content": art.get("content", ""),
            "url": art.get("url", ""),
            "language": art.get("language", "zh"),
            "category": art.get("category", "macro"),
            "importance_score": art.get("importance", 0.5),
            "published_at": art.get("published_at"),
            "content_hash": art.get("content_hash", ""),
            "metadata": {
                "importance": art.get("importance", 0.5),
                "market": art.get("market", []),
                "sector": art.get("sector", []),
            },
        })

    try:
        stored_article_ids = await news_storage.bulk_insert_articles(article_records)
        logger.info("Publisher: stored %d articles", len(stored_article_ids))
    except Exception as e:
        new_errors.append(f"Publisher: article storage failed: {e}")
        stored_article_ids = []

    # ── 2. 存储实体 ──
    entity_records = []
    for i, ent in enumerate(entities):
        # C-3 修复：使用 article_idx 作为 classified_articles 位置索引
        art_idx = ent.get("article_idx", 0)
        article_id = stored_article_ids[art_idx] if art_idx < len(stored_article_ids) else None
        entity_records.append({
            "article_id": article_id,
            "name": ent.get("name", ""),
            "entity_type": ent.get("entity_type", "Concept"),
            "description": ent.get("description", ""),
            "aliases": ent.get("aliases", []),
            "confidence": ent.get("confidence", 0.8),
        })

    stored_entity_ids: list[str] = []
    if entity_records:
        try:
            stored_entity_ids = await news_storage.bulk_insert_entities(entity_records)
            logger.info("Publisher: stored %d entities", len(stored_entity_ids))
        except Exception as e:
            new_errors.append(f"Publisher: entity storage failed: {e}")

    # ── 3. 存储事件 ──
    event_records = []
    for evt in events:
        art_idx = evt.get("article_idx", 0)
        article_id = stored_article_ids[art_idx] if art_idx < len(stored_article_ids) else None
        event_records.append({
            "article_id": article_id,
            "event_type": evt.get("event_type", "technology"),
            "title": evt.get("title", ""),
            "summary": evt.get("summary", ""),
            "event_time": evt.get("event_time"),
            "impact_score": evt.get("impact_score", 0.0),
            "impact_direction": evt.get("impact_direction", "neutral"),
            "market": evt.get("market", []),
            "sector": evt.get("sector", []),
            "confidence": evt.get("confidence", 0.8),
        })

    stored_event_ids: list[str] = []
    if event_records:
        try:
            stored_event_ids = await news_storage.bulk_insert_events(event_records)
            logger.info("Publisher: stored %d events", len(stored_event_ids))
        except Exception as e:
            new_errors.append(f"Publisher: event storage failed: {e}")

    # ── 4. 存储关系 ──
    if relations and stored_entity_ids:
        # 构建实体名称→ID映射
        name_to_id = {}
        for i, ent in enumerate(entities):
            if i < len(stored_entity_ids):
                name_to_id[ent["name"].lower()] = stored_entity_ids[i]

        relation_records = []
        for rel in relations:
            src_id = name_to_id.get(rel.get("source_name", "").lower())
            tgt_id = name_to_id.get(rel.get("target_name", "").lower())
            art_idx = rel.get("article_idx", 0)
            article_id = stored_article_ids[art_idx] if art_idx < len(stored_article_ids) else None
            if src_id and tgt_id:
                relation_records.append({
                    "article_id": article_id,
                    "source_entity": src_id,
                    "target_entity": tgt_id,
                    "relation_type": rel.get("relation_type", "depends_on"),
                    "confidence": rel.get("confidence", 0.7),
                })

        if relation_records:
            try:
                await news_storage.bulk_insert_relations(relation_records)
                logger.info("Publisher: stored %d relations", len(relation_records))
            except Exception as e:
                new_errors.append(f"Publisher: relation storage failed: {e}")

    # ── 5. 更新文章状态 → indexed ──
    if stored_article_ids:
        try:
            await news_storage.update_articles_status(stored_article_ids, "indexed")
        except Exception as e:
            logger.warning("Publisher: status update failed: %s", e)

    # ── 6. 触发 Knowledge Agent（高置信度实体合并到 core schema） ──
    knowledge_triggered = False
    enable_merge = get_policy("news.publisher.enable_knowledge_merge", True)

    if enable_merge and entities:
        high_conf_entities = [
            e for e in entities if e.get("confidence", 0) >= KNOWLEDGE_MERGE_CONFIDENCE
        ]
        if high_conf_entities:
            try:
                await _trigger_knowledge_agent(high_conf_entities, relations)
                knowledge_triggered = True
                logger.info(
                    "Publisher: Knowledge Agent triggered with %d high-confidence entities",
                    len(high_conf_entities),
                )
            except Exception as e:
                logger.warning("Publisher: Knowledge Agent trigger failed: %s", e)
                new_errors.append(f"Publisher: Knowledge Agent trigger failed: {e}")

    return {
        "stored_article_ids": stored_article_ids,
        "stored_event_ids": stored_event_ids,
        "knowledge_agent_triggered": knowledge_triggered,
        "errors": new_errors,
    }


async def _trigger_knowledge_agent(entities: list[dict], relations: list[dict]) -> None:
    """触发 Knowledge Agent 合并高置信度实体和关系到 core schema

    调用 knowledge_agent.storage.postgres 的 bulk_upsert_entities + bulk_insert_relations，
    将新闻实体合并到 core.entities（知识图谱）。
    """
    from knowledge_agent.storage.postgres import knowledge_storage

    # 转换为 Knowledge Agent 期望的格式
    core_entities = []
    for ent in entities:
        core_entities.append({
            "name": ent["name"],
            "entity_type": ent["entity_type"],
            "description": ent.get("description", ""),
            "aliases": ent.get("aliases", []),
            "properties": {"source": "news_agent"},
            "canonical_name": ent["name"],
            "confidence": ent.get("confidence", 0.8),
        })

    entity_ids = await knowledge_storage.bulk_upsert_entities(core_entities)

    # W-6 修复：同步合并高置信度关系到 core.relations
    # 构建实体名称 → core entity ID 映射
    if relations and entity_ids:
        name_to_core_id = {}
        for i, ent in enumerate(entities):
            if i < len(entity_ids):
                name_to_core_id[ent["name"].lower()] = entity_ids[i]

        high_conf_relations = [r for r in relations if r.get("confidence", 0) >= 0.8]
        core_relations = []
        for rel in high_conf_relations:
            src_id = name_to_core_id.get(rel.get("source_name", "").lower())
            tgt_id = name_to_core_id.get(rel.get("target_name", "").lower())
            if src_id and tgt_id:
                core_relations.append({
                    "source_entity": src_id,
                    "target_entity": tgt_id,
                    "relation_type": rel.get("relation_type", "depends_on"),
                    "confidence": rel.get("confidence", 0.8),
                    "properties": {"source": "news_agent"},
                })

        if core_relations:
            try:
                await knowledge_storage.bulk_insert_relations(core_relations)
            except Exception as e:
                logger.warning("Publisher: relation merge to core failed: %s", e)
