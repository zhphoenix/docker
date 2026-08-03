"""PostgreSQL Tool - 封装 PostgreSQL 查询（:5432）"""

import asyncio
import logging
from typing import Optional

import asyncpg

from config.settings import settings

logger = logging.getLogger(__name__)


class PostgresTool:
    """PostgreSQL 查询工具"""

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
        """创建连接池（含语句超时配置）"""
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
                # 注: 当前无 HNSW 索引(2560维超限), 此参数预留未来降维/换模型场景
                "hnsw.ef_search": str(settings.PG_HNSW_EF_SEARCH),
                "statement_timeout": str(settings.PG_STATEMENT_TIMEOUT_MS),
            },
        )
        logger.info(
            "PostgreSQL pool created (min=%d, max=%d, ef_search=%d)",
            settings.PG_POOL_MIN_SIZE,
            settings.PG_POOL_MAX_SIZE,
            settings.PG_HNSW_EF_SEARCH,
        )

    async def close(self) -> None:
        """关闭连接池"""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL connection pool closed")

    async def query(self, sql: str, *args) -> list[dict]:
        """查询

        Args:
            sql: SQL 查询语句（使用 $1, $2 占位符）
            *args: 参数

        Returns:
            [dict, ...]
        """
        await self._ensure_pool()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
            return [dict(r) for r in rows]

    async def execute(self, sql: str, *args) -> str:
        """执行（INSERT/UPDATE/DELETE）

        Args:
            sql: SQL 语句
            *args: 参数

        Returns:
            执行状态字符串
        """
        await self._ensure_pool()
        async with self.pool.acquire() as conn:
            return await conn.execute(sql, *args)

    async def execute_many(self, sql: str, args_list: list[tuple]) -> None:
        """批量执行（使用 asyncpg executemany，高性能）

        Args:
            sql: SQL 语句
            args_list: 参数元组列表
        """
        await self._ensure_pool()
        async with self.pool.acquire() as conn:
            await conn.executemany(sql, args_list)


# 模块级单例
postgres_tool = PostgresTool()
