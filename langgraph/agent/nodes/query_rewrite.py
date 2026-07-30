"""QueryRewrite Node - 查询改写（LLM 驱动）

合规要点（08_Node设计.md）:
  - Query 改写是业务逻辑（Prompt 编排 + LLM 调用 + 结果解析），属于 Node 层职责
  - 调用 llm_tool（基础设施）完成改写，Tool 层不含改写逻辑
  - 单一职责：只负责改写，不负责检索

流程位置:
  Planner → QueryRewrite → Retrieve → Rerank → Reason → Reflect → Finish
"""

import json
import logging

from langchain_core.messages import SystemMessage, HumanMessage

from schemas.state import AgentState
from tools.llm import llm_tool
from prompts.loader import load_prompt

logger = logging.getLogger(__name__)


async def query_rewrite(state: AgentState) -> dict:
    """查询改写节点

    职责：将用户自然语言转化为专业金融检索词。
    调用 llm_tool（基础设施）完成改写。

    输入: state["question"], state["plan"]
    输出: 更新 state["plan"] 中的检索参数
    """
    question = state["question"]
    plan = state.get("plan", {})

    # 检查是否启用改写（可通过 plan 关闭）
    enable_rewrite = plan.get("enable_rewrite", True)
    if not enable_rewrite:
        logger.info("QueryRewrite: disabled by plan, skipping")
        return {"plan": plan}

    vertical_params = plan.get("vertical_params")
    market = plan.get("market", "cn")

    # 构建 Prompt
    system_prompt = load_prompt("query_rewrite")
    user_content = f"原始查询: {question}\n市场: {market}"
    if vertical_params:
        user_content += f"\n垂类参数: {json.dumps(vertical_params, ensure_ascii=False)}"

    # 调用 LLM (通过 llm_tool -- 基础设施)
    try:
        result = await llm_tool.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )
        response = result["choices"][0]["message"]["content"]

        # 解析改写结果
        rewritten = _extract_json(response)
    except Exception as e:
        logger.warning("QueryRewrite: LLM failed (%s), using original query", e)
        rewritten = {"rewritten_query": question, "keywords": []}

    # 更新 plan 中的检索参数
    plan["rewritten_query"] = rewritten.get("rewritten_query", question)
    plan["keywords"] = rewritten.get("keywords", [])
    if rewritten.get("suggested_filters"):
        # 只合并检索相关参数，不覆盖已有值
        for key in ("time_range", "document_type", "symbol"):
            if key not in plan and key in rewritten["suggested_filters"]:
                plan[key] = rewritten["suggested_filters"][key]

    logger.info(
        "QueryRewrite: '%s' -> '%s'",
        question[:50],
        plan["rewritten_query"][:50],
    )

    return {
        "plan": plan,
        "messages": [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
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
        try:
            return json.loads(text[start:end].strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # 尝试提取 { ... } 块
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return {"rewritten_query": "", "keywords": []}
