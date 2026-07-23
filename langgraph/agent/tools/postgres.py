"""PostgreSQL Tool - 封装 PostgreSQL 查询（:5432）"""

import logging
from typing import Optional

import asyncpg

from config.settings import settings

logger = logging.getLogger(__name__)


class PostgresTool:
    """PostgreSQL 查询工具"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """创建连接池"""
        dsn = (
            f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
            f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
        )
        self.pool = await asyncpg.create_pool(dsn)
        logger.info("PostgreSQL connection pool created")

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
        if not self.pool:
            await self.connect()
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
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            return await conn.execute(sql, *args)


# 模块级单例
postgres_tool = PostgresTool()
