"""Finish Node - 结束处理，准备返回"""

import logging

from langchain_core.messages import AIMessage

from schemas.state import AgentState

logger = logging.getLogger(__name__)


async def finish(state: AgentState) -> dict:
    """结束处理

    1. 将最终 answer 写入 messages
    2. 返回 State 更新
    """
    answer = state.get("answer", "")

    logger.info("Finish: completing with answer (%d chars)", len(answer))

    return {
        "messages": [AIMessage(content=answer)],
    }
