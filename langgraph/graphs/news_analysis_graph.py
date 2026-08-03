"""News Intelligence Agent Graph - LangGraph StateGraph 定义

流水线: Cleaner → Deduplicator → EmbeddingDedup → Classifier → [Entity || Event] → Impact → Publisher → END
性能优化: Classifier 完成后 Entity/Event 并行执行（fan-out/fan-in）
DLM: EmbeddingDedup 实现跨批次语义去重（similarity > 0.92）
"""

import logging
import time
from functools import wraps

from langgraph.graph import StateGraph, START, END

from state.news_state import NewsState
from nodes.news.cleaner import news_cleaner
from nodes.news.deduplicator import news_deduplicator
from nodes.news.embedding_dedup import embedding_dedup
from nodes.news.classifier import news_classifier
from nodes.news.entity import news_entity_extractor
from nodes.news.event import news_event_extractor
from nodes.news.impact import news_impact_analyzer
from nodes.news.publisher import news_publisher

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
                "[Perf] news.%s: %.2fs | source=%s | articles=%d",
                node_name, elapsed,
                state.get("source_id", "?"),
                len(state.get("raw_articles", [])),
            )
            return result
        return wrapper
    return decorator


def build_news_intelligence_graph():
    """构建 News Intelligence Agent 的 Workflow

    Cleaner → Deduplicator → Classifier → [EntityExtractor || EventExtractor]
    → ImpactAnalyzer → Publisher → END

    性能优化：Entity 和 Event 提取并行执行（fan-out/fan-in），
    两者都依赖 classified_articles，但彼此无数据依赖。
    """
    graph = StateGraph(NewsState)

    # 添加节点（带计时）
    graph.add_node("cleaner", _timed("cleaner")(news_cleaner))
    graph.add_node("deduplicator", _timed("deduplicator")(news_deduplicator))
    graph.add_node("embedding_dedup", _timed("embedding_dedup")(embedding_dedup))
    graph.add_node("classifier", _timed("classifier")(news_classifier))
    graph.add_node("entity_extractor", _timed("entity_extractor")(news_entity_extractor))
    graph.add_node("event_extractor", _timed("event_extractor")(news_event_extractor))
    graph.add_node("impact_analyzer", _timed("impact_analyzer")(news_impact_analyzer))
    graph.add_node("publisher", _timed("publisher")(news_publisher))

    # 边：入口 → Cleaner → Deduplicator → EmbeddingDedup → Classifier
    graph.add_edge(START, "cleaner")
    graph.add_edge("cleaner", "deduplicator")
    graph.add_edge("deduplicator", "embedding_dedup")
    graph.add_edge("embedding_dedup", "classifier")

    # Fan-out: Classifier 完成后，Entity 和 Event 并行执行
    graph.add_edge("classifier", "entity_extractor")
    graph.add_edge("classifier", "event_extractor")

    # Fan-in: 两者都完成后进入 Impact Analyzer
    graph.add_edge("entity_extractor", "impact_analyzer")
    graph.add_edge("event_extractor", "impact_analyzer")

    # Impact → Publisher → END
    graph.add_edge("impact_analyzer", "publisher")
    graph.add_edge("publisher", END)

    return graph.compile()


# 模块级缓存（避免每次调度都重新编译）
_cached_graph = None


def get_news_graph():
    """获取缓存的 News Intelligence Graph（单次编译）"""
    global _cached_graph
    if _cached_graph is None:
        _cached_graph = build_news_intelligence_graph()
    return _cached_graph
