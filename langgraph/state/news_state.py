"""NewsState 定义 - News Intelligence Agent 的数据载体

注意：不含 messages 字段（非对话型 Agent，是处理流水线）。
"""

from typing import Annotated, TypedDict
import operator


class NewsState(TypedDict):
    """新闻智能管线状态

    所有 Node 只能修改 State，不直接返回结果。
    """

    # ── 输入 ──
    source_id: str                    # 新闻源 ID（registry/news_sources.yaml）
    raw_articles: list[dict]          # [{title, content, url, published_at, source_name}]

    # ── 处理中间态 ──
    cleaned_articles: list[dict]      # 清洗后（含 language, content_hash）
    unique_articles: list[dict]       # 去重后
    classified_articles: list[dict]   # 分类后（含 category, importance_score）

    # ── 提取结果 ──
    entities: list[dict]              # [{name, entity_type, description, confidence, article_idx}]
    events: list[dict]                # [{event_type, title, summary, entities, impact_score, article_idx}]
    relations: list[dict]             # [{source, target, relation_type, confidence, article_idx}]

    # ── 影响分析 ──
    impact_assessments: list[dict]    # [{event_idx, direction, duration, market, sector, score}]

    # ── 存储追踪 ──
    stored_article_ids: list[str]
    stored_event_ids: list[str]
    knowledge_agent_triggered: bool

    # ── 控制（并行安全：fan-out 分支的错误自动累加，不覆盖） ──
    errors: Annotated[list[str], operator.add]

    # ── 跨 Agent 调用链（AC-P4-5） ──
    trace_id: str              # 本次新闻入库的调用链标识，触发 knowledge_ingestion 时共享
