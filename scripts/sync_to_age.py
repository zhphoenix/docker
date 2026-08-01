#!/usr/bin/env python3
"""PostgreSQL → Apache AGE 数据同步脚本

将 core.entities + core.relations 现有数据同步到 AGE Graph。
幂等：使用 MERGE（ON MATCH 更新属性）。

用法：
  python3 scripts/sync_to_age.py
  python3 scripts/sync_to_age.py --batch-size 100 --dry-run
  python3 scripts/sync_to_age.py --entities-only
  python3 scripts/sync_to_age.py --relations-only

环境变量：
  PG_HOST (default: localhost)
  PG_PORT (default: 5433)
  PG_USER (default: postgres)
  PG_PASS (default: postgres)
  PG_DB   (default: ai)
"""

import asyncio
import argparse
import os
import sys
import time

import asyncpg

# ── 配置 ──────────────────────────────────────────────────────────────────────

PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = int(os.environ.get("PG_PORT", "5433"))
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASS = os.environ.get("PG_PASS", "postgres")
PG_DB = os.environ.get("PG_DB", "ai")

GRAPH_NAME = "investment_knowledge_graph"

# 合法 entity_type → Vertex Label 映射
VALID_LABELS = {
    "Company", "Person", "Product", "Technology", "Industry",
    "Country", "Organization", "Event", "Metric", "Concept",
}

# 合法 relation_type → Edge Label
VALID_EDGE_LABELS = {
    "supplier", "customer", "competitor", "depends_on", "owns",
    "uses", "invests_in", "located_in", "impacts", "causes", "SUPERSEDES",
}


def escape_cypher(value: str) -> str:
    """转义 Cypher 字符串"""
    if not value:
        return ""
    return value.replace("\\", "\\\\").replace("'", "\\'")


async def verify_age(conn: asyncpg.Connection) -> bool:
    """验证 AGE 扩展和 Graph 是否就绪"""
    try:
        await conn.execute("LOAD 'age';")
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM ag_catalog.ag_graph WHERE name = $1",
            GRAPH_NAME,
        )
        if row and row["cnt"] > 0:
            print(f"✓ AGE graph '{GRAPH_NAME}' found")
            return True
        else:
            print(f"✗ AGE graph '{GRAPH_NAME}' not found. Run 08-age-init.sql first.")
            return False
    except Exception as e:
        print(f"✗ AGE extension not available: {e}")
        return False


async def sync_entities(conn: asyncpg.Connection, batch_size: int, dry_run: bool) -> int:
    """同步 core.entities → AGE Vertex"""
    print("\n── Syncing Entities ──")

    # 统计
    total = await conn.fetchval(
        "SELECT COUNT(*) FROM core.entities WHERE status = 'active'"
    )
    print(f"  Found {total} active entities in PostgreSQL")

    if dry_run:
        print("  [DRY RUN] Skipping actual sync")
        return total

    synced = 0
    offset = 0

    while offset < total:
        rows = await conn.fetch(
            """
            SELECT id, name, entity_type, description, canonical_name, confidence
            FROM core.entities
            WHERE status = 'active'
            ORDER BY id
            LIMIT $1 OFFSET $2
            """,
            batch_size, offset,
        )

        for row in rows:
            entity_id = str(row["id"])
            name = escape_cypher(row["name"] or "")
            entity_type = row["entity_type"] or "Entity"
            description = escape_cypher(row["description"] or "")
            canonical = escape_cypher(row["canonical_name"] or row["name"] or "")
            confidence = row["confidence"] if row["confidence"] is not None else 1.0

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
                synced += 1
            except Exception as e:
                print(f"  ✗ Entity '{row['name']}' failed: {e}")

        offset += batch_size
        pct = min(100, int(offset / total * 100)) if total > 0 else 100
        print(f"  Progress: {min(offset, total)}/{total} ({pct}%)")

    print(f"  ✓ Synced {synced}/{total} entities")
    return synced


async def sync_relations(conn: asyncpg.Connection, batch_size: int, dry_run: bool) -> int:
    """同步 core.relations → AGE Edge"""
    print("\n── Syncing Relations ──")

    total = await conn.fetchval(
        "SELECT COUNT(*) FROM core.relations WHERE status = 'active'"
    )
    print(f"  Found {total} active relations in PostgreSQL")

    if dry_run:
        print("  [DRY RUN] Skipping actual sync")
        return total

    synced = 0
    offset = 0

    while offset < total:
        rows = await conn.fetch(
            """
            SELECT id, source_entity, target_entity, relation_type, confidence
            FROM core.relations
            WHERE status = 'active'
            ORDER BY id
            LIMIT $1 OFFSET $2
            """,
            batch_size, offset,
        )

        for row in rows:
            source_id = str(row["source_entity"])
            target_id = str(row["target_entity"])
            relation_type = row["relation_type"] or "depends_on"
            confidence = row["confidence"] if row["confidence"] is not None else 1.0

            # 确保 edge label 合法
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
                synced += 1
            except Exception as e:
                # 常见原因：source/target 节点不存在
                if synced % 100 == 0:
                    print(f"  ✗ Relation {source_id[:8]}→{target_id[:8]} failed: {e}")

        offset += batch_size
        pct = min(100, int(offset / total * 100)) if total > 0 else 100
        print(f"  Progress: {min(offset, total)}/{total} ({pct}%)")

    print(f"  ✓ Synced {synced}/{total} relations")
    return synced


async def print_graph_stats(conn: asyncpg.Connection) -> None:
    """打印 AGE Graph 统计信息"""
    print("\n── Graph Statistics ──")
    try:
        cypher = "MATCH (n) RETURN count(n) AS node_count"
        sql = f"SELECT * FROM cypher('{GRAPH_NAME}', $${cypher}$$) AS (node_count agtype);"
        row = await conn.fetchrow(sql)
        print(f"  Nodes: {row['node_count'] if row else '?'}")

        cypher = "MATCH ()-[r]->() RETURN count(r) AS edge_count"
        sql = f"SELECT * FROM cypher('{GRAPH_NAME}', $${cypher}$$) AS (edge_count agtype);"
        row = await conn.fetchrow(sql)
        print(f"  Edges: {row['edge_count'] if row else '?'}")
    except Exception as e:
        print(f"  Stats unavailable: {e}")


async def main():
    parser = argparse.ArgumentParser(description="Sync PostgreSQL data to Apache AGE Graph")
    parser.add_argument("--batch-size", type=int, default=200, help="Batch size (default: 200)")
    parser.add_argument("--dry-run", action="store_true", help="Count only, no writes")
    parser.add_argument("--entities-only", action="store_true", help="Sync entities only")
    parser.add_argument("--relations-only", action="store_true", help="Sync relations only")
    args = parser.parse_args()

    dsn = f"postgresql://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}"
    print(f"Connecting to {PG_HOST}:{PG_PORT}/{PG_DB}...")

    conn = await asyncpg.connect(dsn)

    # 设置 AGE search_path
    await conn.execute("SET search_path = ag_catalog, \"$user\", public;")

    # 验证 AGE
    if not await verify_age(conn):
        await conn.close()
        sys.exit(1)

    start = time.time()

    sync_all = not args.entities_only and not args.relations_only

    if sync_all or args.entities_only:
        await sync_entities(conn, args.batch_size, args.dry_run)

    if sync_all or args.relations_only:
        await sync_relations(conn, args.batch_size, args.dry_run)

    if not args.dry_run:
        await print_graph_stats(conn)

    elapsed = time.time() - start
    print(f"\n✓ Done in {elapsed:.1f}s")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
