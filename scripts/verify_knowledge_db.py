"""
Knowledge Database 验证脚本
============================
验证 31_Knowledge_Database设计规范.md 的所有要求是否已正确落地。

用法:
    python scripts/verify_knowledge_db.py

环境变量:
    POSTGRES_HOST     (默认: localhost)
    POSTGRES_PORT     (默认: 5433)
    POSTGRES_USER     (默认: postgres)
    POSTGRES_PASSWORD (默认: postgres)
    POSTGRES_DB       (默认: ai)

输出:
    checklist 报告（✅ / ❌）
"""

import asyncio
import os
import sys

try:
    import asyncpg
except ImportError:
    print("[ERROR] 需要 asyncpg: pip install asyncpg")
    sys.exit(1)


# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────
PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5433"))
PG_USER = os.getenv("POSTGRES_USER", "postgres")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
PG_DB = os.getenv("POSTGRES_DB", "ai")

# ──────────────────────────────────────────────
# 验证项定义
# ──────────────────────────────────────────────
REQUIRED_SCHEMAS = ["core", "document", "vector", "audit", "taxonomy"]

REQUIRED_TABLES = [
    ("core", "entities"),
    ("core", "relations"),
    ("core", "facts"),
    ("core", "evidence"),
    ("core", "entity_aliases"),
    ("core", "events"),
    ("core", "knowledge_conflicts"),
    ("document", "documents"),
    ("document", "chunks"),
    ("vector", "entity_embeddings"),
    ("audit", "knowledge_versions"),
    ("taxonomy", "entity_types"),
    ("taxonomy", "relation_types"),
    ("taxonomy", "knowledge_statuses"),
]

REQUIRED_COLUMNS = [
    ("core", "entities", "created_by"),
    ("core", "facts", "source_quality"),
    ("core", "facts", "extraction_confidence"),
    ("core", "facts", "validation_score"),
]

COMPAT_VIEWS = [
    ("knowledge", "entities"),
    ("knowledge", "relations"),
    ("knowledge", "facts"),
    ("knowledge", "evidence"),
    ("knowledge", "documents"),
    ("knowledge", "entity_types"),
    ("knowledge", "relation_types"),
]

REQUIRED_INDEXES = [
    "idx_kg_aliases_entity",
    "idx_kg_aliases_alias_trgm",
    "idx_kg_events_type",
    "idx_kg_events_date",
    "idx_kg_conflicts_status",
    "idx_kg_chunks_doc",
    # idx_kg_entity_emb_hnsw 已移除: 2560维超过pgvector HNSW 2000维限制
    "idx_kg_versions_object",
    "idx_kg_versions_unique",
]

PRESET_DATA = [
    ("taxonomy.knowledge_statuses", "discovered"),
    ("taxonomy.knowledge_statuses", "extracted"),
    ("taxonomy.knowledge_statuses", "validated"),
    ("taxonomy.knowledge_statuses", "trusted"),
    ("taxonomy.knowledge_statuses", "outdated"),
    ("taxonomy.knowledge_statuses", "archived"),
    ("taxonomy.relation_types", "supplier"),
    ("taxonomy.relation_types", "customer"),
    ("taxonomy.relation_types", "competitor"),
]


async def main():
    print("=" * 60)
    print("  Knowledge Database 验证")
    print("  基于 31_Knowledge_Database设计规范.md")
    print("=" * 60)

    dsn = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"

    try:
        conn = await asyncpg.connect(dsn)
    except Exception as e:
        print(f"\n[ERROR] 连接失败: {e}")
        sys.exit(1)

    print(f"\n[OK] 连接: {PG_HOST}:{PG_PORT}/{PG_DB}")

    passed = 0
    failed = 0

    def report(ok: bool, label: str):
        nonlocal passed, failed
        icon = "✅" if ok else "❌"
        print(f"  {icon} {label}")
        if ok:
            passed += 1
        else:
            failed += 1

    # ── 1. Schema 验证 ──
    print("\n── Schema ──")
    existing_schemas = {
        r["schema_name"]
        for r in await conn.fetch(
            "SELECT schema_name FROM information_schema.schemata"
        )
    }
    for s in REQUIRED_SCHEMAS:
        report(s in existing_schemas, f"schema: {s}")

    # ── 2. 表验证 ──
    print("\n── 表 ──")
    existing_tables = {
        (r["table_schema"], r["table_name"])
        for r in await conn.fetch(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_type = 'BASE TABLE'"
        )
    }
    for schema, table in REQUIRED_TABLES:
        report((schema, table) in existing_tables, f"{schema}.{table}")

    # ── 3. 列验证 ──
    print("\n── 补充列 ──")
    existing_columns = {
        (r["table_schema"], r["table_name"], r["column_name"])
        for r in await conn.fetch(
            "SELECT table_schema, table_name, column_name "
            "FROM information_schema.columns"
        )
    }
    for schema, table, col in REQUIRED_COLUMNS:
        report(
            (schema, table, col) in existing_columns,
            f"{schema}.{table}.{col}",
        )

    # ── 4. 兼容视图验证 ──
    print("\n── 兼容视图 ──")
    existing_views = {
        (r["table_schema"], r["table_name"])
        for r in await conn.fetch(
            "SELECT table_schema, table_name FROM information_schema.views"
        )
    }
    for schema, view in COMPAT_VIEWS:
        report((schema, view) in existing_views, f"{schema}.{view} (view)")

    # ── 5. 索引验证 ──
    print("\n── 索引 ──")
    existing_indexes = {
        r["indexname"]
        for r in await conn.fetch(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname IN ('core', 'document', 'vector', 'audit', 'taxonomy')"
        )
    }
    for idx in REQUIRED_INDEXES:
        report(idx in existing_indexes, f"index: {idx}")

    # ── 6. 预置数据验证 ──
    print("\n── 预置数据 ──")
    for table, name in PRESET_DATA:
        row = await conn.fetchrow(
            f"SELECT 1 FROM {table} WHERE name = $1", name
        )
        report(row is not None, f"{table}: '{name}'")

    # ── 7. search_path 验证 ──
    print("\n── search_path ──")
    sp = await conn.fetchval(
        "SELECT setting FROM pg_settings WHERE name = 'search_path'"
    )
    has_core = "core" in (sp or "")
    report(has_core, f"search_path 包含 core: {sp}")

    await conn.close()

    # ── 汇总 ──
    total = passed + failed
    print("\n" + "=" * 60)
    print(f"  结果: {passed}/{total} 通过, {failed} 失败")
    if failed == 0:
        print("  🎉 所有验证项通过!")
    else:
        print("  ⚠️  存在未通过项，请检查迁移是否完整执行")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
