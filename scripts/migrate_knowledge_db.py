"""
Knowledge Database 增量迁移脚本
================================
用于已初始化的 PostgreSQL 实例，执行 31_Knowledge_Database设计规范.md 的
多 Schema 架构升级（07-knowledge-database.sql）。

docker-entrypoint-initdb.d 仅在 volume 为空时执行，
已有部署需通过本脚本手动完成迁移。

用法:
    python scripts/migrate_knowledge_db.py

环境变量:
    POSTGRES_HOST     (默认: localhost)
    POSTGRES_PORT     (默认: 5433)  ← 宿主机映射端口
    POSTGRES_USER     (默认: postgres)
    POSTGRES_PASSWORD (默认: postgres)
    POSTGRES_DB       (默认: ai)

特性:
    - 所有 DDL 均为 IF NOT EXISTS / ON CONFLICT DO NOTHING，可安全重复执行
    - 使用 DO $$ 块保证 SET SCHEMA 幂等
"""

import asyncio
import os
import sys
from pathlib import Path

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

SQL_FILE = Path(__file__).parent.parent / "postgres" / "init" / "07-knowledge-database.sql"


async def main():
    print("=" * 60)
    print("  Knowledge Database 增量迁移")
    print("  基于 31_Knowledge_Database设计规范.md")
    print("=" * 60)

    # 检查 SQL 文件
    if not SQL_FILE.exists():
        print(f"\n[ERROR] SQL 文件不存在: {SQL_FILE}")
        sys.exit(1)

    sql_content = SQL_FILE.read_text(encoding="utf-8")
    print(f"\n[OK] 读取 SQL: {SQL_FILE.name} ({len(sql_content)} bytes)")

    # 连接数据库
    dsn = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
    print(f"[..] 连接: {PG_HOST}:{PG_PORT}/{PG_DB}")

    try:
        conn = await asyncpg.connect(dsn)
    except Exception as e:
        print(f"[ERROR] 连接失败: {e}")
        sys.exit(1)

    print("[OK] 连接成功")

    try:
        # 执行迁移
        print("\n[..] 执行迁移...")
        await conn.execute(sql_content)
        print("[OK] 迁移完成!")

        # 验证
        print("\n===== 验证结果 =====")

        schemas = await conn.fetch(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name IN ('core', 'document', 'vector', 'audit', 'taxonomy', 'knowledge') "
            "ORDER BY schema_name"
        )
        print(f"\n  Schema: {[r['schema_name'] for r in schemas]}")

        tables = await conn.fetch(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema IN ('core', 'document', 'vector', 'audit', 'taxonomy') "
            "AND table_type = 'BASE TABLE' "
            "ORDER BY table_schema, table_name"
        )
        print(f"\n  表 ({len(tables)}):")
        for t in tables:
            print(f"    {t['table_schema']}.{t['table_name']}")

        views = await conn.fetch(
            "SELECT table_schema, table_name FROM information_schema.views "
            "WHERE table_schema = 'knowledge' "
            "ORDER BY table_name"
        )
        print(f"\n  兼容视图 ({len(views)}):")
        for v in views:
            print(f"    {v['table_schema']}.{v['table_name']}")
    except Exception as e:
        print(f"[ERROR] 迁移失败: {e}")
        sys.exit(1)
    finally:
        await conn.close()

    print("\n" + "=" * 60)
    print("  迁移成功完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
