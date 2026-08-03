"""Agent Dispatcher - 基于策略配置的 Agent 路由

路由优先级：
  1. 请求中显式指定 model/agent
  2. policies.yaml 中的 routing.rules 正则匹配
  3. 默认 fallback agent (chat)
"""

import importlib
import re
import logging

from schemas.chat import ChatRequest
from agents.base_agent import BaseAgent
from agents.chat_agent import ChatAgent
from config.policy_loader import get_routing_rules, get_policy, get_agents_registry

logger = logging.getLogger(__name__)


def _build_agent_registry() -> dict[str, type[BaseAgent]]:
    """从 agents.yaml 声明式配置动态构建 Agent 注册表

    若配置缺失或导入失败，回退到内置默认注册表（仅 chat），
    保证服务可启动。
    """
    registry: dict[str, type[BaseAgent]] = {}
    for name, spec in get_agents_registry().items():
        module_path = spec.get("module")
        class_name = spec.get("class")
        if not module_path or not class_name:
            continue
        try:
            module = importlib.import_module(module_path)
            registry[name] = getattr(module, class_name)
        except Exception as e:
            logger.error("Failed to load agent '%s' from %s.%s: %s", name, module_path, class_name, e)

    if not registry:
        logger.warning("agents.yaml registry empty, fallback to built-in chat agent")
        registry["chat"] = ChatAgent

    # 确保 chat 始终可用（默认回退 Agent）
    if "chat" not in registry:
        registry["chat"] = ChatAgent
    return registry


# Agent 注册表（声明式配置驱动）
AGENT_REGISTRY: dict[str, type[BaseAgent]] = _build_agent_registry()


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
