"""Node 6: Knowledge Merger - 知识合并 + 存储

合并重复实体/关系，批量写入 PostgreSQL + Qdrant + Apache AGE。
"""

import logging
import uuid

from tools.embedding import embedding_tool
from knowledge_agent.storage.postgres import knowledge_storage
from knowledge_agent.storage.qdrant import knowledge_qdrant
from knowledge_agent.storage.age import knowledge_age

logger = logging.getLogger(__name__)


async def knowledge_merger(state: dict) -> dict:
    """知识合并与存储节点

    1. 合并重复实体（已有 existing_id 的实体 → 更新而非新建）
    2. 解析关系中的实体名称 → 映射到实体 ID
    3. 批量写入 PostgreSQL
    4. 批量索引到 Qdrant
    """
    entities = state.get("entities", [])
    relations = state.get("relations", [])
    facts = state.get("facts", [])
    evidence = state.get("evidence", [])
    document_id = state.get("document_id", "")
    new_errors: list[str] = []

    if not entities:
        new_errors.append("Merger: no entities to store")
        return {"stored_entity_ids": [], "stored_fact_ids": [], "errors": new_errors}

    # ── 1. 准备实体数据 ──
    # 复用 Validator 已计算的 embeddings（避免重复 embed）
    entity_texts = [f"{e['name']}: {e.get('description', '')}" for e in entities]
    cached_embeddings = state.get("entity_embeddings", [])

    if cached_embeddings and len(cached_embeddings) == len(entities):
        embeddings = cached_embeddings
        logger.debug("Merger: reusing %d embeddings from Validator", len(embeddings))
    else:
        # Fallback: 重新计算（兼容无 Validator 路径）
        try:
            embeddings = await embedding_tool.embed(entity_texts)
        except Exception as e:
            logger.warning("Merger: embedding failed: %s", e)
            embeddings = [[] for _ in entities]
            new_errors.append(f"Merger: embedding failed: {e}")

    # 分离新实体和待合并实体
    new_entities: list[dict] = []
    merge_entities: list[dict] = []

    for i, entity in enumerate(entities):
        embedding = embeddings[i] if i < len(embeddings) else None

        entity_record = {
            "name": entity["name"],
            "entity_type": entity["entity_type"],
            "description": entity.get("description", ""),
            "aliases": entity.get("aliases", []),
            "properties": entity.get("properties", {}),
            "canonical_name": entity.get("name"),
            "confidence": entity.get("confidence", 1.0),
            "embedding": str(embedding) if embedding else None,
        }

        if entity.get("existing_id"):
            # 合并到已有实体
            entity_record["id"] = entity["existing_id"]
            merge_entities.append(entity_record)
        else:
            # 新实体
            entity_record["id"] = str(uuid.uuid4())
            new_entities.append(entity_record)

    # 批量 upsert（新 + 合并一起处理，ON CONFLICT 自动合并）
    all_entity_records = new_entities + merge_entities
    stored_entity_ids = await knowledge_storage.bulk_upsert_entities(all_entity_records)

    # 构建 name → id 映射（供关系和事实使用）
    name_to_id: dict[str, str] = {}
    for record in all_entity_records:
        name_to_id[record["name"].lower()] = record["id"]

    # ── 2. 处理关系 ──
    relation_records: list[dict] = []
    for rel in relations:
        source_id = name_to_id.get(rel.get("source", "").lower())
        target_id = name_to_id.get(rel.get("target", "").lower())

        if source_id and target_id:
            relation_records.append({
                "source_entity": source_id,
                "target_entity": target_id,
                "relation_type": rel["relation_type"],
                "confidence": rel.get("confidence"),
                "properties": rel.get("properties", {}),
            })

    if relation_records:
        await knowledge_storage.bulk_insert_relations(relation_records)

    # ── 3. 处理事实 ──
    fact_records: list[dict] = []
    for fact in facts:
        subject_id = name_to_id.get(fact.get("subject", "").lower())
        if subject_id:
            fact_records.append({
                "subject_entity": subject_id,
                "predicate": fact["predicate"],
                "object_value": fact.get("object_value", {}),
                "unit": fact.get("unit"),
                "time_start": fact.get("time_start"),
                "time_end": fact.get("time_end"),
                "source_document": document_id or None,
                "confidence": fact.get("confidence"),
            })

    stored_fact_ids: list[str] = []
    if fact_records:
        stored_fact_ids = await knowledge_storage.bulk_insert_facts(fact_records)

    # ── 4. 处理证据 ──
    if evidence and stored_fact_ids:
        # 将证据关联到对应的事实 ID
        evidence_records = []
        for i, ev in enumerate(evidence):
            if i < len(stored_fact_ids):
                evidence_records.append({
                    "fact_id": stored_fact_ids[i],
                    "document_id": document_id or None,
                    "location": ev.get("location"),
                    "quote": ev.get("quote"),
                    "confidence": ev.get("confidence"),
                })
        if evidence_records:
            await knowledge_storage.bulk_insert_evidence(evidence_records)

    # ── 5. Qdrant 向量索引 ──
    try:
        await knowledge_qdrant.index_entities(all_entity_records)
    except Exception as e:
        logger.warning("Merger: Qdrant entity indexing failed: %s", e)
        new_errors.append(f"Merger: Qdrant entity indexing failed: {e}")

    # 事实向量索引
    if stored_fact_ids and facts:
        fact_index_data = []
        for i, fact in enumerate(facts):
            if i < len(stored_fact_ids):
                fact_index_data.append({
                    "id": stored_fact_ids[i],
                    "subject_name": fact.get("subject", ""),
                    "predicate": fact.get("predicate", ""),
                    "object_value": fact.get("object_value", ""),
                    "entity_id": name_to_id.get(fact.get("subject", "").lower(), ""),
                    "time_start": fact.get("time_start", ""),
                })
        try:
            await knowledge_qdrant.index_facts(fact_index_data)
        except Exception as e:
            logger.warning("Merger: Qdrant fact indexing failed: %s", e)
            new_errors.append(f"Merger: Qdrant fact indexing failed: {e}")

    # ── 6. Apache AGE 图同步（异步，失败不阻塞） ──
    try:
        if knowledge_age.available:
            await knowledge_age.sync_entities(all_entity_records)
            if relation_records:
                await knowledge_age.sync_relations(relation_records)
            logger.debug("Merger: AGE sync completed (%d entities, %d relations)",
                         len(all_entity_records), len(relation_records))
    except Exception as e:
        logger.warning("Merger: AGE sync failed (non-fatal): %s", e)
        new_errors.append(f"Merger: AGE sync failed: {e}")

    logger.info(
        "Merger: stored %d entities, %d relations, %d facts | doc=%s",
        len(stored_entity_ids), len(relation_records), len(stored_fact_ids),
        document_id[:8] if document_id else "?",
    )

    return {
        "stored_entity_ids": stored_entity_ids,
        "stored_fact_ids": stored_fact_ids,
        "errors": new_errors,
    }
