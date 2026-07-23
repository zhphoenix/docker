"""Agent Dispatcher - 根据请求选择对应 Agent"""

import logging

from schemas.chat import ChatRequest
from agents.base_agent import BaseAgent
from agents.chat_agent import ChatAgent
from agents.research_agent import ResearchAgent

logger = logging.getLogger(__name__)


def dispatch_agent(request: ChatRequest) -> BaseAgent:
    """根据请求选择 Agent

    当前为简单规则路由，未来可扩展为 LLM 路由。

    Args:
        request: Chat 请求

    Returns:
        对应的 Agent 实例
    """
    # 简单路由逻辑
    # 如果消息中包含特定关键词，路由到 Research Agent
    last_message = request.messages[-1].content if request.messages else ""

    if _is_research_task(last_message):
        logger.info("Dispatch: routing to ResearchAgent")
        return ResearchAgent()
    else:
        logger.info("Dispatch: routing to ChatAgent")
        return ChatAgent()


def _is_research_task(message: str) -> bool:
    """判断是否为研究任务

    简单关键词匹配，未来可扩展为 LLM 判断。
    """
    research_keywords = [
        "分析", "研究", "报告", "年报", "财务",
        "对比", "评估", "投资", "行业", "市场",
    ]
    return any(kw in message for kw in research_keywords)
