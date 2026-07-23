"""Research Agent - 研究分析（年报、行业）"""

from agents.base_agent import BaseAgent
from graph.builder import get_research_graph


class ResearchAgent(BaseAgent):
    """研究分析 Agent

    完整 Workflow: Planner → Retrieve → Rerank → Reason → Reflect → Finish
    支持反思和重试机制。
    """

    def __init__(self):
        super().__init__(
            graph=get_research_graph(),
            agent_name="research",
        )
