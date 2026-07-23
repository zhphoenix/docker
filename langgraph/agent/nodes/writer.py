"""Writer Node - 格式化最终输出（可选）"""

import logging

from schemas.state import AgentState

logger = logging.getLogger(__name__)


async def writer(state: AgentState) -> dict:
    """格式化最终输出

    用于复杂报告生成场景，对 answer 进行格式化。
    当前为简单透传，未来可扩展为调用 LLM 格式化。
    """
    answer = state.get("answer", "")

    logger.info("Writer: formatting answer (%d chars)", len(answer))

    # 当前简单实现：直接透传
    # 未来可扩展为调用 writer prompt + LLM 格式化
    return {"answer": answer}
