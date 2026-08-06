"""Knowledge PostgreSQL Storage - 批量优化写入 + 图查询

复用 tools.postgres.postgres_tool 单例，
所有操作针对多 Schema 架构下的表：
  core      → entities, relations, facts, evidence
  document  → documents
"""

import json
import logging
import uuid
from datetime import date as date_type
from datetime import datetime

from tools.postgres import postgres_tool
from config.policy_loader import get_policy

logger = logging.getLogger(__name__)


def _to_date(value) -> date_type | None:
    """把事实的时间字段安全转为 date（asyncpg 的 date 列需要 date 对象）

    兼容：date / datetime / ISO 字符串（'2025-12-31'）/ None；非法返回 None。
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date_type):
        return value
    try:
        return date_type.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


class KnowledgePostgresStorage:
    """知识图谱 PostgreSQL 存储层

    职责：
    - 批量 upsert entities / relations / facts / evidence
    - 向量相似搜索（实体消歧）
    - 模糊名称匹配
    - 递归图遍历
    """

    # ──────────────────────────────────────────────
    # 批量写入
    # ──────────────────────────────────────────────

    async def bulk_upsert_entities(self, entities: list[dict]) -> list[str]:
        """批量 upsert 实体（单次网络往返）

        增强（KOC-A3）：写库前先做**批内消歧**——同一批内 canonical_name/name
        相同的实体复用同一 id 并合并 aliases / properties，避免同批同名实体产生
        重复行；再经 ON CONFLICT (id) 与库中既有记录合并 aliases（跨批去重）。

        Args:
            entities: [{"name", "entity_type", "description", "aliases",
                        "properties", "canonical_name", "confidence", "embedding"}]

        Returns:
            实体 ID 列表（与输入顺序一一对应）
        """
        if not entities:
            return []

        # 1. 批内消歧：按同一标识（name/canonical_name 小写）分组，复用统一 id 并合并属性
        groups: dict[str, dict] = {}   # key -> {"record": dict, "indices": list[int]}
        order: list[str] = []
        ids: list[str] = [""] * len(entities)

        for idx, e in enumerate(entities):
            key = (e.get("canonical_name") or e.get("name") or "").lower()
            key = key or uuid.uuid4().hex
            if key not in groups:
                record = dict(e)
                record.setdefault("id", str(uuid.uuid4()))
                groups[key] = {"record": record, "indices": []}
                order.append(key)
            g = groups[key]
            g["indices"].append(idx)
            ids[idx] = g["record"]["id"]

            if len(g["indices"]) > 1:
                # 后续同名实体：合并 aliases（去重）/ properties 到唯一记录，置信度取最大
                rec = g["record"]
                aliases = list(rec.get("aliases", []) or [])
                seen = set(aliases)
                for a in (e.get("aliases", []) or []):
                    if a not in seen:
                        aliases.append(a)
                        seen.add(a)
                rec["aliases"] = aliases
                rec["properties"] = {
                    **(rec.get("properties") or {}),
                    **(e.get("properties") or {}),
                }
                rec["confidence"] = max(
                    float(rec.get("confidence") or 0.0),
                    float(e.get("confidence") or 0.0),
                )

        # 2. 批量 upsert 唯一记录（ON CONFLICT 与库中既有记录合并 aliases）
        unique_records = [groups[k]["record"] for k in order]
        batch_size = get_policy("knowledge.storage.entity_batch_size", 50)

        for batch_start in range(0, len(unique_records), batch_size):
            batch = unique_records[batch_start:batch_start + batch_size]
            args_list = []
            for e in batch:
                args_list.append((
                    e["id"],
                    e["name"],
                    e["entity_type"],
                    e.get("description"),
                    json.dumps(e.get("aliases", []), ensure_ascii=False),
                    json.dumps(e.get("properties", {}), ensure_ascii=False),
                    e.get("canonical_name", e["name"]),
                    e.get("confidence", 1.0),
                    e.get("embedding"),  # VECTOR or None
                ))

            await postgres_tool.execute_many(
                """
                INSERT INTO core.entities
                    (id, name, entity_type, description, aliases, properties,
                     canonical_name, confidence, embedding)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9)
                ON CONFLICT (id) DO UPDATE SET
                    description = COALESCE(EXCLUDED.description, core.entities.description),
                    aliases = core.entities.aliases || EXCLUDED.aliases,
                    properties = core.entities.properties || EXCLUDED.properties,
                    source_count = core.entities.source_count + 1,
                    updated_at = NOW()
                """,
                args_list,
            )

        logger.info("Upserted %d entities (deduped from %d)", len(unique_records), len(entities))
        return ids

    async def bulk_insert_relations(self, relations: list[dict]) -> list[str]:
        """批量插入关系

        Args:
            relations: [{"source_entity", "target_entity", "relation_type",
                         "confidence", "properties"}]

        Returns:
            关系 ID 列表
        """
        if not relations:
            return []

        batch_size = get_policy("knowledge.storage.relation_batch_size", 100)
        ids: list[str] = []

        for batch_start in range(0, len(relations), batch_size):
            batch = relations[batch_start:batch_start + batch_size]
            args_list = []
            for r in batch:
                rid = str(uuid.uuid4())
                ids.append(rid)
                args_list.append((
                    rid,
                    r["source_entity"],
                    r["target_entity"],
                    r["relation_type"],
                    json.dumps(r.get("properties", {}), ensure_ascii=False),
                    r.get("confidence"),
                    r.get("valid_from"),
                    r.get("valid_to"),
                ))

            await postgres_tool.execute_many(
                """
                INSERT INTO core.relations
                    (id, source_entity, target_entity, relation_type, properties,
                     confidence, valid_from, valid_to)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8)
                """,
                args_list,
            )

        logger.info("Inserted %d relations", len(ids))
        return ids

    async def bulk_insert_facts(self, facts: list[dict]) -> list[str]:
        """批量插入事实

        Args:
            facts: [{"subject_entity", "predicate", "object_value", "unit",
                     "time_start", "time_end", "source_document", "confidence"}]

        Returns:
            事实 ID 列表
        """
        if not facts:
            return []

        batch_size = get_policy("knowledge.storage.fact_batch_size", 100)
        ids: list[str] = []

        for batch_start in range(0, len(facts), batch_size):
            batch = facts[batch_start:batch_start + batch_size]
            args_list = []
            for f in batch:
                fid = str(uuid.uuid4())
                ids.append(fid)
                args_list.append((
                    fid,
                    f["subject_entity"],
                    f["predicate"],
                    json.dumps(f["object_value"], ensure_ascii=False),
                    f.get("unit"),
                    _to_date(f.get("time_start")),
                    _to_date(f.get("time_end")),
                    f.get("source_document"),
                    f.get("confidence"),
                ))

            await postgres_tool.execute_many(
                """
                INSERT INTO core.facts
                    (id, subject_entity, predicate, object_value, unit,
                     time_start, time_end, source_document, confidence)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9)
                """,
                args_list,
            )

        logger.info("Inserted %d facts", len(ids))
        return ids

    async def bulk_insert_evidence(self, evidence: list[dict]) -> None:
        """批量插入证据

        Args:
            evidence: [{"fact_id", "document_id", "location", "quote", "confidence"}]
        """
        if not evidence:
            return

        args_list = [
            (
                str(uuid.uuid4()),
                ev["fact_id"],
                ev["document_id"],
                ev.get("location"),
                ev.get("quote"),
                ev.get("confidence"),
            )
            for ev in evidence
        ]

        await postgres_tool.execute_many(
            """
            INSERT INTO core.evidence
                (id, fact_id, document_id, location, quote, confidence)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            args_list,
        )
        logger.info("Inserted %d evidence records", len(args_list))

    async def insert_document(self, doc: dict) -> str:
        """插入知识来源文档

        Returns:
            文档 ID
        """
        doc_id = doc.get("id") or str(uuid.uuid4())
        await postgres_tool.execute(
            """
            INSERT INTO document.documents
                (id, title, document_type, source, url, file_path, hash, publish_date, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
            ON CONFLICT (id) DO NOTHING
            """,
            doc_id,
            doc.get("title"),
            doc.get("document_type"),
            doc.get("source"),
            doc.get("url"),
            doc.get("file_path"),
            doc.get("hash"),
            doc.get("publish_date"),
            json.dumps(doc.get("metadata", {}), ensure_ascii=False),
        )
        return doc_id

    # ──────────────────────────────────────────────
    # 查询
    # ──────────────────────────────────────────────

    async def search_entity_by_embedding(
        self, embedding: list[float], threshold: float = 0.85, limit: int = 5
    ) -> list[dict]:
        """向量相似搜索（实体消歧）

        全表扫描余弦距离排序（2560维无HNSW索引，大表场景建议走 Qdrant）。

        Args:
            embedding: 查询向量
            threshold: 最低相似度阈值
            limit: 返回数量

        Returns:
            [{"id", "name", "entity_type", "canonical_name", "confidence", "similarity"}]
        """
        return await postgres_tool.query(
            """
            SELECT id, name, entity_type, canonical_name, confidence,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM core.entities
            WHERE embedding IS NOT NULL
              AND status = 'active'
              AND 1 - (embedding <=> $1::vector) > $2
            ORDER BY embedding <=> $1::vector
            LIMIT $3
            """,
            str(embedding), threshold, limit,
        )

    async def find_entity_by_name(self, name: str, limit: int = 10) -> list[dict]:
        """精确 + 模糊名称查找

        先精确匹配，再 trigram 模糊匹配。

        Returns:
            [{"id", "name", "entity_type", "canonical_name", "aliases"}]
        """
        # 精确匹配
        exact = await postgres_tool.query(
            """
            SELECT id, name, entity_type, canonical_name, aliases
            FROM core.entities
            WHERE (name = $1 OR canonical_name = $1)
              AND status = 'active'
            LIMIT $2
            """,
            name, limit,
        )
        if exact:
            return exact

        # 模糊匹配（trigram similarity）
        return await postgres_tool.query(
            """
            SELECT id, name, entity_type, canonical_name, aliases,
                   similarity(name, $1) AS sim
            FROM core.entities
            WHERE status = 'active'
              AND similarity(name, $1) > 0.3
            ORDER BY sim DESC
            LIMIT $2
            """,
            name, limit,
        )

    async def find_entities_by_names(self, names: list[str]) -> list[dict]:
        """批量名称查找（替代 N 次 find_entity_by_name）

        单次查询完成所有名称的精确匹配。

        Returns:
            [{"id", "name", "entity_type", "canonical_name"}]
        """
        if not names:
            return []
        return await postgres_tool.query(
            """
            SELECT id, name, entity_type, canonical_name
            FROM core.entities
            WHERE (name = ANY($1) OR canonical_name = ANY($1))
              AND status = 'active'
            """,
            names,
        )

    async def get_facts_by_subjects(self, subject_ids: list[str], limit_per: int = 20) -> list[dict]:
        """批量获取多实体的事实（替代 N 次 get_facts_by_subject）

        Returns:
            [{"id", "subject_entity", "predicate", "object_value", "confidence"}]
        """
        if not subject_ids:
            return []
        total_limit = limit_per * len(subject_ids)
        # 显式转换 UUID 类型，避免 asyncpg 类型不匹配
        uuids = [uuid.UUID(sid) for sid in subject_ids]
        return await postgres_tool.query(
            """
            SELECT id, subject_entity, predicate, object_value, confidence
            FROM core.facts
            WHERE subject_entity = ANY($1)
            ORDER BY time_start DESC NULLS LAST
            LIMIT $2
            """,
            uuids, total_limit,
        )

    async def get_entity_neighbors(self, entity_id: str, depth: int = 2) -> list[dict]:
        """递归图遍历（CTE）

        Args:
            entity_id: 起始实体 ID
            depth: 最大遍历深度（硬限 ≤ 2）

        Returns:
            [{"source_entity", "target_entity", "relation_type", "depth"}]
        """
        depth = min(depth, get_policy("knowledge.retrieval.graph_max_depth", 2))

        return await postgres_tool.query(
            """
            WITH RECURSIVE graph AS (
                SELECT source_entity, target_entity, relation_type, 1 AS depth
                FROM core.relations
                WHERE source_entity = $1 AND status = 'active'

                UNION ALL

                SELECT r.source_entity, r.target_entity, r.relation_type, g.depth + 1
                FROM core.relations r
                JOIN graph g ON r.source_entity = g.target_entity
                WHERE g.depth < $2 AND r.status = 'active'
            )
            SELECT DISTINCT source_entity, target_entity, relation_type, depth
            FROM graph
            ORDER BY depth
            """,
            entity_id, depth,
        )

    async def get_facts_by_subject(
        self, subject_entity: str, predicate: str | None = None, limit: int = 50
    ) -> list[dict]:
        """查询实体的事实

        Args:
            subject_entity: 主体实体 ID
            predicate: 可选谓词过滤
            limit: 返回数量

        Returns:
            事实记录列表
        """
        if predicate:
            return await postgres_tool.query(
                """
                SELECT id, predicate, object_value, unit, time_start, time_end,
                       confidence, verification_status
                FROM core.facts
                WHERE subject_entity = $1 AND predicate = $2
                ORDER BY time_start DESC NULLS LAST
                LIMIT $3
                """,
                subject_entity, predicate, limit,
            )

        return await postgres_tool.query(
            """
            SELECT id, predicate, object_value, unit, time_start, time_end,
                   confidence, verification_status
            FROM core.facts
            WHERE subject_entity = $1
            ORDER BY time_start DESC NULLS LAST
            LIMIT $2
            """,
            subject_entity, limit,
        )

    async def get_entities_by_type(self, entity_type: str, limit: int = 50) -> list[dict]:
        """按类型查询实体"""
        return await postgres_tool.query(
            """
            SELECT id, name, entity_type, description, canonical_name, confidence
            FROM core.entities
            WHERE entity_type = $1 AND status = 'active'
            ORDER BY source_count DESC
            LIMIT $2
            """,
            entity_type, limit,
        )

    async def search_entities(self, name: str = "", entity_type: str = "", limit: int = 20) -> list[dict]:
        """综合搜索实体（名称 + 类型过滤）"""
        conditions = ["status = 'active'"]
        params: list = []
        idx = 1

        if name:
            conditions.append(f"(name ILIKE ${idx} OR canonical_name ILIKE ${idx})")
            params.append(f"%{name}%")
            idx += 1

        if entity_type:
            conditions.append(f"entity_type = ${idx}")
            params.append(entity_type)
            idx += 1

        where_clause = " AND ".join(conditions)
        params.append(limit)

        return await postgres_tool.query(
            f"""
            SELECT id, name, entity_type, description, canonical_name,
                   confidence, source_count
            FROM core.entities
            WHERE {where_clause}
            ORDER BY source_count DESC
            LIMIT ${idx}
            """,
            *params,
        )

    # ──────────────────────────────────────────────
    # Knowledge Inbox（HITL 审核流，Phase 5）
    # ──────────────────────────────────────────────

    async def insert_inbox(
        self,
        object_type: str,
        object_id: str,
        confidence: float | None,
        content: dict,
        source: str = "agent",
    ) -> str:
        """写入 Knowledge Inbox

        Args:
            object_type: entity / fact / relation / event / document
            object_id: 对象 UUID
            confidence: 置信度 (0-1)
            content: 待审内容（JSON 可序列化）
            source: 来源（agent / document_id / ...）

        Returns:
            inbox_id (UUID)
        """
        inbox_id = str(uuid.uuid4())
        await postgres_tool.execute(
            """
            INSERT INTO core.knowledge_inbox
                (id, object_type, object_id, status, confidence, content, source)
            VALUES ($1, $2, $3, 'EXTRACTED', $4, $5::jsonb, $6)
            """,
            inbox_id,
            object_type,
            object_id,
            confidence,
            json.dumps(content, ensure_ascii=False),
            source,
        )
        return inbox_id

    async def update_inbox_status(
        self, inbox_id: str, status: str, reviewer: str | None = None
    ) -> None:
        """更新 Inbox 记录状态

        Args:
            inbox_id: Inbox 记录 ID
            status: APPROVED / REJECTED / READY_REVIEW / ARCHIVED
            reviewer: 审核人（system 表示自动审批）
        """
        await postgres_tool.execute(
            """
            UPDATE core.knowledge_inbox
            SET status = $2,
                reviewer = COALESCE($3, reviewer),
                review_time = CASE WHEN $2 IN ('APPROVED', 'REJECTED') THEN NOW() ELSE review_time END,
                updated_at = NOW()
            WHERE id = $1
            """,
            inbox_id,
            status,
            reviewer,
        )

    async def find_inbox(self, status: str | None = None, limit: int = 50) -> list[dict]:
        """查询 Inbox 记录

        Args:
            status: 状态过滤（NEW/EXTRACTED/READY_REVIEW/APPROVED/REJECTED/ARCHIVED）
            limit: 返回数量上限

        Returns:
            Inbox 记录列表
        """
        if status:
            return await postgres_tool.query(
                """
                SELECT id, object_type, object_id, status, confidence, source, content,
                       reviewer, review_time, created_at, updated_at
                FROM core.knowledge_inbox
                WHERE status = $1
                ORDER BY created_at ASC
                LIMIT $2
                """,
                status, limit,
            )
        return await postgres_tool.query(
            """
            SELECT id, object_type, object_id, status, confidence, source, content,
                   reviewer, review_time, created_at, updated_at
            FROM core.knowledge_inbox
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )

    # ──────────────────────────────────────────────
    # 版本审计（KOC-A3）
    # ──────────────────────────────────────────────

    async def record_knowledge_version(
        self,
        object_type: str,
        object_id: str,
        content: dict,
        created_by: str = "system",
    ) -> int:
        """写入 audit.knowledge_versions（KOC-A3）

        每次写入自动递增版本号（object_type, object_id, version 唯一）。

        Args:
            object_type: entity / relation / fact / event / document
            object_id: 对象 UUID
            content: 版本快照（JSON 可序列化）
            created_by: 写入者

        Returns:
            本次写入的版本号
        """
        oid = object_id if isinstance(object_id, uuid.UUID) else uuid.UUID(str(object_id))
        rows = await postgres_tool.query(
            """
            SELECT COALESCE(MAX(version), 0) + 1 AS next_version
            FROM audit.knowledge_versions
            WHERE object_type = $1 AND object_id = $2
            """,
            object_type, oid,
        )
        next_version = int(rows[0]["next_version"]) if rows else 1
        await postgres_tool.execute(
            """
            INSERT INTO audit.knowledge_versions
                (object_type, object_id, version, content, created_by)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            """,
            object_type, oid, next_version,
            json.dumps(content, ensure_ascii=False), created_by,
        )
        logger.info(
            "[audit.knowledge_versions] %s %s v%d",
            object_type, str(oid)[:8], next_version,
        )
        return next_version

    # ──────────────────────────────────────────────
    # 审核日志（KOC-A4）
    # ──────────────────────────────────────────────

    async def record_review_log(
        self,
        inbox_id: str,
        action: str,
        reviewer: str = "human",
        reason: str = "",
    ) -> str:
        """写入 audit.knowledge_review_log（KOC-A4）

        记录 Inbox 审核动作（approve / reject / auto_approve）。

        Args:
            inbox_id: knowledge_inbox 记录 ID
            action: approve / reject / auto_approve
            reviewer: 审核人（human / system）
            reason: 拒绝原因等备注

        Returns:
            review_log_id (UUID)
        """
        review_log_id = str(uuid.uuid4())
        await postgres_tool.execute(
            """
            INSERT INTO audit.knowledge_review_log
                (id, inbox_id, action, reviewer, reason)
            VALUES ($1, $2, $3, $4, $5)
            """,
            review_log_id,
            inbox_id,
            action,
            reviewer,
            (reason or "")[:500],
        )
        logger.info(
            "[audit.knowledge_review_log] inbox=%s action=%s reviewer=%s",
            str(inbox_id)[:8], action, reviewer,
        )
        return review_log_id

    # ──────────────────────────────────────────────
    # Render Queue（KOC-F1）
    # ──────────────────────────────────────────────

    async def get_inbox(self, inbox_id: str) -> dict | None:
        """读取单条 Inbox 记录（含 object_id / content）"""
        rows = await postgres_tool.query(
            """
            SELECT id, object_type, object_id, status, confidence, source, content,
                   reviewer, review_time, created_at, updated_at
            FROM core.knowledge_inbox
            WHERE id = $1
            """,
            inbox_id,
        )
        return rows[0] if rows else None

    async def enqueue_render_job(
        self,
        entity_id: str,
        entity_type: str,
        section: str | None = None,
        priority: int | None = None,
    ) -> str:
        """写入 core.knowledge_render_jobs（KOC-F1）

        审核通过后自动入 Render Queue。优先级策略：Company/Event 优先，
        priority 越小越优先（默认映射需显式传递，否则按业务类型推导）。

        Args:
            entity_id: core.entities.id
            entity_type: 业务类型 Company/Industry/Event/Person/Security/Document
            section: 增量更新用 Section（可选）
            priority: 显式优先级；None 时按 entity_type 推导

        Returns:
            render_job_id (UUID)
        """
        if priority is None:
            priority = RENDER_TYPE_PRIORITY.get(str(entity_type).lower(), 5)
        job_id = str(uuid.uuid4())
        await postgres_tool.execute(
            """
            INSERT INTO core.knowledge_render_jobs
                (id, entity, type, section, status, priority)
            VALUES ($1, $2, $3, $4, 'pending', $5)
            """,
            job_id,
            entity_id,
            entity_type,
            section,
            priority,
        )
        logger.info(
            "[knowledge_render_jobs] enqueue entity=%s type=%s priority=%d job=%s",
            str(entity_id)[:8], entity_type, priority, str(job_id)[:8],
        )
        return job_id

    async def list_render_jobs(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """查询 Render Queue 任务（KOC-F2）

        Args:
            status: 状态过滤（pending/running/done/failed），None=全部
            limit: 返回数量上限

        Returns:
            render_jobs 列表（含关联实体名，左侧优先展示高优先级）
        """
        if status:
            return await postgres_tool.query(
                """
                SELECT j.id, j.entity, j.type, j.section, j.status, j.retry,
                       j.priority, j.error_message, j.created_at, j.updated_at,
                       e.name AS entity_name
                FROM core.knowledge_render_jobs j
                LEFT JOIN core.entities e ON e.id = j.entity
                WHERE j.status = $1
                ORDER BY j.priority ASC, j.created_at ASC
                LIMIT $2
                """,
                status, limit,
            )
        return await postgres_tool.query(
            """
            SELECT j.id, j.entity, j.type, j.section, j.status, j.retry,
                   j.priority, j.error_message, j.created_at, j.updated_at,
                   e.name AS entity_name
            FROM core.knowledge_render_jobs j
            LEFT JOIN core.entities e ON e.id = j.entity
            ORDER BY j.priority ASC, j.created_at ASC
            LIMIT $1
            """,
            limit,
        )

    async def retry_render_job(self, job_id: str) -> bool:
        """手动重试失败的渲染任务（KOC-F2）

        failed → pending，清空 error_message，保留 priority/retry 计数。

        Returns:
            是否成功（job 存在且原状态为 failed，否则 False）
        """
        rows = await postgres_tool.query(
            """
            UPDATE core.knowledge_render_jobs
            SET status = 'pending', error_message = NULL, updated_at = NOW()
            WHERE id = $1 AND status = 'failed'
            RETURNING id
            """,
            job_id,
        )
        if rows:
            logger.info(
                "[knowledge_render_jobs] retry job=%s", str(job_id)[:8],
            )
            return True
        logger.warning(
            "[knowledge_render_jobs] retry skipped (not failed) job=%s",
            str(job_id)[:8],
        )
        return False


# 渲染优先级映射：Company/Event 优先（priority 越小越优先）（KOC-F1）
RENDER_TYPE_PRIORITY = {
    "company": 1,
    "event": 2,
    "person": 3,
    "security": 3,
    "industry": 4,
    "document": 5,
}


# 模块级单例
knowledge_storage = KnowledgePostgresStorage()
