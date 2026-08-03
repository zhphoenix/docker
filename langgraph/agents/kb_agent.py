"""KB Agent - 知识库管理（RAG 检索）"""

from agents.base_agent import BaseAgent
from graphs import get_kb_graph


class KBAgent(BaseAgent):
    """知识库 Agent

    Workflow: Retrieve → Rerank → Reason → Finish

    能力：
    - RAG 检索知识库
    - 索引维护（预留）
    """

    def __init__(self):
        super().__init__(
            graph=get_kb_graph(),
            agent_name="kb",
        )
