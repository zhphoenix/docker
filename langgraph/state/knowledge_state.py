"""KnowledgeState 定义 - Knowledge Ingestion Agent 的数据载体

注意：不含 messages 字段（非对话型 Agent，是处理流水线）。
"""

from typing import Annotated, TypedDict
import operator


class KnowledgeState(TypedDict):
    """知识提取流水线状态

    所有 Node 只能修改 State，不直接返回结果。
    """

    # ── 输入 ──
    document_id: str
    document_type: str
    raw_text: str
    source_metadata: dict

    # ── 分片 ──
    chunks: list[dict]

    # ── 提取结果 ──
    entities: list[dict]
    relations: list[dict]
    facts: list[dict]
    evidence: list[dict]

    # ── 校验 ──
    conflicts: list[dict]
    confidence_score: float

    # ── 性能优化：Embedding 缓存（Validator 计算，Merger 复用） ──
    entity_embeddings: list[list[float]]

    # ── 存储追踪 ──
    stored_entity_ids: list[str]
    stored_fact_ids: list[str]

    # ── 控制（并行安全：fan-out 分支的错误自动累加，不覆盖） ──
    errors: Annotated[list[str], operator.add]
