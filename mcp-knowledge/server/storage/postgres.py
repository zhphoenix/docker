"""PostgreSQL 存储层 - asyncpg 连接池 + 知识查询

多 Schema 架构：core / document / vector / audit / taxonomy
"""

import asyncio
import json
import logging
import uuid
from typing import Optional

import asyncpg

from server.config import settings

logger = logging.getLogger(__name__)


class PostgresStorage:
    """PostgreSQL 连接池 + 知识图谱查询"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self._lock = asyncio.Lock()

    async def _ensure_pool(self) -> None:
        """双重检查锁定，防止并发协程重复创建连接池"""
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
            "MCP PG pool created (min=%d, max=%d)",
            settings.PG_POOL_MIN_SIZE,
            settings.PG_POOL_MAX_SIZE,
        )

    async def close(self) -> None:
        """关闭连接池"""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("MCP PG pool closed")

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

    async def execute(self, sql: str, *args) -> str:
        """执行"""
        await self._ensure_pool()
        async with self.pool.acquire() as conn:
            return await conn.execute(sql, *args)

    # ──────────────────────────────────────────────
    # Entity 查询
    # ──────────────────────────────────────────────

    async def search_entities(self, name: str = "", entity_type: str = "", limit: int = 20) -> list[dict]:
        """搜索实体（ILIKE + 类型过滤）"""
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

        return await self.query(
            f"""
            SELECT id, name, entity_type, description, canonical_name,
                   confidence, source_count, aliases, properties
            FROM core.entities
            WHERE {where_clause}
            ORDER BY source_count DESC
            LIMIT ${idx}
            """,
            *params,
        )

    async def get_entity_by_id(self, entity_id: str) -> Optional[dict]:
        """按 ID 获取实体"""
        return await self.query_one(
            """
            SELECT id, name, entity_type, description, canonical_name,
                   confidence, source_count, aliases, properties,
                   status, created_at, updated_at
            FROM core.entities
            WHERE id = $1 AND status = 'active'
            """,
            uuid.UUID(entity_id),
        )

    async def get_entities_by_ids(self, entity_ids: list[str]) -> list[dict]:
        """批量按 ID 获取实体（避免 N+1 查询）"""
        if not entity_ids:
            return []
        uuids = [uuid.UUID(eid) for eid in entity_ids]
        return await self.query(
            """
            SELECT id, name, entity_type, description, canonical_name,
                   confidence, source_count, aliases, properties
            FROM core.entities
            WHERE id = ANY($1) AND status = 'active'
            """,
            uuids,
        )

    async def find_entity_by_name(self, name: str, limit: int = 5) -> list[dict]:
        """精确 + trigram 模糊名称查找"""
        exact = await self.query(
            """
            SELECT id, name, entity_type, canonical_name, aliases, confidence
            FROM core.entities
            WHERE (name = $1 OR canonical_name = $1) AND status = 'active'
            LIMIT $2
            """,
            name, limit,
        )
        if exact:
            return exact

        return await self.query(
            """
            SELECT id, name, entity_type, canonical_name, aliases, confidence,
                   similarity(name, $1) AS sim
            FROM core.entities
            WHERE status = 'active' AND similarity(name, $1) > 0.3
            ORDER BY sim DESC
            LIMIT $2
            """,
            name, limit,
        )

    async def get_entity_graph(self, entity_id: str, depth: int = 2) -> list[dict]:
        """递归图遍历（CTE, depth≤2）"""
        depth = min(depth, 2)
        return await self.query(
            """
            WITH RECURSIVE graph AS (
                SELECT source_entity, target_entity, relation_type, confidence, 1 AS depth
                FROM core.relations
                WHERE source_entity = $1 AND status = 'active'

                UNION ALL

                SELECT r.source_entity, r.target_entity, r.relation_type, r.confidence, g.depth + 1
                FROM core.relations r
                JOIN graph g ON r.source_entity = g.target_entity
                WHERE g.depth < $2 AND r.status = 'active'
            )
            SELECT DISTINCT source_entity, target_entity, relation_type, confidence, depth
            FROM graph
            ORDER BY depth
            LIMIT 500
            """,
            uuid.UUID(entity_id), depth,
        )

    # ──────────────────────────────────────────────
    # Fact 查询
    # ──────────────────────────────────────────────

    async def search_facts(
        self, entity_id: str, predicate: str = "", limit: int = 50
    ) -> list[dict]:
        """查询实体事实"""
        if predicate:
            return await self.query(
                """
                SELECT f.id, f.predicate, f.object_value, f.unit,
                       f.time_start, f.time_end, f.confidence,
                       f.verification_status, f.lifecycle_status,
                       d.title AS source_title
                FROM core.facts f
                LEFT JOIN document.documents d ON f.source_document = d.id
                WHERE f.subject_entity = $1 AND f.predicate ILIKE $2
                ORDER BY f.time_start DESC NULLS LAST
                LIMIT $3
                """,
                uuid.UUID(entity_id), f"%{predicate}%", limit,
            )

        return await self.query(
            """
            SELECT f.id, f.predicate, f.object_value, f.unit,
                   f.time_start, f.time_end, f.confidence,
                   f.verification_status, f.lifecycle_status,
                   d.title AS source_title
            FROM core.facts f
            LEFT JOIN document.documents d ON f.source_document = d.id
            WHERE f.subject_entity = $1
            ORDER BY f.time_start DESC NULLS LAST
            LIMIT $2
            """,
            uuid.UUID(entity_id), limit,
        )

    async def get_fact_history(self, fact_id: str) -> list[dict]:
        """获取事实版本历史"""
        return await self.query(
            """
            SELECT id, version, content, created_by, created_at
            FROM audit.knowledge_versions
            WHERE object_type = 'fact' AND object_id = $1
            ORDER BY version DESC
            """,
            uuid.UUID(fact_id),
        )

    async def get_timeline(self, entity_id: str, limit: int = 30) -> list[dict]:
        """获取实体事件时间线"""
        return await self.query(
            """
            SELECT id, event_type, title, description, event_date, impact, confidence
            FROM core.events
            WHERE entities @> $1::jsonb
            ORDER BY event_date DESC NULLS LAST
            LIMIT $2
            """,
            json.dumps([entity_id]), limit,
        )

    # ──────────────────────────────────────────────
    # Analysis 查询
    # ──────────────────────────────────────────────

    async def get_relations_by_types(self, entity_id: str, relation_types: list[str], limit: int = 50) -> list[dict]:
        """按关系类型查询（供应链等）"""
        return await self.query(
            """
            SELECT r.id, r.source_entity, r.target_entity, r.relation_type,
                   r.confidence, r.valid_from, r.valid_to,
                   e.name AS target_name, e.entity_type AS target_type
            FROM core.relations r
            JOIN core.entities e ON r.target_entity = e.id
            WHERE r.source_entity = $1
              AND r.relation_type = ANY($2)
              AND r.status = 'active'
            ORDER BY r.confidence DESC NULLS LAST
            LIMIT $3
            """,
            uuid.UUID(entity_id), relation_types, limit,
        )

    async def get_risk_factors(self, entity_id: str) -> dict:
        """风险因素聚合：低置信度事实 + 冲突 + 负面事件"""
        low_conf_facts = await self.query(
            """
            SELECT id, predicate, object_value, confidence, time_start
            FROM core.facts
            WHERE subject_entity = $1 AND confidence < 0.7
            ORDER BY confidence ASC
            LIMIT 20
            """,
            uuid.UUID(entity_id),
        )

        conflicts = await self.query(
            """
            SELECT kc.id, kc.conflict_type, kc.status, kc.created_at,
                   fa.predicate AS fact_a_predicate,
                   fb.predicate AS fact_b_predicate
            FROM core.knowledge_conflicts kc
            JOIN core.facts fa ON kc.fact_a = fa.id
            JOIN core.facts fb ON kc.fact_b = fb.id
            WHERE (fa.subject_entity = $1 OR fb.subject_entity = $1)
              AND kc.status = 'open'
            ORDER BY kc.created_at DESC
            LIMIT 10
            """,
            uuid.UUID(entity_id),
        )

        return {"low_confidence_facts": low_conf_facts, "conflicts": conflicts}

    # ──────────────────────────────────────────────
    # Write 操作
    # ──────────────────────────────────────────────

    async def create_entity(self, entity: dict) -> str:
        """创建实体"""
        eid = str(uuid.uuid4())
        await self.execute(
            """
            INSERT INTO core.entities
                (id, name, entity_type, description, aliases, properties, canonical_name, confidence)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8)
            """,
            uuid.UUID(eid),
            entity["name"],
            entity["entity_type"],
            entity.get("description"),
            json.dumps(entity.get("aliases", []), ensure_ascii=False),
            json.dumps(entity.get("properties", {}), ensure_ascii=False),
            entity.get("canonical_name", entity["name"]),
            entity.get("confidence", 1.0),
        )
        return eid

    async def create_fact(self, fact: dict) -> str:
        """创建事实"""
        fid = str(uuid.uuid4())
        await self.execute(
            """
            INSERT INTO core.facts
                (id, subject_entity, predicate, object_value, unit,
                 time_start, time_end, source_document, confidence)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9)
            """,
            uuid.UUID(fid),
            uuid.UUID(fact["subject_entity"]),
            fact["predicate"],
            json.dumps(fact["object_value"], ensure_ascii=False),
            fact.get("unit"),
            fact.get("time_start"),
            fact.get("time_end"),
            uuid.UUID(fact["source_document"]) if fact.get("source_document") else None,
            fact.get("confidence", 1.0),
        )
        return fid

    async def create_relation(self, relation: dict) -> str:
        """创建关系"""
        rid = str(uuid.uuid4())
        await self.execute(
            """
            INSERT INTO core.relations
                (id, source_entity, target_entity, relation_type, properties, confidence)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6)
            """,
            uuid.UUID(rid),
            uuid.UUID(relation["source_entity"]),
            uuid.UUID(relation["target_entity"]),
            relation["relation_type"],
            json.dumps(relation.get("properties", {}), ensure_ascii=False),
            relation.get("confidence"),
        )
        return rid

    async def update_knowledge(self, object_type: str, object_id: str, updates: dict) -> bool:
        """更新知识对象（版本化，事务保护）"""
        await self._ensure_pool()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # 1. 读取当前快照
                if object_type == "entity":
                    row = await conn.fetchrow(
                        "SELECT * FROM core.entities WHERE id = $1", uuid.UUID(object_id)
                    )
                elif object_type == "fact":
                    row = await conn.fetchrow(
                        "SELECT * FROM core.facts WHERE id = $1", uuid.UUID(object_id)
                    )
                else:
                    return False

                if not row:
                    return False
                current = dict(row)

                # 2. 获取当前最大版本号
                max_ver = await conn.fetchrow(
                    """
                    SELECT COALESCE(MAX(version), 0) AS max_v
                    FROM audit.knowledge_versions
                    WHERE object_type = $1 AND object_id = $2
                    """,
                    object_type, uuid.UUID(object_id),
                )
                new_version = (max_ver["max_v"] if max_ver else 0) + 1

                # 3. 写入版本快照
                await conn.execute(
                    """
                    INSERT INTO audit.knowledge_versions
                        (id, object_type, object_id, version, content, created_by)
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                    """,
                    uuid.uuid4(),
                    object_type,
                    uuid.UUID(object_id),
                    new_version,
                    json.dumps(current, default=str, ensure_ascii=False),
                    updates.get("updated_by", "mcp-server"),
                )

                # 4. 更新主表
                if object_type == "entity":
                    set_parts = []
                    params = []
                    idx = 1
                    for key in ("name", "description", "entity_type", "canonical_name", "confidence"):
                        if key in updates:
                            set_parts.append(f"{key} = ${idx}")
                            params.append(updates[key])
                            idx += 1
                    if set_parts:
                        set_parts.append("updated_at = NOW()")
                        params.append(uuid.UUID(object_id))
                        await conn.execute(
                            f"UPDATE core.entities SET {', '.join(set_parts)} WHERE id = ${idx}",
                            *params,
                        )
                elif object_type == "fact":
                    if "object_value" in updates:
                        await conn.execute(
                            "UPDATE core.facts SET object_value = $1::jsonb WHERE id = $2",
                            json.dumps(updates["object_value"], ensure_ascii=False),
                            uuid.UUID(object_id),
                        )

                return True


# 模块级单例
pg_storage = PostgresStorage()
