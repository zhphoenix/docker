"""Agent Dispatcher - 基于策略配置的 Agent 路由

路由优先级：
  1. 请求中显式指定 model/agent
  2. policies.yaml 中的 routing.rules 正则匹配
  3. 默认 fallback agent (chat)
"""

import re
import logging

from schemas.chat import ChatRequest
from agents.base_agent import BaseAgent
from agents.chat_agent import ChatAgent
from agents.research_agent import ResearchAgent
from agents.kb_agent import KBAgent
from agents.investment_agent import InvestmentAgent
from config.policy_loader import get_routing_rules, get_policy

logger = logging.getLogger(__name__)

# Agent 注册表
AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "chat": ChatAgent,
    "research": ResearchAgent,
    "kb": KBAgent,
    "investment": InvestmentAgent,
}


def dispatch_agent(request: ChatRequest) -> BaseAgent:
    """根据请求选择 Agent

    路由策略：
      1. 如果 model 字段指定了 agent 名称，直接使用
      2. 按 policies.yaml 中的 routing.rules 优先级匹配
      3. 回退到默认 agent
    """
    # 策略 1: 显式指定
    if request.model and request.model in AGENT_REGISTRY:
        logger.info("Dispatch: explicit model='%s'", request.model)
        return AGENT_REGISTRY[request.model]()

    # 策略 2: 规则匹配
    last_message = request.messages[-1].content if request.messages else ""
    rules = get_routing_rules()

    # 按 priority 降序排列
    sorted_rules = sorted(rules, key=lambda r: r.get("priority", 0), reverse=True)

    for rule in sorted_rules:
        pattern = rule.get("pattern", "")
        agent_name = rule.get("agent", "chat")
        if pattern and re.search(pattern, last_message):
            if agent_name in AGENT_REGISTRY:
                logger.info("Dispatch: rule matched pattern='%s' → %s", pattern, agent_name)
                return AGENT_REGISTRY[agent_name]()

    # 策略 3: 默认
    default = get_policy("routing.default_agent", "chat")
    logger.info("Dispatch: default → %s", default)
    return AGENT_REGISTRY.get(default, ChatAgent)()


def list_agents() -> list[dict[str, str]]:
    """列出所有可用 Agent"""
    return [
        {"id": name, "name": f"AI-Platform/{name}", "description": cls.__doc__ or ""}
        for name, cls in AGENT_REGISTRY.items()
    ]
