"""Knowledge Organization Agent Graph - LangGraph StateGraph 定义

流水线: Parser → Entity → Relation → Fact → Validator → Merger → END
"""

import logging

from langgraph.graph import StateGraph, START, END

from knowledge_agent.state import KnowledgeState
from knowledge_agent.nodes.parser import document_parser
from knowledge_agent.nodes.entity import entity_extractor
from knowledge_agent.nodes.relation import relation_extractor
from knowledge_agent.nodes.fact import fact_extractor
from knowledge_agent.nodes.validator import knowledge_validator
from knowledge_agent.nodes.merger import knowledge_merger

logger = logging.getLogger(__name__)


def build_knowledge_organization_graph():
    """构建 Knowledge Organization Agent 的 Workflow

    Parser → EntityExtractor → RelationExtractor → FactExtractor
    → Validator → Merger → END
    """
    graph = StateGraph(KnowledgeState)

    # 添加节点
    graph.add_node("parser", document_parser)
    graph.add_node("entity_extractor", entity_extractor)
    graph.add_node("relation_extractor", relation_extractor)
    graph.add_node("fact_extractor", fact_extractor)
    graph.add_node("validator", knowledge_validator)
    graph.add_node("merger", knowledge_merger)

    # 添加边（线性流水线）
    graph.add_edge(START, "parser")
    graph.add_edge("parser", "entity_extractor")
    graph.add_edge("entity_extractor", "relation_extractor")
    graph.add_edge("relation_extractor", "fact_extractor")
    graph.add_edge("fact_extractor", "validator")
    graph.add_edge("validator", "merger")
    graph.add_edge("merger", END)

    return graph.compile()
