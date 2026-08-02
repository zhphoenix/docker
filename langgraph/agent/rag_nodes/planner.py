"""Planner Node - 理解用户问题，生成执行计划"""

import json
import logging

from langchain_core.messages import SystemMessage, HumanMessage

from schemas.state import AgentState
from tools.llm import llm_tool
from prompts.loader import load_prompt

logger = logging.getLogger(__name__)


async def planner(state: AgentState) -> dict:
    """生成执行计划

    1. 加载 planner prompt
    2. 调用 LLM 分析问题
    3. 解析输出为 plan dict
    4. 写入 state["plan"]
    """
    question = state["question"]
    logger.info("Planner: analyzing question: %s", question[:100])

    # 加载 prompt
    system_prompt = load_prompt("planner")

    # 调用 LLM
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]
    result = await llm_tool.chat(messages, temperature=0.3)
    response = result["choices"][0]["message"]["content"]

    # 解析 plan（尝试 JSON 解析）
    try:
        # 尝试从 response 中提取 JSON
        plan = _extract_json(response)
    except (json.JSONDecodeError, ValueError):
        # 如果解析失败，使用默认 plan
        logger.warning("Planner: failed to parse plan, using default")
        plan = {
            "steps": [question],
            "tools": ["qdrant"],
        }

    logger.info("Planner: plan generated with %d steps", len(plan.get("steps", [])))

    return {
        "plan": plan,
        "messages": [
            SystemMessage(content=system_prompt),
            HumanMessage(content=question),
        ],
    }


def _extract_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 代码块
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        return json.loads(text[start:end].strip())

    # 尝试提取 { ... } 块
    start = text.index("{")
    end = text.rindex("}") + 1
    return json.loads(text[start:end])
