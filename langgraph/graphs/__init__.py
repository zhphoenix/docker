"""Graphs Registry - 工作流定义统一入口

依据 config/workflows.yaml 声明式注册表，按需导入对应模块的 builder
编译 Graph 并缓存。所有调用方应从这里获取编译后的 Graph，
而不要直接 import 各 graph 模块，以便统一管理生命周期。

Usage:
    from graphs import get_research_graph
    graph = get_research_graph()
    result = await graph.ainvoke(initial_state)
"""

import importlib
import logging

from config.policy_loader import get_workflows_registry

logger = logging.getLogger(__name__)

# 编译后的 Graph 缓存 {workflow_name: compiled_graph}
_compiled_cache: dict = {}


def _resolve_builder(workflow_name: str):
    """根据 workflows.yaml 解析出某个工作流的 builder 可调用对象"""
    registry = get_workflows_registry()
    spec = registry.get(workflow_name)
    if not spec:
        raise KeyError(f"Workflow '{workflow_name}' not found in workflows.yaml")
    module_path = spec.get("module")
    builder_name = spec.get("builder")
    if not module_path or not builder_name:
        raise ValueError(f"Workflow '{workflow_name}' missing module/builder in workflows.yaml")
    module = importlib.import_module(module_path)
    return getattr(module, builder_name)


def get_graph(workflow_name: str):
    """获取指定工作流的编译后 Graph（带缓存）

    Args:
        workflow_name: workflows.yaml 中定义的工作流名
                       （research / chat / kb / news / knowledge / document）
    """
    if workflow_name in _compiled_cache:
        return _compiled_cache[workflow_name]

    builder = _resolve_builder(workflow_name)
    graph = builder()
    _compiled_cache[workflow_name] = graph
    logger.info("Graph '%s' compiled and cached", workflow_name)
    return graph


def get_research_graph():
    """获取 Research Agent Graph（完整投资研究流程）"""
    return get_graph("research")


def get_chat_graph():
    """获取 Chat Agent Graph（简化流程）"""
    return get_graph("chat")


def get_kb_graph():
    """获取 KB Agent Graph（知识库流程）"""
    return get_graph("kb")


def get_news_graph():
    """获取 News Intelligence Graph"""
    return get_graph("news")


def get_knowledge_graph():
    """获取 Knowledge Ingestion Graph"""
    return get_graph("knowledge")


def get_document_graph():
    """获取 Document Graph（文档处理流程）"""
    return get_graph("document")


def list_workflows() -> list[str]:
    """列出 workflows.yaml 中定义的所有工作流名"""
    return list(get_workflows_registry().keys())


__all__ = [
    "get_graph",
    "get_research_graph",
    "get_chat_graph",
    "get_kb_graph",
    "get_news_graph",
    "get_knowledge_graph",
    "get_document_graph",
    "list_workflows",
]
