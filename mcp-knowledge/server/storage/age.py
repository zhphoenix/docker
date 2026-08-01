"""Apache AGE 图存储层 - Cypher 查询引擎

通过 PostgreSQL 的 AGE 扩展执行 Cypher 查询。
复用 pg_storage 的连接池（同一 PostgreSQL 实例）。

Graph: investment_knowledge_graph
Fallback: AGE 不可用时由调用方降级为 PG CTE。
"""

import json
import logging
from typing import Optional

import asyncpg

from server.config import settings

logger = logging.getLogger(__name__)

GRAPH_NAME = "investment_knowledge_graph"


class AGEStorage:
    """Apache AGE 图存储 — 通过 asyncpg 执行 Cypher"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self._available: bool = False

    @property
    def available(self) -> bool:
        """AGE 是否可用"""
        return self._available and self.pool is not None

    async def connect(self) -> None:
        """创建独立连接池并验证 AGE 扩展可用"""
        dsn = (
            f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
            f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
        )
        try:
            self.pool = await asyncpg.create_pool(
                dsn,
                min_size=2,
                max_size=10,
                command_timeout=30,
                server_settings={
                    "search_path": f"ag_catalog, \"$user\", public",
                },
            )
            # 验证 AGE 扩展已加载
            async with self.pool.acquire() as conn:
                await conn.execute("LOAD 'age';")
                row = await conn.fetchrow(
                    "SELECT COUNT(*) AS cnt FROM ag_catalog.ag_graph WHERE name = $1",
                    GRAPH_NAME,
                )
                if row and row["cnt"] > 0:
                    self._available = True
                    logger.info("AGE storage connected (graph=%s)", GRAPH_NAME)
                else:
                    self._available = False
                    logger.warning(
                        "AGE extension loaded but graph '%s' not found. "
                        "Run postgres/init/08-age-init.sql first.",
                        GRAPH_NAME,
                    )
        except Exception as e:
            self._available = False
            logger.warning("AGE storage unavailable: %s (fallback to PG CTE)", e)

    async def close(self) -> None:
        """关闭连接池"""
        if self.pool:
            await self.pool.close()
            self.pool = None
            self._available = False
            logger.info("AGE storage closed")

    async def execute_cypher(
        self, cypher: str, columns: list[str] | None = None
    ) -> list[dict]:
        """执行 Cypher 查询（通过 AGE SQL 包装）

        Args:
            cypher: 完整 Cypher 语句（不含 SELECT * FROM cypher(...) 包装）
            columns: 返回列名列表（默认 ["result"]）

        Returns:
            解析后的字典列表
        """
        if not self.available:
            raise RuntimeError("AGE storage not available")

        if columns is None:
            columns = ["result"]

        col_defs = ", ".join(f"{c} agtype" for c in columns)
        sql = f"""
            SELECT * FROM cypher('{GRAPH_NAME}', $$
                {cypher}
            $$) AS ({col_defs});
        """

        async with self.pool.acquire() as conn:
            await conn.execute("LOAD 'age';")
            rows = await conn.fetch(sql)
            results = []
            for row in rows:
                parsed = {}
                for col in columns:
                    val = row[col]
                    parsed[col] = self._parse_agtype(val)
                results.append(parsed)
            return results

    async def execute_cypher_write(self, cypher: str) -> None:
        """执行 Cypher 写入（CREATE/MERGE/SET/DELETE）"""
        if not self.available:
            raise RuntimeError("AGE storage not available")

        sql = f"""
            SELECT * FROM cypher('{GRAPH_NAME}', $$
                {cypher}
            $$) AS (v agtype);
        """

        async with self.pool.acquire() as conn:
            await conn.execute("LOAD 'age';")
            await conn.execute(sql)

    # ──────────────────────────────────────────────
    # 图遍历查询
    # ──────────────────────────────────────────────

    async def get_entity_graph(self, entity_name: str, depth: int = 2) -> dict:
        """从实体出发的多跳图遍历

        Returns:
            {nodes: [{id, name, entity_type}], edges: [{source, target, relation_type, confidence, depth}]}
        """
        depth = min(max(depth, 1), 3)

        cypher = f"""
            MATCH path = (e:Entity)-[*1..{depth}]-(related:Entity)
            WHERE e.name = '{self._escape(entity_name)}'
               OR e.canonical_name = '{self._escape(entity_name)}'
            UNWIND nodes(path) AS n
            WITH collect(DISTINCT n) AS all_nodes
            UNWIND relationships(path) AS r
            RETURN all_nodes, collect(DISTINCT r) AS all_edges
        """

        try:
            results = await self.execute_cypher(cypher, ["all_nodes", "all_edges"])
        except Exception as e:
            logger.warning("AGE get_entity_graph failed: %s", e)
            raise

        if not results:
            return {"nodes": [], "edges": []}

        raw_nodes = results[0].get("all_nodes", [])
        raw_edges = results[0].get("all_edges", [])

        nodes = []
        seen_ids = set()
        for n in raw_nodes:
            if isinstance(n, dict):
                nid = n.get("entity_id", n.get("id", ""))
                if nid not in seen_ids:
                    seen_ids.add(nid)
                    nodes.append({
                        "id": nid,
                        "name": n.get("name", ""),
                        "entity_type": n.get("entity_type", ""),
                    })

        edges = []
        for r in raw_edges:
            if isinstance(r, dict):
                edges.append({
                    "source": r.get("source_id", r.get("start_id", "")),
                    "target": r.get("target_id", r.get("end_id", "")),
                    "relation_type": r.get("relation_type", r.get("label", "")),
                    "confidence": r.get("confidence"),
                    "depth": r.get("depth", 1),
                })

        return {"nodes": nodes, "edges": edges}

    async def trace_event_impact(self, event_name: str, depth: int = 3) -> dict:
        """事件影响链追踪

        Event → impacted Entities → their relations → ...

        Returns:
            {event, impact_chain: [{entity, entity_type, relation, depth}], total_impacted}
        """
        depth = min(max(depth, 1), 4)

        cypher = f"""
            MATCH (ev:Event)-[:impacts]->(e:Entity)
            WHERE ev.name CONTAINS '{self._escape(event_name)}'
               OR ev.title CONTAINS '{self._escape(event_name)}'
            WITH ev, e
            MATCH path = (e)-[*1..{depth}]-(impacted:Entity)
            UNWIND nodes(path) AS n
            WITH ev, collect(DISTINCT n) AS impacted_nodes,
                 collect(DISTINCT e) AS direct_entities
            RETURN ev, direct_entities, impacted_nodes
        """

        try:
            results = await self.execute_cypher(cypher, ["ev", "direct_entities", "impacted_nodes"])
        except Exception as e:
            logger.warning("AGE trace_event_impact failed: %s", e)
            raise

        if not results:
            return {"event": event_name, "impact_chain": [], "total_impacted": 0}

        row = results[0]
        event_info = row.get("ev", {})
        direct = row.get("direct_entities", [])
        impacted = row.get("impacted_nodes", [])

        impact_chain = []
        seen = set()
        for n in impacted:
            if isinstance(n, dict):
                nid = n.get("entity_id", n.get("id", ""))
                if nid not in seen:
                    seen.add(nid)
                    impact_chain.append({
                        "entity": n.get("name", ""),
                        "entity_id": nid,
                        "entity_type": n.get("entity_type", ""),
                    })

        return {
            "event": {
                "name": event_info.get("name", event_name) if isinstance(event_info, dict) else event_name,
                "description": event_info.get("description", "") if isinstance(event_info, dict) else "",
            },
            "direct_entities": [
                {"name": e.get("name", ""), "entity_type": e.get("entity_type", "")}
                for e in direct if isinstance(e, dict)
            ],
            "impact_chain": impact_chain,
            "total_impacted": len(impact_chain),
        }

    async def search_events(
        self, query: str, event_type: str = "", limit: int = 10
    ) -> list[dict]:
        """搜索事件节点 + 关联实体

        Returns:
            [{name, event_type, description, date, impacted_entities: [...]}]
        """
        type_filter = f"AND ev.event_type = '{self._escape(event_type)}'" if event_type else ""

        cypher = f"""
            MATCH (ev:Event)
            WHERE (ev.name CONTAINS '{self._escape(query)}'
                   OR ev.description CONTAINS '{self._escape(query)}')
                  {type_filter}
            OPTIONAL MATCH (ev)-[:impacts]->(e:Entity)
            WITH ev, collect(e.name) AS entities
            RETURN ev, entities
            LIMIT {limit}
        """

        try:
            results = await self.execute_cypher(cypher, ["ev", "entities"])
        except Exception as e:
            logger.warning("AGE search_events failed: %s", e)
            raise

        events = []
        for row in results:
            ev = row.get("ev", {})
            if isinstance(ev, dict):
                events.append({
                    "name": ev.get("name", ""),
                    "event_type": ev.get("event_type", ""),
                    "description": ev.get("description", ""),
                    "date": ev.get("event_date", ev.get("date", "")),
                    "impacted_entities": row.get("entities", []),
                })
        return events

    # ──────────────────────────────────────────────
    # 写入（数据同步）
    # ──────────────────────────────────────────────

    async def sync_entity(self, entity: dict) -> None:
        """同步单个实体到 AGE Graph（MERGE 幂等）"""
        entity_id = entity.get("id", "")
        name = self._escape(entity.get("name", ""))
        entity_type = self._escape(entity.get("entity_type", "Entity"))
        description = self._escape(entity.get("description", ""))
        canonical = self._escape(entity.get("canonical_name", entity.get("name", "")))
        confidence = entity.get("confidence", 1.0)

        # 使用具体类型标签 + 通用 Entity 标签
        label = entity_type if entity_type in (
            "Company", "Person", "Product", "Technology", "Industry",
            "Country", "Organization", "Event", "Metric", "Concept",
        ) else "Entity"

        cypher = f"""
            MERGE (e:{label} {{entity_id: '{entity_id}'}})
            SET e.name = '{name}',
                e.entity_type = '{entity_type}',
                e.description = '{description}',
                e.canonical_name = '{canonical}',
                e.confidence = {confidence}
            RETURN e
        """
        await self.execute_cypher_write(cypher)

    async def sync_entities(self, entities: list[dict]) -> int:
        """批量同步实体"""
        count = 0
        for entity in entities:
            try:
                await self.sync_entity(entity)
                count += 1
            except Exception as e:
                logger.warning("AGE sync_entity failed for '%s': %s", entity.get("name"), e)
        return count

    async def sync_relation(self, relation: dict) -> None:
        """同步单条关系到 AGE Graph（MERGE 幂等）"""
        source_id = relation.get("source_entity", "")
        target_id = relation.get("target_entity", "")
        relation_type = relation.get("relation_type", "depends_on")
        confidence = relation.get("confidence", 1.0) or 1.0

        # 确保 relation_type 是合法的 edge label
        valid_types = (
            "supplier", "customer", "competitor", "depends_on", "owns",
            "uses", "invests_in", "located_in", "impacts", "causes", "SUPERSEDES",
        )
        if relation_type not in valid_types:
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
        await self.execute_cypher_write(cypher)

    async def sync_relations(self, relations: list[dict]) -> int:
        """批量同步关系"""
        count = 0
        for rel in relations:
            try:
                await self.sync_relation(rel)
                count += 1
            except Exception as e:
                logger.warning(
                    "AGE sync_relation failed (%s→%s): %s",
                    rel.get("source_entity", "?")[:8],
                    rel.get("target_entity", "?")[:8],
                    e,
                )
        return count

    # ──────────────────────────────────────────────
    # 内部工具
    # ──────────────────────────────────────────────

    @staticmethod
    def _escape(value: str) -> str:
        """转义 Cypher 字符串中的单引号"""
        if not value:
            return ""
        return value.replace("'", "\\'").replace("\\", "\\\\")

    @staticmethod
    def _parse_agtype(value) -> any:
        """解析 AGE agtype 返回值

        AGE 通过 asyncpg 返回的 agtype 可能是 str 或已解析的 dict/list。
        """
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        return value


# 模块级单例
age_storage = AGEStorage()
