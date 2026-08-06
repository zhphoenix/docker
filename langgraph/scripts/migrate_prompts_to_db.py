"""Prompt 全量迁移：将 prompts/*.md 一次性导入 agent_prompts 表（DB 成为唯一事实源）

用法: 在 langgraph 容器内执行
    python scripts/migrate_prompts_to_db.py

环境变量:
    PG_DSN - PostgreSQL 连接串 (默认: postgresql://postgres:postgres@localhost:5433/ai)
    PROMPTS_DIR - prompts 目录 (默认: {langgraph}/prompts)

设计:
    - 文件名映射: "chat/system.md" → (agent_id=chat, name=system)
                     "reason.md"      → (agent_id=common, name=reason)
    - 幂等: 已存在 (agent_id, name, version=1) 则跳过。
    - 输出对账清单: 文件数 vs 实际写入 DB 行数。
"""

import asyncio
import os
import sys
from pathlib import Path

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = Path(os.environ.get("PROMPTS_DIR", str(PROJECT_ROOT / "prompts")))
DSN = os.environ.get("PG_DSN", "postgresql://postgres:postgres@localhost:5433/ai")


def path_to_keys(rel: Path) -> tuple[str, str]:
    """将相对路径映射为 (agent_id, name)"""
    parts = rel.parts
    if len(parts) == 1:
        return "common", parts[0]
    return parts[0], "/".join(parts[1:])


async def run() -> int:
    if not PROMPTS_DIR.exists():
        print(f"ERROR: {PROMPTS_DIR} not found")
        return 1

    files = sorted(PROMPTS_DIR.rglob("*.md"))
    print(f"Found {len(files)} prompt files under {PROMPTS_DIR}")

    conn = await asyncpg.connect(DSN)
    try:
        inserted = 0
        skipped = 0
        for f in files:
            rel = f.relative_to(PROMPTS_DIR).with_suffix("")
            agent_id, name = path_to_keys(rel)
            content = f.read_text(encoding="utf-8")
            # 幂等 upsert：已存在 v1 则跳过
            result = await conn.execute(
                """
                INSERT INTO agent_prompts (agent_id, name, content, version, is_active)
                VALUES ($1, $2, $3, 1, true)
                ON CONFLICT (agent_id, name, version) DO NOTHING
                """,
                agent_id, name, content,
            )
            if result.startswith("INSERT"):
                inserted += 1
                print(f"  + {agent_id}/{name} ({len(content)} chars)")
            else:
                skipped += 1

        # 对账：统计 DB 中现有行数
        rows = await conn.fetch(
            "SELECT agent_id, name, version FROM agent_prompts ORDER BY agent_id, name, version"
        )
        print("\n=== 对账清单 ===")
        print(f"文件数: {len(files)} | 本次写入: {inserted} | 跳过(已存在): {skipped}")
        print(f"DB agent_prompts 总行数: {len(rows)}")
        if files:
            print(f"DB/文件 比例: {len(rows)}/{len(files)}")
        for r in rows:
            print(f"  {r['agent_id']}/{r['name']} v{r['version']}")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))