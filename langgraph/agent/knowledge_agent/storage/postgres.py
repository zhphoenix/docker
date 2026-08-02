"""Knowledge PostgreSQL Storage - 批量优化写入 + 图查询

复用 tools.postgres.postgres_tool 单例，
所有操作针对多 Schema 架构下的表：
  core      → entities, relations, facts, evidence
  document  → documents
"""

import json
import logging
import uuid

from tools.postgres import postgres_tool
from config.policy_loader import get_policy

logger = logging.getLogger(__name__)


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

        ON CONFLICT 时合并 aliases / properties，source_count + 1。

        Args:
            entities: [{"name", "entity_type", "description", "aliases",
                        "properties", "canonical_name", "confidence", "embedding"}]

        Returns:
            实体 ID 列表
        """
        if not entities:
            return []

        batch_size = get_policy("knowledge.storage.entity_batch_size", 50)
        ids: list[str] = []

        for batch_start in range(0, len(entities), batch_size):
            batch = entities[batch_start:batch_start + batch_size]
            args_list = []
            for e in batch:
                eid = e.get("id") or str(uuid.uuid4())
                ids.append(eid)
                args_list.append((
                    eid,
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

        logger.info("Upserted %d entities", len(ids))
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
                    f.get("time_start"),
                    f.get("time_end"),
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


# 模块级单例
knowledge_storage = KnowledgePostgresStorage()
