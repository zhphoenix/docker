"""Investment Agent - 价值投资分析（大师方法论）"""

from agents.base_agent import BaseAgent
from graphs import get_research_graph


class InvestmentAgent(BaseAgent):
    """价值投资分析 Agent

    使用完整 Research Workflow（Planner → Retrieve → Rerank → Reason → Reflect → Finish），
    配合 Investment 专用 Prompt（巴菲特/芒格/费雪/林奇框架）。

    能力：
    - DCF 估值分析
    - 护城河评估
    - 排雷 24 信号检测
    - 所有者盈余计算
    - 多大师视角综合
    """

    def __init__(self):
        super().__init__(
            graph=get_research_graph(),
            agent_name="investment",
        )
