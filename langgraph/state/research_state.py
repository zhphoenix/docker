"""AgentState 定义 - 所有 Node 的统一数据载体"""

from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """统一 Agent 状态

    所有 Node 只能修改 State，不直接返回结果。
    """

    # 消息历史（使用 add_messages 注解，自动追加）
    messages: Annotated[list[BaseMessage], add_messages]

    # 用户原始问题（API 层写入）
    question: str

    # 执行计划（Planner 生成）
    plan: dict

    # 检索到的文档 Chunk（Retrieve / Rerank 填充）
    documents: list[dict]

    # 工具调用结果缓存
    tool_results: dict

    # LLM 生成的回答（Reason / Writer 写入）
    answer: str

    # 反思结果（Reflect 填充：quality, confidence, retry_count）
    reflect: dict

    # 运行元数据（耗时、token 用量等）
    metadata: dict
