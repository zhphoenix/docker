"""InvestmentResearchSkill - 投资研究高级数据收集（编排层）

合规要点:
  - 市场路由、数据聚合等业务逻辑在 Skill 层实现（不在 Tool 层）
  - Tool 层只做纯 SDK 调用
  - 聚合 RAGSearchSkill + FinancialDataTool 的能力

四大能力:
  1. 结构化数据卡片（股价、汇率）
  2. 权威度分级过滤
  3. 时效过滤
  4. Query 改写（由 query_rewrite Node 完成，本 Skill 消费结果）
"""

import logging
from datetime import datetime, timezone
from typing import Any

from skills.base_skill import BaseSkill
from skills.rag_search import RAGSearchSkill
from tools.financial_data import financial_data_tool
from schemas.financial import StockPriceCard, ExchangeRateCard

logger = logging.getLogger(__name__)


class InvestmentResearchSkill(BaseSkill):
    """投资研究高级数据收集 Skill（编排层）

    聚合四大能力。业务逻辑（市场路由、数据格式转换）在此层实现，
    Tool 层只做纯 SDK 调用。
    """

    @property
    def name(self) -> str:
        return "investment_research"

    @property
    def description(self) -> str:
        return "投资研究高级数据收集：结构化金融卡片 + 权威度过滤 + 时效过滤 + RAG 检索"

    @property
    def tags(self) -> list[str]:
        return ["investment", "research", "financial-data", "advanced-search"]

    def __init__(self):
        self._financial = financial_data_tool  # Tool: 纯 SDK 封装
        self._rag = RAGSearchSkill()           # Skill: 带过滤的 RAG

    async def execute(self, **kwargs) -> dict[str, Any]:
        """执行投资研究数据收集

        Args:
            query: 查询文本（必填）
            market: 市场代码（cn/hk/us，默认 cn）
            symbol: 股票代码（可选）
            top_k: RAG 返回数量（默认 5）
            min_authority: 最低权威度（可选，如 "very_high"）
            time_range: 时效过滤（可选，如 {"start_date": "2025-01-01"}）
            need_financial_card: 是否需要实时行情卡片（默认 False）
            need_exchange_rate: 是否需要汇率卡片（默认 False）
            base_currency: 基础货币（默认 USD）
            target_currency: 目标货币（默认 CNY）
        """
        market = kwargs.get("market", "cn")
        symbol = kwargs.get("symbol")
        query = kwargs.get("query", "")

        result_data: dict[str, Any] = {
            "documents": [],
            "financial_card": None,
            "exchange_card": None,
        }

        # 1. RAG 检索（带权威度 + 时效过滤）
        try:
            rag_result = await self._rag.execute(
                query=query,
                market=market,
                symbol=symbol,
                min_authority=kwargs.get("min_authority"),
                time_range=kwargs.get("time_range"),
                top_k=kwargs.get("top_k", 5),
            )
            if rag_result.get("success"):
                result_data["documents"] = rag_result.get("data", [])
            else:
                logger.warning("RAG search failed: %s", rag_result.get("error"))
        except Exception as e:
            logger.exception("RAG search error")

        # 2. 实时金融数据卡片（市场路由 -- 业务逻辑在 Skill 层）
        need_card = kwargs.get("need_financial_card", False)
        if need_card and symbol:
            financial_card = await self._get_stock_card(market, symbol)
            if financial_card:
                result_data["financial_card"] = financial_card

        # 3. 汇率卡片
        need_fx = kwargs.get("need_exchange_rate", False)
        if need_fx:
            exchange_card = await self._get_exchange_card(
                kwargs.get("base_currency", "USD"),
                kwargs.get("target_currency", "CNY"),
            )
            if exchange_card:
                result_data["exchange_card"] = exchange_card

        return {
            "success": True,
            "data": result_data,
        }

    async def _get_stock_card(self, market: str, symbol: str) -> dict | None:
        """获取股票行情卡片（市场路由逻辑）"""
        try:
            if market == "cn":
                raw = await self._financial.get_cn_stock_quote(symbol)
            elif market == "hk":
                raw = await self._financial.get_hk_stock_quote(symbol)
            else:
                raw = await self._financial.get_us_stock_quote(symbol)

            if "error" in raw:
                logger.warning("Stock quote error: %s", raw["error"])
                return None

            # 计算 change_pct（yfinance 未提供）
            change_pct = raw.get("change_pct", 0)
            if not change_pct and raw.get("price") and raw.get("change"):
                prev = raw["price"] - raw["change"]
                if prev:
                    change_pct = round(raw["change"] / prev * 100, 2)

            card = StockPriceCard(
                symbol=raw.get("symbol", symbol),
                name=raw.get("name", ""),
                price=raw.get("price", 0),
                change=raw.get("change", 0),
                change_pct=change_pct,
                market_status="closed",  # 默认休市，可后续扩展判断
                updated_at=datetime.now(timezone.utc),
                source=raw.get("source", "unknown"),
            )
            return card.model_dump()
        except Exception as e:
            logger.exception("Failed to get stock card for %s/%s", market, symbol)
            return None

    async def _get_exchange_card(self, base: str, target: str) -> dict | None:
        """获取汇率卡片"""
        try:
            raw = await self._financial.get_forex_rate(base, target)
            if "error" in raw:
                logger.warning("Forex rate error: %s", raw["error"])
                return None

            card = ExchangeRateCard(
                base_currency=raw.get("base_currency", base),
                target_currency=raw.get("target_currency", target),
                rate=raw.get("rate", 0),
                inverse_rate=raw.get("inverse_rate", 0),
                updated_at=datetime.now(timezone.utc),
                source=raw.get("source", "unknown"),
            )
            return card.model_dump()
        except Exception as e:
            logger.exception("Failed to get exchange card for %s/%s", base, target)
            return None
