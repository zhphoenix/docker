"""Node 5: Knowledge Validator - 知识校验

实体消歧（向量相似搜索）+ 冲突检测。
"""

import json
import logging

from tools.llm import llm_tool
from tools.embedding import embedding_tool
from prompts.loader import load_prompt
from config.policy_loader import get_policy
from knowledge_agent.storage.postgres import knowledge_storage

logger = logging.getLogger(__name__)


async def knowledge_validator(state: dict) -> dict:
    """知识校验节点

    1. 对每个实体进行向量相似搜索，查找已有实体（消歧）
    2. 检测事实冲突（同 subject+predicate 不同 value）
    3. 生成校验报告
    """
    entities = state.get("entities", [])
    facts = state.get("facts", [])
    errors = list(state.get("errors", []))

    if not entities:
        return {"conflicts": [], "confidence_score": 0.0, "errors": errors}

    threshold = get_policy("knowledge.extraction.entity_similarity_threshold", 0.85)

    # ── 1. 实体消歧：向量相似搜索 ──
    entity_merges: list[dict] = []

    # 批量 embed 实体名称
    entity_texts = [f"{e['name']}: {e.get('description', '')}" for e in entities]
    try:
        embeddings = await embedding_tool.embed(entity_texts)
    except Exception as e:
        logger.warning("Validator: embedding failed: %s", e)
        embeddings = []
        errors.append(f"Validator: embedding failed: {e}")

    # 对每个实体搜索已有匹配
    for i, entity in enumerate(entities):
        if i >= len(embeddings):
            break

        try:
            matches = await knowledge_storage.search_entity_by_embedding(
                embedding=embeddings[i],
                threshold=threshold,
                limit=3,
            )
            if matches:
                best = matches[0]
                entity_merges.append({
                    "new_name": entity["name"],
                    "new_index": i,
                    "existing_id": str(best["id"]),
                    "existing_name": best["name"],
                    "similarity": best.get("similarity", 0),
                    "action": "merge",
                })
                # 标记实体已有 ID（合并用）
                entity["existing_id"] = str(best["id"])
        except Exception as e:
            logger.debug("Validator: entity search failed for %s: %s", entity["name"], e)

    # ── 2. 事实冲突检测 ──
    conflicts: list[dict] = []

    # 按 subject 分组查找已有事实
    subjects_with_facts = set()
    for f in facts:
        subject = f.get("subject", "")
        if subject:
            subjects_with_facts.add(subject)

    for subject_name in subjects_with_facts:
        # 查找该 subject 对应的已有实体
        existing = await knowledge_storage.find_entity_by_name(subject_name, limit=1)
        if not existing:
            continue

        entity_id = str(existing[0]["id"])
        existing_facts = await knowledge_storage.get_facts_by_subject(entity_id, limit=20)

        # 比对新旧事实
        new_subject_facts = [f for f in facts if f.get("subject", "").lower() == subject_name.lower()]
        for nf in new_subject_facts:
            for ef in existing_facts:
                if ef.get("predicate", "").lower() == nf.get("predicate", "").lower():
                    # 同 predicate，检查值是否冲突
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

    # ── 3. 计算置信度 ──
    total_entities = len(entities)
    merged_count = len(entity_merges)
    conflict_count = len(conflicts)

    # 简单评分：无冲突高分，有冲突降分
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
        "errors": errors,
    }
