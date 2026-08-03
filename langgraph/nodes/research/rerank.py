"""Rerank Node - 文档重排序节点（极简）

职责仅限于：
  读取 State → 调用 RerankerTool → 更新 State

截断、Top-K、Retry、超时等全部由 RerankerTool 处理。
"""

import logging
import time

from state.research_state import AgentState
from tools.reranker import reranker_tool

logger = logging.getLogger(__name__)


async def rerank(state: AgentState) -> dict:
    """对检索结果重排序（Fail Open）

    失败时返回原始排序，不中断 Workflow。
    """
    question = state["question"]
    documents = state.get("documents", [])

    if not documents:
        logger.warning("Rerank: skipped, documents=0")
        return {"documents": []}

    logger.info("Rerank start | documents=%d", len(documents))
    start = time.perf_counter()

    # 提取文档内容，交给 RerankerTool 处理截断/Top-K
    contents = [doc.get("content", "") for doc in documents]

    try:
        results = await reranker_tool.rerank(question, contents)
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.warning("Rerank failed | reason=%s | elapsed=%.2fs", e, elapsed)
        return {"documents": documents}

    # 映射回文档（Immutable：copy + 新列表）
    reranked: list[dict] = []
    for rank, r in enumerate(results, start=1):
        idx = r.get("index", 0)
        if 0 <= idx < len(documents):
            doc = documents[idx].copy()
            doc["rerank_score"] = r.get("relevance_score", 0.0)
            doc["rerank_rank"] = rank
            reranked.append(doc)

    # 未参与 rerank 的文档追加在后
    reranked_indices = {r.get("index", 0) for r in results}
    for i, doc in enumerate(documents):
        if i not in reranked_indices:
            reranked.append(doc.copy())

    elapsed = time.perf_counter() - start
    logger.info(
        "Rerank finished | input=%d | reranked=%d | elapsed=%.2fs",
        len(documents),
        len(reranked),
        elapsed,
    )

    return {"documents": reranked}
