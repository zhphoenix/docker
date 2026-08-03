"""Thread Manager - LangGraph 会话线程管理

负责生成 thread_id 与组装 RunnableConfig，供带 Checkpointer 的
对话型 Graph 实现多轮会话的状态持久化。

Usage:
    from memory.thread_manager import build_run_config
    config = build_run_config(thread_id="user-123")
    result = await graph.ainvoke(state, config=config)
"""

import uuid


def new_thread_id() -> str:
    """生成一个唯一的 thread_id"""
    return f"thread-{uuid.uuid4().hex[:16]}"


def build_run_config(thread_id: str | None = None, checkpoint_ns: str = "") -> dict:
    """组装 LangGraph RunnableConfig

    Args:
        thread_id: 会话线程 ID；为 None 时自动生成
        checkpoint_ns: checkpoint 命名空间（子图隔离时使用）

    Returns:
        {"configurable": {"thread_id": ..., "checkpoint_ns": ...}}
    """
    configurable = {"thread_id": thread_id or new_thread_id()}
    if checkpoint_ns:
        configurable["checkpoint_ns"] = checkpoint_ns
    return {"configurable": configurable}
