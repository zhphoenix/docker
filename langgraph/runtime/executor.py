"""Runtime Executor - Graph 执行统一入口

封装 Graph 的调用（ainvoke / astream），屏蔽调用方对具体 Graph
实例与编译细节的依赖。配合 memory.checkpoint 可为需要多轮会话的
Graph 注入 Checkpointer。

Usage:
    from runtime.executor import run_graph, stream_graph
    result = await run_graph("research", initial_state)
    async for chunk in stream_graph("chat", initial_state):
        ...
"""

import logging
from typing import AsyncGenerator, Any

from graphs import get_graph

logger = logging.getLogger(__name__)


async def run_graph(workflow_name: str, initial_state: dict, config: dict | None = None) -> dict:
    """执行指定工作流（非流式）

    Args:
        workflow_name: workflows.yaml 中的工作流名
        initial_state: 初始 State
        config: LangGraph RunnableConfig（thread_id 等）

    Returns:
        最终 State
    """
    graph = get_graph(workflow_name)
    logger.info("Executor: running workflow '%s'", workflow_name)
    return await graph.ainvoke(initial_state, config=config)


async def stream_graph(
    workflow_name: str, initial_state: dict, config: dict | None = None
) -> AsyncGenerator[Any, None]:
    """执行指定工作流（流式）

    Args:
        workflow_name: workflows.yaml 中的工作流名
        initial_state: 初始 State
        config: LangGraph RunnableConfig

    Yields:
        LangGraph 的流式输出（values 模式）
    """
    graph = get_graph(workflow_name)
    logger.info("Executor: streaming workflow '%s'", workflow_name)
    async for chunk in graph.astream(initial_state, config=config, stream_mode="values"):
        yield chunk


def get_compiled_graph(workflow_name: str):
    """直接获取编译后的 Graph（供需要手动控制的调用方）"""
    return get_graph(workflow_name)
