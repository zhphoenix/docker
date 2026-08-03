"""Node 6: Knowledge Merger - 知识合并 + 存储

合并重复实体/关系，批量写入 PostgreSQL + Qdrant + Apache AGE。
"""

import json
import logging
import uuid

from tools.embedding import embedding_tool
from knowledge_agent.storage.postgres import knowledge_storage
from knowledge_agent.storage.qdrant import knowledge_qdrant
from knowledge_agent.storage.age import knowledge_age
from config.policy_loader import get_policy
from services.approval import create_approval

logger = logging.getLogger(__name__)

# Inbox 自动审批置信度阈值（高置信度+可信来源 → 直接 APPROVED，否则人工审核）
INBOX_AUTO_APPROVE_CONFIDENCE = 0.85
INBOX_AUTO_APPROVE_SOURCES = {"annual_report", "earnings_call", "document"}


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

    # 分离新实体和待合并实体（嵌入式消歧：名称精确 + 向量相似）
    new_entities: list[dict] = []
    merge_entities: list[dict] = []
    merge_report: dict = {
        "checked": 0,
        "by_name": [],
        "by_embedding": [],
        "created_new": 0,
    }

    # 1. 名称精确消歧：一次批量查找全部候选新实体名
    # 记录 (idx -> entity_record)，供后续向量消歧复用
    candidates: dict[int, dict] = {}  # idx -> entity_record
    candidate_names: set[str] = set()
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
            "_embedding_vec": embedding,  # 内部用于向量消歧
        }

        if entity.get("existing_id"):
            # 已由上游 Validator 识别的重复实体 → 直接合并到已有实体
            entity_record["id"] = entity["existing_id"]
            merge_entities.append(entity_record)
        else:
            # 新实体候选：先消歧核对，命中则改为合并
            candidates[i] = entity_record
            candidate_names.add(entity["name"])

    if candidates:
        name_to_id: dict[str, str] = {}
        try:
            found = await knowledge_storage.find_entities_by_names(list(candidate_names))
            for row in found:
                nm = (row.get("name") or "").lower()
                canonical = (row.get("canonical_name") or "").lower()
                if nm and nm not in name_to_id:
                    name_to_id[nm] = str(row["id"])
                if canonical and canonical not in name_to_id:
                    name_to_id[canonical] = str(row["id"])
        except Exception as e:
            logger.warning("Merger: name-resolution batch lookup failed: %s", e)

        for i, record in candidates.items():
            key = record["name"].lower()
            existing_id = name_to_id.get(key)
            if existing_id:
                # 名称精确命中抽象实体（含 canonical_name）→ 合并
                record.pop("_embedding_vec", None)
                record["id"] = existing_id
                merge_entities.append(record)
                merge_report["by_name"].append({
                    "name": record["name"],
                    "kept_id": existing_id,
                })
                continue

            # 2. 名称未命中 → 向量相似消歧（需有效 embedding）
            vec = record.get("_embedding_vec")
            if vec:
                vec = [float(x) for x in vec] if not all(isinstance(x, float) for x in vec) else vec
                try:
                    sim_rows = await knowledge_storage.search_entity_by_embedding(
                        vec, threshold=0.85, limit=1
                    )
                    if sim_rows:
                        kept_id = str(sim_rows[0]["id"])
                        record.pop("_embedding_vec", None)
                        record["id"] = kept_id
                        merge_entities.append(record)
                        merge_report["by_embedding"].append({
                            "name": record["name"],
                            "kept_id": kept_id,
                            "kept_name": sim_rows[0].get("name", ""),
                            "similarity": round(float(sim_rows[0].get("similarity", 0)), 4),
                        })
                        continue
                except Exception as e:
                    logger.warning("Merger: embedding-resolution failed for '%s': %s",
                                   record["name"], e)

            # 3. 未命中 → 新建实体
            record.pop("_embedding_vec", None)
            record["id"] = str(uuid.uuid4())
            new_entities.append(record)
            merge_report["created_new"] += 1

    merge_report["checked"] = len(candidates)

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
            # Temporal：从关系属性或顶层取 valid_from/valid_to
            rel_props = rel.get("properties", {}) or {}
            valid_from = (
                rel.get("valid_from")
                or rel_props.get("valid_from")
                or rel_props.get("time_start")
            )
            valid_to = (
                rel.get("valid_to")
                or rel_props.get("valid_to")
                or rel_props.get("time_end")
            )
            relation_records.append({
                "source_entity": source_id,
                "target_entity": target_id,
                "relation_type": rel["relation_type"],
                "confidence": rel.get("confidence"),
                "properties": rel_props,
                "valid_from": valid_from or None,
                "valid_to": valid_to or None,
            })

    if relation_records:
        await knowledge_storage.bulk_insert_relations(relation_records)

    # ── 3. 处理事实 ──
    # 记录每条保留事实对应对应证据（与 fact_records 对齐，避免被测序号错位）
    fact_records: list[dict] = []
    fact_evidence: list[dict] = []
    for idx, fact in enumerate(facts):
        subject_id = name_to_id.get(fact.get("subject", "").lower())
        ev = evidence[idx] if idx < len(evidence) else None
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
            fact_evidence.append(ev if ev is not None else None)

    stored_fact_ids: list[str] = []
    if fact_records:
        stored_fact_ids = await knowledge_storage.bulk_insert_facts(fact_records)

    # ── 4. 处理证据 ──
    # 按 fact_records 顺序与 stored_fact_ids 对齐，跳过无证据的 fact
    if stored_fact_ids:
        evidence_records = []
        for i, ev in enumerate(fact_evidence):
            if not ev or i >= len(stored_fact_ids):
                continue
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

    # ── 7. Knowledge Inbox 审核流（HITL 规范 §4，Phase 5） ──
    # 新实体先入 Inbox；高置信度+可信来源 → 自动 APPROVED；否则 READY_REVIEW 并创建人工审批
    inbox_records: list[dict] = []
    try:
        auto_confidence = get_policy("knowledge.inbox.auto_approve_confidence", INBOX_AUTO_APPROVE_CONFIDENCE)
        source_meta = (state.get("source_metadata") or {})
        source_kind = str(source_meta.get("source", "") or source_meta.get("document_type", "") or "agent").lower()
        trusted_source = any(k in source_kind for k in INBOX_AUTO_APPROVE_SOURCES)
        # 预构建合并实体 ID 集合，避免循环内重复重建（O(n²)）
        merge_entity_ids = {m.get("id") for m in merge_entities}

        for idx, rec in enumerate(all_entity_records):
            if idx >= len(stored_entity_ids):
                break
            eid = stored_entity_ids[idx]
            conf = float(rec.get("confidence") or 0.0)
            content = {
                "name": rec.get("name"),
                "entity_type": rec.get("entity_type"),
                "description": rec.get("description", ""),
                "action": "merge" if rec.get("id") in merge_entity_ids else "create",
                "source_document": document_id,
            }
            inbox_id = await knowledge_storage.insert_inbox(
                "entity", eid, conf, content, source=document_id or "agent"
            )
            inbox_records.append({"inbox_id": inbox_id, "entity_id": eid, "name": rec.get("name"), "confidence": conf})

            # 自动审批：高置信度 且 来源可信 → 无需人工
            if conf >= auto_confidence and trusted_source:
                await knowledge_storage.update_inbox_status(inbox_id, "APPROVED", reviewer="system")
            else:
                # 低置信度 → READY_REVIEW + 创建人工审批任务（复用 approval.py）
                await knowledge_storage.update_inbox_status(inbox_id, "READY_REVIEW", reviewer=None)
                try:
                    await create_approval(
                        title=f"审核知识实体: {rec.get('name')}",
                        action_type="knowledge_inbox_approve",
                        params={"inbox_id": inbox_id, "object_id": eid, "object_type": "entity"},
                        content_preview=json.dumps(content, ensure_ascii=False),
                        created_by="knowledge_agent",
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning("Merger: approval creation failed for %s: %s", rec.get("name"), e)

        logger.info("Merger: %d/%d entities logged to knowledge_inbox", len(inbox_records), len(stored_entity_ids))
    except Exception as e:  # noqa: BLE001
        logger.warning("Merger: knowledge_inbox logging failed (non-fatal): %s", e)
        new_errors.append(f"Merger: knowledge_inbox logging failed: {e}")

    logger.info(
        "Merger: stored %d entities, %d relations, %d facts | doc=%s",
        len(stored_entity_ids), len(relation_records), len(stored_fact_ids),
        document_id[:8] if document_id else "?",
    )

    return {
        "stored_entity_ids": stored_entity_ids,
        "stored_fact_ids": stored_fact_ids,
        "errors": new_errors,
        "merge_report": merge_report,
        "inbox_records": inbox_records,
    }
