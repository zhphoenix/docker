"""Node 5: Knowledge Validator - 知识校验

实体消歧（Qdrant 向量检索）+ 冲突检测（批量查询优化）。
性能优化：
- 实体消歧从 PG 全表扫描改为 Qdrant 向量检索
- 事实冲突检测从 N+1 查询改为 ANY($1) 批量查询
- Embeddings 写入 State 供 Merger 复用
"""

import asyncio
import logging

from tools.embedding import embedding_tool
from config.policy_loader import get_policy
from storage.knowledge.postgres import knowledge_storage
from storage.knowledge.qdrant import knowledge_qdrant

logger = logging.getLogger(__name__)


async def knowledge_validator(state: dict) -> dict:
    """知识校验节点

    1. 批量 embed 实体名称（结果写入 State 供 Merger 复用）
    2. 对每个实体进行 Qdrant 向量检索，查找已有实体（消歧）
    3. 批量检测事实冲突（同 subject+predicate 不同 value）
    4. 生成校验报告
    """
    entities = state.get("entities", [])
    facts = state.get("facts", [])
    new_errors: list[str] = []

    if not entities:
        return {
            "conflicts": [], "confidence_score": 0.0,
            "entity_embeddings": [], "errors": new_errors,
        }

    threshold = get_policy("knowledge.extraction.entity_similarity_threshold", 0.85)

    # ── 1. 批量 embed 实体名称（结果供 Merger 复用） ──
    entity_texts = [f"{e['name']}: {e.get('description', '')}" for e in entities]
    entity_embeddings: list[list[float]] = []
    try:
        entity_embeddings = await embedding_tool.embed(entity_texts)
    except Exception as e:
        logger.warning("Validator: embedding failed: %s", e)
        new_errors.append(f"Validator: embedding failed: {e}")

    # ── 2. 实体消歧：Qdrant 向量检索（替代 PG 全表扫描） ──
    entity_merges: list[dict] = []

    if not entity_embeddings:
        new_errors.append("Validator: embeddings unavailable, skipping disambiguation")
    else:
        # 并行 Qdrant 向量检索（替代逐个串行 await）
        search_tasks = [
            knowledge_qdrant.search_entities_by_vector(vector=emb, limit=3)
            for emb in entity_embeddings
        ]
        all_matches = await asyncio.gather(*search_tasks, return_exceptions=True)

        for i, (entity, matches) in enumerate(zip(entities, all_matches)):
            if isinstance(matches, Exception):
                logger.debug("Validator: entity search failed for %s: %s", entity["name"], matches)
                continue
            if matches:
                best = matches[0]
                score = best.get("score", 0)
                if score >= threshold:
                    entity_merges.append({
                        "new_name": entity["name"],
                        "new_index": i,
                        "existing_id": best["id"],
                        "existing_name": best.get("payload", {}).get("name", ""),
                        "similarity": score,
                        "action": "merge",
                    })
                    # 标记实体已有 ID（合并用）
                    entity["existing_id"] = best["id"]

    # ── 3. 事实冲突检测（批量查询优化） ──
    conflicts: list[dict] = []

    # 收集所有 subject 名称
    subjects_with_facts = list({
        f.get("subject", "") for f in facts if f.get("subject")
    })

    if subjects_with_facts:
        # 批量查找实体（1 次查询替代 N 次 find_entity_by_name）
        existing_entities = await knowledge_storage.find_entities_by_names(subjects_with_facts)

        # 构建 name → id 映射
        name_to_entity_id: dict[str, str] = {}
        for ent in existing_entities:
            name_to_entity_id[ent["name"].lower()] = str(ent["id"])
            if ent.get("canonical_name"):
                name_to_entity_id[ent["canonical_name"].lower()] = str(ent["id"])

        # 批量获取所有相关实体的事实（1 次查询替代 N 次 get_facts_by_subject）
        entity_ids = list(set(name_to_entity_id.values()))
        existing_facts = await knowledge_storage.get_facts_by_subjects(entity_ids, limit_per=20)

        # 按 subject_entity 分组
        facts_by_entity: dict[str, list[dict]] = {}
        for ef in existing_facts:
            sid = str(ef.get("subject_entity", ""))
            facts_by_entity.setdefault(sid, []).append(ef)

        # 比对新旧事实
        for subject_name in subjects_with_facts:
            entity_id = name_to_entity_id.get(subject_name.lower())
            if not entity_id:
                continue

            entity_existing_facts = facts_by_entity.get(entity_id, [])
            new_subject_facts = [
                f for f in facts
                if f.get("subject", "").lower() == subject_name.lower()
            ]

            for nf in new_subject_facts:
                for ef in entity_existing_facts:
                    if ef.get("predicate", "").lower() == nf.get("predicate", "").lower():
                        old_val = str(ef.get("object_value", ""))
                        new_val = str(nf.get("object_value", ""))
                        if old_val != new_val:
                            conflicts.append({
                                "subject": subject_name,
                                "predicate": nf["predicate"],
                                "existing_value": old_val,
                                "new_value": new_val,
                                "severity": "medium",
                                "recommendation": "保留两个，标记来源差异",
                            })

    # ── 4. 计算置信度 ──
    total_entities = len(entities)
    merged_count = len(entity_merges)
    conflict_count = len(conflicts)

    if total_entities > 0:
        confidence = max(0.0, 1.0 - (conflict_count * 0.1) - (merged_count * 0.02))
    else:
        confidence = 0.0

    logger.info(
        "Validator: %d entities, %d merges, %d conflicts, confidence=%.2f",
        total_entities, merged_count, conflict_count, confidence,
    )

    return {
        "entities": entities,  # 更新后的实体（含 existing_id 标记）
        "conflicts": conflicts,
        "confidence_score": round(confidence, 3),
        "entity_embeddings": entity_embeddings,  # 供 Merger 复用
        "errors": new_errors,
    }
