"""Agent Dispatcher - 基于策略配置的 Agent 路由

路由优先级：
  1. 请求中显式指定 model/agent
  2. policies.yaml 中的 routing.rules 正则匹配
  3. 默认 fallback agent (chat)
"""

import importlib
import re
import logging
import threading
import time
from pathlib import Path

from schemas.chat import ChatRequest
from agents.base_agent import BaseAgent
from agents.chat_agent import ChatAgent
from config.policy_loader import (
    get_routing_rules,
    get_policy,
    get_agents_registry,
    AGENTS_FILE,
    POLICIES_FILE,
)

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


# ---- 热更新（AC-P4-1）----
_WATCH_INTERVAL = 5.0  # 后台监听轮询间隔（秒）
_watcher_started = False
_watcher_stop = threading.Event()
_watcher_thread: threading.Thread | None = None
_watched_mtimes: dict[str, float] = {}


def _snapshot_mtimes() -> dict[str, float]:
    """快照配置文件 mtime（文件缺失自动跳过）"""
    snap: dict[str, float] = {}
    for path in (AGENTS_FILE, POLICIES_FILE):
        try:
            if path.exists():
                snap[str(path)] = path.stat().st_mtime
        except OSError:
            pass
    return snap


def reload_agent_registry() -> dict[str, type[BaseAgent]]:
    """热更新 Agent 注册表：重建 AGENT_REGISTRY（无服务重启）

    - 重新读取 agents.yaml 并 importlib 导入最新 Agent 类
    - 原地替换（clear + update）：保证所有 `from services.router import
      AGENT_REGISTRY` 的引用方指向同一 dict 对象，新请求立即路由到新配置
    - 不断开在途请求：dispatch_agent 每次调用 AGENT_REGISTRY[name]() 实例化
      全新 Agent 对象，在途请求持有既有实例，不受注册表替换影响
    """
    global AGENT_REGISTRY, _watched_mtimes
    logger.info("Reloading agent registry from agents.yaml ...")
    new_registry = _build_agent_registry()
    AGENT_REGISTRY.clear()
    AGENT_REGISTRY.update(new_registry)
    _watched_mtimes = _snapshot_mtimes()
    logger.info("Agent registry hot-reloaded: %d agents available", len(AGENT_REGISTRY))
    return AGENT_REGISTRY


def _watch_loop(stop_event: threading.Event) -> None:
    """后台监听 agents.yaml / policies.yaml 变化，变更时自动热更新"""
    global _watched_mtimes
    _watched_mtimes = _watched_mtimes or _snapshot_mtimes()
    while not stop_event.is_set():
        try:
            for path, mtime in _snapshot_mtimes().items():
                if _watched_mtimes.get(path) != mtime:
                    logger.info("Config file '%s' changed, hot-reloading registry", path)
                    reload_agent_registry()
                    break
        except Exception as e:
            logger.warning("Agent config watcher error: %s", e)
        stop_event.wait(_WATCH_INTERVAL)


def start_agent_watcher() -> None:
    """启动 Agent 配置监听线程（幂等）"""
    global _watcher_thread, _watcher_started
    if _watcher_started:
        return
    _watcher_started = True
    _watcher_stop.clear()
    _watcher_thread = threading.Thread(
        target=_watch_loop,
        args=(_watcher_stop,),
        name="agent-config-watcher",
        daemon=True,
    )
    _watcher_thread.start()
    logger.info("Agent config watcher started (interval=%.1fs)", _WATCH_INTERVAL)


def stop_agent_watcher() -> None:
    """停止 Agent 配置监听线程"""
    global _watcher_started
    _watcher_stop.set()
    _watcher_started = False
    logger.info("Agent config watcher stopped")


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
