"""Knowledge Agent - 知识管理（Obsidian 读写，预留）"""

from agents.base_agent import BaseAgent
from graph.builder import get_chat_graph


class KnowledgeAgent(BaseAgent):
    """知识管理 Agent（预留）

    未来将集成 Obsidian MCP 读写，
    当前使用 Chat Graph 作为占位。
    """

    def __init__(self):
        super().__init__(
            graph=get_chat_graph(),
            agent_name="knowledge",
        )
