"""导入 providers.yaml 到 PostgreSQL providers 表

用法: python scripts/import_providers.py

环境变量:
    PROVIDERS_YAML - providers.yaml 文件路径 (默认: {PROJECT_ROOT}/data/providers.yaml)
    PG_DSN         - PostgreSQL 连接串 (默认: postgresql://postgres:postgres@localhost:5433/ai)
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg
import yaml

# 项目根目录（基于脚本位置推导）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

YAML_PATH = Path(os.environ.get("PROVIDERS_YAML", str(PROJECT_ROOT / "data" / "providers.yaml")))
DSN = os.environ.get("PG_DSN", "postgresql://postgres:postgres@localhost:5433/ai")


async def main():
    if not YAML_PATH.exists():
        print(f"ERROR: {YAML_PATH} not found")
        sys.exit(1)

    with open(YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    providers = data.get("providers", [])
    print(f"Loaded {len(providers)} providers from YAML")

    conn = await asyncpg.connect(DSN)

    # 确保表存在
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS providers (
            id                VARCHAR(50) PRIMARY KEY,
            name              VARCHAR(200) NOT NULL,
            name_en           VARCHAR(200),
            market            JSONB DEFAULT '[]',
            category          JSONB DEFAULT '[]',
            official          BOOLEAN DEFAULT false,
            free              BOOLEAN DEFAULT true,
            status            VARCHAR(20) DEFAULT 'unknown',
            protocol          JSONB DEFAULT '[]',
            base_url          TEXT,
            sdk               VARCHAR(100),
            supports          JSONB DEFAULT '[]',
            fallback          JSONB DEFAULT '[]',
            rate_limit        JSONB DEFAULT '{}',
            authentication    BOOLEAN DEFAULT false,
            priority          INTEGER DEFAULT 0,
            config            JSONB DEFAULT '{}',
            doc_url           TEXT,
            notes             TEXT,
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            updated_at        TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    inserted = 0
    for p in providers:
        pid = p.get("id", "")
        if not pid:
            continue

        # 提取 base_url（从 implementation 或 doc_url）
        impl = p.get("implementation", {})
        base_url = impl.get("base_url") or p.get("doc_url", "")

        # config 存放 implementation 等额外信息
        config = {}
        if impl:
            config["implementation"] = impl
        if p.get("verified_version"):
            config["verified_version"] = p["verified_version"]

        try:
            await conn.execute(
                """
                INSERT INTO providers (id, name, name_en, market, category, official, free,
                    status, protocol, base_url, sdk, supports, fallback, rate_limit,
                    authentication, priority, config, doc_url, notes)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
                ON CONFLICT (id) DO UPDATE SET
                    name=EXCLUDED.name, market=EXCLUDED.market, category=EXCLUDED.category,
                    status=EXCLUDED.status, priority=EXCLUDED.priority,
                    supports=EXCLUDED.supports, updated_at=NOW()
                """,
                pid,
                p.get("name", pid),
                p.get("name_en"),
                json.dumps(p.get("market", [])),
                json.dumps(p.get("category", [])),
                p.get("official", False),
                p.get("free", True),
                p.get("status", "unknown"),
                json.dumps(p.get("protocol", [])),
                base_url,
                p.get("sdk"),
                json.dumps(p.get("supports", [])),
                json.dumps(p.get("fallback", [])),
                json.dumps(p.get("rate_limit", {})),
                p.get("authentication", False) if isinstance(p.get("authentication"), bool) else bool(p.get("authentication")),
                p.get("priority", 0),
                json.dumps(config),
                p.get("doc_url"),
                p.get("notes"),
            )
            inserted += 1
        except Exception as e:
            print(f"  WARN: failed to insert {pid}: {e}")

    await conn.close()
    print(f"Done: {inserted} providers imported")


if __name__ == "__main__":
    asyncio.run(main())
