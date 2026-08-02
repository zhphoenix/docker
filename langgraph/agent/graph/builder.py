"""Graph Builder - 封装 Graph 构建与 Checkpointer 生命周期"""

import logging

from graph.graph import build_research_graph, build_chat_graph, build_kb_graph

logger = logging.getLogger(__name__)

# 缓存编译后的 Graph
_research_graph = None
_chat_graph = None
_kb_graph = None


def get_research_graph():
    """获取 Research Agent Graph（带 Checkpoint）"""
    global _research_graph
    if _research_graph is None:
        _research_graph = build_research_graph()
        logger.info("Research graph compiled")
    return _research_graph


def get_chat_graph():
    """获取 Chat Agent Graph"""
    global _chat_graph
    if _chat_graph is None:
        _chat_graph = build_chat_graph()
        logger.info("Chat graph compiled")
    return _chat_graph


def get_kb_graph():
    """获取 KB Agent Graph"""
    global _kb_graph
    if _kb_graph is None:
        _kb_graph = build_kb_graph()
        logger.info("KB graph compiled")
    return _kb_graph
