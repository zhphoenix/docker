"""Retrieve Node - 语义检索（Embedding + Qdrant）"""

import logging

from schemas.state import AgentState
from tools.embedding import embedding_tool
from tools.qdrant import qdrant_tool
from qdrant_client.models import Filter, FieldCondition, MatchValue

logger = logging.getLogger(__name__)


async def retrieve(state: AgentState) -> dict:
    """语义检索

    1. 从 plan 提取检索查询
    2. 调用 Embedding 服务向量化
    3. 调用 Qdrant 检索 Top-K
    4. 写入 state["documents"]
    """
    question = state["question"]
    plan = state.get("plan", {})

    # 确定检索参数
    market = plan.get("market", "cn")
    symbol = plan.get("symbol")
    year = plan.get("year")
    document_type = plan.get("document_type")

    logger.info("Retrieve: searching for market=%s, symbol=%s", market, symbol)

    # 1. Embedding 向量化
    vectors = await embedding_tool.embed([question])
    vector = vectors[0]

    # 2. 构建过滤条件
    query_filter = _build_filter(market, symbol, year, document_type)

    # 3. Qdrant 检索
    collection = f"documents_{market}"
    results = await qdrant_tool.search(
        collection=collection,
        vector=vector,
        limit=10,
        query_filter=query_filter,
    )

    # 4. 格式化文档
    documents = [
        {
            "content": r["payload"].get("content", ""),
            "score": r["score"],
            "source": r["payload"].get("source", ""),
            "market": r["payload"].get("market", market),
            "symbol": r["payload"].get("symbol", symbol),
            "year": r["payload"].get("year"),
            "page_start": r["payload"].get("page_start"),
            "page_end": r["payload"].get("page_end"),
        }
        for r in results
    ]

    logger.info("Retrieve: found %d documents", len(documents))

    return {"documents": documents}


def _build_filter(
    market: str = None,
    symbol: str = None,
    year: int = None,
    document_type: str = None,
) -> Filter | None:
    """构建 Qdrant 过滤条件"""
    conditions = []

    if market:
        conditions.append(
            FieldCondition(key="market", match=MatchValue(value=market))
        )
    if symbol:
        conditions.append(
            FieldCondition(key="symbol", match=MatchValue(value=symbol))
        )
    if year:
        conditions.append(
            FieldCondition(key="year", match=MatchValue(value=year))
        )
    if document_type:
        conditions.append(
            FieldCondition(key="document_type", match=MatchValue(value=document_type))
        )

    if not conditions:
        return None

    return Filter(must=conditions)
