"""Chat Agent - 简单问答 + RAG"""

from agents.base_agent import BaseAgent
from graph.builder import get_chat_graph


class ChatAgent(BaseAgent):
    """简单问答 Agent

    Workflow: Retrieve → Rerank → Reason → Finish
    """

    def __init__(self):
        super().__init__(
            graph=get_chat_graph(),
            agent_name="chat",
        )
