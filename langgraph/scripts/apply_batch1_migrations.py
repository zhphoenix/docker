"""应用批次 1 迁移文件到存量 DB（幂等）

15-knowledge-package.sql → knowledge_packages 表
16-news-health.sql      → news.collect_runs 表 + news.sources 扩列

init 脚本仅首次初始化生效，存量 DB 需手动应用，此脚本即该手动入口。
用 asyncpg 多语句执行（单连接 + 简单协议），不通过 psql CLI 暴露凭据。
"""
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

LANGGRAPH = Path(__file__).resolve().parent.parent
PROJ = LANGGRAPH.parent
load_dotenv(PROJ / ".env", override=False)
sys.path.insert(0, str(LANGGRAPH))

MIGRATIONS = [
    PROJ / "postgres/init/15-knowledge-package.sql",
    PROJ / "postgres/init/16-news-health.sql",
]


async def main() -> int:
    from tools.postgres import postgres_tool
    await postgres_tool.connect()
    ok = True
    async with postgres_tool.pool.acquire() as conn:
        for m in MIGRATIONS:
            sql = m.read_text(encoding="utf-8")
            try:
                await conn.execute(sql)
                print(f"[OK] {m.name}")
            except Exception as e:
                print(f"[FAIL] {m.name}: {e}")
                ok = False
    await postgres_tool.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))