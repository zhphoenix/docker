"""Knowledge Node - Obsidian Vault 读写操作

根据 LLM 回答判断是否需要写入 Vault。
短笔记直接写入，重要内容走审批流程。
"""

import logging
import re

from schemas.state import AgentState
from tools.obsidian import obsidian_tool
from config.policy_loader import get_policy

logger = logging.getLogger(__name__)

# Vault 写入路径模板
_VAULT_BASE = "03_Investment/Companies"


async def knowledge(state: AgentState) -> dict:
    """知识管理节点

    检查回答中是否包含写入 Vault 的意图，
    如果包含则自动写入 Obsidian Vault。

    策略:
      - 短内容 (< approval_threshold) → 直接写入
      - 长内容 (>= approval_threshold) → 创建审批请求
    """
    answer = state.get("answer", "")
    question = state.get("question", "")
    metadata = state.get("metadata", {})

    # 检查是否有写入意图（关键词匹配）
    write_keywords = ["写入", "记录", "保存", "笔记", "vault", "obsidian", "归档"]
    should_write = any(kw in question.lower() for kw in write_keywords)

    if not should_write or not answer:
        return {"metadata": {**metadata, "vault_written": False}}

    # 从问题中提取公司名/代码作为文件名
    symbol = metadata.get("symbol", "")
    company = _extract_company(question)
    filename = f"{symbol}_{company}" if symbol and company else (symbol or company or "research_note")

    vault_path = f"{_VAULT_BASE}/{filename}/Research.md"
    note_content = f"\n\n## {question}\n\n{answer}\n\n---\n"

    # 判断是否需要审批
    approval_threshold = get_policy("approval.content_threshold", 2000)

    if len(answer) >= approval_threshold:
        # 长内容 → 创建审批请求
        try:
            from services.approval import create_approval
            approval_id = await create_approval(
                title=f"Vault 写入: {filename}",
                action_type="vault_write",
                params={"filepath": vault_path, "content": note_content},
                content_preview=answer[:500],
                created_by="kb_agent",
            )
            logger.info("Knowledge: approval created | %s | %s", approval_id[:8], vault_path)
            return {"metadata": {
                **metadata,
                "vault_written": False,
                "approval_id": approval_id,
                "approval_pending": True,
            }}
        except Exception as e:
            logger.warning("Knowledge: approval creation failed (%s)", e)

    # 短内容 → 直接写入
    try:
        await obsidian_tool.append_to_note(vault_path, note_content)
        logger.info("Knowledge: written to Vault at %s", vault_path)
        return {"metadata": {**metadata, "vault_written": True, "vault_path": vault_path}}
    except Exception as e:
        logger.warning("Knowledge: Vault write failed (%s), skipping", e)
        return {"metadata": {**metadata, "vault_written": False, "vault_error": str(e)}}


def _extract_company(question: str) -> str:
    """从问题中提取公司名"""
    # 简单匹配：去除常见动词和助词
    patterns = [
        r"关于(.+?)的",
        r"(.+?)的(?:分析|研究|报告|笔记)",
        r"将(.+?)写入",
        r"把(.+?)保存",
    ]
    for p in patterns:
        m = re.search(p, question)
        if m:
            return m.group(1).strip()[:20]
    return ""
