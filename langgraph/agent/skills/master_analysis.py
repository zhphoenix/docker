"""Master Analysis Skill - 投资大师分析框架

封装巴菲特/芒格/费雪/林奇方法论，结合 RAG 检索生成结构化分析报告。
"""

import logging
from typing import Any

from skills.base_skill import BaseSkill
from skills.rag_search import RAGSearchSkill
from tools.llm import llm_tool
from prompts.loader import load_prompt

logger = logging.getLogger(__name__)

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
        return "运用巴菲特/芒格/费雪/林奇方法论，基于年报数据生成投资分析报告"

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
            query: 分析问题（如"腾讯控股的护城河分析"）
            symbol: 股票代码（如"00700"）
            market: 市场（cn/hk/us，默认 cn）
            dimension: 分析维度（moat/financial/risk/valuation/growth/comprehensive）
            year: 年报年份（可选）
            top_k: 检索文档数（默认 10）
        """
        query = kwargs.get("query", "")
        symbol = kwargs.get("symbol")
        market = kwargs.get("market", "cn")
        dimension = kwargs.get("dimension", "comprehensive")
        year = kwargs.get("year")
        top_k = kwargs.get("top_k", 10)

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

            # 3. 构建分析 Prompt
            system_prompt = load_prompt("investment/system")
            analysis_instruction = (
                f"## 分析任务\n"
                f"分析维度：{dim_desc}\n"
                f"分析对象：{query}\n\n"
                f"## 检索到的年报数据\n{context}\n\n"
                f"请基于以上数据，运用投资大师方法论进行深入的{dim_desc}。"
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
