"""Rerank Node - 对检索结果重排序"""

import logging

from schemas.state import AgentState
from tools.reranker import reranker_tool

logger = logging.getLogger(__name__)


async def rerank(state: AgentState) -> dict:
    """对检索结果重排序

    1. 获取 state["documents"]
    2. 调用 Reranker 服务
    3. 按相关性重新排序
    4. 更新 state["documents"]
    """
    question = state["question"]
    documents = state.get("documents", [])

    if not documents:
        logger.warning("Rerank: no documents to rerank")
        return {"documents": []}

    logger.info("Rerank: reranking %d documents", len(documents))

    # 提取文档内容
    contents = [doc.get("content", "") for doc in documents]

    # 调用 Reranker
    results = await reranker_tool.rerank(question, contents)

    # 根据 reranker 结果重新排序
    reranked = []
    for r in results:
        idx = r.get("index", 0)
        if 0 <= idx < len(documents):
            doc = documents[idx].copy()
            doc["rerank_score"] = r.get("relevance_score", 0.0)
            reranked.append(doc)

    logger.info("Rerank: reranked %d documents", len(reranked))

    return {"documents": reranked}
