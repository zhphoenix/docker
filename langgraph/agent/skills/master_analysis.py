"""Master Analysis Skill - 投资大师分析框架

封装巴菲特/芒格/费雪/林奇方法论，结合 RAG 检索 + 电话会议记录
生成结构化投资分析报告。
"""

import logging
from pathlib import Path
from typing import Any

from skills.base_skill import BaseSkill
from skills.rag_search import RAGSearchSkill
from tools.llm import llm_tool
from prompts.loader import load_prompt

logger = logging.getLogger(__name__)

# 电话会议记录存放目录
EARNINGS_CALLS_DIR = Path("files/earnings_calls")

# 分析维度
ANALYSIS_DIMENSIONS = {
    "moat": "护城河分析（网络效应、规模经济、品牌、转换成本、数据壁垒）",
    "financial": "财务健康度（所有者盈余、ROIC、FCF、负债率）",
    "risk": "排雷分析（24 信号检测：应收/存货/现金流/商誉/关联交易）",
    "valuation": "估值分析（DCF、PEG、安全边际）",
    "growth": "成长性分析（费雪 15 点、市场空间、竞争格局）",
    "comprehensive": "综合大师分析（巴菲特+芒格+费雪+林奇多视角）",
}


class MasterAnalysisSkill(BaseSkill):
    """投资大师分析 Skill

    结合 RAG 检索 + LLM 推理，运用大师方法论生成分析报告。
    """

    @property
    def name(self) -> str:
        return "master_analysis"

    @property
    def description(self) -> str:
        return "运用巴菲特/芒格/费雪/林奇方法论，基于年报 + 电话会议记录生成投资分析报告"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def tags(self) -> list[str]:
        return ["investment", "analysis", "value-investing", "master"]

    def __init__(self):
        self._rag = RAGSearchSkill()

    def validate_params(self, **kwargs) -> list[str]:
        errors = []
        if not kwargs.get("query") and not kwargs.get("symbol"):
            errors.append("Either 'query' or 'symbol' is required")
        dimension = kwargs.get("dimension", "comprehensive")
        if dimension not in ANALYSIS_DIMENSIONS:
            errors.append(
                f"Invalid dimension '{dimension}'. "
                f"Choose from: {', '.join(ANALYSIS_DIMENSIONS.keys())}"
            )
        return errors

    async def execute(self, **kwargs) -> dict[str, Any]:
        """执行大师分析
    
        Args:
            query: 分析问题（如“腾讯控股的护城河分析”）
            symbol: 股票代码（如“00700”）
            market: 市场（cn/hk/us，默认 cn）
            dimension: 分析维度（moat/financial/risk/valuation/growth/comprehensive）
            year: 年报年份（可选）
            top_k: 检索文档数（默认 10）
            with_earnings_call: 是否包含电话会议分析（默认 True，有数据时自动启用）
        """
        query = kwargs.get("query", "")
        symbol = kwargs.get("symbol")
        market = kwargs.get("market", "cn")
        dimension = kwargs.get("dimension", "comprehensive")
        year = kwargs.get("year")
        top_k = kwargs.get("top_k", 10)
        with_earnings_call = kwargs.get("with_earnings_call", True)

        # 构建查询
        if not query and symbol:
            dim_desc = ANALYSIS_DIMENSIONS.get(dimension, "综合分析")
            query = f"{symbol} {dim_desc}"

        logger.info(
            "MasterAnalysis: query='%s', market=%s, symbol=%s, dimension=%s",
            query, market, symbol, dimension,
        )

        try:
            # 1. RAG 检索相关文档
            rag_result = await self._rag.execute(
                query=query,
                market=market,
                symbol=symbol,
                year=year,
                top_k=top_k,
                use_rerank=True,
            )

            if not rag_result.get("success"):
                return {"success": False, "error": f"RAG search failed: {rag_result.get('error')}"}

            documents = rag_result.get("data", [])
            if not documents:
                return {"success": False, "error": "No relevant documents found"}

            # 2. 构建上下文
            context = self._build_context(documents)
            dim_desc = ANALYSIS_DIMENSIONS.get(dimension, "综合大师分析")

            # 3. 电话会议数据收集（如有）
            earnings_call_context = ""
            if with_earnings_call and symbol:
                earnings_call_context = await self._collect_earnings_calls(
                    symbol=symbol, year=year, market=market
                )

            # 4. 构建分析 Prompt
            system_prompt = load_prompt("investment/system")
            analysis_instruction = (
                f"## 分析任务\n"
                f"分析维度：{dim_desc}\n"
                f"分析对象：{query}\n\n"
                f"## 检索到的年报数据\n{context}\n"
            )

            if earnings_call_context:
                analysis_instruction += (
                    f"\n## 电话会议记录\n{earnings_call_context}\n\n"
                    f"请结合年报数据和电话会议记录进行交叉验证分析。"
                    f"重点关注：管理层表态与年报数据的一致性、业绩指引兑现情况、Q&A中的关键信号。\n"
                )

            analysis_instruction += (
                f"\n请基于以上数据，运用投资大师方法论进行深入的{dim_desc}。"
                f"要求：定量为主、定性为辅，明确给出关键指标和结论，风险提示不可省略。"
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": analysis_instruction},
            ]

            # 4. LLM 生成分析
            answer = await llm_tool.chat(messages, temperature=0.7, max_tokens=4096)

            return {
                "success": True,
                "data": {
                    "query": query,
                    "dimension": dimension,
                    "analysis": answer,
                    "document_count": len(documents),
                    "has_earnings_call": bool(earnings_call_context),
                    "sources": [
                        {"symbol": d.get("symbol"), "year": d.get("year"), "score": d.get("score")}
                        for d in documents[:5]
                    ],
                },
            }

        except Exception as e:
            logger.exception("Master analysis failed")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _build_context(documents: list[dict]) -> str:
        """构建文档上下文"""
        parts = []
        for i, doc in enumerate(documents, 1):
            symbol = doc.get("symbol", "")
            year = doc.get("year", "")
            source = f"{symbol}/{year}" if symbol else "unknown"
            content = doc.get("content", "")[:2000]
            parts.append(f"[文档 {i}] 来源: {source}\n{content}")
        return "\n\n---\n\n".join(parts)

    async def _collect_earnings_calls(
        self, symbol: str, year: int | None, market: str
    ) -> str:
        """收集电话会议记录

        扫描 files/earnings_calls/ 目录，查找匹配的电话会议文件，
        读取并构建分析上下文。

        Args:
            symbol: 股票代码
            year: 目标年份（None 则取最新）
            market: 市场代码

        Returns:
            电话会议上下文字符串，无数据时返回空字符串
        """
        if not EARNINGS_CALLS_DIR.exists():
            logger.info("Earnings calls directory not found: %s", EARNINGS_CALLS_DIR)
            return ""

        # 查找匹配的电话会议文件
        # 命名规则: {symbol}_{company}_{year}Q{N}_earnings_call.md
        pattern = f"{symbol}_*_earnings_call.md"
        call_files = sorted(EARNINGS_CALLS_DIR.glob(pattern), reverse=True)

        if not call_files:
            logger.info("No earnings call files found for %s", symbol)
            return ""

        # 按年份过滤
        if year:
            year_files = [f for f in call_files if str(year) in f.name]
            if year_files:
                call_files = year_files

        # 取最近 2 个季度的电话会议记录
        recent_files = call_files[:2]

        parts = []
        for call_file in recent_files:
            try:
                content = call_file.read_text(encoding="utf-8")
                if len(content.strip()) < 100:
                    continue
                # 截断过长内容
                content = content[:5000]
                parts.append(f"[电话会议] {call_file.name}\n{content}")
                logger.info("Loaded earnings call: %s", call_file.name)
            except Exception as e:
                logger.warning("Failed to read earnings call %s: %s", call_file.name, e)

        if not parts:
            return ""

        logger.info("Collected %d earnings call transcripts for %s", len(parts), symbol)
        return "\n\n---\n\n".join(parts)

    async def analyze_earnings_call(self, symbol: str, year: int | None = None, market: str = "cn") -> dict[str, Any]:
        """独立电话会议分析（可单独调用）

        仅分析电话会议记录，不依赖年报 RAG 检索。

        Args:
            symbol: 股票代码
            year: 年份（可选）
            market: 市场（cn/hk/us）

        Returns:
            分析结果 dict
        """
        earnings_context = await self._collect_earnings_calls(symbol, year, market)
        if not earnings_context:
            return {
                "success": False,
                "error": f"No earnings call transcripts found for {symbol}",
            }

        try:
            system_prompt = load_prompt("earnings_call_analysis")
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"分析以下电话会议记录：\n\n{earnings_context}"},
            ]
            answer = await llm_tool.chat(messages, temperature=0.5, max_tokens=4096)
            return {
                "success": True,
                "data": {
                    "symbol": symbol,
                    "analysis": answer,
                    "transcript_count": earnings_context.count("[电话会议]"),
                },
            }
        except Exception as e:
            logger.exception("Earnings call analysis failed")
            return {"success": False, "error": str(e)}
