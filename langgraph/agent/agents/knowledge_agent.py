"""Knowledge Agent - 知识管理（Obsidian Vault 读写 + RAG 检索）"""

from agents.base_agent import BaseAgent
from graph.builder import get_knowledge_graph


class KnowledgeAgent(BaseAgent):
    """知识管理 Agent

    Workflow: Retrieve → Rerank → Reason → Knowledge → Finish

    能力：
    - RAG 检索知识库
    - 自动写入 Obsidian Vault（检测到写入意图时）
    - 索引维护（预留）
    """

    def __init__(self):
        super().__init__(
            graph=get_knowledge_graph(),
            agent_name="knowledge",
        )
