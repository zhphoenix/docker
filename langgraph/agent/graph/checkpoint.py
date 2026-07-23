"""Checkpoint 配置 - PostgreSQL AsyncPostgresSaver"""

import logging

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from config.settings import settings

logger = logging.getLogger(__name__)


async def get_checkpointer() -> AsyncPostgresSaver:
    """获取 PostgreSQL Checkpointer

    注意：必须使用 async with 管理生命周期

    Returns:
        AsyncPostgresSaver 实例
    """
    conn_string = settings.CHECKPOINT_CONNSTRING
    logger.info("Creating checkpointer with connection: %s", conn_string.split("@")[-1])

    checkpointer = await AsyncPostgresSaver.from_conn_string(conn_string)
    return checkpointer
