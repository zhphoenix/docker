"""Retrieve Node - 语义检索（Embedding + Qdrant）"""

import logging
import re

from schemas.state import AgentState
from schemas.authority import get_authority_level
from tools.embedding import embedding_tool
from tools.qdrant import qdrant_tool, Filter, FieldCondition, MatchValue, Range

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

    # 使用改写后的 query（由 query_rewrite Node 生成），回退到原始 question
    search_query = plan.get("rewritten_query", question)

    # 确定检索参数
    # 市场检测：关键词检测优先于 Planner 输出（Planner 常误判 hk→cn）
    detected_market = _detect_market(question)
    planner_market = _normalize_market(plan.get("market")) if plan.get("market") else None
    if detected_market != "cn":
        # 关键词明确指向 hk/us，以检测结果为准
        market = detected_market
    else:
        # 关键词未检测到明确市场，信任 Planner
        market = planner_market or "cn"
    symbol = _normalize_symbol(plan.get("symbol"), market) if plan.get("symbol") else None
    year = plan.get("year")
    document_type = plan.get("document_type")
    time_range_data = plan.get("time_range")

    logger.info("Retrieve: searching for market=%s, symbol=%s, query='%s'", market, symbol, search_query[:50])

    # 1. Embedding 向量化（使用改写后的 query）
    vectors = await embedding_tool.embed([search_query])
    vector = vectors[0]

    # 2. 构建过滤条件（含时效过滤）
    query_filter = _build_filter(market, symbol, year, document_type, time_range_data)

    # 3. Qdrant 检索
    collection = f"documents_{market}"
    results = await qdrant_tool.search(
        collection=collection,
        vector=vector,
        limit=10,
        query_filter=query_filter,
    )

    # 4. 回退策略：如果带 filter 返回 0 结果，去掉 symbol filter 重试
    if not results and symbol:
        logger.info("Retrieve: 0 results with filters, retrying without symbol filter")
        fallback_filter = _build_filter(market, None, year, document_type, time_range_data)
        results = await qdrant_tool.search(
            collection=collection,
            vector=vector,
            limit=10,
            query_filter=fallback_filter,
        )

    # 5. 二次回退：如果仍为 0，去掉所有 filter 只保留 market
    if not results:
        logger.info("Retrieve: 0 results with market=%s, retrying without filters", market)
        results = await qdrant_tool.search(
            collection=collection,
            vector=vector,
            limit=10,
            query_filter=None,
        )

    # 6. 格式化文档 + 权威度标注
    documents = [
        {
            "content": r["payload"].get("content", ""),
            "score": r["score"],
            "source": f"{r['payload'].get('symbol', '')}/{r['payload'].get('year', '')}",
            "market": r["payload"].get("market", market),
            "symbol": r["payload"].get("symbol", symbol),
            "year": r["payload"].get("year"),
            "page_start": r["payload"].get("page_start"),
            "page_end": r["payload"].get("page_end"),
            "authority": get_authority_level(
                r["payload"].get("source_provider", "_default")
            ),
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
    time_range: dict = None,
) -> Filter | None:
    """构建 Qdrant 过滤条件

    Args:
        market: 市场代码
        symbol: 股票代码
        year: 年份
        document_type: 文档类型
        time_range: 时效过滤 {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}
    """
    conditions = []

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

    # 时效过滤：优先用 published_date（天级精度），回退到 year
    if time_range:
        start_date = time_range.get("start_date")
        end_date = time_range.get("end_date")
        if start_date:
            conditions.append(
                FieldCondition(key="published_date", range=Range(gte=str(start_date)))
            )
        if end_date:
            conditions.append(
                FieldCondition(key="published_date", range=Range(lte=str(end_date)))
            )

    if not conditions:
        return None

    return Filter(must=conditions)


def _detect_market(question: str) -> str:
    """根据查询关键词自动推断市场

    优先级：显式指定 > 关键词匹配 > 默认 cn
    """
    q = question.lower()

    # 港股关键词
    hk_keywords = [
        "港股", "hk", "hong kong", "联交所", "00700", "09988", "09618",
        "腾讯控股", "腾讯", "阿里巴巴－Ｗ", "京东", "百度", "美团", "小米集团",
        "网易", "携程", "理想汽车", "蔚来", "小鹏", "快手",
    ]
    # 美股关键词
    us_keywords = [
        "美股", "nasdaq", "nyse", "aapl", "nvda", "tsla", "msft",
        "googl", "meta", "amzn", "apple", "nvidia", "tesla", "microsoft",
    ]

    for kw in hk_keywords:
        if kw in q:
            logger.info("Detect market: hk (keyword=%s)", kw)
            return "hk"
    for kw in us_keywords:
        if kw in q:
            logger.info("Detect market: us (keyword=%s)", kw)
            return "us"

    return "cn"


def _normalize_market(raw: str) -> str:
    """标准化市场代码（处理 LLM 输出中文的情况）

    支持输入："港股"/"hk"/"HK" → "hk"，"A股"/"cn"/"cn" → "cn"，"美股"/"us" → "us"
    """
    if not raw:
        return "cn"
    r = raw.strip().lower()
    if r in ("cn", "hk", "us"):
        return r
    if r in ("港股", "香港", "h股"):
        return "hk"
    if r in ("a股", "大陆", "中国", "内地", "沪深"):
        return "cn"
    if r in ("美股", "美国"):
        return "us"
    return "cn"


def _normalize_symbol(raw: str, market: str = "cn") -> str | None:
    """标准化股票代码

    支持输入：
      - "00700" → "00700"
      - "0700.HK" / "700.HK" → "00700" (港股)
      - "000002" → "000002" (A股)
      - "万科A" → None (无法直接转换中文名称)
      - "AAPL" → "AAPL" (美股)
    """
    if not raw:
        return None

    s = raw.strip()

    # 去除后缀 (.HK, .SS, .SZ, .SH 等)
    s = re.sub(r'\.(HK|SS|SZ|SH|hk|ss|sz|sh)$', '', s, flags=re.IGNORECASE)

    # 纯数字 → 根据市场补前导零
    if s.isdigit():
        if market == "hk":
            return s.zfill(5)  # 港股 5 位
        elif market == "cn":
            return s.zfill(6)  # A股 6 位
        else:
            return s

    # 美股 ticker（纯字母）
    if s.isalpha():
        return s.upper()

    # 中文名称（无法直接匹配）
    return None
