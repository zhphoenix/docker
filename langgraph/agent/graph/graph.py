"""Graph 定义 - LangGraph StateGraph 构建"""

import logging

from langgraph.graph import StateGraph, START, END

from graph.state import AgentState
from rag_nodes.planner import planner
from rag_nodes.retrieve import retrieve
from rag_nodes.rerank import rerank
from rag_nodes.reason import reason
from rag_nodes.reflect import reflect
from rag_nodes.finish import finish
from rag_nodes.knowledge import knowledge
from rag_nodes.query_rewrite import query_rewrite

logger = logging.getLogger(__name__)


def should_continue(state: AgentState) -> str:
    """Reflect 节点后的条件路由

    - quality == "good" → finish
    - retry_count >= 2 → finish（强制结束）
    - quality == "bad" → retrieve（补充检索）
    """
    reflect_result = state.get("reflect", {})
    quality = reflect_result.get("quality", "good")
    retry_count = reflect_result.get("retry_count", 0)

    if quality == "good":
        logger.info("Route: quality=good → finish")
        return "finish"
    elif retry_count >= 2:
        logger.info("Route: retry_count=%d >= 2 → finish (forced)", retry_count)
        return "finish"
    else:
        logger.info("Route: quality=bad, retry_count=%d → retrieve", retry_count)
        return "retrieve"


def build_research_graph() -> StateGraph:
    """构建 Research Agent 的完整 Workflow

    Planner → QueryRewrite → Retrieve → Rerank → Reason → Reflect
                                                          ↓
                                                (bad) → Retrieve (retry)
                                                (good) → Finish → END
    """
    graph = StateGraph(AgentState)

    # 添加节点
    graph.add_node("planner", planner)
    graph.add_node("query_rewrite", query_rewrite)
    graph.add_node("retrieve", retrieve)
    graph.add_node("rerank", rerank)
    graph.add_node("reason", reason)
    graph.add_node("reflect", reflect)
    graph.add_node("finish", finish)

    # 添加边
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "query_rewrite")
    graph.add_edge("query_rewrite", "retrieve")
    graph.add_edge("retrieve", "rerank")
    graph.add_edge("rerank", "reason")
    graph.add_edge("reason", "reflect")

    # 条件边
    graph.add_conditional_edges(
        "reflect",
        should_continue,
        {"finish": "finish", "retrieve": "retrieve"},
    )

    graph.add_edge("finish", END)

    return graph.compile()


def build_chat_graph() -> StateGraph:
    """构建 Chat Agent 的简化 Workflow

    Retrieve → Rerank → Reason → Finish → END
    （跳过 Planner 和 Reflect）
    """
    graph = StateGraph(AgentState)

    # 添加节点
    graph.add_node("retrieve", retrieve)
    graph.add_node("rerank", rerank)
    graph.add_node("reason", reason)
    graph.add_node("finish", finish)

    # 添加边
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "rerank")
    graph.add_edge("rerank", "reason")
    graph.add_edge("reason", "finish")
    graph.add_edge("finish", END)

    return graph.compile()


def build_kb_graph() -> StateGraph:
    """构建 KB Agent（知识库）的 Workflow

    Retrieve → Rerank → Reason → Knowledge (Vault 读写) → Finish → END
    """
    graph = StateGraph(AgentState)

    graph.add_node("retrieve", retrieve)
    graph.add_node("rerank", rerank)
    graph.add_node("reason", reason)
    graph.add_node("knowledge", knowledge)
    graph.add_node("finish", finish)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "rerank")
    graph.add_edge("rerank", "reason")
    graph.add_edge("reason", "knowledge")
    graph.add_edge("knowledge", "finish")
    graph.add_edge("finish", END)

    return graph.compile()
