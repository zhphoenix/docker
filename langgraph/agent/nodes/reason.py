"""Reason Node - LLM 推理生成回答"""

import logging

from schemas.state import AgentState
from tools.llm import llm_tool
from prompts.loader import load_prompt

logger = logging.getLogger(__name__)


async def reason(state: AgentState) -> dict:
    """LLM 推理生成回答

    1. 加载 reason prompt
    2. 构建上下文：question + documents
    3. 调用 LLM
    4. 写入 state["answer"]
    """
    question = state["question"]
    documents = state.get("documents", [])

    logger.info("Reason: generating answer with %d documents", len(documents))

    # 构建上下文
    context = _build_context(documents)

    # 根据 Agent 类型加载不同 Prompt
    agent_name = state.get("metadata", {}).get("agent", "research")
    prompt_map = {
        "investment": "investment/system",
        "chat": "chat/system",
        "knowledge": "chat/system",
    }
    prompt_name = prompt_map.get(agent_name, "reason")

    try:
        system_prompt = load_prompt(prompt_name, question=question, context=context)
    except FileNotFoundError:
        system_prompt = load_prompt("reason", question=question, context=context)

    # 调用 LLM
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]
    result = await llm_tool.chat(messages, temperature=0.7, max_tokens=4096)
    logger.info("LLM response type: %s, keys: %s", type(result), list(result.keys()) if isinstance(result, dict) else "N/A")
    answer = result["choices"][0]["message"]["content"]

    # 提取 token 用量
    usage = result.get("usage", {})
    metadata = state.get("metadata", {})
    metadata.update({
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    })

    logger.info("Reason: answer generated (%d chars, %d tokens)", len(answer), usage.get("total_tokens", 0))

    return {"answer": answer, "metadata": metadata}


def _build_context(documents: list[dict]) -> str:
    """将文档列表构建为上下文字符串"""
    if not documents:
        return "（无检索结果）"

    parts = []
    for i, doc in enumerate(documents, 1):
        symbol = doc.get("symbol", "")
        year = doc.get("year", "")
        market = doc.get("market", "")
        source = f"{symbol}/{year}" if symbol else (market or "unknown")
        content = doc.get("content", "")
        parts.append(f"[文档 {i}] 来源: {source}\n{content}")

    return "\n\n---\n\n".join(parts)
