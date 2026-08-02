"""Reflect Node - 检查答案质量，决定是否需要重新检索"""

import json
import logging

from schemas.state import AgentState
from tools.llm import llm_tool
from prompts.loader import load_prompt

logger = logging.getLogger(__name__)


async def reflect(state: AgentState) -> dict:
    """反思检查

    1. 加载 reflect prompt
    2. 调用 LLM 评估答案质量
    3. 输出：quality(good/bad), confidence, retry_count
    4. 写入 state["reflect"]
    """
    question = state["question"]
    answer = state.get("answer", "")
    metadata = state.get("metadata", {})

    # 获取当前重试次数
    current_reflect = state.get("reflect", {})
    retry_count = current_reflect.get("retry_count", 0)

    logger.info("Reflect: evaluating answer quality (retry_count=%d)", retry_count)

    # 加载 prompt
    system_prompt = load_prompt("reflect", question=question, answer=answer)

    # 调用 LLM
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "请评估上述回答的质量。"},
    ]
    result = await llm_tool.chat(messages, temperature=0.3)
    response = result["choices"][0]["message"]["content"]

    # 解析评估结果
    try:
        reflect_result = _extract_json(response)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Reflect: failed to parse result, defaulting to good")
        reflect_result = {
            "quality": "good",
            "confidence": 0.5,
            "reason": "Failed to parse evaluation result",
        }

    # 更新 retry_count
    reflect_result["retry_count"] = retry_count + 1

    logger.info(
        "Reflect: quality=%s, confidence=%.2f",
        reflect_result.get("quality"),
        reflect_result.get("confidence", 0),
    )

    return {"reflect": reflect_result}


def _extract_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        return json.loads(text[start:end].strip())

    start = text.index("{")
    end = text.rindex("}") + 1
    return json.loads(text[start:end])
