"""Knowledge AGE Storage - Apache AGE 图同步（Knowledge Agent 专用）

复用 tools.postgres 的连接配置，独立连接池执行 Cypher 写入。
仅用于 Merger 节点双写（异步，失败不阻塞主流程）。

Graph: investment_knowledge_graph
"""

import logging
from typing import Optional

import asyncpg

from config.settings import settings

logger = logging.getLogger(__name__)

GRAPH_NAME = "investment_knowledge_graph"

# 合法 Vertex Labels
VALID_LABELS = {
    "Company", "Person", "Product", "Technology", "Industry",
    "Country", "Organization", "Event", "Metric", "Concept",
}

# 合法 Edge Labels
VALID_EDGE_LABELS = {
    "supplier", "customer", "competitor", "depends_on", "owns",
    "uses", "invests_in", "located_in", "impacts", "causes", "SUPERSEDES",
}


def _escape(value: str) -> str:
    """转义 Cypher 字符串"""
    if not value:
        return ""
    return value.replace("\\", "\\\\").replace("'", "\\'")


class KnowledgeAGEStorage:
    """Knowledge Agent AGE 图存储（写入专用）"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self._available: bool = False

    @property
    def available(self) -> bool:
        return self._available and self.pool is not None

    async def connect(self) -> None:
        """初始化 AGE 连接池"""
        dsn = (
            f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
            f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
        )
        try:
            self.pool = await asyncpg.create_pool(
                dsn,
                min_size=1,
                max_size=5,
                command_timeout=30,
            )
            async with self.pool.acquire() as conn:
                await conn.execute("LOAD 'age';")
                row = await conn.fetchrow(
                    "SELECT COUNT(*) AS cnt FROM ag_catalog.ag_graph WHERE name = $1",
                    GRAPH_NAME,
                )
                if row and row["cnt"] > 0:
                    self._available = True
                    logger.info("Knowledge AGE storage connected (graph=%s)", GRAPH_NAME)
                else:
                    self._available = False
                    logger.info("Knowledge AGE: graph not found, sync disabled")
        except Exception as e:
            self._available = False
            logger.info("Knowledge AGE storage unavailable: %s", e)

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
            self.pool = None
            self._available = False

    async def sync_entities(self, entities: list[dict]) -> int:
        """批量同步实体到 AGE（MERGE 幂等）"""
        if not self.available or not entities:
            return 0

        count = 0
        async with self.pool.acquire() as conn:
            await conn.execute("LOAD 'age';")
            for entity in entities:
                entity_id = entity.get("id", "")
                name = _escape(entity.get("name", ""))
                entity_type = entity.get("entity_type", "Entity")
                description = _escape(entity.get("description", ""))
                canonical = _escape(entity.get("canonical_name", entity.get("name", "")))
                confidence = entity.get("confidence", 1.0) or 1.0

                label = entity_type if entity_type in VALID_LABELS else "Entity"

                cypher = f"""
                    MERGE (e:{label} {{entity_id: '{entity_id}'}})
                    SET e.name = '{name}',
                        e.entity_type = '{entity_type}',
                        e.description = '{description}',
                        e.canonical_name = '{canonical}',
                        e.confidence = {confidence}
                    RETURN e
                """
                sql = f"SELECT * FROM cypher('{GRAPH_NAME}', $${cypher}$$) AS (v agtype);"

                try:
                    await conn.execute(sql)
                    count += 1
                except Exception as e:
                    logger.debug("AGE sync_entity '%s' failed: %s", name, e)

        return count

    async def sync_relations(self, relations: list[dict]) -> int:
        """批量同步关系到 AGE（MERGE 幂等）"""
        if not self.available or not relations:
            return 0

        count = 0
        async with self.pool.acquire() as conn:
            await conn.execute("LOAD 'age';")
            for rel in relations:
                source_id = rel.get("source_entity", "")
                target_id = rel.get("target_entity", "")
                relation_type = rel.get("relation_type", "depends_on")
                confidence = rel.get("confidence", 1.0) or 1.0

                if relation_type not in VALID_EDGE_LABELS:
                    relation_type = "depends_on"

                cypher = f"""
                    MATCH (a:Entity {{entity_id: '{source_id}'}})
                    MATCH (b:Entity {{entity_id: '{target_id}'}})
                    MERGE (a)-[r:{relation_type}]->(b)
                    SET r.confidence = {confidence},
                        r.source_id = '{source_id}',
                        r.target_id = '{target_id}',
                        r.relation_type = '{relation_type}'
                    RETURN r
                """
                sql = f"SELECT * FROM cypher('{GRAPH_NAME}', $${cypher}$$) AS (e agtype);"

                try:
                    await conn.execute(sql)
                    count += 1
                except Exception as e:
                    logger.debug(
                        "AGE sync_relation %s→%s failed: %s",
                        source_id[:8], target_id[:8], e,
                    )

        return count


# 模块级单例
knowledge_age = KnowledgeAGEStorage()
