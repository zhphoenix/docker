"""Knowledge Organization Agent Graph - LangGraph StateGraph 定义

流水线: Parser → Entity → [Relation || Fact] → Validator → Merger → END
性能优化: Entity 完成后 Relation/Fact 并行执行（fan-out/fan-in）
"""

import logging
import time
from functools import wraps

from langgraph.graph import StateGraph, START, END

from knowledge_agent.state import KnowledgeState
from knowledge_agent.nodes.parser import document_parser
from knowledge_agent.nodes.entity import entity_extractor
from knowledge_agent.nodes.relation import relation_extractor
from knowledge_agent.nodes.fact import fact_extractor
from knowledge_agent.nodes.validator import knowledge_validator
from knowledge_agent.nodes.merger import knowledge_merger

logger = logging.getLogger(__name__)


def _timed(node_name: str):
    """节点计时装饰器（性能基线监控）"""
    def decorator(func):
        @wraps(func)
        async def wrapper(state: dict) -> dict:
            start = time.perf_counter()
            result = await func(state)
            elapsed = time.perf_counter() - start
            logger.info(
                "[Perf] %s: %.2fs | doc=%s",
                node_name, elapsed, state.get("document_id", "?")[:8],
            )
            return result
        return wrapper
    return decorator


def build_knowledge_organization_graph():
    """构建 Knowledge Organization Agent 的 Workflow

    Parser → EntityExtractor → [RelationExtractor || FactExtractor]
    → Validator → Merger → END

    性能优化：Relation 和 Fact 提取并行执行（fan-out/fan-in），
    两者都依赖 Entity 结果 + chunks，但彼此无数据依赖。
    """
    graph = StateGraph(KnowledgeState)

    # 添加节点（带计时）
    graph.add_node("parser", _timed("parser")(document_parser))
    graph.add_node("entity_extractor", _timed("entity_extractor")(entity_extractor))
    graph.add_node("relation_extractor", _timed("relation_extractor")(relation_extractor))
    graph.add_node("fact_extractor", _timed("fact_extractor")(fact_extractor))
    graph.add_node("validator", _timed("validator")(knowledge_validator))
    graph.add_node("merger", _timed("merger")(knowledge_merger))

    # 边：入口 → Parser → Entity
    graph.add_edge(START, "parser")
    graph.add_edge("parser", "entity_extractor")

    # Fan-out: Entity 完成后，Relation 和 Fact 并行执行
    graph.add_edge("entity_extractor", "relation_extractor")
    graph.add_edge("entity_extractor", "fact_extractor")

    # Fan-in: 两者都完成后进入 Validator
    graph.add_edge("relation_extractor", "validator")
    graph.add_edge("fact_extractor", "validator")

    # Validator → Merger → END
    graph.add_edge("validator", "merger")
    graph.add_edge("merger", END)

    return graph.compile()
