"""Node 6: Knowledge Merger - 知识合并 + 存储

合并重复实体/关系，批量写入 PostgreSQL + Qdrant + Apache AGE。
"""

import json
import logging
import uuid

from tools.embedding import embedding_tool
from storage.knowledge.postgres import knowledge_storage
from storage.knowledge.qdrant import knowledge_qdrant
from storage.knowledge.age import knowledge_age
from config.policy_loader import get_policy
from services.approval import create_approval
from schemas.knowledge_package import (
    Entity,
    Evidence,
    Fact,
    KnowledgePackage,
    Relation,
)

logger = logging.getLogger(__name__)


class MergerStorage:
    """Merger 写入目标抽象（DP-C3）

    抽象 knowledge_merger 依赖的存储接口，使写入目标可注入：
      - CoreMergerStorage：默认，直写 core.*（direct 现状路径）
      - PackageDraftMergerStorage：写 KnowledgePackage 草稿（package 通道）
    消歧查询与 knowledge_inbox HITL 触发逻辑保持不变。
    """

    async def find_entities_by_names(self, names):
        raise NotImplementedError

    async def search_entity_by_embedding(self, vec, threshold, limit):
        raise NotImplementedError

    async def bulk_upsert_entities(self, records):
        raise NotImplementedError

    async def bulk_insert_relations(self, records):
        raise NotImplementedError

    async def bulk_insert_facts(self, records):
        raise NotImplementedError

    async def bulk_insert_evidence(self, records):
        raise NotImplementedError

    async def insert_inbox(self, object_type, object_id, confidence, content, source="agent"):
        raise NotImplementedError

    async def update_inbox_status(self, inbox_id, status, reviewer=None):
        raise NotImplementedError

    async def record_knowledge_version(self, object_type, object_id, content, created_by="system"):
        raise NotImplementedError

    async def record_review_log(self, inbox_id, action, reviewer="human", reason=""):
        raise NotImplementedError

    async def enqueue_render_job(self, entity_id, entity_type, section=None, priority=None):
        raise NotImplementedError


class CoreMergerStorage(MergerStorage):
    """默认后端：直写 core.*（现状，direct 通道）"""

    def __init__(self, storage=None):
        self._storage = storage or knowledge_storage

    async def find_entities_by_names(self, names):
        return await self._storage.find_entities_by_names(names)

    async def search_entity_by_embedding(self, vec, threshold, limit):
        return await self._storage.search_entity_by_embedding(vec, threshold=threshold, limit=limit)

    async def bulk_upsert_entities(self, records):
        return await self._storage.bulk_upsert_entities(records)

    async def bulk_insert_relations(self, records):
        return await self._storage.bulk_insert_relations(records)

    async def bulk_insert_facts(self, records):
        return await self._storage.bulk_insert_facts(records)

    async def bulk_insert_evidence(self, records):
        return await self._storage.bulk_insert_evidence(records)

    async def insert_inbox(self, object_type, object_id, confidence, content, source="agent"):
        return await self._storage.insert_inbox(object_type, object_id, confidence, content, source=source)

    async def update_inbox_status(self, inbox_id, status, reviewer=None):
        return await self._storage.update_inbox_status(inbox_id, status, reviewer=reviewer)

    async def record_knowledge_version(self, object_type, object_id, content, created_by="system"):
        return await self._storage.record_knowledge_version(object_type, object_id, content, created_by=created_by)

    async def record_review_log(self, inbox_id, action, reviewer="human", reason=""):
        return await self._storage.record_review_log(inbox_id, action, reviewer=reviewer, reason=reason)

    async def enqueue_render_job(self, entity_id, entity_type, section=None, priority=None):
        return await self._storage.enqueue_render_job(entity_id, entity_type, section=section, priority=priority)


class PackageDraftMergerStorage(MergerStorage):
    """Package 草稿后端：写入 KnowledgePackage 草稿（package 通道）

    消歧查询（find_entities_by_names / search_entity_by_embedding）仍走 core.*，
    因草稿尚未落库、数据量小；写入目标改为 Package 草稿对象。
    低置信实体仍写入 knowledge_inbox（HITL 触发逻辑不变）。
    """

    def __init__(self, package: KnowledgePackage, core_storage=None):
        self.package = package
        self._core = core_storage or knowledge_storage

    async def find_entities_by_names(self, names):
        return await self._core.find_entities_by_names(names)

    async def search_entity_by_embedding(self, vec, threshold, limit):
        return await self._core.search_entity_by_embedding(vec, threshold=threshold, limit=limit)

    async def bulk_upsert_entities(self, records):
        ids: list[str] = []
        for r in records:
            eid = r.get("id") or str(uuid.uuid4())
            ids.append(eid)
            self.package.entities.append(Entity(
                id=eid,
                name=r["name"],
                entity_type=r["entity_type"],
                aliases=r.get("aliases", []),
                properties=r.get("properties", {}),
                canonical_name=r.get("canonical_name", r["name"]),
                confidence=r.get("confidence"),
            ))
        return ids

    async def bulk_insert_relations(self, records):
        ids: list[str] = []
        for r in records:
            rid = str(uuid.uuid4())
            ids.append(rid)
            props = dict(r.get("properties", {}))
            if r.get("valid_from"):
                props["valid_from"] = r["valid_from"]
            if r.get("valid_to"):
                props["valid_to"] = r["valid_to"]
            self.package.relations.append(Relation(
                id=rid,
                source_entity=r["source_entity"],
                target_entity=r["target_entity"],
                relation_type=r["relation_type"],
                properties=props,
                confidence=r.get("confidence"),
            ))
        return ids

    async def bulk_insert_facts(self, records):
        ids: list[str] = []
        for r in records:
            fid = str(uuid.uuid4())
            ids.append(fid)
            self.package.facts.append(Fact(
                id=fid,
                subject_entity=r["subject_entity"],
                predicate=r["predicate"],
                object_value=r.get("object_value", {}),
                unit=r.get("unit"),
                time_start=r.get("time_start"),
                time_end=r.get("time_end"),
                source_document=r.get("source_document"),
                confidence=r.get("confidence"),
            ))
        return ids

    async def bulk_insert_evidence(self, records):
        for r in records:
            self.package.evidence.append(Evidence(
                id=str(uuid.uuid4()),
                fact_id=r.get("fact_id"),
                document_id=r.get("document_id"),
                location=r.get("location"),
                quote=r.get("quote"),
                confidence=r.get("confidence"),
            ))

    async def insert_inbox(self, object_type, object_id, confidence, content, source="agent"):
        return await self._core.insert_inbox(object_type, object_id, confidence, content, source=source)

    async def update_inbox_status(self, inbox_id, status, reviewer=None):
        return await self._core.update_inbox_status(inbox_id, status, reviewer=reviewer)

    async def record_knowledge_version(self, object_type, object_id, content, created_by="system"):
        # 草稿通道未落库，版本审计暂不写入（KOC-A3 仅对落库对象记录）
        return 1

    async def record_review_log(self, inbox_id, action, reviewer="human", reason=""):
        # 草稿通道未落库，Inbox 审核日志仍走 core.*（KOC-A4）
        return await self._core.record_review_log(inbox_id, action, reviewer=reviewer, reason=reason)

    async def enqueue_render_job(self, entity_id, entity_type, section=None, priority=None):
        # 草稿通道实体尚未落库（core.entities 无对应行），渲染由消费后触发（KOC-F4），此处不入队
        return None


# Inbox 自动审批置信度阈值（高置信度+可信来源 → 直接 APPROVED，否则人工审核）
INBOX_AUTO_APPROVE_CONFIDENCE = 0.85
INBOX_AUTO_APPROVE_SOURCES = {"annual_report", "earnings_call", "document"}


async def knowledge_merger(state: dict, storage: MergerStorage | None = None) -> dict:
    """知识合并与存储节点

    1. 合并重复实体（已有 existing_id 的实体 → 更新而非新建）
    2. 解析关系中的实体名称 → 映射到实体 ID
    3. 批量写入 PostgreSQL
    4. 批量索引到 Qdrant

    写入目标通过 storage 注入（DP-C3）：默认 CoreMergerStorage 直写 core.*；
    注入 PackageDraftMergerStorage 时写入 Package 草稿。
    """
    storage = storage or CoreMergerStorage()
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
            found = await storage.find_entities_by_names(list(candidate_names))
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
                    sim_rows = await storage.search_entity_by_embedding(
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

    # 批量 upsert（新 + 合并一起处理，批内同名消歧 + ON CONFLICT 自动合并）
    all_entity_records = new_entities + merge_entities
    stored_entity_ids = await storage.bulk_upsert_entities(all_entity_records)

    # ── 1.5 写 audit.knowledge_versions（KOC-A3）──
    # 复用 storage 抽象，为每个落库实体写版本快照；失败不阻塞主流程
    try:
        for _idx, _rec in enumerate(all_entity_records):
            if _idx >= len(stored_entity_ids):
                break
            await storage.record_knowledge_version(
                "entity",
                stored_entity_ids[_idx],
                {
                    "name": _rec.get("name"),
                    "entity_type": _rec.get("entity_type"),
                    "aliases": _rec.get("aliases", []),
                    "canonical_name": _rec.get("canonical_name", _rec.get("name")),
                },
                created_by="knowledge_merger",
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("Merger: audit.knowledge_versions write failed (non-fatal): %s", e)
        new_errors.append(f"Merger: audit.knowledge_versions write failed: {e}")

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
        await storage.bulk_insert_relations(relation_records)

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
        stored_fact_ids = await storage.bulk_insert_facts(fact_records)

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
            await storage.bulk_insert_evidence(evidence_records)

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
            inbox_id = await storage.insert_inbox(
                "entity", eid, conf, content, source=document_id or "agent"
            )
            inbox_records.append({"inbox_id": inbox_id, "entity_id": eid, "name": rec.get("name"), "confidence": conf})

            # 自动审批：高置信度 且 来源可信 → 无需人工，写 auto_approve 审核日志（KOC-A4）并入 Render Queue（KOC-F1）
            if conf >= auto_confidence and trusted_source:
                await storage.update_inbox_status(inbox_id, "APPROVED", reviewer="system")
                try:
                    await storage.record_review_log(
                        inbox_id, "auto_approve", reviewer="system", reason=""
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning("Failed to write auto_approve review_log: %s", e)
                # KOC-F1: 审核通过 → 自动入 Render Queue（direct 通道实体已落库）
                try:
                    await storage.enqueue_render_job(
                        eid, rec.get("entity_type") or "Document"
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning("Failed to enqueue render job for %s: %s", rec.get("name"), e)
            else:
                # 低置信度 → READY_REVIEW + 创建人工审批任务（复用 approval.py）
                await storage.update_inbox_status(inbox_id, "READY_REVIEW", reviewer=None)
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
